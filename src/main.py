"""
main.py — FastAPI application entry point for QueryTrace.

Minimal HTTP boundary: validates the request, resolves dependencies,
delegates to the pipeline, and maps the result to the API response.
No pipeline business logic lives here.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src import auth, jobs
from src.models import (
    AskResponse,
    BlockedSummary,
    QueryRequest,
    QueryResponse,
    DocumentChunk,
    CompareRequest,
    CompareResponse,
    IngestAccepted,
    IngestJobStatus,
    LoginRequest,
)
from src.pipeline import run_pipeline, PipelineError
from src.workspaces import (
    InvalidWorkspaceSlug,
    Workspace,
    WorkspaceNotFound,
    default_workspace,
    get_workspace,
    list_workspaces,
)

app = FastAPI(title="QueryTrace", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_frontend_cache(request: Request, call_next):
    """Avoid stale frontend bundles after deploys on long-lived browser tabs."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/app"):
        response.headers["Cache-Control"] = "no-store"
    return response

# Fase 2: roles/metadata/users are resolved per request through the
# workspace resolver (corpora/<slug>/) — no module-level corpus state.
# Requests that do not name a workspace use the default one.

_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

# /evals cache, one entry per workspace slug. Cleared per slug after ingest.
_evals_cache: Dict[str, dict] = {}

_logger = logging.getLogger(__name__)

# Session audit — in-memory store for live /query calls (q013+).
# Resets on process restart. Globally shared across all demo visitors;
# entries carry their workspace slug.
_session_audit: List[dict] = []
_session_audit_lock = threading.Lock()
_session_started_at: str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _benchmark_count() -> int:
    """Audit ids continue after the default workspace's benchmark (q013+)."""
    with open(get_workspace().evals_path) as f:
        return len(json.load(f)["queries"])

_BENCHMARK_COUNT: int = _benchmark_count()


def _ingest_enabled() -> bool:
    """Ingest is enabled unless ALLOW_INGEST is explicitly 'false' or '0'.

    Kill-switch only (defense in depth) — since Fase P, /ingest additionally
    requires an admin session, so public deploys can leave this on.
    """
    return os.getenv("ALLOW_INGEST", "true").strip().lower() not in {"false", "0"}


# ── Workspace resolution at the API edge (Fase 2) ──────────────────────────


def _workspace_or_http(slug: Optional[str]) -> Workspace:
    """Resolve a workspace slug, mapping resolver errors to HTTP codes.

    Malformed slug (traversal, uppercase, empty) → 400; well-formed but
    unknown → 404. Validation happens before any filesystem access.
    """
    try:
        return get_workspace(slug)
    except InvalidWorkspaceSlug as e:
        raise HTTPException(status_code=400, detail=str(e))
    except WorkspaceNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


def _session_workspace_slug(session: Optional[dict]) -> Optional[str]:
    """The workspace a session is bound to (pre-Fase-2 cookies → default)."""
    if session is None:
        return None
    return session.get("workspace") or default_workspace()


def _resolve_request_workspace(
    requested: Optional[str], session: Optional[dict]
) -> Workspace:
    """Resolve the workspace a request targets, honoring session binding.

    A session belongs to exactly one workspace: an explicit request workspace
    that contradicts it → 403 (never a silent role remap across corpora).
    Absent → the session's workspace. Guests: requested slug or the default.
    """
    if session is not None:
        bound = _session_workspace_slug(session)
        if requested is not None and requested != bound:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Your session belongs to workspace {bound!r}; "
                    f"sign out (or sign in there) to use workspace {requested!r}."
                ),
            )
        return _workspace_or_http(bound)
    return _workspace_or_http(requested)


# ── Session auth (Fase P) ──────────────────────────────────────────────────


def _blocked_disclosure(ws: Workspace) -> str:
    """How much non-admin product sessions learn about blocked docs.

    "count" (default): count + required roles only. "titles": full detail.
    The knob lives in the workspace manifest (Fase 2); the BLOCKED_DISCLOSURE
    env var, when set, overrides it (ops escape hatch, read per-request).
    """
    value = os.getenv("BLOCKED_DISCLOSURE", "").strip().lower()
    if value in {"count", "titles"}:
        return value
    manifest_value = str(ws.manifest.get("blocked_disclosure", "count")).strip().lower()
    return manifest_value if manifest_value in {"count", "titles"} else "count"


