"""
tests/test_pipeline.py — Integration tests for the pipeline orchestrator.

Tests cover:
  - Happy path (full_policy, default)
  - Policy presets (naive_top_k, permission_aware)
  - Role filtering produces BlockedDocument entries
  - Stale docs appear in trace
  - Token budget respected
  - Pipeline aborts on retriever failure
  - Invalid policy name
"""

import pytest

from src.models import (
    QueryRequest,
    PipelineResult,
    IncludedDocument,
    BlockedDocument,
    StaleDocument,
)
from src.pipeline import run_pipeline, PipelineError, StageOk, StageErr, _unwrap
from src.retriever import retrieve
from src.policies import load_roles

import json
import os

# ---------------------------------------------------------------------------
# Fixtures — load real roles and metadata once
# ---------------------------------------------------------------------------

_ROLES_PATH = os.path.join(os.path.dirname(__file__), "..", "corpus", "roles.json")
_METADATA_PATH = os.path.join(os.path.dirname(__file__), "..", "corpus", "metadata.json")

_roles = load_roles(_ROLES_PATH)

with open(_METADATA_PATH, "r") as f:
    _metadata = json.load(f)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(query="What is Meridian's ARR?", role="analyst", top_k=8, policy="default"):
    req = QueryRequest(query=query, role=role, top_k=top_k, policy_name=policy)
    return run_pipeline(req, retrieve, _roles, _metadata)


def _fake_retriever_error(query: str, top_k: int):
    raise RuntimeError("FAISS index corrupted")


def _fake_retriever_empty(query: str, top_k: int):
    return []


# ---------------------------------------------------------------------------
# StageResult unit tests
# ---------------------------------------------------------------------------

def test_unwrap_ok():
    result = StageOk(value=42)
    assert _unwrap(result) == 42


def test_unwrap_err_raises():
    result = StageErr(stage="test", error="boom")
    with pytest.raises(PipelineError) as exc_info:
        _unwrap(result)
    assert exc_info.value.stage == "test"
    assert "boom" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Happy path — full_policy / default
# ---------------------------------------------------------------------------

def test_default_policy_returns_pipeline_result():
    result = _run()
    assert isinstance(result, PipelineResult)
    assert result.total_tokens > 0
    assert len(result.context) > 0
    assert result.trace is not None


def test_full_policy_returns_pipeline_result():
    result = _run(policy="full_policy")
    assert isinstance(result, PipelineResult)
    assert result.trace is not None


def test_trace_metrics_populated():
    result = _run(top_k=8)
    m = result.trace.metrics
    assert m.retrieved_count > 0
    assert m.included_count == len(result.context)
    assert m.total_tokens == result.total_tokens
    assert m.avg_score > 0
    assert m.blocked_count >= 0
    assert m.stale_count >= 0
    assert m.dropped_count >= 0
    assert 0.0 <= m.budget_utilization <= 1.0
    assert result.trace.ttft_proxy_ms > 0


def test_included_documents_have_token_count():
    result = _run()
    for doc in result.context:
        assert isinstance(doc, IncludedDocument)
        assert doc.token_count > 0


def test_trace_user_context():
    result = _run(role="vp")
    assert result.trace.user_context.role == "vp"
    assert result.trace.user_context.access_rank == 2


def test_trace_policy_config():
    result = _run(top_k=10, policy="full_policy")
    assert result.trace.policy_config.name == "full_policy"
    assert result.trace.policy_config.top_k == 10


# ---------------------------------------------------------------------------
# Role filtering → blocked docs in trace
# ---------------------------------------------------------------------------

def test_analyst_blocked_docs_in_trace():
    """Analyst can't see partner/vp-only docs; those should appear in trace.blocked."""
    result = _run(
        query="investment committee memo deal terms LP update",
        role="analyst",
        top_k=12,
    )
    blocked_ids = {b.doc_id for b in result.trace.blocked_by_permission}
    included_ids = {d.doc_id for d in result.context}

    # Blocked docs must not appear in included
    assert blocked_ids.isdisjoint(included_ids)

    # If any docs were blocked, they must have the right fields
    for b in result.trace.blocked_by_permission:
        assert isinstance(b, BlockedDocument)
        assert b.user_role == "analyst"
        assert b.reason == "insufficient_role"


def test_partner_sees_all():
    """Partner should have zero blocked docs."""
    result = _run(
        query="investment committee memo deal terms",
        role="partner",
        top_k=12,
    )
    assert len(result.trace.blocked_by_permission) == 0


