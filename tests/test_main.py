"""Tests for main.py — API endpoint integration tests."""

import pytest
from fastapi.testclient import TestClient

import src.main as _main_module
from src.main import app

client = TestClient(app)


@pytest.fixture()
def reset_session_audit():
    """Reset the in-memory audit store so session-audit tests start clean."""
    with _main_module._session_audit_lock:
        _main_module._session_audit.clear()
    yield


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_query_returns_200():
    resp = client.post("/query", json={"query": "What is Meridian's revenue?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "context" in data
    assert "total_tokens" in data
    assert "query" in data


def test_query_respects_role_filtering():
    # Analyst should NOT see partner-level docs (doc_010, doc_011)
    resp = client.post("/query", json={
        "query": "investment committee memo deal terms",
        "role": "analyst",
        "top_k": 12,
    })
    data = resp.json()
    doc_ids = [c["doc_id"] for c in data["context"]]
    assert "doc_010" not in doc_ids  # IC memo is partner-only
    assert "doc_011" not in doc_ids  # LP update is partner-only


def test_query_partner_can_see_all():
    resp = client.post("/query", json={
        "query": "investment committee memo deal terms",
        "role": "partner",
        "top_k": 12,
    })
    data = resp.json()
    doc_ids = [c["doc_id"] for c in data["context"]]
    # Partner should be able to see partner-level docs
    # At least some results should be returned
    assert len(data["context"]) > 0


def test_query_invalid_role_returns_422():
    resp = client.post("/query", json={
        "query": "test",
        "role": "viewer",
    })
    assert resp.status_code == 400


def test_query_invalid_policy_returns_400():
    resp = client.post("/query", json={
        "query": "test",
        "role": "analyst",
        "policy_name": "bogus_policy",
    })
    assert resp.status_code == 400
    assert "Unknown policy" in resp.json()["detail"]


def test_query_context_has_freshness_scores():
    resp = client.post("/query", json={"query": "Meridian financial model"})
    data = resp.json()
    for chunk in data["context"]:
        assert "freshness_score" in chunk


# ── /compare endpoint tests ──

def test_compare_returns_all_three_policies():
    resp = client.post("/compare", json={
        "query": "investment committee memo deal terms LP update",
        "role": "analyst",
        "top_k": 12,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["results"].keys()) == {"naive_top_k", "permission_aware", "full_policy"}
    for policy_result in data["results"].values():
        assert "context" in policy_result
        assert "total_tokens" in policy_result
        assert "decision_trace" in policy_result
        assert policy_result["decision_trace"] is not None

    # Core invariant: naive_top_k skips permission filter; full_policy enforces it
    naive_trace = data["results"]["naive_top_k"]["decision_trace"]
    full_trace = data["results"]["full_policy"]["decision_trace"]
    assert naive_trace["metrics"]["blocked_count"] == 0
    assert full_trace["metrics"]["blocked_count"] > 0


def test_compare_empty_policies_returns_400():
    resp = client.post("/compare", json={
        "query": "test query",
        "policies": [],
    })
    assert resp.status_code == 400


def test_compare_invalid_role_returns_400():
    resp = client.post("/compare", json={
        "query": "test query",
        "role": "viewer",
    })
    assert resp.status_code == 400


def test_compare_unknown_policy_returns_400():
    resp = client.post("/compare", json={
        "query": "test query",
        "role": "analyst",
        "policies": ["unknown_policy"],
    })
    assert resp.status_code == 400


# ── /evals endpoint tests ──

_EXPECTED_AGGREGATE_KEYS = {
    "queries_run",
    "queries_failed",
    "avg_precision_at_5",
    "avg_recall",
    "permission_violation_rate",
    "avg_context_docs",
    "avg_total_tokens",
    "avg_freshness_score",
    "avg_blocked_count",
    "avg_stale_count",
    "avg_dropped_count",
    "avg_budget_utilization",
}


def test_evals_returns_200():
    resp = client.get("/evals")
    assert resp.status_code == 200
    data = resp.json()
    assert "per_query" in data
    assert "aggregate" in data


def test_evals_has_aggregate_keys():
    data = client.get("/evals").json()
    actual_keys = set(data["aggregate"].keys())
    assert _EXPECTED_AGGREGATE_KEYS.issubset(actual_keys), (
        f"Missing aggregate keys: {_EXPECTED_AGGREGATE_KEYS - actual_keys}"
    )


def test_evals_has_twelve_queries():
    data = client.get("/evals").json()
    assert len(data["per_query"]) == 12


def test_evals_no_permission_violations():
    data = client.get("/evals").json()
    for r in data["per_query"]:
        if "error" in r:
            continue  # skip error records — they have no permission_violations key
        assert r.get("permission_violations") == [], (
            f"Query {r['id']} has permission violations: {r.get('permission_violations')}"
        )


def test_evals_per_query_has_required_keys():
    data = client.get("/evals").json()
    required = {"id", "role", "precision_at_5", "recall", "permission_violations"}
    for r in data["per_query"]:
        if "error" in r:
            continue  # error records only have id, query, role, error
        missing = required - set(r.keys())
        assert not missing, f"Query {r.get('id')} missing keys: {missing}"


def test_evals_caching_returns_identical_results():
    resp1 = client.get("/evals")
    resp2 = client.get("/evals")
    assert resp1.json() == resp2.json()


# ── /session-audit endpoint tests ──

def test_session_audit_returns_200(reset_session_audit):
    resp = client.get("/session-audit")
    assert resp.status_code == 200
    data = resp.json()
    assert "session_started_at" in data
    assert "benchmark_count" in data
    assert "entries" in data


def test_session_audit_benchmark_count(reset_session_audit):
    data = client.get("/session-audit").json()
    assert data["benchmark_count"] == 12


def test_session_audit_id_starts_after_benchmark(reset_session_audit):
    client.post("/query", json={"query": "test audit id", "role": "analyst"})
    entries = client.get("/session-audit").json()["entries"]
    assert len(entries) == 1
    assert entries[0]["id"] == "q013"


def test_session_audit_id_increments(reset_session_audit):
    client.post("/query", json={"query": "first query", "role": "analyst"})
    client.post("/query", json={"query": "second query", "role": "vp"})
    entries = client.get("/session-audit").json()["entries"]
    assert len(entries) == 2
    assert entries[0]["id"] == "q013"
    assert entries[1]["id"] == "q014"


def test_session_audit_query_appends_one_entry(reset_session_audit):
    before = len(client.get("/session-audit").json()["entries"])
    client.post("/query", json={"query": "append test", "role": "analyst"})
    after = len(client.get("/session-audit").json()["entries"])
    assert after - before == 1


def test_session_audit_compare_does_not_append(reset_session_audit):
    before = len(client.get("/session-audit").json()["entries"])
    client.post("/compare", json={"query": "compare test", "role": "analyst"})
    after = len(client.get("/session-audit").json()["entries"])
    assert after == before


def test_session_audit_evals_does_not_append(reset_session_audit):
    before = len(client.get("/session-audit").json()["entries"])
    client.get("/evals")
    after = len(client.get("/session-audit").json()["entries"])
    assert after == before


def test_session_audit_entry_shape(reset_session_audit):
    client.post("/query", json={"query": "shape test", "role": "vp", "policy_name": "full_policy"})
    entry = client.get("/session-audit").json()["entries"][0]
    assert entry["id"] == "q013"
    assert "created_at" in entry
    assert entry["query"] == "shape test"
    assert entry["role"] == "vp"
    assert entry["policy_name"] == "full_policy"
    assert "metrics" in entry
    m = entry["metrics"]
    for key in ("included_count", "total_tokens", "avg_score", "avg_freshness_score",
                "blocked_count", "stale_count", "dropped_count", "budget_utilization"):
        assert key in m, f"Missing metrics key: {key}"
    assert "doc_ids" in entry
    for key in ("included", "blocked", "stale", "dropped"):
        assert key in entry["doc_ids"], f"Missing doc_ids key: {key}"


def test_session_audit_live_entries_have_null_precision_recall(reset_session_audit):
    client.post("/query", json={"query": "null check", "role": "analyst"})
    entry = client.get("/session-audit").json()["entries"][0]
    assert entry["precision_at_5"] is None
    assert entry["recall"] is None