def _get_session(http_request: Request) -> Optional[dict]:
    """Return the verified session payload from the cookie, or None (guest)."""
    token = http_request.cookies.get(auth.SESSION_COOKIE, "")
    if not token:
        return None
    return auth.verify_session_token(token, auth.get_secret_key())


def _apply_session_to_request(request, session):
    """Derive role (and policy, for non-admins) from the session.

    - An explicit body `role` that contradicts the session → 400 (early error
      beats silent override). Absent → the session role is used.
    - Non-admin product sessions always run `full_policy`; the policy selector
      is a lab instrument. An explicit conflicting `policy_name` → 400.
    Guests (no session) keep the current lab behavior untouched.
    (Workspace binding is handled by _resolve_request_workspace.)
    """
    if session is None:
        return request
    if "role" in request.model_fields_set and request.role != session["role"]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"role is derived from your session ({session['role']!r}); "
                f"remove the conflicting role field ({request.role!r}) from the request"
            ),
        )
    updates = {"role": session["role"]}
    if not session["is_admin"]:
        if (
            "policy_name" in request.model_fields_set
            and request.policy_name not in ("default", "full_policy")
        ):
            raise HTTPException(
                status_code=400,
                detail="policy is fixed to full_policy for product sessions",
            )
        updates["policy_name"] = "full_policy"
    return request.model_copy(update=updates)


def _redact_trace_for_viewer(trace, session, ws: Workspace):
    """Server-side blocked-docs redaction (P.4).

    Non-admin sessions with disclosure=count get {count, required_roles}
    instead of the full blocked list — enforced at the API edge so curl reveals
    nothing the UI hides. Guests (lab) and admins receive the full trace.
    """
    if trace is None or session is None or session.get("is_admin"):
        return trace
    if _blocked_disclosure(ws) == "titles":
        return trace
    required = sorted({b.required_role for b in trace.blocked_by_permission})
    return trace.model_copy(update={
        "blocked_by_permission": [],
        "blocked_summary": BlockedSummary(
            # Deduped to parent documents: blocked entries are per-chunk
            # (Fase 5 Etapa B) and "N documents withheld" must count docs.
            count=len({b.doc_id for b in trace.blocked_by_permission}),
            required_roles=required,
        ),
    })


def _to_chunks(included) -> List[DocumentChunk]:
    """Map pipeline IncludedDocuments to API DocumentChunks (shared by
    /query, /compare and /ask)."""
    return [
        DocumentChunk(
            doc_id=inc.doc_id,
            content=inc.content,
            score=inc.score,
            freshness_score=inc.freshness_score,
            tags=inc.tags,
            title=inc.title,
            doc_type=inc.doc_type,
            date=inc.date,
            superseded_by=inc.superseded_by,
            chunk_id=inc.chunk_id,
            chunk_index=inc.chunk_index,
            chunk_count=inc.chunk_count,
        )
        for inc in included
    ]


def _unique_doc_ids(entries) -> List[str]:
    """Unique parent doc_ids in first-seen order (chunk entries → doc view)."""
    return list(dict.fromkeys(e.doc_id for e in entries))


def _client_ip(http_request: Request) -> str:
    """Client IP for rate limiting; honors X-Forwarded-For behind a proxy."""
    forwarded = http_request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return http_request.client.host if http_request.client else "unknown"


def prepare_ingest(*args, **kwargs):
    """Lazy proxy so /ingest can be monkeypatched without import-time cost."""
    from src.ingest import prepare_ingest as _prepare_ingest

    return _prepare_ingest(*args, **kwargs)


def finalize_ingest(*args, **kwargs):
    """Lazy proxy for the job-side half of the ingest."""
    from src.ingest import finalize_ingest as _finalize_ingest

    return _finalize_ingest(*args, **kwargs)


