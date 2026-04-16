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
    """One candidate document as returned by the retriever (plain-dict shape)."""
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


class StaleDocument(BaseModel):
    """A superseded document included with a freshness penalty."""
    model_config = _strict()

    doc_id: str
    superseded_by: str
    freshness_score: float
    penalty_applied: float = 0.5


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


class DroppedByBudget(BaseModel):
    """A document that scored high enough but was cut by the token budget."""
    model_config = _strict()

    doc_id: str
    token_count: int
    score: float
    freshness_score: float


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

class TraceMetrics(BaseModel):
    """Aggregate statistics for one pipeline run."""
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


class DecisionTrace(BaseModel):
    """Full audit trail: every decision made during the pipeline run."""
    model_config = _strict()

    user_context: UserContext
    policy_config: PolicyConfig
    included: List[IncludedDocument] = Field(default_factory=list)
    blocked_by_permission: List[BlockedDocument] = Field(default_factory=list)
    demoted_as_stale: List[StaleDocument] = Field(default_factory=list)
    dropped_by_budget: List[DroppedByBudget] = Field(default_factory=list)
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
    policy_name added with a safe default.
    """
    model_config = ConfigDict(extra="forbid")

    query: str
    role: str = "analyst"
    top_k: int = 5
    policy_name: str = "default"


class DocumentChunk(BaseModel):
    """One document in the query response.  Preserved for frontend compatibility."""

    doc_id: str
    content: str
    score: float
    freshness_score: Optional[float] = None
    tags: List[str] = Field(default_factory=list)
    title: Optional[str] = None
    doc_type: Optional[str] = None
    date: Optional[str] = None
    superseded_by: Optional[str] = None


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

    query: str
    role: str = "analyst"
    top_k: int = 5
    policies: List[str] = Field(
        default_factory=lambda: ["naive_top_k", "permission_aware", "full_policy"]
    )


class CompareResponse(BaseModel):
    """POST /compare response — one QueryResponse per requested policy."""
    model_config = ConfigDict(extra="forbid")

    query: str
    role: str
    results: Dict[str, QueryResponse]
