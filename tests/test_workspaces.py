"""Tests for src.workspaces — the multi-workspace resolver (Fase 2).

Slug validation is security-relevant: slugs are user input that gets joined
into filesystem paths, so traversal attempts must die before any I/O.
"""

import pytest

from src import workspaces
from src.workspaces import (
    InvalidWorkspaceSlug,
    Workspace,
    WorkspaceNotFound,
    default_workspace,
    get_workspace,
    invalidate_workspace_cache,
    list_workspaces,
    validate_slug,
)


# ---------------------------------------------------------------------------
# Slug validation (anti path-traversal gate)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("slug", [
    "pe-deal", "saas-internal", "a", "workspace-2", "x" * 40,
])
def test_validate_slug_accepts_wellformed(slug):
    assert validate_slug(slug) == slug


@pytest.mark.parametrize("slug", [
    "../pe-deal",          # traversal
    "..",                  # traversal
    "pe-deal/../secrets",  # traversal mid-path
    "pe_deal",             # underscore not allowed
    "PE-DEAL",             # uppercase not allowed
    "",                    # empty
    " ",                   # whitespace
    "pe deal",             # space
    "pe.deal",             # dot
    "/etc/passwd",         # absolute path
    "x" * 41,              # too long
])
def test_validate_slug_rejects_malicious_or_malformed(slug):
    with pytest.raises(InvalidWorkspaceSlug):
        validate_slug(slug)


def test_validate_slug_rejects_non_string():
    with pytest.raises(InvalidWorkspaceSlug):
        validate_slug(None)
    with pytest.raises(InvalidWorkspaceSlug):
        validate_slug(123)


def test_get_workspace_traversal_never_touches_filesystem(monkeypatch):
    """A traversal slug must fail in validation, before any path is built."""
    def boom(*args, **kwargs):
        raise AssertionError("filesystem was touched for an invalid slug")

    monkeypatch.setattr(workspaces.os.path, "isdir", boom)
    monkeypatch.setattr(workspaces.os.path, "exists", boom)
    with pytest.raises(InvalidWorkspaceSlug):
        get_workspace("../../etc")


# ---------------------------------------------------------------------------
# Resolution & caching
# ---------------------------------------------------------------------------

def test_default_workspace_is_pe_deal():
    assert default_workspace() == "pe-deal"


def test_default_workspace_env_override(monkeypatch):
    monkeypatch.setenv("QUERYTRACE_DEFAULT_WORKSPACE", "saas-internal")
    assert default_workspace() == "saas-internal"


def test_get_workspace_none_resolves_default():
    ws = get_workspace()
    assert ws.slug == "pe-deal"


def test_get_workspace_loads_pe_deal_completely():
    ws = get_workspace("pe-deal")
    assert isinstance(ws, Workspace)
    assert ws.manifest["slug"] == "pe-deal"
    assert set(ws.roles.keys()) == {"analyst", "vp", "partner"}
    assert len(ws.metadata["documents"]) >= 16
    assert "julia" in ws.users
    # Paths point into corpora/pe-deal and artifacts/pe-deal
    assert "corpora" in ws.metadata_path and "pe-deal" in ws.metadata_path
    assert "artifacts" in ws.index_path and "pe-deal" in ws.index_path


def test_get_workspace_unknown_slug_raises_not_found():
    with pytest.raises(WorkspaceNotFound):
        get_workspace("does-not-exist")


def test_get_workspace_is_cached():
    invalidate_workspace_cache("pe-deal")
    ws1 = get_workspace("pe-deal")
    ws2 = get_workspace("pe-deal")
    assert ws1 is ws2


def test_invalidate_workspace_cache_reloads():
    ws1 = get_workspace("pe-deal")
    invalidate_workspace_cache("pe-deal")
    ws2 = get_workspace("pe-deal")
    assert ws1 is not ws2
    assert ws1.slug == ws2.slug


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def test_list_workspaces_includes_pe_deal_with_doc_count():
    summaries = {w["slug"]: w for w in list_workspaces()}
    assert "pe-deal" in summaries
    pe = summaries["pe-deal"]
    assert pe["name"] == "Atlas Capital — PE Deal Room"
    assert pe["doc_count"] >= 16
    assert pe["description"]