def invalidate_caches(workspace: Optional[str] = None) -> None:
    """Lazy proxy for retriever cache reset used after ingest."""
    from src.retriever import invalidate_caches as _invalidate_caches

    _invalidate_caches(workspace)


@app.get("/health")
def health():
    from src.ask import ask_enabled

    return {
        "status": "ok",
        "ingest_enabled": _ingest_enabled(),
        "ask_enabled": ask_enabled(),
        "default_workspace": default_workspace(),
    }


# ── Auth endpoints (Fase P; workspace-bound since Fase 2) ───────────────────

@app.post("/login")
def login(body: LoginRequest, http_request: Request, response: Response):
    """Verify demo credentials against one workspace's personas.

    The session cookie is bound to that workspace: using it against another
    workspace returns 403 (see _resolve_request_workspace).
    """
    client_ip = http_request.client.host if http_request.client else "unknown"
    if not auth.allow_login_attempt(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts; wait a minute.")

    ws = _workspace_or_http(body.workspace)
    user = auth.verify_credentials(ws.users, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = auth.create_session_token(user, auth.get_secret_key(), workspace=ws.slug)
    response.set_cookie(
        auth.SESSION_COOKIE,
        token,
        max_age=auth.SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return {
        "username": user["username"],
        "name": user["name"],
        "role": user["role"],
        "is_admin": bool(user.get("is_admin", False)),
        "workspace": ws.slug,
    }


@app.get("/me")
def me(http_request: Request):
    """Current session identity, or 401 for guests."""
    session = _get_session(http_request)
    if session is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return {
        "username": session["username"],
        "name": session["name"],
        "role": session["role"],
        "is_admin": session["is_admin"],
        "workspace": _session_workspace_slug(session),
    }


@app.post("/logout")
def logout(response: Response):
    response.delete_cookie(auth.SESSION_COOKIE)
    return {"status": "ok"}


def _persona_cards(ws: Workspace) -> List[dict]:
    """Login-screen persona cards for one workspace (no password hashes)."""
    total = len(ws.metadata["documents"])
    cards = []
    for user in ws.users.values():
        rank = ws.roles[user["role"]]["access_rank"]
        visible = sum(
            1 for d in ws.metadata["documents"]
            if ws.roles.get(d["min_role"], {}).get("access_rank", 10**9) <= rank
        )
        cards.append({
            "username": user["username"],
            "name": user["name"],
            "role": user["role"],
            "is_admin": bool(user.get("is_admin", False)),
            "password_hint": user.get("password_hint", ""),
            "docs_visible": visible,
            "total_docs": total,
        })
    return cards


@app.get("/personas")
def personas(workspace: Optional[str] = None):
    """Public persona cards for the login screen (per workspace).

    Demo passwords are intentionally exposed (password_hint) — fictitious
    accounts over fictitious data; the login screen and README publish them.
    """
    ws = _workspace_or_http(workspace)
    return {"workspace": ws.slug, "personas": _persona_cards(ws)}


# ── Workspace endpoints (Fase 2) ────────────────────────────────────────────

@app.get("/workspaces")
def workspaces_index():
    """All available workspaces (slug, name, description, doc_count)."""
    return {"workspaces": list_workspaces(), "default": default_workspace()}


@app.get("/workspaces/{slug}/meta")
def workspace_meta(slug: str):
    """Everything the frontend needs to render one workspace.

    Roles carry computed docs_visible counts (from metadata, not hardcoded);
    scenarios/example_queries/placeholders come from the manifest; personas
    match /personas (no password hashes).
    """
    ws = _workspace_or_http(slug)
    role_hints = ws.manifest.get("role_hints", {})
    roles = [
        {
            "name": name,
            "access_rank": role["access_rank"],
            "description": role.get("description", ""),
            "hint": role_hints.get(name, ""),
            "docs_visible": sum(
                1 for d in ws.metadata["documents"]
                if ws.roles.get(d["min_role"], {}).get("access_rank", 10**9)
                <= role["access_rank"]
            ),
        }
        for name, role in sorted(
            ws.roles.items(), key=lambda item: item[1]["access_rank"]
        )
    ]
    return {
        "slug": ws.slug,
        "name": ws.manifest.get("name", ws.slug),
        "description": ws.manifest.get("description", ""),
        "total_docs": len(ws.metadata["documents"]),
        "doc_types": ws.manifest.get("doc_types", []),
        "roles": roles,
        "scenarios": ws.manifest.get("scenarios", []),
        "example_queries": ws.manifest.get("example_queries", []),
        "search_placeholder": ws.manifest.get("search_placeholder", ""),
        "empty_state_description": ws.manifest.get("empty_state_description", ""),
        "personas": _persona_cards(ws),
    }


@app.get("/", include_in_schema=False)
def root():
    """Redirect the service root to the static app UI."""
    return RedirectResponse(url="/app", status_code=307)


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, http_request: Request):
    from functools import partial

    from src.retriever import retrieve

    # Session (Fase P): role — and policy, for non-admins — derive from the
    # signed cookie. Guests keep the lab behavior (role from the body).
    # Workspace (Fase 2): sessions are bound to one workspace; guests pick any.
    session = _get_session(http_request)
    ws = _resolve_request_workspace(request.workspace, session)
    request = _apply_session_to_request(request, session)

    # Input validation — reject unknown roles before entering the pipeline
    if request.role not in ws.roles:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role: {request.role!r}. Valid roles: {list(ws.roles.keys())}",
        )

    # Delegate to the pipeline
    try:
        result = run_pipeline(
            request, partial(retrieve, workspace=ws.slug), ws.roles, ws.metadata
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PipelineError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed at '{e.stage}': {e.error}",
        )

    # Map PipelineResult → QueryResponse (API boundary)
    response = QueryResponse(
        query=request.query,
        context=_to_chunks(result.context),
        total_tokens=result.total_tokens,
        decision_trace=_redact_trace_for_viewer(result.trace, session, ws),
    )

    try:
        trace = result.trace
        if trace is not None:
            with _session_audit_lock:
                live_index = len(_session_audit) + 1
                qid = f"q{_BENCHMARK_COUNT + live_index:03d}"
                _session_audit.append({
                    "id": qid,
                    "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "user": session["username"] if session else None,
                    "workspace": ws.slug,
                    "query": request.query,
                    "role": request.role,
                    "policy_name": request.policy_name,
                    "precision_at_5": None,
                    "recall": None,
                    "metrics": {
                        # Doc-level counts (chunk entries deduped to parent
                        # docs, Fase 5 Etapa B) — matches the doc_ids arrays.
                        "included_count": trace.metrics.included_doc_count,
                        "total_tokens": trace.metrics.total_tokens,
                        "avg_score": trace.metrics.avg_score,
                        "avg_freshness_score": trace.metrics.avg_freshness_score,
                        "blocked_count": trace.metrics.blocked_doc_count,
                        "stale_count": trace.metrics.stale_doc_count,
                        "dropped_count": trace.metrics.dropped_doc_count,
                        "budget_utilization": trace.metrics.budget_utilization,
                    },
                    "doc_ids": {
                        # Deduped to parent documents (entries are per-chunk
                        # since Fase 5 Etapa B); order preserved.
                        "included": _unique_doc_ids(trace.included),
                        "blocked": _unique_doc_ids(trace.blocked_by_permission),
                        "stale": _unique_doc_ids(trace.demoted_as_stale),
                        "dropped": _unique_doc_ids(trace.dropped_by_budget),
                    },
                })
        else:
            _logger.warning("Skipping session audit: pipeline returned trace=None")
    except Exception:
        _logger.warning("Session audit logging failed", exc_info=True)

    return response


# Deliberately `def` (not `async def`): the model call is a blocking HTTP
# request (up to ~30s of timeout) — threadpool dispatch keeps the event loop
# responsive, same reasoning as /ingest.
@app.post("/ask", response_model=AskResponse)
def ask(request: QueryRequest, http_request: Request):
    """Grounded answer over the governed context (Fase 4 — Ask mode).

    Same request body and session rules as /query. The packed context goes
    to a Claude model; the answer returns with mechanically validated
    [doc_id] citations and the full decision trace — what the model saw
    (context) and what it never saw (blocked_by_permission) are auditable.

    Gate order: feature flag (403) → session/workspace/role (Fase P/2)
    → cache (replays are free) → rate limit (429) → pipeline → model (502).
    """
    from functools import partial

    from src import ask as ask_mod
    from src.retriever import retrieve

    if not ask_mod.ask_enabled():
        raise HTTPException(
            status_code=403,
            detail="Ask mode is disabled on this deployment (no model API key configured).",
        )

    session = _get_session(http_request)
    ws = _resolve_request_workspace(request.workspace, session)
    request = _apply_session_to_request(request, session)

    if request.role not in ws.roles:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role: {request.role!r}. Valid roles: {list(ws.roles.keys())}",
        )

    key = ask_mod.cache_key(
        ws.slug, request.query, request.role, request.policy_name, request.top_k
    )
    cached = ask_mod.cache_get(key)
    if cached is not None:
        return cached.model_copy(update={
            "cached": True,
            "decision_trace": _redact_trace_for_viewer(
                cached.decision_trace, session, ws
            ),
        })

    if not ask_mod.allow_ask(_client_ip(http_request)):
        raise HTTPException(
            status_code=429,
            detail=(
                f"Ask is limited to {ask_mod.max_per_minute()} model calls per "
                "minute per visitor; repeated queries are served from cache — "
                "please retry in a minute."
            ),
        )

    try:
        result = run_pipeline(
            request, partial(retrieve, workspace=ws.slug), ws.roles, ws.metadata
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PipelineError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed at '{e.stage}': {e.error}",
        )

    prompt_docs = ask_mod.trim_to_context_cap(result.context)
    system, user = ask_mod.build_prompt(request.query, prompt_docs)
    try:
        reply = ask_mod.call_model(system, user)
    except ask_mod.AskUpstreamError as e:
        raise HTTPException(status_code=502, detail=str(e))

    citations = ask_mod.extract_citations(
        reply.text, [d.doc_id for d in prompt_docs]
    )
    response = AskResponse(
        query=request.query,
        answer=reply.text,
        citations=citations,
        grounded_doc_count=ask_mod.grounded_doc_count(citations),
        model=reply.model,
        usage=reply.usage,
        cached=False,
        context=_to_chunks(result.context),
        total_tokens=result.total_tokens,
        decision_trace=result.trace,
    )
    ask_mod.cache_put(key, response)
    return response.model_copy(update={
        "decision_trace": _redact_trace_for_viewer(result.trace, session, ws),
    })


