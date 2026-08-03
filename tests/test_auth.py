"""Tests for Fase P — session auth, server-derived role, trace redaction,
per-session capabilities, and audit attribution."""

import pytest
from fastapi.testclient import TestClient

import src.main as _main_module
from src import auth
from src.main import app


# ---------------------------------------------------------------------------
# Unit: token signing / verification
# ---------------------------------------------------------------------------

_USER = {"username": "julia", "name": "Julia Ferreyra", "role": "analyst", "is_admin": False}
_SECRET = "test-secret"


def test_token_roundtrip():
    token = auth.create_session_token(_USER, _SECRET)
    payload = auth.verify_session_token(token, _SECRET)
    assert payload is not None
    assert payload["username"] == "julia"
    assert payload["role"] == "analyst"
    assert payload["is_admin"] is False


def test_token_tampering_returns_none_never_raises():
    token = auth.create_session_token(_USER, _SECRET)
    payload_part, sig = token.split(".", 1)
    # Forge a partner role by rebuilding the payload with the same signature
    forged = auth._b64e(
        auth._b64d(payload_part).replace(b'"analyst"', b'"partner"')
    ) + "." + sig
    assert auth.verify_session_token(forged, _SECRET) is None


def test_token_wrong_secret_rejected():
    token = auth.create_session_token(_USER, "secret-a")
    assert auth.verify_session_token(token, "secret-b") is None


def test_token_expiry():
    token = auth.create_session_token(_USER, _SECRET, now=1000.0)
    assert auth.verify_session_token(token, _SECRET, now=1000.0 + auth.SESSION_TTL_SECONDS + 1) is None
    assert auth.verify_session_token(token, _SECRET, now=1000.0 + 10) is not None


@pytest.mark.parametrize("garbage", ["", "abc", "a.b", "!!.!!", "x" * 500])
def test_token_garbage_returns_none(garbage):
    assert auth.verify_session_token(garbage, _SECRET) is None


def test_rate_limiter_blocks_after_limit():
    auth.reset_rate_limiter()
    for _ in range(auth.LOGIN_RATE_LIMIT):
        assert auth.allow_login_attempt("1.2.3.4", now=100.0) is True
    assert auth.allow_login_attempt("1.2.3.4", now=100.0) is False
    # A different IP is unaffected; the window eventually clears
    assert auth.allow_login_attempt("5.6.7.8", now=100.0) is True
    assert auth.allow_login_attempt("1.2.3.4", now=100.0 + auth.LOGIN_RATE_WINDOW_SECONDS + 1) is True
    auth.reset_rate_limiter()


# ---------------------------------------------------------------------------
# Endpoint fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    auth.reset_rate_limiter()
    c = TestClient(app)
    yield c
    auth.reset_rate_limiter()


def _login(c, username, password):
    return c.post("/login", json={"username": username, "password": password})


@pytest.fixture()
def julia_client(client):
    assert _login(client, "julia", "demo-analyst").status_code == 200
    return client


@pytest.fixture()
def admin_client(client):
    assert _login(client, "patricia", "demo-admin").status_code == 200
    return client


# ---------------------------------------------------------------------------
# /login, /me, /logout, /personas
# ---------------------------------------------------------------------------

def test_login_ok_sets_cookie_and_identity(client):
    resp = _login(client, "victoria", "demo-vp")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "username": "victoria",
        "name": "Victoria Sosa",
        "role": "vp",
        "is_admin": False,
        "workspace": "pe-deal",  # sessions are workspace-bound since Fase 2
    }
    assert auth.SESSION_COOKIE in resp.cookies


def test_login_bad_password_401(client):
    assert _login(client, "julia", "wrong").status_code == 401


def test_login_unknown_user_401(client):
    assert _login(client, "nobody", "demo-analyst").status_code == 401


def test_login_rate_limited_429(client):
    for _ in range(auth.LOGIN_RATE_LIMIT):
        _login(client, "julia", "wrong")
    assert _login(client, "julia", "demo-analyst").status_code == 429


def test_me_without_cookie_401(client):
    assert client.get("/me").status_code == 401


def test_me_with_session(julia_client):
    body = julia_client.get("/me").json()
    assert body["username"] == "julia"
    assert body["role"] == "analyst"
    assert body["is_admin"] is False


def test_logout_clears_session(julia_client):
    assert julia_client.get("/me").status_code == 200
    julia_client.post("/logout")
    assert julia_client.get("/me").status_code == 401


def test_tampered_cookie_is_401_not_500(client):
    client.cookies.set(auth.SESSION_COOKIE, "forged.garbage")
    assert client.get("/me").status_code == 401


def test_personas_shape_and_visibility(client):
    body = client.get("/personas").json()
    cards = {p["username"]: p for p in body["personas"]}
    assert set(cards) == {"julia", "victoria", "patricia"}
    assert cards["julia"]["docs_visible"] == 6
    assert cards["victoria"]["docs_visible"] == 12
    assert cards["patricia"]["docs_visible"] == 16
    assert cards["patricia"]["is_admin"] is True
    for p in cards.values():
        assert p["total_docs"] == 16
        assert p["password_hint"]  # deliberately public demo credentials
        assert "password_sha256" not in p


# ---------------------------------------------------------------------------
# P.3 — server-derived role
# ---------------------------------------------------------------------------

def test_session_role_conflict_400(julia_client):
    """THE key test of the phase: analyst session asserting partner → 400."""
    resp = julia_client.post("/query", json={"query": "IC memo deal terms", "role": "partner"})
    assert resp.status_code == 400
    assert "session" in resp.json()["detail"]


