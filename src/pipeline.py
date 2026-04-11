"""
pipeline.py — Explicit orchestrator for the QueryTrace retrieval pipeline.

Flow:
  retrieve → permission_filter → freshness_scorer → budget_packer → trace_builder

Each stage returns a StageResult (StageOk | StageErr).  The pipeline
inspects the result after each stage and aborts on the first failure via
PipelineError.  No I/O is performed here — all external dependencies are
injected via Protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Union

from src.models import (
    BlockedDocument,
    DecisionTrace,
    FreshnessScoredDocument,
    IncludedDocument,
    PipelineResult,
    PolicyConfig,
    QueryRequest,
    ScoredDocument,
    StaleDocument,
    TraceMetrics,
    UserContext,
)
from src.policies import resolve_policy
from src.protocols import MetadataStoreProtocol, RetrieverProtocol, RoleStoreProtocol

# Existing stage functions — wrapped, not rewritten
from src.freshness import apply_freshness
from src.context_assembler import assemble, _count_tokens


# ---------------------------------------------------------------------------
# Stage result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StageOk:
    """A stage completed successfully."""
    value: Any


@dataclass(frozen=True)
class StageErr:
    """A stage failed."""
    stage: str
    error: str


StageResult = Union[StageOk, StageErr]


class PipelineError(Exception):
    """Raised when a pipeline stage fails.  Caught by the HTTP boundary."""

    def __init__(self, stage: str, error: str):
        self.stage = stage
        self.error = error
        super().__init__(f"Pipeline failed at '{stage}': {error}")


def _unwrap(result: StageResult) -> Any:
    """Extract value from StageOk, or raise PipelineError from StageErr."""
    if isinstance(result, StageErr):
        raise PipelineError(result.stage, result.error)
    return result.value


# ---------------------------------------------------------------------------
# Stage 1: Retrieve
# ---------------------------------------------------------------------------

def _retrieve_stage(
    query: str,
    top_k: int,
    retriever: RetrieverProtocol,
) -> StageResult:
    """Call the retriever and validate each result into ScoredDocument."""
    try:
        raw_dicts = retriever(query, top_k)
        docs = [ScoredDocument.model_validate(d) for d in raw_dicts]
        return StageOk(docs)
    except Exception as e:
        return StageErr(stage="retrieve", error=str(e))


# ---------------------------------------------------------------------------
# Stage 2: Permission filter
# ---------------------------------------------------------------------------

def _permission_stage(
    docs: List[ScoredDocument],
    user_ctx: UserContext,
    roles: RoleStoreProtocol,
    policy: PolicyConfig,
) -> StageResult:
    """Drop documents the user's role cannot access.  Returns (permitted, blocked)."""
    if policy.skip_permission_filter:
        return StageOk((docs, []))

    try:
        user_rank = user_ctx.access_rank
        permitted: List[ScoredDocument] = []
        blocked: List[BlockedDocument] = []

        for doc in docs:
            doc_role_meta = roles.get(doc.min_role) if hasattr(roles, "get") else roles[doc.min_role]
            doc_rank = doc_role_meta["access_rank"] if doc_role_meta else float("inf")

            if doc_rank <= user_rank:
                permitted.append(doc)
            else:
                blocked.append(
                    BlockedDocument(
                        doc_id=doc.doc_id,
                        required_role=doc.min_role,
                        user_role=user_ctx.role,
                    )
                )

        return StageOk((permitted, blocked))
    except Exception as e:
        return StageErr(stage="permission_filter", error=str(e))


# ---------------------------------------------------------------------------
# Stage 3: Freshness scorer
# ---------------------------------------------------------------------------

def _freshness_stage(
    docs: List[ScoredDocument],
    metadata: MetadataStoreProtocol,
    policy: PolicyConfig,
) -> StageResult:
    """Score documents by recency.  Returns (scored_docs, stale_entries)."""
    if policy.skip_freshness:
        scored = [
            FreshnessScoredDocument(
                **doc.model_dump(), freshness_score=0.0, is_stale=False,
            )
            for doc in docs
        ]
        return StageOk((scored, []))

    try:
        # Convert to dicts for the existing apply_freshness wrapper
        raw_dicts = [doc.model_dump() for doc in docs]
        scored_dicts = apply_freshness(raw_dicts, metadata, policy.half_life_days)

        scored: List[FreshnessScoredDocument] = []
        stale: List[StaleDocument] = []

        for d in scored_dicts:
            is_stale = bool(d.get("superseded_by"))
            fd = FreshnessScoredDocument(
                doc_id=d["doc_id"],
                score=d["score"],
                excerpt=d["excerpt"],
                min_role=d["min_role"],
                tags=d.get("tags", []),
                date=d.get("date"),
                superseded_by=d.get("superseded_by"),
                title=d.get("title"),
                short_summary=d.get("short_summary"),
                sensitivity=d.get("sensitivity"),
                freshness_score=d["freshness_score"],
                is_stale=is_stale,
            )
            scored.append(fd)

            if is_stale and d.get("superseded_by"):
                stale.append(
                    StaleDocument(
                        doc_id=d["doc_id"],
                        superseded_by=d["superseded_by"],
                        freshness_score=d["freshness_score"],
                    )
                )

        return StageOk((scored, stale))
    except Exception as e:
        return StageErr(stage="freshness", error=str(e))