@app.post("/compare", response_model=CompareResponse)
def compare(request: CompareRequest, http_request: Request):
    """Run the same query through multiple policy presets side-by-side.

    Returns one QueryResponse per requested policy, keyed by policy name.
    Orchestrates existing run_pipeline() — no business logic duplication.
    Lab/guest and admin only: product sessions don't get the policy selector.
    """
    from functools import partial

    from src.retriever import retrieve

    session = _get_session(http_request)
    if session is not None and not session["is_admin"]:
        raise HTTPException(
            status_code=403,
            detail="Side-by-side comparison is a lab/admin tool, not available in product sessions.",
        )

    ws = _resolve_request_workspace(request.workspace, session)

    if request.role not in ws.roles:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role: {request.role!r}. Valid roles: {list(ws.roles.keys())}",
        )

    if not request.policies:
        raise HTTPException(status_code=400, detail="policies list must not be empty")

    retriever = partial(retrieve, workspace=ws.slug)
    results: dict = {}
    for policy_name in request.policies:
        query_req = QueryRequest(
            query=request.query,
            role=request.role,
            top_k=request.top_k,
            policy_name=policy_name,
            workspace=ws.slug,
        )
        try:
            result = run_pipeline(query_req, retriever, ws.roles, ws.metadata)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except PipelineError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Pipeline failed for policy '{policy_name}' at '{e.stage}': {e.error}",
            )

        results[policy_name] = QueryResponse(
            query=request.query,
            context=_to_chunks(result.context),
            total_tokens=result.total_tokens,
            decision_trace=result.trace,
        )

    return CompareResponse(query=request.query, role=request.role, results=results)


