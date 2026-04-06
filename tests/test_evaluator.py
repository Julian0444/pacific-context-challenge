"""Tests for evaluator.py — metric functions and eval harness."""

import os
import pytest
from src.evaluator import load_test_queries, precision_at_k, run_evals

EVALS_PATH = os.path.join(os.path.dirname(__file__), "..", "evals", "test_queries.json")


# ---- precision_at_k --------------------------------------------------------

def test_precision_perfect():
    assert precision_at_k(["a", "b", "c"], ["a", "b", "c"], k=3) == pytest.approx(1.0)


def test_precision_zero():
    assert precision_at_k(["x", "y", "z"], ["a", "b"], k=3) == pytest.approx(0.0)


def test_precision_partial():
    # 1 hit in top 2 → 0.5
    assert precision_at_k(["a", "x"], ["a", "b"], k=2) == pytest.approx(0.5)


def test_precision_k_larger_than_results():
    # k=5 but only 2 docs assembled — clamp to 2
    assert precision_at_k(["a", "b"], ["a", "b"], k=5) == pytest.approx(1.0)


def test_precision_empty_retrieved():
    assert precision_at_k([], ["a"], k=5) == pytest.approx(0.0)


def test_precision_only_top_k_matters():
    # hit is at position 4, k=3 → should not count
    assert precision_at_k(["x", "y", "z", "a"], ["a"], k=3) == pytest.approx(0.0)


# ---- load_test_queries ------------------------------------------------------

def test_load_test_queries_count():
    queries = load_test_queries(EVALS_PATH)
    assert len(queries) >= 6


def test_load_test_queries_required_fields():
    queries = load_test_queries(EVALS_PATH)
    for q in queries:
        assert "id" in q
        assert "query" in q
        assert "role" in q
        assert "expected_doc_ids" in q


def test_load_test_queries_valid_roles():
    queries = load_test_queries(EVALS_PATH)
    valid_roles = {"analyst", "vp", "partner"}
    for q in queries:
        assert q["role"] in valid_roles, f"{q['id']} has invalid role: {q['role']!r}"


def test_load_test_queries_expected_are_lists():
    queries = load_test_queries(EVALS_PATH)
    for q in queries:
        assert isinstance(q["expected_doc_ids"], list)


# ---- run_evals (integration) ------------------------------------------------

@pytest.fixture(scope="module")
def eval_results():
    queries = load_test_queries(EVALS_PATH)
    return run_evals(queries, k=5, top_k=8)


def test_run_evals_structure(eval_results):
    assert "per_query" in eval_results
    assert "aggregate" in eval_results


def test_run_evals_no_failures(eval_results):
    assert eval_results["aggregate"]["queries_failed"] == 0


def test_run_evals_no_permission_violations(eval_results):
    for r in eval_results["per_query"]:
        if "error" in r:
            continue
        assert r["permission_violations"] == [], (
            f"Query {r['id']} violated permissions: {r['permission_violations']}"
        )


def test_run_evals_aggregate_keys(eval_results):
    agg = eval_results["aggregate"]
    assert "avg_precision_at_5" in agg
    assert "avg_recall" in agg
    assert "permission_violation_rate" in agg
    assert "avg_context_docs" in agg
    assert "avg_total_tokens" in agg


def test_run_evals_known_good_queries(eval_results):
    """The integration/CTO query (q007) should reliably surface doc_009 and doc_006."""
    r = next(r for r in eval_results["per_query"] if r["id"] == "q007")
    assert "doc_009" in r["assembled_ids"]
    assert "doc_006" in r["assembled_ids"]


def test_run_evals_lp_update_partner(eval_results):
    """The LP update query (q008) should surface doc_011 at partner level."""
    r = next(r for r in eval_results["per_query"] if r["id"] == "q008")
    assert "doc_011" in r["assembled_ids"]


def test_run_evals_freshness_is_meaningful(eval_results):
    """Avg freshness should be well above zero with corpus-relative dating."""
    agg = eval_results["aggregate"]
    assert agg["avg_freshness_score"] > 0.1, (
        f"Freshness scores are too small ({agg['avg_freshness_score']:.2e}) — "
        "corpus-relative dating may not be active"
    )
