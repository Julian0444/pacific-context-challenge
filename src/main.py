"""
main.py — FastAPI application entry point for QueryTrace.

Minimal HTTP boundary: validates the request, resolves dependencies,
delegates to the pipeline, and maps the result to the API response.
No pipeline business logic lives here.
"""

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.models import QueryRequest, QueryResponse, DocumentChunk, CompareRequest, CompareResponse
from src.pipeline import run_pipeline, PipelineError
from src.policies import load_roles
from src.retriever import retrieve

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