@app.get("/evals")
def evals(http_request: Request, workspace: Optional[str] = None):
    """Return cached evaluator results for one workspace (cached per slug).

    Lab/guest and admin only (see the Fase P capability table)."""
    session = _get_session(http_request)
    if session is not None and not session["is_admin"]:
        raise HTTPException(
            status_code=403,
            detail="Metrics are a lab/admin tool, not available in product sessions.",
        )
    ws = _resolve_request_workspace(workspace, session)
    if ws.slug not in _evals_cache:
        from src.evaluator import load_test_queries, run_evals

        queries = load_test_queries(ws.evals_path)
        _evals_cache[ws.slug] = run_evals(queries, k=5, top_k=8, workspace=ws.slug)
    return _evals_cache[ws.slug]


@app.get("/session-audit")
def session_audit(http_request: Request):
    """Return the in-memory session audit log (live queries since process start).

    Admin sessions see user attribution ("julia asked …"); the guest lab sees
    the anonymous version. Product (non-admin) sessions don't get the mode.
    """
    session = _get_session(http_request)
    if session is not None and not session["is_admin"]:
        raise HTTPException(
            status_code=403,
            detail="Session audit is a lab/admin tool, not available in product sessions.",
        )
    with _session_audit_lock:
        entries = list(_session_audit)
    if session is None or not session["is_admin"]:
        entries = [{**e, "user": None} for e in entries]
    return {
        "session_started_at": _session_started_at,
        "benchmark_count": _BENCHMARK_COUNT,
        "entries": entries,
    }