def test_list_workspaces_entries_are_resolvable():
    for summary in list_workspaces():
        ws = get_workspace(summary["slug"])
        assert len(ws.metadata["documents"]) == summary["doc_count"]


# ---------------------------------------------------------------------------
# API: workspace endpoints + workspace param (Fase 2, tanda 2)
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from src import auth
    from src.main import app

    auth.reset_rate_limiter()
    c = TestClient(app)
    yield c
    auth.reset_rate_limiter()


def test_health_reports_default_workspace(client):
    body = client.get("/health").json()
    assert body["default_workspace"] == "pe-deal"


def test_workspaces_endpoint_lists_and_defaults(client):
    body = client.get("/workspaces").json()
    slugs = [w["slug"] for w in body["workspaces"]]
    assert "pe-deal" in slugs
    assert body["default"] == "pe-deal"
    for w in body["workspaces"]:
        assert {"slug", "name", "description", "doc_count"} <= set(w.keys())


def test_workspace_meta_shape_and_counts(client):
    body = client.get("/workspaces/pe-deal/meta").json()
    assert body["slug"] == "pe-deal"
    assert body["total_docs"] == 16
    roles = {r["name"]: r for r in body["roles"]}
    assert set(roles) == {"analyst", "vp", "partner"}
    # docs_visible computed from metadata — must match the persona counts
    assert roles["analyst"]["docs_visible"] == 6
    assert roles["vp"]["docs_visible"] == 12
    assert roles["partner"]["docs_visible"] == 16
    # roles sorted by access_rank
    assert [r["name"] for r in body["roles"]] == ["analyst", "vp", "partner"]
    assert len(body["scenarios"]) == 3
    assert len(body["example_queries"]) == 3
    assert body["doc_types"]  # non-empty, manifest-driven
    personas = {p["username"] for p in body["personas"]}
    assert personas == {"julia", "victoria", "patricia"}
    for p in body["personas"]:
        assert "password_sha256" not in p


def test_workspace_meta_unknown_slug_404(client):
    assert client.get("/workspaces/nope-nope/meta").status_code == 404


def test_workspace_meta_traversal_slug_rejected(client):
    # ".." as a path segment must never resolve; encoded form hits our 400
    assert client.get("/workspaces/%2e%2e/meta").status_code in (400, 404)
    assert client.get("/workspaces/UPPER/meta").status_code == 400


def test_query_with_explicit_default_workspace_matches_implicit(client):
    payload = {"query": "investment committee memo deal terms", "role": "analyst", "top_k": 12}
    implicit = client.post("/query", json=payload).json()
    explicit = client.post("/query", json={**payload, "workspace": "pe-deal"}).json()
    ids = lambda r: [c["doc_id"] for c in r["context"]]  # noqa: E731
    assert ids(implicit) == ids(explicit)
    assert implicit["total_tokens"] == explicit["total_tokens"]
    imp_blocked = [b["doc_id"] for b in implicit["decision_trace"]["blocked_by_permission"]]
    exp_blocked = [b["doc_id"] for b in explicit["decision_trace"]["blocked_by_permission"]]
    assert imp_blocked == exp_blocked


def test_query_invalid_workspace_slug_400(client):
    resp = client.post("/query", json={"query": "x", "workspace": "../etc"})
    assert resp.status_code == 400
    assert "Invalid workspace slug" in resp.json()["detail"]


def test_query_unknown_workspace_404(client):
    resp = client.post("/query", json={"query": "x", "workspace": "ghost-ws"})
    assert resp.status_code == 404


