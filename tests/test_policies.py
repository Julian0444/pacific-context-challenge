"""Tests for policies.py — role loading.

Permission filtering goes through src/stages/permission_filter.py
(filter_permissions), tested in tests/test_stages.py::TestPermissionFilter.
"""

import os
from src.policies import load_roles

ROLES_PATH = os.path.join(os.path.dirname(__file__), "..", "corpora", "pe-deal", "roles.json")


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
