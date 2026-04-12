"""Tests for freshness.py — recency scoring and stale-doc demotion."""

import pytest
from datetime import datetime, timedelta
from src.freshness import compute_freshness, apply_freshness


# ---- compute_freshness (backwards-compatible, reference_date=None) ----------

def test_compute_freshness_today_is_one():
    today = datetime.now().strftime("%Y-%m-%d")
    score = compute_freshness(today, half_life_days=30)
    assert score == pytest.approx(1.0, abs=0.01)


def test_compute_freshness_one_half_life_ago():
    one_hl_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    score = compute_freshness(one_hl_ago, half_life_days=30)
    assert score == pytest.approx(0.5, abs=0.05)


def test_compute_freshness_very_old_is_near_zero():
    old = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    score = compute_freshness(old, half_life_days=30)
    assert score < 0.01


def test_compute_freshness_returns_between_zero_and_one():
    date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
    score = compute_freshness(date, half_life_days=30)
    assert 0.0 <= score <= 1.0


# ---- compute_freshness with explicit reference_date -------------------------

def test_compute_freshness_same_as_reference_is_one():
    score = compute_freshness("2024-04-18", reference_date="2024-04-18")
    assert score == pytest.approx(1.0)


def test_compute_freshness_one_year_before_reference():
    score = compute_freshness("2023-04-18", half_life_days=365, reference_date="2024-04-18")
    assert score == pytest.approx(0.5, abs=0.02)


def test_compute_freshness_newer_scores_higher():
    """A document from April 2024 should score higher than one from June 2023."""
    newer = compute_freshness("2024-04-10", half_life_days=365, reference_date="2024-04-18")
    older = compute_freshness("2023-06-15", half_life_days=365, reference_date="2024-04-18")
    assert newer > older
    # Both should be in a meaningful range, not near-zero
    assert newer > 0.9
    assert older > 0.4


# ---- apply_freshness (LEGACY) -----------------------------------------------
# apply_freshness() mutates plain dicts and is no longer called on any request
# path.  Freshness scoring now goes through stages/freshness_scorer.py
# (score_freshness), tested in tests/test_stages.py::TestFreshnessScorer.
# These tests are skipped to avoid misleading confidence in dead code.

_LEGACY_SKIP = pytest.mark.skip(
    reason="legacy: apply_freshness() replaced by stages/freshness_scorer.py"
)


def _make_chunk(doc_id, score=0.9):
    return {"doc_id": doc_id, "score": score}


def _make_metadata(doc_id, date, superseded_by=None):
    return {
        "id": doc_id,
        "date": date,
        "superseded_by": superseded_by,
    }


@_LEGACY_SKIP
def test_apply_freshness_attaches_score():
    chunks = [_make_chunk("doc_001")]
    metadata = {"documents": [_make_metadata("doc_001", datetime.now().strftime("%Y-%m-%d"))]}
    result = apply_freshness(chunks, metadata)
    assert "freshness_score" in result[0]
    assert result[0]["freshness_score"] > 0.9


@_LEGACY_SKIP
def test_apply_freshness_demotes_stale():
    today = datetime.now().strftime("%Y-%m-%d")
    chunks = [
        _make_chunk("doc_stale", score=0.95),
        _make_chunk("doc_fresh", score=0.90),
    ]
    metadata = {
        "documents": [
            _make_metadata("doc_stale", today, superseded_by="doc_fresh"),
            _make_metadata("doc_fresh", today, superseded_by=None),
        ]
    }
    result = apply_freshness(chunks, metadata)
    stale = next(c for c in result if c["doc_id"] == "doc_stale")
    fresh = next(c for c in result if c["doc_id"] == "doc_fresh")
    assert stale["freshness_score"] < fresh["freshness_score"]


@_LEGACY_SKIP
def test_apply_freshness_preserves_order():
    today = datetime.now().strftime("%Y-%m-%d")
    chunks = [_make_chunk("a"), _make_chunk("b")]
    metadata = {"documents": [
        _make_metadata("a", today),
        _make_metadata("b", today),
    ]}
    result = apply_freshness(chunks, metadata)
    assert [c["doc_id"] for c in result] == ["a", "b"]


@_LEGACY_SKIP
def test_apply_freshness_corpus_relative_meaningful_scores():
    """With corpus-relative dating, scores span a useful range (not all ~0)."""
    chunks = [
        _make_chunk("newest"),
        _make_chunk("oldest"),
    ]
    metadata = {
        "documents": [
            _make_metadata("newest", "2024-04-18"),
            _make_metadata("oldest", "2023-06-15"),
        ]
    }
    result = apply_freshness(chunks, metadata)
    newest = next(c for c in result if c["doc_id"] == "newest")
    oldest = next(c for c in result if c["doc_id"] == "oldest")
    assert newest["freshness_score"] == pytest.approx(1.0)
    assert oldest["freshness_score"] > 0.4
    assert newest["freshness_score"] > oldest["freshness_score"]


@_LEGACY_SKIP
def test_apply_freshness_stale_pair_visible_demotion():
    """Superseded doc is visibly penalized when both it and its replacement are present."""
    chunks = [
        _make_chunk("doc_stale", score=0.95),
        _make_chunk("doc_current", score=0.90),
    ]
    metadata = {
        "documents": [
            _make_metadata("doc_stale", "2024-03-25", superseded_by="doc_current"),
            _make_metadata("doc_current", "2024-04-10", superseded_by=None),
        ]
    }
    result = apply_freshness(chunks, metadata)
    stale = next(c for c in result if c["doc_id"] == "doc_stale")
    current = next(c for c in result if c["doc_id"] == "doc_current")
    # Stale: base ~0.97 * 0.5 = ~0.48, Current: base 1.0
    assert current["freshness_score"] > 0.9
    assert stale["freshness_score"] < 0.6
    # The gap should be large enough to influence the assembler's combined score
    assert current["freshness_score"] - stale["freshness_score"] > 0.3