def test_compare_carries_workspace_param(client):
    resp = client.post("/compare", json={
        "query": "IC memo deal terms", "role": "partner", "workspace": "pe-deal",
    })
    assert resp.status_code == 200
    resp404 = client.post("/compare", json={"query": "x", "workspace": "ghost-ws"})
    assert resp404.status_code == 404


def test_login_binds_session_to_workspace(client):
    resp = client.post("/login", json={
        "username": "julia", "password": "demo-analyst", "workspace": "pe-deal",
    })
    assert resp.status_code == 200
    assert resp.json()["workspace"] == "pe-deal"
    me = client.get("/me").json()
    assert me["workspace"] == "pe-deal"


def test_login_without_workspace_binds_default(client):
    resp = client.post("/login", json={"username": "julia", "password": "demo-analyst"})
    assert resp.status_code == 200
    assert resp.json()["workspace"] == "pe-deal"


def test_session_used_against_other_workspace_403(client):
    """A session minted for another workspace must be rejected — never a
    silent role remap. (Minted directly so the test does not depend on a
    second corpus existing.)"""
    from src import auth

    user = {"username": "ghost", "name": "Ghost", "role": "analyst", "is_admin": True}
    token = auth.create_session_token(
        user, auth.get_secret_key(), workspace="another-workspace"
    )
    client.cookies.set(auth.SESSION_COOKIE, token)
    resp = client.post("/query", json={"query": "x", "workspace": "pe-deal"})
    assert resp.status_code == 403
    assert "another-workspace" in resp.json()["detail"]


def test_pre_fase2_cookie_without_workspace_still_works(client):
    """Cookies minted before Fase 2 (workspace=None) resolve to the default."""
    from src import auth

    user = {"username": "julia", "name": "Julia Ferreyra", "role": "analyst",
            "is_admin": False}
    token = auth.create_session_token(user, auth.get_secret_key())
    client.cookies.set(auth.SESSION_COOKIE, token)
    resp = client.post("/query", json={"query": "ARR growth"})
    assert resp.status_code == 200
    assert resp.json()["decision_trace"]["user_context"]["role"] == "analyst"


def test_personas_accepts_workspace_param(client):
    body = client.get("/personas", params={"workspace": "pe-deal"}).json()
    assert body["workspace"] == "pe-deal"
    assert {p["username"] for p in body["personas"]} == {"julia", "victoria", "patricia"}
    assert client.get("/personas", params={"workspace": "ghost-ws"}).status_code == 404


def test_evals_unknown_workspace_404(client):
    assert client.get("/evals", params={"workspace": "ghost-ws"}).status_code == 404


def test_session_audit_entries_carry_workspace(client):
    import src.main as main_mod

    with main_mod._session_audit_lock:
        main_mod._session_audit.clear()
    client.post("/query", json={"query": "workspace audit test", "role": "analyst"})
    entries = client.get("/session-audit").json()["entries"]
    assert entries and entries[-1]["workspace"] == "pe-deal"


# ---------------------------------------------------------------------------
# Fase 2, tanda 4 — second corpus (saas-internal) + isolation
# ---------------------------------------------------------------------------
# Note: doc ids (doc_001…) are per-workspace namespaces and collide across
# corpora by design, so isolation is asserted on titles/content, never on ids.

def _titles(slug):
    return {d["title"] for d in get_workspace(slug).metadata["documents"]}


def _trace_doc_ids(trace):
    ids = [d["doc_id"] for d in trace["included"]]
    ids += [d["doc_id"] for d in trace["blocked_by_permission"]]
    ids += [d["doc_id"] for d in trace["demoted_as_stale"]]
    ids += [d["doc_id"] for d in trace["dropped_by_budget"]]
    return ids


def test_saas_workspace_listed_and_resolvable():
    summaries = {w["slug"]: w for w in list_workspaces()}
    assert "saas-internal" in summaries
    assert summaries["saas-internal"]["doc_count"] == 14
    ws = get_workspace("saas-internal")
    assert set(ws.roles.keys()) == {"employee", "manager", "exec"}


