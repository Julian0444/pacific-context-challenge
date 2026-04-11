"""
tests/test_models.py — Contract/validation tests for src/models.py.

These tests assert the shape and constraints of every Pydantic model in the
pipeline: required fields, defaults, immutability, and rejection of unknown keys.
"""

import pytest
from pydantic import ValidationError

from src.models import (
    UserContext,
    PolicyConfig,
    ScoredDocument,
    FreshnessScoredDocument,
    BlockedDocument,
    StaleDocument,
    IncludedDocument,
    TraceMetrics,
    DecisionTrace,
    PipelineResult,
    QueryRequest,
    QueryResponse,
    DocumentChunk,
)


# ---------------------------------------------------------------------------
# UserContext
# ---------------------------------------------------------------------------

def test_user_context_valid():
    uc = UserContext(role="analyst", access_rank=1)
    assert uc.role == "analyst"
    assert uc.access_rank == 1


def test_user_context_frozen():
    uc = UserContext(role="analyst", access_rank=1)
    with pytest.raises(Exception):  # ValidationError or TypeError depending on pydantic v
        uc.role = "vp"


def test_user_context_rejects_extra():
    with pytest.raises(ValidationError):
        UserContext(role="analyst", access_rank=1, unknown_field="x")


# ---------------------------------------------------------------------------
# PolicyConfig
# ---------------------------------------------------------------------------

def test_policy_config_defaults():
    pc = PolicyConfig()
    assert pc.name == "default"
    assert pc.token_budget == 2048
    assert pc.top_k == 5
    assert pc.half_life_days == 365


def test_policy_config_custom():
    pc = PolicyConfig(name="strict", token_budget=1024, top_k=3, half_life_days=180)
    assert pc.token_budget == 1024


def test_policy_config_frozen():
    pc = PolicyConfig()
    with pytest.raises(Exception):
        pc.token_budget = 9999


# ---------------------------------------------------------------------------
# ScoredDocument
# ---------------------------------------------------------------------------

def test_scored_document_minimal():
    doc = ScoredDocument(
        doc_id="doc_001",
        score=0.87,
        excerpt="Some excerpt text.",
        min_role="analyst",
    )
    assert doc.doc_id == "doc_001"
    assert doc.tags == []
    assert doc.superseded_by is None


def test_scored_document_ignores_extra_keys():
    # The retriever returns extra keys (rank, file_name, type) — must not raise.
    doc = ScoredDocument(
        doc_id="doc_002",
        score=0.75,
        excerpt="Text",
        min_role="vp",
        rank=1,
        file_name="doc.txt",
        type="memo",
    )
    assert doc.doc_id == "doc_002"


def test_scored_document_frozen():
    doc = ScoredDocument(doc_id="doc_001", score=0.9, excerpt="x", min_role="analyst")
    with pytest.raises(Exception):
        doc.score = 0.0


# ---------------------------------------------------------------------------
# FreshnessScoredDocument
# ---------------------------------------------------------------------------

def test_freshness_scored_document_valid():
    doc = FreshnessScoredDocument(
        doc_id="doc_003",
        score=0.8,
        excerpt="Fresh content",
        min_role="analyst",
        freshness_score=0.95,
        is_stale=False,
    )
    assert doc.freshness_score == 0.95
    assert not doc.is_stale


def test_freshness_scored_document_stale_flag():
    doc = FreshnessScoredDocument(
        doc_id="doc_002",
        score=0.7,
        excerpt="Old content",
        min_role="analyst",
        freshness_score=0.3,
        is_stale=True,
        superseded_by="doc_003",
    )
    assert doc.is_stale
    assert doc.superseded_by == "doc_003"


# ---------------------------------------------------------------------------
# BlockedDocument
# ---------------------------------------------------------------------------

def test_blocked_document_valid():
    bd = BlockedDocument(doc_id="doc_010", required_role="partner", user_role="analyst")
    assert bd.reason == "insufficient_role"
    assert bd.doc_id == "doc_010"


