"""
models.py — Pydantic request and response schemas for the QueryTrace API.
"""

from pydantic import BaseModel
from typing import List, Optional


class QueryRequest(BaseModel):
    query: str
    role: str = "analyst"
    top_k: int = 5


class DocumentChunk(BaseModel):
    doc_id: str
    content: str
    score: float
    freshness_score: Optional[float] = None
    tags: List[str] = []


class QueryResponse(BaseModel):
    query: str
    context: List[DocumentChunk]
    total_tokens: int
