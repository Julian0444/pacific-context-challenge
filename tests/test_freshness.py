"""Tests for freshness.py — recency scoring.

Stale-doc demotion is applied in stages/freshness_scorer.py and tested in
tests/test_stages.py::TestFreshnessScorer.
"""

import pytest
from datetime import datetime, timedelta
from src.freshness import compute_freshness


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