def test_blocked_document_rejects_extra():
    with pytest.raises(ValidationError):
        BlockedDocument(
            doc_id="doc_010",
            required_role="partner",
            user_role="analyst",
            sneaky_field="bad",
        )


# ---------------------------------------------------------------------------
# StaleDocument
# ---------------------------------------------------------------------------

def test_stale_document_valid():
    sd = StaleDocument(doc_id="doc_002", superseded_by="doc_003", freshness_score=0.4)
    assert sd.penalty_applied == 0.5


# ---------------------------------------------------------------------------
# IncludedDocument
# ---------------------------------------------------------------------------

def test_included_document_valid():
    inc = IncludedDocument(
        doc_id="doc_005",
        content="Full context text here.",
        score=0.91,
        freshness_score=0.88,
        token_count=120,
    )
    assert inc.tags == []
    assert inc.token_count == 120


# ---------------------------------------------------------------------------
# TraceMetrics
# ---------------------------------------------------------------------------

def test_trace_metrics_valid():
    tm = TraceMetrics(
        retrieved_count=8,
        blocked_count=2,
        stale_count=1,
        included_count=5,
        total_tokens=1800,
        avg_score=0.78,
        avg_freshness_score=0.72,
    )
    assert tm.included_count == 5


# ---------------------------------------------------------------------------
# DecisionTrace
# ---------------------------------------------------------------------------

def test_decision_trace_empty_lists():
    dt = DecisionTrace(
        user_context=UserContext(role="analyst", access_rank=1),
        policy_config=PolicyConfig(),
        metrics=TraceMetrics(
            retrieved_count=5,
            blocked_count=0,
            stale_count=0,
            included_count=5,
            total_tokens=900,
            avg_score=0.82,
            avg_freshness_score=0.76,
        ),
    )
    assert dt.blocked == []
    assert dt.stale == []
    assert dt.included == []


# ---------------------------------------------------------------------------
# PipelineResult
# ---------------------------------------------------------------------------

def test_pipeline_result_no_trace():
    inc = IncludedDocument(
        doc_id="doc_001", content="x", score=0.9, freshness_score=0.8, token_count=50
    )
    pr = PipelineResult(context=[inc], total_tokens=50, trace=None)
    assert pr.trace is None
    assert len(pr.context) == 1


# ---------------------------------------------------------------------------
# QueryRequest — API boundary
# ---------------------------------------------------------------------------

def test_query_request_defaults():
    qr = QueryRequest(query="What is ARR?")
    assert qr.role == "analyst"
    assert qr.top_k == 5
    assert qr.policy_name == "default"


def test_query_request_policy_name():
    qr = QueryRequest(query="Revenue?", policy_name="strict")
    assert qr.policy_name == "strict"


def test_query_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        QueryRequest(query="Revenue?", not_a_field=True)


def test_query_request_backward_compat_fields():
    # All original fields still work exactly as before.
    qr = QueryRequest(query="DD risks", role="vp", top_k=8)
    assert qr.role == "vp"
    assert qr.top_k == 8


# ---------------------------------------------------------------------------
# QueryResponse — API boundary
# ---------------------------------------------------------------------------

def test_query_response_no_trace():
    chunk = DocumentChunk(doc_id="doc_001", content="text", score=0.9)
    resp = QueryResponse(query="q", context=[chunk], total_tokens=100)
    assert resp.decision_trace is None
    assert resp.total_tokens == 100


def test_query_response_backward_compat_fields():
    chunk = DocumentChunk(doc_id="doc_001", content="text", score=0.9, freshness_score=0.8, tags=["deal"])
    resp = QueryResponse(query="q", context=[chunk], total_tokens=200)
    assert resp.context[0].freshness_score == 0.8
    assert resp.context[0].tags == ["deal"]
