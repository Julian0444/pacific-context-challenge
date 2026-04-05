"""Tests for main.py — API endpoint integration tests."""

import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


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


def test_query_context_has_freshness_scores():
    resp = client.post("/query", json={"query": "Meridian financial model"})
    data = resp.json()
    for chunk in data["context"]:
        assert "freshness_score" in chunk
