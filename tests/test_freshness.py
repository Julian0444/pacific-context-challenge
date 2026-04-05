"""Tests for freshness.py — recency scoring and stale-doc demotion."""

import pytest
from datetime import datetime, timedelta
from src.freshness import compute_freshness, apply_freshness


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


def _make_chunk(doc_id, score=0.9):
    return {"doc_id": doc_id, "score": score}


def _make_metadata(doc_id, date, superseded_by=None):
    return {
        "id": doc_id,
        "date": date,
        "superseded_by": superseded_by,
    }


def test_apply_freshness_attaches_score():
    chunks = [_make_chunk("doc_001")]
    metadata = {"documents": [_make_metadata("doc_001", datetime.now().strftime("%Y-%m-%d"))]}
    result = apply_freshness(chunks, metadata)
    assert "freshness_score" in result[0]
    assert result[0]["freshness_score"] > 0.9


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
    # Stale doc should have lower freshness despite same date
    assert stale["freshness_score"] < fresh["freshness_score"]


def test_apply_freshness_preserves_order():
    today = datetime.now().strftime("%Y-%m-%d")
    chunks = [_make_chunk("a"), _make_chunk("b")]
    metadata = {"documents": [
        _make_metadata("a", today),
        _make_metadata("b", today),
    ]}
    result = apply_freshness(chunks, metadata)
    assert [c["doc_id"] for c in result] == ["a", "b"]
