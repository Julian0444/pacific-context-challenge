"""
trace_builder.py — Reducer/aggregator: assembles DecisionTrace from stage outputs.

Takes the outputs of all upstream stages and produces a first-class
DecisionTrace with structured decision outcomes and aggregate metrics.
"""

from __future__ import annotations

from typing import List

from src.models import (
    BlockedDocument,
    DecisionTrace,
    DroppedByBudget,
    IncludedDocument,
    PolicyConfig,
    StaleDocument,
    TraceMetrics,
    UserContext,
)


class TraceAccountingError(RuntimeError):
    """Internal accounting invariant violated (blocked + included + dropped
    != retrieved). Deliberately NOT a ValueError: the HTTP boundary maps
    ValueError to 400 (bad request), but this is a server-side bug and must
    surface as 500."""


def build_trace(
    user_ctx: UserContext,
    policy: PolicyConfig,
    retrieved_count: int,
    included: List[IncludedDocument],
    blocked: List[BlockedDocument],
    stale: List[StaleDocument],
    dropped: List[DroppedByBudget],
    total_tokens: int,
    budget_utilization: float,
    ttft_proxy_ms: float,
) -> DecisionTrace:
    """Assemble the full audit trace from all stage outputs.

    Args:
        user_ctx:           Who made the request.
        policy:             Policy config used for this run.
        retrieved_count:    Number of raw candidates from the retriever.
        included:           Documents that made it into final context.
        blocked:            Documents blocked by permission filter.
        stale:              Superseded documents (demoted, not removed).
        dropped:            Documents cut by the token budget.
        total_tokens:       Total tokens in the assembled context.
        budget_utilization: Fraction of token budget used (0.0–1.0).
        ttft_proxy_ms:      Pipeline execution time in milliseconds.

    Returns:
        A fully populated DecisionTrace.
    """
    # Invariant: every retrieved CHUNK must end up in exactly one bucket.
    # Counts are chunk-level since Fase 5 Etapa B (the retrieval unit is the
    # chunk); doc-level views are derived below for the UI.
    accounted = len(blocked) + len(included) + len(dropped)
    if accounted != retrieved_count:
        raise TraceAccountingError(
            f"Chunk accounting mismatch: "
            f"blocked({len(blocked)}) + included({len(included)}) + "
            f"dropped({len(dropped)}) = {accounted}, expected {retrieved_count}"
        )

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
        dropped_count=len(dropped),
        included_count=len(included),
        total_tokens=total_tokens,
        budget_utilization=budget_utilization,
        avg_score=round(avg_score, 6),
        avg_freshness_score=round(avg_freshness, 6),
        included_doc_count=len({d.doc_id for d in included}),
        blocked_doc_count=len({d.doc_id for d in blocked}),
        stale_doc_count=len({d.doc_id for d in stale}),
        dropped_doc_count=len({d.doc_id for d in dropped}),
    )

    return DecisionTrace(
        user_context=user_ctx,
        policy_config=policy,
        included=included,
        blocked_by_permission=blocked,
        demoted_as_stale=stale,
        dropped_by_budget=dropped,
        total_tokens=total_tokens,
        ttft_proxy_ms=round(ttft_proxy_ms, 2),
        metrics=metrics,
    )