# Multipart framing + form fields ride alongside the file in the request
# body, so a Content-Length slightly above the file cap is legitimate.
_MULTIPART_OVERHEAD_BYTES = 64 * 1024


# Deliberately `def` (not `async def`): the synchronous half (extraction +
# dedup) still takes up to ~1s for a large PDF. As a plain function FastAPI
# dispatches it to the threadpool, so the event loop stays responsive. The
# heavy half (reindex) runs on the single-worker job executor (src/jobs.py).
@app.post("/ingest", response_model=IngestAccepted, status_code=202)
def ingest(
    http_request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    date: str = Form(...),
    min_role: str = Form(...),
    doc_type: str = Form(...),
    sensitivity: str = Form(...),
    tags: str = Form(""),
    workspace: str = Form(""),
):
    """Queue a document (.pdf/.txt/.md/.docx) for ingestion into one workspace.

    Accepts multipart/form-data. Everything cheap fails the request itself:
    auth (401/403), field validation (400), size caps (413), unsupported
    extension / magic-bytes mismatch (415), duplicate content (409). On
    success the request returns **202 + job_id** and the heavy half (persist
    + full FAISS/BM25 reindex) runs on the single-worker job executor —
    poll GET /ingest/jobs/{job_id} for queued → extracting → embedding →
    indexing → done|failed. A failed job rolls back its .txt and metadata
    entry (no orphans).
    """
    from src.ingest import (
        MAX_UPLOAD_BYTES,
        SUPPORTED_EXTENSIONS,
        IngestError,
    )

    if not _ingest_enabled():
        raise HTTPException(
            status_code=403,
            detail="Ingest is disabled on this deployment.",
        )

    # Fase P: uploading requires an admin session (this replaces the old
    # INGEST_API_KEY plan; ALLOW_INGEST above stays as an env kill-switch).
    session = _get_session(http_request)
    if session is None:
        raise HTTPException(status_code=401, detail="Sign in as an admin to upload documents.")
    if not session["is_admin"]:
        raise HTTPException(status_code=403, detail="Uploading requires an admin account.")

    # Fase 2: the admin session must belong to the target workspace.
    ws = _resolve_request_workspace(workspace.strip() or None, session)

    # Cheap rejection before touching the body: a declared 2 GB request never
    # gets its file read. (Starlette has already spooled the multipart to a
    # temp file by now, but we still skip buffering it into RAM.)
    content_length = http_request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > MAX_UPLOAD_BYTES + _MULTIPART_OVERHEAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Request body exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.",
        )

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type {ext or '(none)'!r}; "
                   f"expected one of {', '.join(SUPPORTED_EXTENSIONS)}.",
        )

    # Chunked read with a hard cap: stop buffering the moment the file passes
    # the limit instead of loading it whole and measuring afterwards.
    chunks = []
    total = 0
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB size limit.",
            )
        chunks.append(chunk)
    file_bytes = b"".join(chunks)
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

    try:
        prepared = prepare_ingest(
            file_bytes=file_bytes,
            title=title,
            date=date,
            min_role=min_role,
            doc_type=doc_type,
            sensitivity=sensitivity,
            tags=tag_list,
            workspace=ws,
            filename=file.filename or f"upload{ext}",
        )
    except IngestError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Corpus layout error: {e}")

    job = jobs.get_store().create(ws.slug)
    job_id = job["id"]

    def _run_ingest_job():
        store = jobs.get_store()
        store.update(job_id, state="extracting")
        try:
            entry = finalize_ingest(
                prepared,
                on_stage=lambda stage: store.update(job_id, state=stage),
            )
        except IngestError as e:
            store.update(
                job_id, state="failed",
                error={"status_code": e.status_code, "detail": str(e)},
            )
            return
        except Exception as e:
            store.update(
                job_id, state="failed",
                error={"status_code": 500, "detail": f"Ingest failed: {e}"},
            )
            return

        invalidate_caches(ws.slug)
        _evals_cache.pop(ws.slug, None)

        # The resolver cache was invalidated by finalize_ingest; this
        # re-resolve loads the post-ingest metadata.
        total_documents = len(get_workspace(ws.slug).metadata["documents"])
        store.update(
            job_id, state="done",
            result={
                "status": "ok",
                "doc_id": entry["id"],
                "title": entry["title"],
                "file_name": entry["file_name"],
                "type": entry["type"],
                "date": entry["date"],
                "min_role": entry["min_role"],
                "sensitivity": entry["sensitivity"],
                "tags": entry["tags"],
                "total_documents": total_documents,
            },
        )

    jobs.submit(_run_ingest_job)
    return IngestAccepted(job_id=job_id, state="queued", workspace=ws.slug)


