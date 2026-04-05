"""
main.py — FastAPI application entry point for QueryTrace.

Defines API routes:
  POST /query  — accepts a natural language query and returns assembled context
  GET  /health — liveness check
"""

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.models import QueryRequest, QueryResponse, DocumentChunk
from src.retriever import retrieve
from src.policies import load_roles, filter_by_role
from src.freshness import apply_freshness
from src.context_assembler import assemble

app = FastAPI(title="QueryTrace", version="0.1.0")

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
    # Validate role
    if request.role not in _roles:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role: {request.role!r}. Valid roles: {list(_roles.keys())}",
        )

    # 1. Retrieve top-k candidates via semantic search
    results = retrieve(request.query, top_k=request.top_k)

    # 2. Filter by role-based access control
    filtered = filter_by_role(results, request.role, _roles)

    # 3. Attach freshness scores (and demote stale docs)
    scored = apply_freshness(filtered, _metadata)

    # 4. Assemble within token budget
    context_list, total_tokens = assemble(scored)

    # Convert to response model
    context = [
        DocumentChunk(
            doc_id=c["doc_id"],
            content=c["content"],
            score=c["score"],
            freshness_score=c.get("freshness_score"),
            tags=c.get("tags", []),
        )
        for c in context_list
    ]

    return QueryResponse(
        query=request.query,
        context=context,
        total_tokens=total_tokens,
    )
