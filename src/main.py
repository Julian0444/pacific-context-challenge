"""
main.py — FastAPI application entry point for QueryTrace.

Minimal HTTP boundary: validates the request, resolves dependencies,
delegates to the pipeline, and maps the result to the API response.
No pipeline business logic lives here.
"""

import json
import os
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.models import (
    QueryRequest,
    QueryResponse,
    DocumentChunk,
    CompareRequest,
    CompareResponse,
    IngestResponse,
)
from src.pipeline import run_pipeline, PipelineError
from src.policies import load_roles
from src.retriever import retrieve, invalidate_caches
from src.evaluator import load_test_queries, run_evals
from src.ingest import ingest_document, IngestError

app = FastAPI(title="QueryTrace", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load roles and metadata once at startup
_ROLES_PATH = os.path.join(os.path.dirname(__file__), "..", "corpus", "roles.json")
_METADATA_PATH = os.path.join(os.path.dirname(__file__), "..", "corpus", "metadata.json")

_roles = load_roles(_ROLES_PATH)

with open(_METADATA_PATH, "r") as _f:
    _metadata = json.load(_f)

_EVALS_PATH = os.path.join(os.path.dirname(__file__), "..", "evals", "test_queries.json")
_evals_cache: Optional[dict] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    # Input validation — reject unknown roles before entering the pipeline
    if request.role not in _roles:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role: {request.role!r}. Valid roles: {list(_roles.keys())}",
        )

    # Delegate to the pipeline
    try:
        result = run_pipeline(request, retrieve, _roles, _metadata)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PipelineError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed at '{e.stage}': {e.error}",
        )

    # Map PipelineResult → QueryResponse (API boundary)
    context = [
        DocumentChunk(
            doc_id=inc.doc_id,
            content=inc.content,
            score=inc.score,
            freshness_score=inc.freshness_score,
            tags=inc.tags,
            title=inc.title,
            doc_type=inc.doc_type,
            date=inc.date,
            superseded_by=inc.superseded_by,
        )
        for inc in result.context
    ]

    return QueryResponse(
        query=request.query,
        context=context,
        total_tokens=result.total_tokens,
        decision_trace=result.trace,
    )


@app.post("/compare", response_model=CompareResponse)
def compare(request: CompareRequest):
    """Run the same query through multiple policy presets side-by-side.

    Returns one QueryResponse per requested policy, keyed by policy name.
    Orchestrates existing run_pipeline() — no business logic duplication.
    """
    if request.role not in _roles:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role: {request.role!r}. Valid roles: {list(_roles.keys())}",
        )

    if not request.policies:
        raise HTTPException(status_code=400, detail="policies list must not be empty")

    results: dict = {}
    for policy_name in request.policies:
        query_req = QueryRequest(
            query=request.query,
            role=request.role,
            top_k=request.top_k,
            policy_name=policy_name,
        )
        try:
            result = run_pipeline(query_req, retrieve, _roles, _metadata)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except PipelineError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Pipeline failed for policy '{policy_name}' at '{e.stage}': {e.error}",
            )

        context = [
            DocumentChunk(
                doc_id=inc.doc_id,
                content=inc.content,
                score=inc.score,
                freshness_score=inc.freshness_score,
                tags=inc.tags,
                title=inc.title,
                doc_type=inc.doc_type,
                date=inc.date,
                superseded_by=inc.superseded_by,
            )
            for inc in result.context
        ]

        results[policy_name] = QueryResponse(
            query=request.query,
            context=context,
            total_tokens=result.total_tokens,
            decision_trace=result.trace,
        )

    return CompareResponse(query=request.query, role=request.role, results=results)


@app.get("/evals")
def evals():
    """Return cached evaluator results (runs on first call, cached thereafter)."""
    global _evals_cache
    if _evals_cache is None:
        queries = load_test_queries(_EVALS_PATH)
        _evals_cache = run_evals(queries, k=5, top_k=8)
    return _evals_cache


@app.post("/ingest", response_model=IngestResponse)
async def ingest(
    file: UploadFile = File(...),
    title: str = Form(...),
    date: str = Form(...),
    min_role: str = Form(...),
    doc_type: str = Form(...),
    sensitivity: str = Form(...),
    tags: str = Form(""),
):
    """Ingest a PDF into the corpus and rebuild the index.

    Accepts multipart/form-data. Writes extracted text as a .txt file under
    corpus/documents/, appends to corpus/metadata.json, and rebuilds the
    FAISS + BM25 artifacts. Returns the new doc_id and metadata echo.

    Side effects (in order, under a lock in src.ingest):
      1. Write <sanitized_title>.txt to corpus/documents/
      2. Append entry to corpus/metadata.json
      3. Rebuild FAISS + BM25 on disk
      4. Invalidate retriever._bm25 (FAISS is re-read per request)
      5. Reload _metadata in this process
      6. Clear _evals_cache so /evals recomputes against the new corpus
    """
    global _metadata, _evals_cache

    if (file.content_type or "").lower() not in ("application/pdf", "application/octet-stream"):
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(
                status_code=415,
                detail=f"Expected a PDF upload; got content-type {file.content_type!r}.",
            )

    pdf_bytes = await file.read()
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

    try:
        entry = ingest_document(
            pdf_bytes=pdf_bytes,
            title=title,
            date=date,
            min_role=min_role,
            doc_type=doc_type,
            sensitivity=sensitivity,
            tags=tag_list,
        )
    except IngestError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Corpus layout error: {e}")

    invalidate_caches()

    with open(_METADATA_PATH, "r") as _f:
        fresh = json.load(_f)
    _metadata["documents"] = fresh["documents"]

    _evals_cache = None

    return IngestResponse(
        status="ok",
        doc_id=entry["id"],
        title=entry["title"],
        file_name=entry["file_name"],
        type=entry["type"],
        date=entry["date"],
        min_role=entry["min_role"],
        sensitivity=entry["sensitivity"],
        tags=entry["tags"],
        total_documents=len(_metadata["documents"]),
    )
