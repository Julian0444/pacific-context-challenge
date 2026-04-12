"""
tests/test_stages.py — Unit tests for the typed pipeline stages.

Tests each stage in isolation with synthetic inputs (no FAISS, no disk I/O).
Also includes pipeline-level integration tests for blocked, stale, and
dropped-by-budget scenarios using the real corpus.
"""

import pytest

from src.models import (
    BlockedDocument,
    DroppedByBudget,
    FreshnessScoredDocument,
    IncludedDocument,
    PolicyConfig,
    ScoredDocument,
    StaleDocument,
    UserContext,
)
from src.stages.permission_filter import filter_permissions, PermissionResult
from src.stages.freshness_scorer import score_freshness, FreshnessResult, STALE_PENALTY
from src.stages.budget_packer import pack_budget, BudgetResult
from src.stages.trace_builder import build_trace


# ---------------------------------------------------------------------------
# Helpers — synthetic data factories
# ---------------------------------------------------------------------------

def _scored(doc_id, score=0.8, min_role="analyst", **kw):
    return ScoredDocument(
        doc_id=doc_id, score=score, excerpt=f"Excerpt for {doc_id}",
        min_role=min_role, **kw,
    )


def _freshness_scored(doc_id, score=0.8, freshness_score=0.9, is_stale=False, **kw):
    return FreshnessScoredDocument(
        doc_id=doc_id, score=score, excerpt=f"Excerpt for {doc_id}",
        min_role="analyst", freshness_score=freshness_score,
        is_stale=is_stale, **kw,
    )


_ROLES = {
    "analyst": {"name": "analyst", "access_rank": 1},
    "vp": {"name": "vp", "access_rank": 2},
    "partner": {"name": "partner", "access_rank": 3},
}

_METADATA = {
    "documents": [
        {"id": "doc_001", "date": "2024-04-18", "superseded_by": None, "min_role": "analyst"},
        {"id": "doc_002", "date": "2023-10-15", "superseded_by": "doc_003", "min_role": "analyst"},
        {"id": "doc_003", "date": "2024-01-20", "superseded_by": None, "min_role": "analyst"},
    ],
}


# ===========================================================================
# permission_filter
# ===========================================================================

class TestPermissionFilter:

    def test_analyst_sees_analyst_docs(self):
        docs = [_scored("doc_001"), _scored("doc_002")]
        ctx = UserContext(role="analyst", access_rank=1)
        result = filter_permissions(docs, ctx, _ROLES)
        assert isinstance(result, PermissionResult)
        assert len(result.permitted) == 2
        assert len(result.blocked) == 0

    def test_analyst_blocked_from_vp_docs(self):
        docs = [_scored("doc_001"), _scored("doc_010", min_role="vp")]
        ctx = UserContext(role="analyst", access_rank=1)
        result = filter_permissions(docs, ctx, _ROLES)
        assert len(result.permitted) == 1
        assert len(result.blocked) == 1
        assert result.blocked[0].doc_id == "doc_010"
        assert result.blocked[0].reason == "insufficient_role"
        assert result.blocked[0].required_role == "vp"
        assert result.blocked[0].user_role == "analyst"

    def test_partner_sees_all(self):
        docs = [
            _scored("doc_001"),
            _scored("doc_010", min_role="vp"),
            _scored("doc_011", min_role="partner"),
        ]
        ctx = UserContext(role="partner", access_rank=3)
        result = filter_permissions(docs, ctx, _ROLES)
        assert len(result.permitted) == 3
        assert len(result.blocked) == 0

    def test_empty_input(self):
        result = filter_permissions([], UserContext(role="analyst", access_rank=1), _ROLES)
        assert result.permitted == []
        assert result.blocked == []

    def test_blocked_has_structured_fields(self):
        docs = [_scored("doc_011", min_role="partner")]
        ctx = UserContext(role="vp", access_rank=2)
        result = filter_permissions(docs, ctx, _ROLES)
        b = result.blocked[0]
        assert isinstance(b, BlockedDocument)
        assert b.required_role == "partner"
        assert b.user_role == "vp"

    def test_unknown_min_role_blocks_doc_not_pipeline(self):
        """A doc with an unknown min_role should be blocked, not crash the pipeline."""
        docs = [
            _scored("good", min_role="analyst"),
            _scored("bad", min_role="admin"),  # unknown role
            _scored("also_good", min_role="vp"),
        ]
        ctx = UserContext(role="vp", access_rank=2)
        result = filter_permissions(docs, ctx, _ROLES)
        assert len(result.permitted) == 2
        assert len(result.blocked) == 1
        assert result.blocked[0].doc_id == "bad"
        assert result.blocked[0].reason == "unknown_min_role"