def test_saas_meta_counts(client):
    body = client.get("/workspaces/saas-internal/meta").json()
    assert body["total_docs"] == 14
    roles = {r["name"]: r for r in body["roles"]}
    assert roles["employee"]["docs_visible"] == 6
    assert roles["manager"]["docs_visible"] == 10
    assert roles["exec"]["docs_visible"] == 14
    assert {p["username"] for p in body["personas"]} == {"sofia", "marcos", "alex"}
    assert len(body["scenarios"]) == 3


def test_isolation_saas_query_never_touches_pe_docs(client):
    """THE multi-tenancy test: a query in saas-internal must never surface
    pe-deal documents — in included, blocked, stale, or dropped — even when
    the query is a verbatim pe-deal topic and the policy is the naive one."""
    resp = client.post("/query", json={
        "query": "Meridian acquisition investment committee ARR growth deal terms",
        "role": "exec",
        "workspace": "saas-internal",
        "top_k": 14,
        "policy_name": "naive_top_k",
    })
    assert resp.status_code == 200
    data = resp.json()
    trace = data["decision_trace"]
    saas_titles = _titles("saas-internal")
    for chunk in data["context"]:
        assert chunk["title"] in saas_titles
    # Every trace bucket holds only saas doc ids (same namespace) and the
    # returned content/trace never mention the other corpus's entities.
    # (The request query is echoed back, so assert on context+trace, not text.)
    assert set(_trace_doc_ids(trace)) <= {
        d["id"] for d in get_workspace("saas-internal").metadata["documents"]
    }
    import json as _json

    payload = _json.dumps(data["context"]) + _json.dumps(trace)
    assert "Meridian" not in payload
    assert "Atlas Capital" not in payload


def test_isolation_pe_query_never_touches_saas_docs(client):
    resp = client.post("/query", json={
        "query": "Nimbus salary compensation bands on-call runbook helios-db outage",
        "role": "partner",
        "workspace": "pe-deal",
        "top_k": 16,
        "policy_name": "naive_top_k",
    })
    assert resp.status_code == 200
    data = resp.json()
    pe_titles = _titles("pe-deal")
    for chunk in data["context"]:
        assert chunk["title"] in pe_titles
    import json as _json

    payload = _json.dumps(data["context"]) + _json.dumps(data["decision_trace"])
    assert "Nimbus" not in payload
    assert "helios-db" not in payload


def test_roles_do_not_cross_workspaces(client):
    """pe-deal roles are invalid in saas-internal and vice versa — there is
    no silent role mapping between corpora."""
    r1 = client.post("/query", json={"query": "x", "role": "partner", "workspace": "saas-internal"})
    assert r1.status_code == 400
    assert "Unknown role" in r1.json()["detail"]
    r2 = client.post("/query", json={"query": "x", "role": "exec", "workspace": "pe-deal"})
    assert r2.status_code == 400


def test_cross_workspace_session_julia_cannot_query_saas(client):
    """A pe-deal cookie (julia) used against saas-internal → 403, with both
    corpora actually on disk (complements the minted-cookie test above)."""
    resp = client.post("/login", json={
        "username": "julia", "password": "demo-analyst", "workspace": "pe-deal",
    })
    assert resp.status_code == 200
    resp = client.post("/query", json={"query": "salary bands", "workspace": "saas-internal"})
    assert resp.status_code == 403
    assert "pe-deal" in resp.json()["detail"]