# ---------------------------------------------------------------------------
# Stage 4: Budget packer
# ---------------------------------------------------------------------------

def _assemble_stage(
    docs: List[FreshnessScoredDocument],
    policy: PolicyConfig,
) -> StageResult:
    """Rank by combined score and greedily pack within token budget.

    When policy.skip_budget is True, all docs pass through with no budget cap.
    Returns (included_docs, total_tokens).
    """
    if policy.skip_budget:
        # Dangerous baseline: include everything, no budget enforcement
        try:
            total_tokens = 0
            included: List[IncludedDocument] = []
            for doc in docs:
                text = doc.excerpt
                tk = _count_tokens(text)
                total_tokens += tk
                included.append(
                    IncludedDocument(
                        doc_id=doc.doc_id,
                        content=text,
                        score=doc.score,
                        freshness_score=doc.freshness_score,
                        tags=doc.tags,
                        token_count=tk,
                    )
                )
            return StageOk((included, total_tokens))
        except Exception as e:
            return StageErr(stage="assemble", error=str(e))

    try:
        raw_dicts = [doc.model_dump() for doc in docs]
        context_list, total_tokens = assemble(raw_dicts, policy.token_budget)

        included = [
            IncludedDocument(
                doc_id=c["doc_id"],
                content=c["content"],
                score=c["score"],
                freshness_score=c.get("freshness_score", 0.0),
                tags=c.get("tags", []),
                token_count=c["token_count"],
            )
            for c in context_list
        ]
        return StageOk((included, total_tokens))
    except Exception as e:
        return StageErr(stage="assemble", error=str(e))


# ---------------------------------------------------------------------------
# Stage 5: Trace builder
# ---------------------------------------------------------------------------

def _build_trace(
    user_ctx: UserContext,
    policy: PolicyConfig,
    retrieved_count: int,
    blocked: List[BlockedDocument],
    stale: List[StaleDocument],
    included: List[IncludedDocument],
    total_tokens: int,
) -> DecisionTrace:
    """Assemble the full audit trace from all stage outputs."""
    avg_score = (
        sum(d.score for d in included) / len(included) if included else 0.0
    )
    avg_freshness = (
        sum(d.freshness_score for d in included) / len(included) if included else 0.0
    )

    metrics = TraceMetrics(
        retrieved_count=retrieved_count,
        blocked_count=len(blocked),
        stale_count=len(stale),
        included_count=len(included),
        total_tokens=total_tokens,
        avg_score=round(avg_score, 6),
        avg_freshness_score=round(avg_freshness, 6),
    )

    return DecisionTrace(
        user_context=user_ctx,
        policy_config=policy,
        blocked=blocked,
        stale=stale,
        included=included,
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_pipeline(
    request: QueryRequest,
    retriever: RetrieverProtocol,
    roles: RoleStoreProtocol,
    metadata: MetadataStoreProtocol,
) -> PipelineResult:
    """Execute the full retrieval pipeline.

    Sequence: retrieve → permission_filter → freshness → assemble → trace.
    Aborts on first stage failure with PipelineError.

    Args:
        request:   Validated query request (query, role, top_k, policy_name).
        retriever: Callable satisfying RetrieverProtocol.
        roles:     Role definitions (role_name → dict with access_rank).
        metadata:  Raw corpus metadata (dict with "documents" key).

    Returns:
        PipelineResult with context, total_tokens, and decision trace.

    Raises:
        PipelineError: if any stage fails.
    """
    # Resolve policy preset and build user context
    policy = resolve_policy(request.policy_name, request.top_k)
    user_rank = roles[request.role]["access_rank"]
    user_ctx = UserContext(role=request.role, access_rank=user_rank)

    # Stage 1 — Retrieve
    candidates: List[ScoredDocument] = _unwrap(
        _retrieve_stage(request.query, policy.top_k, retriever)
    )

    # Stage 2 — Permission filter
    permitted, blocked = _unwrap(
        _permission_stage(candidates, user_ctx, roles, policy)
    )

    # Stage 3 — Freshness scorer
    scored, stale = _unwrap(
        _freshness_stage(permitted, metadata, policy)
    )

    # Stage 4 — Budget packer
    included, total_tokens = _unwrap(
        _assemble_stage(scored, policy)
    )

    # Stage 5 — Trace builder
    trace = _build_trace(
        user_ctx, policy, len(candidates), blocked, stale, included, total_tokens,
    )

    return PipelineResult(context=included, total_tokens=total_tokens, trace=trace)