# ===========================================================================
# freshness_scorer
# ===========================================================================

class TestFreshnessScorer:

    def test_scores_attached(self):
        docs = [_scored("doc_001"), _scored("doc_003")]
        result = score_freshness(docs, _METADATA)
        assert isinstance(result, FreshnessResult)
        assert len(result.scored) == 2
        for fd in result.scored:
            assert isinstance(fd, FreshnessScoredDocument)
            assert fd.freshness_score > 0

    def test_stale_doc_flagged(self):
        docs = [_scored("doc_002", superseded_by="doc_003")]
        result = score_freshness(docs, _METADATA)
        assert len(result.stale) == 1
        s = result.stale[0]
        assert isinstance(s, StaleDocument)
        assert s.doc_id == "doc_002"
        assert s.superseded_by == "doc_003"

    def test_stale_penalty_applied(self):
        docs = [_scored("doc_002", superseded_by="doc_003"), _scored("doc_003")]
        result = score_freshness(docs, _METADATA)
        stale_score = next(d for d in result.scored if d.doc_id == "doc_002")
        fresh_score = next(d for d in result.scored if d.doc_id == "doc_003")
        # doc_002 is older AND penalized — must be lower
        assert stale_score.freshness_score < fresh_score.freshness_score
        assert stale_score.is_stale is True
        assert fresh_score.is_stale is False

    def test_non_stale_no_penalty(self):
        docs = [_scored("doc_001")]
        result = score_freshness(docs, _METADATA)
        assert result.scored[0].freshness_score > 0
        assert result.scored[0].is_stale is False
        assert len(result.stale) == 0

    def test_unknown_doc_gets_zero_freshness(self):
        docs = [_scored("doc_999")]
        result = score_freshness(docs, _METADATA)
        assert result.scored[0].freshness_score == 0.0

    def test_empty_input(self):
        result = score_freshness([], _METADATA)
        assert result.scored == []
        assert result.stale == []

    def test_superseded_by_from_metadata(self):
        """Even if ScoredDocument.superseded_by is None, metadata can flag it."""
        docs = [_scored("doc_002")]  # no superseded_by on the ScoredDocument
        result = score_freshness(docs, _METADATA)
        assert result.scored[0].is_stale is True
        assert result.scored[0].superseded_by == "doc_003"
        assert len(result.stale) == 1


# ===========================================================================
# budget_packer
# ===========================================================================

