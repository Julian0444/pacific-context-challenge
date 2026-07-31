"""
models.py — Pydantic contract models for the QueryTrace pipeline.

Organised from upstream to downstream in the pipeline:
  UserContext → PolicyConfig
  → ScoredDocument (retriever output)
  → FreshnessScoredDocument (after freshness scoring)
  → BlockedDocument / StaleDocument / IncludedDocument (decision outcomes)
  → TraceMetrics / DecisionTrace (observability)
  → PipelineResult (internal)
  → QueryRequest / QueryResponse (API boundary)

All domain models are frozen + extra="forbid" to act as value objects.
QueryRequest/QueryResponse omit frozen so FastAPI can do its thing.
DocumentChunk is preserved unchanged for frontend compatibility.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared config helper
# ---------------------------------------------------------------------------

def _strict() -> ConfigDict:
    """Frozen, no-extra config for internal value-object models."""
    return ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------------------
# Context & Policy
# ---------------------------------------------------------------------------

class UserContext(BaseModel):
    """Who is making the request and what rank do they hold."""
    model_config = _strict()

    role: str
    access_rank: int


class PolicyConfig(BaseModel):
    """Tunable knobs for a single pipeline run."""
    model_config = _strict()

    name: str = "default"
    token_budget: int = 2048
    top_k: int = 5
    half_life_days: int = 365
    skip_permission_filter: bool = False
    skip_freshness: bool = False
    skip_budget: bool = False


# ---------------------------------------------------------------------------
# Retriever output
# ---------------------------------------------------------------------------

class ScoredDocument(BaseModel):
    """One candidate CHUNK as returned by the retriever (plain-dict shape).

    Since Fase 5 Etapa B the retrieval unit is the chunk: `doc_id` is the
    parent document id (permissions, freshness, evals and citations all key
    on it) and `chunk_id`/`chunk_index` identify the specific chunk. The
    chunk fields default to None so pre-chunking payloads stay valid.
    """
    model_config = ConfigDict(frozen=True, extra="ignore")  # ignore unknown keys from retriever

    doc_id: str
    score: float
    excerpt: str
    min_role: str
    tags: List[str] = Field(default_factory=list)
    date: Optional[str] = None
    superseded_by: Optional[str] = None
    # Extra retriever fields kept for completeness
    title: Optional[str] = None
    short_summary: Optional[str] = None
    sensitivity: Optional[str] = None
    doc_type: Optional[str] = None
    # Chunk identity (Fase 5 Etapa B)
    chunk_id: Optional[str] = None
    chunk_index: Optional[int] = None
    chunk_count: Optional[int] = None


# ---------------------------------------------------------------------------
# Freshness stage output
# ---------------------------------------------------------------------------

class FreshnessScoredDocument(BaseModel):
    """ScoredDocument after freshness scoring has been applied."""
    model_config = _strict()

    doc_id: str
    score: float
    excerpt: str
    min_role: str
    tags: List[str] = Field(default_factory=list)
    date: Optional[str] = None
    superseded_by: Optional[str] = None
    title: Optional[str] = None
    short_summary: Optional[str] = None
    sensitivity: Optional[str] = None
    doc_type: Optional[str] = None
    chunk_id: Optional[str] = None
    chunk_index: Optional[int] = None
    chunk_count: Optional[int] = None
    freshness_score: float
    is_stale: bool = False


# ---------------------------------------------------------------------------
# Decision outcomes
# ---------------------------------------------------------------------------

class BlockedDocument(BaseModel):
    """A document excluded by role-based access control."""
    model_config = _strict()

    doc_id: str
    reason: str = "insufficient_role"
    required_role: str
    user_role: str
    title: Optional[str] = None
    doc_type: Optional[str] = None
    chunk_id: Optional[str] = None


class StaleDocument(BaseModel):
    """A superseded document included with a freshness penalty."""
    model_config = _strict()

    doc_id: str
    superseded_by: str
    freshness_score: float
    penalty_applied: float = 0.5
    title: Optional[str] = None
    chunk_id: Optional[str] = None


class IncludedDocument(BaseModel):
    """A document that made it into the final assembled context."""
    model_config = _strict()

    doc_id: str
    content: str
    score: float
    freshness_score: float
    tags: List[str] = Field(default_factory=list)
    token_count: int
    title: Optional[str] = None
    doc_type: Optional[str] = None
    date: Optional[str] = None
    superseded_by: Optional[str] = None
    chunk_id: Optional[str] = None
    chunk_index: Optional[int] = None
    chunk_count: Optional[int] = None


class DroppedByBudget(BaseModel):
    """A document that scored high enough but was cut by the token budget."""
    model_config = _strict()

    doc_id: str
    token_count: int
    score: float
    freshness_score: float
    title: Optional[str] = None
    chunk_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

class TraceMetrics(BaseModel):
    """Aggregate statistics for one pipeline run.

    All *_count fields count CHUNKS (the retrieval unit since Fase 5 Etapa B)
    — the trace accounting invariant (blocked + included + dropped ==
    retrieved) is chunk-level. The *_doc_count fields count unique parent
    documents, which is what users reason about in the UI.
    """
    model_config = _strict()

    retrieved_count: int
    blocked_count: int
    stale_count: int
    dropped_count: int
    included_count: int
    total_tokens: int
    budget_utilization: float
    avg_score: float
    avg_freshness_score: float
    included_doc_count: Optional[int] = None
    blocked_doc_count: Optional[int] = None
    stale_doc_count: Optional[int] = None
    dropped_doc_count: Optional[int] = None


class BlockedSummary(BaseModel):
    """Redacted view of blocked documents for non-admin product sessions.

    Replaces the full blocked_by_permission list at the API boundary when
    BLOCKED_DISCLOSURE=count (default): the viewer learns how many documents
    were withheld and which role would unlock them — never which documents.
    """
    model_config = _strict()

    count: int
    required_roles: List[str] = Field(default_factory=list)


class DecisionTrace(BaseModel):
    """Full audit trail: every decision made during the pipeline run."""
    model_config = _strict()

    user_context: UserContext
    policy_config: PolicyConfig
    included: List[IncludedDocument] = Field(default_factory=list)
    blocked_by_permission: List[BlockedDocument] = Field(default_factory=list)
    demoted_as_stale: List[StaleDocument] = Field(default_factory=list)
    dropped_by_budget: List[DroppedByBudget] = Field(default_factory=list)
    # Populated only on redacted responses (non-admin sessions, disclosure=count);
    # None on lab/admin responses where blocked_by_permission is fully visible.
    blocked_summary: Optional[BlockedSummary] = None
    total_tokens: int
    ttft_proxy_ms: float = 0.0
    metrics: TraceMetrics


# ---------------------------------------------------------------------------
# Internal pipeline result
# ---------------------------------------------------------------------------

class PipelineResult(BaseModel):
    """What the pipeline hands back before serialisation to the API response."""
    model_config = _strict()

    context: List[IncludedDocument]
    total_tokens: int
    trace: Optional[DecisionTrace] = None


# ---------------------------------------------------------------------------
# API boundary — backward-compatible with existing frontend
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    """POST /query request body.

    Backward-compatible: query, role, top_k are unchanged.
    policy_name added with a safe default. workspace (Fase 2) is optional —
    None resolves to the server's default workspace.
    """
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    role: str = "analyst"
    top_k: int = Field(default=5, ge=1, le=50)
    policy_name: str = "default"
    workspace: Optional[str] = Field(default=None, max_length=40)


class DocumentChunk(BaseModel):
    """One context item in the query response — one CHUNK since Fase 5 Etapa B.

    `doc_id` is the parent document; `chunk_id`/`chunk_index`/`chunk_count`
    let the frontend group sibling chunks into a single document card.
    """

    doc_id: str
    content: str
    score: float
    freshness_score: Optional[float] = None
    tags: List[str] = Field(default_factory=list)
    title: Optional[str] = None
    doc_type: Optional[str] = None
    date: Optional[str] = None
    superseded_by: Optional[str] = None
    chunk_id: Optional[str] = None
    chunk_index: Optional[int] = None
    chunk_count: Optional[int] = None


class QueryResponse(BaseModel):
    """POST /query response.

    Backward-compatible: context and total_tokens are unchanged.
    decision_trace is optional so existing clients ignore it.
    """
    model_config = ConfigDict(extra="forbid")

    query: str
    context: List[DocumentChunk]
    total_tokens: int
    decision_trace: Optional[DecisionTrace] = None


class CompareRequest(BaseModel):
    """POST /compare request body.

    Runs the same query/role through multiple named policy presets
    and returns one QueryResponse per policy.
    """
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    role: str = "analyst"
    top_k: int = Field(default=5, ge=1, le=50)
    policies: List[str] = Field(
        default_factory=lambda: ["naive_top_k", "permission_aware", "full_policy"]
    )
    workspace: Optional[str] = Field(default=None, max_length=40)


class CompareResponse(BaseModel):
    """POST /compare response — one QueryResponse per requested policy."""
    model_config = ConfigDict(extra="forbid")

    query: str
    role: str
    results: Dict[str, QueryResponse]


class LoginRequest(BaseModel):
    """POST /login request body.

    workspace selects which workspace's personas to authenticate against;
    the resulting session is bound to that workspace (Fase 2).
    """
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    workspace: Optional[str] = Field(default=None, max_length=40)


class IngestResponse(BaseModel):
    """POST /ingest response — confirms the new corpus entry."""
    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    doc_id: str
    title: str
    file_name: str
    type: str
    date: str
    min_role: str
    sensitivity: str
    tags: List[str]
    total_documents: int


class IngestAccepted(BaseModel):
    """POST /ingest 202 response — the upload was validated and queued (Fase 3)."""
    model_config = ConfigDict(extra="forbid")

    job_id: str
    state: str
    workspace: str


class IngestJobError(BaseModel):
    """Typed failure carried by a failed ingest job."""
    model_config = ConfigDict(extra="forbid")

    status_code: int
    detail: str


class IngestJobStatus(BaseModel):
    """GET /ingest/jobs/{job_id} response — job progress + terminal payload."""
    model_config = ConfigDict(extra="forbid")

    id: str
    workspace: str
    state: str
    created_at: str
    updated_at: str
    error: Optional[IngestJobError] = None
    result: Optional[IngestResponse] = None


class Citation(BaseModel):
    """One [doc_id] citation extracted from an Ask answer (Fase 4).

    valid=True iff the cited id was in the context the model actually saw —
    a mechanical check against the packed documents, no LLM judge.
    """
    model_config = _strict()

    doc_id: str
    valid: bool


class AskUsage(BaseModel):
    """Token usage of one Ask model call — cost transparency in the UI."""
    model_config = _strict()

    input_tokens: int
    output_tokens: int


class AskResponse(BaseModel):
    """POST /ask response (Fase 4).

    Same request body as /query. The decision trace travels with every
    answer: what the model saw (context/included) and what it never saw
    (blocked_by_permission) are part of the response contract.
    """
    model_config = ConfigDict(extra="forbid")

    query: str
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    grounded_doc_count: int = 0
    model: str
    usage: AskUsage
    cached: bool = False
    context: List[DocumentChunk] = Field(default_factory=list)
    total_tokens: int = 0
    decision_trace: Optional[DecisionTrace] = None
