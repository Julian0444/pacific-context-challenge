"""
pipeline.py — Explicit orchestrator for the QueryTrace retrieval pipeline.

Flow:
  retrieve → permission_filter → freshness_scorer → budget_packer → trace_builder

Each stage returns a typed result.  The pipeline wraps each call in
StageOk / StageErr and aborts on first failure via PipelineError.
No I/O is performed here — all external dependencies are injected
via Protocol.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, List, Union

from src.models import (
    FreshnessScoredDocument,
    PipelineResult,
    QueryRequest,
    ScoredDocument,
    UserContext,
)
from src.policies import resolve_policy
from src.protocols import MetadataStoreProtocol, RetrieverProtocol, RoleStoreProtocol
from src.stages import filter_permissions, score_freshness, pack_budget, build_trace


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
# Stage wrappers (thin error boundaries around typed stages)
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


def _permission_stage(docs, user_ctx, roles, policy) -> StageResult:
    if policy.skip_permission_filter:
        from src.stages.permission_filter import PermissionResult
        return StageOk(PermissionResult(permitted=docs, blocked=[]))
    try:
        return StageOk(filter_permissions(docs, user_ctx, roles))
    except Exception as e:
        return StageErr(stage="permission_filter", error=str(e))


def _freshness_stage(docs, metadata, policy) -> StageResult:
    if policy.skip_freshness:
        scored = [
            FreshnessScoredDocument(
                **doc.model_dump(), freshness_score=0.0, is_stale=False,
            )
            for doc in docs
        ]
        from src.stages.freshness_scorer import FreshnessResult
        return StageOk(FreshnessResult(scored=scored, stale=[]))
    try:
        return StageOk(score_freshness(docs, metadata, policy.half_life_days))
    except Exception as e:
        return StageErr(stage="freshness", error=str(e))


def _budget_stage(docs, policy) -> StageResult:
    try:
        return StageOk(pack_budget(
            docs,
            token_budget=policy.token_budget,
            enforce_budget=not policy.skip_budget,
        ))
    except Exception as e:
        return StageErr(stage="budget_packer", error=str(e))


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

    Sequence: retrieve → permission_filter → freshness → budget_packer → trace.
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
    t0 = time.monotonic()

    # Resolve policy preset and build user context
    policy = resolve_policy(request.policy_name, request.top_k)
    user_rank = roles[request.role]["access_rank"]
    user_ctx = UserContext(role=request.role, access_rank=user_rank)

    # Stage 1 — Retrieve
    # Over-retrieve by 3× to compensate for downstream permission attrition.
    # For a 12-doc corpus with analyst access (5 of 12 visible), top_k=8
    # leaves only 2-3 candidates after filtering.  The budget packer still
    # enforces the token budget regardless of how many candidates enter.
    retrieve_k = policy.top_k * 3
    candidates: List[ScoredDocument] = _unwrap(
        _retrieve_stage(request.query, retrieve_k, retriever)
    )

    # Stage 2 — Permission filter
    perm_result = _unwrap(_permission_stage(candidates, user_ctx, roles, policy))

    # Stage 3 — Freshness scorer
    fresh_result = _unwrap(_freshness_stage(perm_result.permitted, metadata, policy))

    # Stage 4 — Budget packer
    budget_result = _unwrap(_budget_stage(fresh_result.scored, policy))

    ttft_proxy_ms = (time.monotonic() - t0) * 1000.0

    # Stage 5 — Trace builder
    trace = build_trace(
        user_ctx=user_ctx,
        policy=policy,
        retrieved_count=len(candidates),
        included=budget_result.packed,
        blocked=perm_result.blocked,
        stale=fresh_result.stale,
        dropped=budget_result.over_budget,
        total_tokens=budget_result.total_tokens,
        budget_utilization=budget_result.budget_utilization,
        ttft_proxy_ms=ttft_proxy_ms,
    )

    return PipelineResult(
        context=budget_result.packed,
        total_tokens=budget_result.total_tokens,
        trace=trace,
    )