def test_session_role_derived_when_absent(julia_client):
    resp = julia_client.post("/query", json={"query": "investment committee memo deal terms", "top_k": 12})
    assert resp.status_code == 200
    trace = resp.json()["decision_trace"]
    assert trace["user_context"]["role"] == "analyst"
    doc_ids = [c["doc_id"] for c in resp.json()["context"]]
    assert "doc_010" not in doc_ids  # partner-only IC memo stays out


def test_session_role_matching_body_ok(julia_client):
    resp = julia_client.post("/query", json={"query": "ARR growth", "role": "analyst"})
    assert resp.status_code == 200


def test_session_policy_fixed_to_full(julia_client):
    resp = julia_client.post("/query", json={"query": "ARR growth", "policy_name": "naive_top_k"})
    assert resp.status_code == 400
    resp = julia_client.post("/query", json={"query": "ARR growth"})
    assert resp.json()["decision_trace"]["policy_config"]["name"] == "full_policy"


def test_admin_keeps_policy_selector(admin_client):
    resp = admin_client.post("/query", json={"query": "ARR growth", "policy_name": "naive_top_k"})
    assert resp.status_code == 200
    assert resp.json()["decision_trace"]["policy_config"]["name"] == "naive_top_k"


def test_guest_lab_unchanged(client):
    """No session → the lab keeps accepting role from the body."""
    resp = client.post("/query", json={"query": "IC memo", "role": "partner", "top_k": 12})
    assert resp.status_code == 200
    assert resp.json()["decision_trace"]["user_context"]["role"] == "partner"


# ---------------------------------------------------------------------------
# P.4 — trace redaction at the API edge
# ---------------------------------------------------------------------------

_WALL_QUERY = {"query": "investment committee memo deal terms LP update", "top_k": 12}


def test_non_admin_raw_json_has_no_blocked_doc_ids(julia_client):
    """Assert on the raw response, not the DOM: curl must not reveal titles."""
    resp = julia_client.post("/query", json=_WALL_QUERY)
    trace = resp.json()["decision_trace"]
    assert trace["blocked_by_permission"] == []
    summary = trace["blocked_summary"]
    assert summary["count"] > 0
    assert set(summary["required_roles"]) <= {"vp", "partner"}
    assert "doc_010" not in resp.text and "doc_011" not in resp.text


def test_admin_trace_is_never_redacted(admin_client):
    """Admin sessions get the unredacted trace (blocked_summary stays None)."""
    resp = admin_client.post("/query", json=_WALL_QUERY)
    assert resp.status_code == 200
    assert resp.json()["decision_trace"]["blocked_summary"] is None


def test_titles_knob_discloses_blocked_detail(client, monkeypatch):
    """BLOCKED_DISCLOSURE=titles turns off redaction for product sessions."""
    monkeypatch.setenv("BLOCKED_DISCLOSURE", "titles")
    auth.reset_rate_limiter()
    _login(client, "julia", "demo-analyst")
    resp = client.post("/query", json=_WALL_QUERY)
    trace = resp.json()["decision_trace"]
    assert len(trace["blocked_by_permission"]) > 0
    assert trace["blocked_summary"] is None


def test_guest_gets_full_blocked_detail(client):
    resp = client.post("/query", json={**_WALL_QUERY, "role": "analyst"})
    trace = resp.json()["decision_trace"]
    assert len(trace["blocked_by_permission"]) > 0
    assert trace["blocked_summary"] is None


# ---------------------------------------------------------------------------
# P.5 — capability gating
# ---------------------------------------------------------------------------

def test_compare_forbidden_for_product_session(julia_client):
    assert julia_client.post("/compare", json={"query": "x"}).status_code == 403


def test_evals_forbidden_for_product_session(julia_client):
    assert julia_client.get("/evals").status_code == 403


def test_session_audit_forbidden_for_product_session(julia_client):
    assert julia_client.get("/session-audit").status_code == 403


def test_compare_allowed_for_admin(admin_client):
    resp = admin_client.post("/compare", json={"query": "ARR growth"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Audit attribution
# ---------------------------------------------------------------------------

@pytest.fixture()
def reset_audit():
    with _main_module._session_audit_lock:
        _main_module._session_audit.clear()
    yield


def test_audit_attributes_user_for_admin_viewer(reset_audit, client):
    auth.reset_rate_limiter()
    _login(client, "julia", "demo-analyst")
    client.post("/query", json={"query": "attribution test"})
    client.post("/logout")
    _login(client, "patricia", "demo-admin")
    entries = client.get("/session-audit").json()["entries"]
    assert entries and entries[-1]["user"] == "julia"


def test_audit_anonymous_for_guest_viewer(reset_audit, client):
    auth.reset_rate_limiter()
    _login(client, "julia", "demo-analyst")
    client.post("/query", json={"query": "anon test"})
    client.post("/logout")
    entries = client.get("/session-audit").json()["entries"]
    assert entries and all(e["user"] is None for e in entries)


# ---------------------------------------------------------------------------
# /ingest gating
# ---------------------------------------------------------------------------

def test_ingest_requires_session_401(client):
    resp = client.post(
        "/ingest",
        data={"title": "x", "date": "2024-01-01", "min_role": "analyst",
              "doc_type": "research_note", "sensitivity": "low", "tags": ""},
        files={"file": ("x.pdf", b"%PDF-", "application/pdf")},
    )
    assert resp.status_code == 401


def test_ingest_requires_admin_403(julia_client):
    resp = julia_client.post(
        "/ingest",
        data={"title": "x", "date": "2024-01-01", "min_role": "analyst",
              "doc_type": "research_note", "sensitivity": "low", "tags": ""},
        files={"file": ("x.pdf", b"%PDF-", "application/pdf")},
    )
    assert resp.status_code == 403