def test_cross_workspace_session_sofia_cannot_query_pe(client):
    resp = client.post("/login", json={
        "username": "sofia", "password": "demo-employee", "workspace": "saas-internal",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workspace"] == "saas-internal"
    assert body["role"] == "employee"
    # Her own workspace works…
    ok = client.post("/query", json={"query": "on-call escalation", "workspace": "saas-internal"})
    assert ok.status_code == 200
    # …the other one is forbidden.
    resp = client.post("/query", json={"query": "IC memo", "workspace": "pe-deal"})
    assert resp.status_code == 403


def test_saas_login_users_do_not_exist_in_pe(client):
    resp = client.post("/login", json={
        "username": "sofia", "password": "demo-employee", "workspace": "pe-deal",
    })
    assert resp.status_code == 401


def test_saas_employee_wall_blocks_comp_bands(client):
    """The saas permission-wall scenario: an employee asking for salary bands
    never receives the manager-level compensation documents."""
    resp = client.post("/query", json={
        "query": "engineering compensation bands salary ranges senior engineers",
        "role": "employee",
        "workspace": "saas-internal",
        "top_k": 8,
    })
    data = resp.json()
    comp_titles = {
        "Nimbus Analytics — Engineering Compensation Bands 2023",
        "Nimbus Analytics — Engineering Compensation Bands 2024",
    }
    included_titles = {c["title"] for c in data["context"]}
    assert not (included_titles & comp_titles)
    assert data["decision_trace"]["metrics"]["blocked_count"] > 0


def test_saas_stale_pairs_demoted(client):
    """All three saas superseded pairs demote under full_policy."""
    resp = client.post("/query", json={
        "query": "on-call runbook compensation bands product roadmap draft final",
        "role": "exec",
        "workspace": "saas-internal",
        "top_k": 14,
        "policy_name": "full_policy",
    })
    stale_ids = {s["doc_id"] for s in resp.json()["decision_trace"]["demoted_as_stale"]}
    assert {"doc_003", "doc_007", "doc_013"} <= stale_ids


# ---------------------------------------------------------------------------
# Evaluator per workspace (saas benchmark)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def saas_eval_results():
    from src.evaluator import load_test_queries, run_evals

    queries = load_test_queries(get_workspace("saas-internal").evals_path)
    return run_evals(queries, k=5, top_k=8, workspace="saas-internal")


def test_saas_evals_zero_violations_full_policy(saas_eval_results):
    agg = saas_eval_results["aggregate"]
    assert agg["queries_failed"] == 0
    assert agg["permission_violation_rate"] == 0.0


def test_saas_evals_recall_and_precision_floor(saas_eval_results):
    agg = saas_eval_results["aggregate"]
    assert agg["avg_recall"] == 1.0
    assert agg["avg_precision_at_5"] >= 0.20


def test_saas_evals_naive_baseline_leaks():
    from src.evaluator import load_test_queries, run_evals

    queries = load_test_queries(get_workspace("saas-internal").evals_path)
    naive = run_evals(queries, k=5, top_k=8, policy_name="naive_top_k",
                      workspace="saas-internal")
    assert naive["aggregate"]["permission_violation_rate"] > 0


def test_evals_endpoint_serves_saas_workspace(client):
    body = client.get("/evals", params={"workspace": "saas-internal"}).json()
    assert len(body["per_query"]) == 12
    assert body["aggregate"]["permission_violation_rate"] == 0.0


# ---------------------------------------------------------------------------
# Ingest vocabularies are workspace-scoped
# ---------------------------------------------------------------------------

def test_ingest_validation_uses_workspace_vocabularies():
    from src.ingest import IngestError, _validate_inputs

    saas = get_workspace("saas-internal")
    pe = get_workspace("pe-deal")

    def kwargs_for(ws):
        return {
            "valid_roles": ws.roles.keys(),
            "valid_doc_types": ws.manifest["doc_types"],
        }

    # "runbook"/"employee" are valid in saas-internal…
    _validate_inputs("t", "2024-01-01", "employee", "runbook", "low", **kwargs_for(saas))
    # …and invalid in pe-deal (and vice versa).
    with pytest.raises(IngestError):
        _validate_inputs("t", "2024-01-01", "employee", "runbook", "low", **kwargs_for(pe))
    with pytest.raises(IngestError):
        _validate_inputs("t", "2024-01-01", "analyst", "deal_memo", "low", **kwargs_for(saas))
    _validate_inputs("t", "2024-01-01", "analyst", "deal_memo", "low", **kwargs_for(pe))