class TestBudgetPacker:

    def test_basic_packing(self):
        docs = [_freshness_scored("doc_001"), _freshness_scored("doc_002")]
        result = pack_budget(docs, token_budget=5000)
        assert isinstance(result, BudgetResult)
        assert len(result.packed) == 2
        assert len(result.over_budget) == 0
        assert result.total_tokens > 0
        assert 0.0 < result.budget_utilization <= 1.0

    def test_budget_drops_excess(self):
        docs = [
            _freshness_scored("doc_001", score=0.9, freshness_score=0.95),
            _freshness_scored("doc_002", score=0.8, freshness_score=0.85),
            _freshness_scored("doc_003", score=0.7, freshness_score=0.75),
        ]
        result = pack_budget(docs, token_budget=12)
        assert result.total_tokens <= 12
        # At least one doc should be dropped (each excerpt is ~6 tokens)
        assert len(result.over_budget) > 0

    def test_over_budget_has_structured_fields(self):
        docs = [_freshness_scored("doc_001", score=0.9, freshness_score=0.95)]
        result = pack_budget(docs, token_budget=1)  # too small for any doc
        assert len(result.over_budget) == 1
        d = result.over_budget[0]
        assert isinstance(d, DroppedByBudget)
        assert d.doc_id == "doc_001"
        assert d.token_count > 0
        assert d.score == 0.9
        assert d.freshness_score == 0.95

    def test_packed_has_token_count(self):
        docs = [_freshness_scored("doc_001")]
        result = pack_budget(docs, token_budget=5000)
        assert result.packed[0].token_count > 0
        assert isinstance(result.packed[0], IncludedDocument)

    def test_ranking_by_combined_score(self):
        docs = [
            _freshness_scored("low", score=0.1, freshness_score=0.1),
            _freshness_scored("high", score=0.9, freshness_score=0.9),
        ]
        result = pack_budget(docs, token_budget=5000)
        assert result.packed[0].doc_id == "high"
        assert result.packed[1].doc_id == "low"

    def test_empty_input(self):
        result = pack_budget([], token_budget=2048)
        assert result.packed == []
        assert result.over_budget == []
        assert result.total_tokens == 0
        assert result.budget_utilization == 0.0

    def test_budget_utilization_ratio(self):
        docs = [_freshness_scored("doc_001")]
        result = pack_budget(docs, token_budget=5000)
        expected = result.total_tokens / 5000
        assert abs(result.budget_utilization - round(expected, 4)) < 0.001


# ===========================================================================
# trace_builder
# ===========================================================================

class TestTraceBuilder:

    def test_basic_trace(self):
        included = [IncludedDocument(
            doc_id="doc_001", content="text", score=0.9,
            freshness_score=0.8, token_count=50,
        )]
        trace = build_trace(
            user_ctx=UserContext(role="analyst", access_rank=1),
            policy=PolicyConfig(),
            retrieved_count=1,
            included=included,
            blocked=[],
            stale=[],
            dropped=[],
            total_tokens=50,
            budget_utilization=0.025,
            ttft_proxy_ms=12.5,
        )
        assert trace.total_tokens == 50
        assert trace.ttft_proxy_ms == 12.5
        assert trace.metrics.included_count == 1
        assert trace.metrics.blocked_count == 0
        assert trace.metrics.dropped_count == 0
        assert trace.metrics.budget_utilization == 0.025
        assert trace.metrics.avg_score == 0.9
        assert trace.metrics.avg_freshness_score == 0.8

    def test_trace_with_all_categories(self):
        included = [IncludedDocument(
            doc_id="doc_001", content="text", score=0.9,
            freshness_score=0.8, token_count=50,
        )]
        blocked = [BlockedDocument(
            doc_id="doc_010", required_role="partner", user_role="analyst",
        )]
        stale = [StaleDocument(
            doc_id="doc_002", superseded_by="doc_003", freshness_score=0.3,
        )]
        dropped = [DroppedByBudget(
            doc_id="doc_005", token_count=500, score=0.6, freshness_score=0.5,
        )]
        # retrieved=3: 1 included + 1 blocked + 1 dropped
        trace = build_trace(
            user_ctx=UserContext(role="analyst", access_rank=1),
            policy=PolicyConfig(),
            retrieved_count=3,
            included=included,
            blocked=blocked,
            stale=stale,
            dropped=dropped,
            total_tokens=50,
            budget_utilization=0.025,
            ttft_proxy_ms=8.3,
        )
        assert len(trace.blocked_by_permission) == 1
        assert len(trace.demoted_as_stale) == 1
        assert len(trace.dropped_by_budget) == 1
        assert trace.metrics.retrieved_count == 3
        assert trace.metrics.blocked_count == 1
        assert trace.metrics.stale_count == 1
        assert trace.metrics.dropped_count == 1

    def test_trace_empty_context(self):
        trace = build_trace(
            user_ctx=UserContext(role="analyst", access_rank=1),
            policy=PolicyConfig(),
            retrieved_count=0,
            included=[],
            blocked=[],
            stale=[],
            dropped=[],
            total_tokens=0,
            budget_utilization=0.0,
            ttft_proxy_ms=1.0,
        )
        assert trace.metrics.avg_score == 0.0
        assert trace.metrics.avg_freshness_score == 0.0
        assert trace.metrics.included_count == 0

    def test_accounting_mismatch_raises(self):
        """If blocked + included + dropped != retrieved, build_trace must fail."""
        with pytest.raises(ValueError, match="Document accounting mismatch"):
            build_trace(
                user_ctx=UserContext(role="analyst", access_rank=1),
                policy=PolicyConfig(),
                retrieved_count=10,  # but only 1 doc accounted for
                included=[IncludedDocument(
                    doc_id="doc_001", content="x", score=0.9,
                    freshness_score=0.8, token_count=5,
                )],
                blocked=[],
                stale=[],
                dropped=[],
                total_tokens=5,
                budget_utilization=0.0,
                ttft_proxy_ms=1.0,
            )