def _require_admin_session(http_request: Request) -> dict:
    """Shared gate for the ingest job endpoints: admin session or 401/403."""
    if not _ingest_enabled():
        raise HTTPException(
            status_code=403, detail="Ingest is disabled on this deployment."
        )
    session = _get_session(http_request)
    if session is None:
        raise HTTPException(status_code=401, detail="Sign in as an admin to view ingest jobs.")
    if not session["is_admin"]:
        raise HTTPException(status_code=403, detail="Ingest jobs require an admin account.")
    return session


@app.get("/ingest/jobs", response_model=List[IngestJobStatus])
def ingest_jobs_index(http_request: Request):
    """Ingest jobs for the admin session's workspace, newest first."""
    session = _require_admin_session(http_request)
    ws = _resolve_request_workspace(None, session)
    return jobs.get_store().list(workspace=ws.slug)


@app.get("/ingest/jobs/{job_id}", response_model=IngestJobStatus)
def ingest_job_status(job_id: str, http_request: Request):
    """One ingest job's progress. 404 once it ages out of retention."""
    session = _require_admin_session(http_request)
    ws = _resolve_request_workspace(None, session)
    job = jobs.get_store().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job id.")
    # Fase 2 semantics: sessions see only their own workspace's jobs.
    if job["workspace"] != ws.slug:
        raise HTTPException(
            status_code=403,
            detail="This job belongs to a different workspace.",
        )
    return job


# Mount the static frontend last so JSON routes above are not shadowed.
# Served at /app/ (Starlette's StaticFiles with html=True falls back to index.html
# for directory requests). Same-origin serving means the frontend's API_BASE
# can be an empty string in production — no CORS preflight required.
app.mount("/app", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
