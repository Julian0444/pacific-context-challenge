"""Tests for policies.py — role-based access control."""

import os
import pytest
from src.policies import load_roles, filter_by_role

ROLES_PATH = os.path.join(os.path.dirname(__file__), "..", "corpus", "roles.json")


def test_load_roles_returns_all_three_roles():
    roles = load_roles(ROLES_PATH)
    assert "analyst" in roles
    assert "vp" in roles
    assert "partner" in roles


def test_load_roles_has_access_rank():
    roles = load_roles(ROLES_PATH)
    assert roles["analyst"]["access_rank"] == 1
    assert roles["vp"]["access_rank"] == 2
    assert roles["partner"]["access_rank"] == 3


def _make_chunk(doc_id, min_role):
    """Helper to build a minimal retrieval result dict."""
    return {
        "doc_id": doc_id,
        "min_role": min_role,
        "score": 0.9,
        "title": f"Doc {doc_id}",
        "excerpt": "...",
    }


@pytest.fixture
def roles():
    return load_roles(ROLES_PATH)


def test_analyst_sees_only_analyst_docs(roles):
    chunks = [
        _make_chunk("d1", "analyst"),
        _make_chunk("d2", "vp"),
        _make_chunk("d3", "partner"),
    ]
    filtered = filter_by_role(chunks, "analyst", roles)
    assert [c["doc_id"] for c in filtered] == ["d1"]


def test_vp_sees_analyst_and_vp_docs(roles):
    chunks = [
        _make_chunk("d1", "analyst"),
        _make_chunk("d2", "vp"),
        _make_chunk("d3", "partner"),
    ]
    filtered = filter_by_role(chunks, "vp", roles)
    assert [c["doc_id"] for c in filtered] == ["d1", "d2"]


def test_partner_sees_all_docs(roles):
    chunks = [
        _make_chunk("d1", "analyst"),
        _make_chunk("d2", "vp"),
        _make_chunk("d3", "partner"),
    ]
    filtered = filter_by_role(chunks, "partner", roles)
    assert len(filtered) == 3


def test_unknown_role_raises(roles):
    chunks = [_make_chunk("d1", "analyst")]
    with pytest.raises(ValueError):
        filter_by_role(chunks, "viewer", roles)