# ===========================================================================
# Pipeline integration — blocked, stale, dropped-by-budget
# ===========================================================================

import json
import os
from src.pipeline import run_pipeline, PipelineError
from src.retriever import retrieve
from src.policies import load_roles

_ROLES_PATH = os.path.join(os.path.dirname(__file__), "..", "corpus", "roles.json")
_METADATA_PATH = os.path.join(os.path.dirname(__file__), "..", "corpus", "metadata.json")
_real_roles = load_roles(_ROLES_PATH)
with open(_METADATA_PATH) as f:
    _real_metadata = json.load(f)

from src.models import QueryRequest


def _run(query="What is Meridian's ARR?", role="analyst", top_k=8, policy="default"):
    req = QueryRequest(query=query, role=role, top_k=top_k, policy_name=policy)
    return run_pipeline(req, retrieve, _real_roles, _real_metadata)


class TestPipelineBlockedStaleDropped:

    def test_analyst_blocked_docs_traced(self):
        result = _run(
            query="investment committee memo deal terms LP update",
            role="analyst", top_k=12,
        )
        assert len(result.trace.blocked_by_permission) > 0
        for b in result.trace.blocked_by_permission:
            assert b.user_role == "analyst"
            assert b.reason == "insufficient_role"
        # Blocked must not appear in included
        blocked_ids = {b.doc_id for b in result.trace.blocked_by_permission}
        included_ids = {d.doc_id for d in result.context}
        assert blocked_ids.isdisjoint(included_ids)

    def test_stale_docs_traced(self):
        result = _run(
            query="financial model research notes revenue",
            role="partner", top_k=12,
        )
        for s in result.trace.demoted_as_stale:
            assert s.superseded_by
            assert s.freshness_score >= 0

    def test_dropped_by_budget_traced(self):
        """With a tiny budget, some docs must be dropped."""
        req = QueryRequest(
            query="Meridian revenue growth ARR",
            role="partner", top_k=12,
            policy_name="full_policy",
        )
        from src.policies import resolve_policy
        # Run with a very small budget to force drops
        policy = resolve_policy("full_policy", top_k=12).model_copy(update={"token_budget": 100})
        user_ctx = UserContext(role="partner", access_rank=3)

        from src.pipeline import _retrieve_stage, _permission_stage, _freshness_stage, _budget_stage, _unwrap
        candidates = _unwrap(_retrieve_stage(req.query, policy.top_k, retrieve))
        perm = _unwrap(_permission_stage(candidates, user_ctx, _real_roles, policy))
        fresh = _unwrap(_freshness_stage(perm.permitted, _real_metadata, policy))
        budget = _unwrap(_budget_stage(fresh.scored, policy))

        assert budget.total_tokens <= 100
        assert len(budget.over_budget) > 0
        for d in budget.over_budget:
            assert isinstance(d, DroppedByBudget)
            assert d.token_count > 0

    def test_budget_utilization_in_trace(self):
        result = _run(top_k=8)
        assert 0.0 <= result.trace.metrics.budget_utilization <= 1.0

    def test_ttft_proxy_positive(self):
        result = _run()
        assert result.trace.ttft_proxy_ms > 0