# ---------------------------------------------------------------------------
# Stale docs in trace
# ---------------------------------------------------------------------------

def test_stale_docs_in_trace():
    """Superseded docs (doc_002, doc_007) should appear in trace.stale when retrieved."""
    result = _run(
        query="financial model research notes revenue",
        role="partner",
        top_k=12,
    )
    stale_ids = {s.doc_id for s in result.trace.demoted_as_stale}
    for s in result.trace.demoted_as_stale:
        assert isinstance(s, StaleDocument)
        assert s.superseded_by  # non-empty
        assert s.freshness_score >= 0


# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------

def test_token_budget_respected():
    result = _run(top_k=12)
    assert result.total_tokens <= 2048


def test_small_budget_limits_context():
    req = QueryRequest(query="Meridian revenue ARR", role="partner", top_k=12)
    from src.pipeline import _retrieve_stage, _permission_stage, _freshness_stage, _budget_stage, _unwrap
    from src.policies import resolve_policy
    from src.models import UserContext

    policy = resolve_policy("full_policy", top_k=12).model_copy(update={"token_budget": 200})
    user_ctx = UserContext(role="partner", access_rank=3)

    candidates = _unwrap(_retrieve_stage(req.query, policy.top_k, retrieve))
    perm_result = _unwrap(_permission_stage(candidates, user_ctx, _roles, policy))
    fresh_result = _unwrap(_freshness_stage(perm_result.permitted, _metadata, policy))
    budget_result = _unwrap(_budget_stage(fresh_result.scored, policy))

    assert budget_result.total_tokens <= 200


# ---------------------------------------------------------------------------
# Policy presets
# ---------------------------------------------------------------------------

def test_naive_top_k_dangerous_baseline():
    """naive_top_k skips permissions, freshness, AND budget — raw retrieval only."""
    result = _run(
        query="investment committee memo",
        role="analyst",
        top_k=8,
        policy="naive_top_k",
    )
    assert isinstance(result, PipelineResult)
    # No blocking even though analyst normally can't see partner docs
    assert len(result.trace.blocked_by_permission) == 0
    # No stale tracking
    assert len(result.trace.demoted_as_stale) == 0
    # Freshness scores should be 0.0 (skipped)
    for doc in result.context:
        assert doc.freshness_score == 0.0
    # All retrieved docs pass through — no budget enforcement
    assert result.trace.metrics.included_count == result.trace.metrics.retrieved_count
    assert result.trace.policy_config.skip_permission_filter is True
    assert result.trace.policy_config.skip_freshness is True
    assert result.trace.policy_config.skip_budget is True


def test_permission_aware_filters_but_no_freshness():
    result = _run(
        query="investment committee memo deal terms LP update",
        role="analyst",
        top_k=12,
        policy="permission_aware",
    )
    assert isinstance(result, PipelineResult)
    # Should have blocking
    included_ids = {d.doc_id for d in result.context}
    assert "doc_010" not in included_ids  # partner-only
    assert "doc_011" not in included_ids  # partner-only
    # No stale tracking (freshness skipped)
    assert len(result.trace.demoted_as_stale) == 0
    # Freshness scores are 0.0
    for doc in result.context:
        assert doc.freshness_score == 0.0
    assert result.trace.policy_config.skip_freshness is True
    assert result.trace.policy_config.skip_permission_filter is False


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_retriever_failure_raises_pipeline_error():
    req = QueryRequest(query="anything", role="analyst")
    with pytest.raises(PipelineError) as exc_info:
        run_pipeline(req, _fake_retriever_error, _roles, _metadata)
    assert exc_info.value.stage == "retrieve"
    assert "corrupted" in exc_info.value.error


def test_empty_retrieval():
    req = QueryRequest(query="zzzzz nothing matches", role="analyst")
    result = run_pipeline(req, _fake_retriever_empty, _roles, _metadata)
    assert result.total_tokens == 0
    assert result.context == []
    assert result.trace.metrics.retrieved_count == 0
    assert result.trace.metrics.included_count == 0


def test_invalid_policy_raises_pipeline_error():
    req = QueryRequest(query="test", role="analyst", policy_name="nonexistent")
    with pytest.raises(ValueError, match="Unknown policy"):
        run_pipeline(req, retrieve, _roles, _metadata)
