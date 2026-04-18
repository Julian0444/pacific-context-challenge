# NICE-B Execution Plan — IDEA 11 (Render-first Read-Only Deploy)

Date: 2026-04-17
Branch: `codex/must-a-idea1-2`
Scope: Make the full app (FastAPI backend + static frontend) deployable as a single read-only service. **Target host: Render** (Railway works from the same Procfile; Fly.io would need a Dockerfile and is out of scope). No business-logic changes. One production-gate env flag (`ALLOW_INGEST`). New `Procfile`, static mount at `/app`, environment-aware `API_BASE` in the frontend.

Preflight: tests 172 / 14 / 0. Working tree clean. Artifacts present and tracked. `requirements.txt` complete. No Procfile yet.

---

## Executive summary

IDEA 11 is a packaging pass, not a feature. Five deltas:
1. `src/main.py` mounts `frontend/` at `/app` via `StaticFiles`.
2. New `Procfile` at repo root for buildpack-based hosts.
3. `frontend/app.js` picks `API_BASE` by `window.location.hostname`.
4. `/ingest` is gated by `ALLOW_INGEST` env var (default enabled, set to `false` in prod).
5. Artifacts stay committed; `.gitignore` stays loose enough to let them in. The Admin tab in the UI degrades gracefully when ingest is off.

All edits are additive or defensive. No existing route path changes. No backend logic changes. Same-origin serving eliminates the CORS dependency for prod while preserving local `file://` → `localhost:8000` dev.

---

## 1. Missing / weak areas in the prompt

1. **`ALLOW_INGEST` semantics undefined.** Prompt says "disable in production with env var ALLOW_INGEST" but does not specify: default when unset, accepted truthy/falsy strings, read-at-startup vs read-at-request, failure mode (403 vs 404 vs 503), and whether the frontend Admin tab should be hidden. Decision: default **enabled** when unset (so `tests/test_ingest.py` — which uses `TestClient(app)` against `/ingest` — keeps passing without monkeypatching); disable only when the var is exactly `"false"` or `"0"` (case-insensitive); read per-request so tests and local dev don't need a restart; return `403 Forbidden` with a clear detail; frontend hides the Admin tab via a `GET /health` capability probe.
2. **Capability probe.** `GET /health` currently returns `{"status": "ok"}`. The frontend needs to know whether `/ingest` is allowed. Decision: extend `/health` to return `{"status": "ok", "ingest_enabled": bool}` and let the frontend hide the Admin mode button + `#admin-section` when `false`. Additive, backward-compatible.
3. **Static mount path collision.** `app.mount("/app", ...)` will not collide with any existing route (`/health`, `/query`, `/compare`, `/evals`, `/ingest`, `/docs`, `/openapi.json`). Decision: mount at `/app` as specified. The root path `/` is left unmounted — document that the demo URL is `http(s)://<host>/app/`.
4. **Trailing-slash behavior.** `StaticFiles(directory=..., html=True)` serves `index.html` only for `/app/` (with trailing slash). `/app` without slash redirects 307 on Starlette. Acceptable default; call out in CLAUDE.md so reviewers don't file it as a bug.
5. **`API_BASE` edge cases.** The prompt's one-liner treats only `localhost`. Does not cover `127.0.0.1`, LAN IPs, or `0.0.0.0`. Decision: extend the check to `hostname === 'localhost' || hostname === '127.0.0.1'` → `'http://localhost:8000'`; everything else → `''` (same-origin). No change for production.
6. **Host platform choice.** Prompt lists three hosts. No platform-specific config committed (no `railway.toml`, no `render.yaml`, no `fly.toml`). Decision: ship only the generic `Procfile`; add a one-paragraph deploy note to CLAUDE.md covering Railway (Procfile is native), Render (Procfile or Start Command), and Fly (needs its own Dockerfile — out of scope for this batch).
7. **Python runtime pin.** Railway auto-detects Python but may pick 3.12. MUST-D runs on 3.9.6 + LibreSSL with `tf-keras` as a workaround. Decision: add `.python-version` (or `runtime.txt` equivalent) pinning to `3.11.x` — the lowest-drama modern Python that avoids the `tf-keras` hack. Flag as optional if it balloons build time; fallback is to let the host pick and fix on red.
8. **Build image size.** `sentence-transformers` + `faiss-cpu` + `pdfplumber` (via `pdfminer.six`) + `tiktoken` ≈ 1.5–2 GB after install, plus the MiniLM weights (~90 MB) downloaded at first query. On Railway's free tier this is close to the memory ceiling. Out of scope for implementation but call out as a deploy risk.
9. **Model cold-start.** `sentence-transformers` lazy-loads MiniLM on the first query. First-query latency on cold container ≈ 3–8 s. Demo UX consideration only.
10. **Verification asks not itemized.** Only step 7 of the prompt is a verify line. See verification plan below.
11. **"Do not push sensitive files."** Prompt says so but lists no candidates. Scan for real risks: `.env`, `*.key`, `*.pem`, OS junk. None exist in-repo (checked: `corpus/`, `artifacts/`, `src/` are public demo data; no secret scanner needed but a pre-push grep is cheap).

---

## 2. Hidden serving / deploy / environment risks

### FastAPI / static serving
- **Route ordering.** `StaticFiles` must be mounted **after** `CORSMiddleware` is registered and **after** JSON API routes are declared so nothing shadows `/app/*`. Since `/app` doesn't collide with any existing path, order is cosmetic, but put the mount at the bottom of `main.py` to keep the import-time surface predictable.
- **Missing `frontend/` at runtime.** If the directory isn't shipped (e.g., added to `.dockerignore` by accident), FastAPI will raise at startup. Not a current risk — `frontend/` is tracked — but worth an acceptance check.
- **`html=True` redirects directory requests** to `index.html`. It also serves files with their declared MIME type by extension (good for `.js`, `.css`). No extra config needed.
- **CORS still needed in dev.** When the frontend is served from `file://` (local dev pattern used today), the `API_BASE=http://localhost:8000` fetch is cross-origin — the existing `allow_origins=["*"]` keeps dev working. Must not tighten CORS in this batch.

### API_BASE
- **Compare / Evals regression window.** Four `fetch(${API_BASE}/...)` call sites (app.js:205, 235, 701, 1121). The empty-string-for-prod pattern yields relative URLs like `/query` — these resolve against the page's origin, so on `http(s)://host/app/` they become `http(s)://host/query`. Correct.
- **Service workers / cache busters.** None exist; no concern.
- **Port drift in dev.** If the user runs uvicorn on a non-8000 port locally (e.g., `--port 8080`), the frontend at `file://` will still point to `:8000` and fail silently. Acceptable — matches today's behavior. Call out in CLAUDE.md.

### ALLOW_INGEST in read-only deploy
- **Test suite impact.** `tests/test_ingest.py` hits `/ingest` four times via `TestClient`. Default-enabled gating keeps the suite green. If `ALLOW_INGEST=false` is ever set in CI, the suite fails; call out in CLAUDE.md so CI config doesn't regress it.
- **Attack surface.** `/ingest` today has no RBAC; anyone who can reach the host can append to the corpus and trigger a ~10s reindex. Disabling it in prod is the whole point of this knob. Implementation must fail closed — default-enabled is a dev convenience, but the production environment explicitly sets `ALLOW_INGEST=false`.
- **Frontend degradation.** Admin tab hitting `/ingest` → `403` produces a confusing "server rejected upload" message. Mitigation: hide the tab entirely when `/health.ingest_enabled === false`.
- **Ingest tests with env set.** If a developer exports `ALLOW_INGEST=false` in their shell and runs pytest, tests fail. Acceptable — documented, not a real regression risk.

### Artifacts, `.gitignore`, sensitive files
- **`.gitignore` today** only excludes `artifacts/*.faiss|*.pkl|*.npy` — none of the three real artifacts match these patterns, so all three are correctly tracked. Verified via `git ls-files artifacts/`.
- **Runtime writes to `artifacts/`.** On a successful ingest, `src/indexer.build_and_save()` rewrites all three. On an ephemeral-fs host, those writes last only until restart — matches the ephemeral caveat that MUST-D already documented. When `ALLOW_INGEST=false`, no writes happen — the three committed artifacts are authoritative.
- **No secrets in repo.** Confirmed by scan: no `.env*`, no `*.pem|*.key`, no cloud credentials. The "don't push sensitive files" ask is a posture reminder, not a fix.
- **`corpus/documents/*.txt` and `corpus/metadata.json`** are committed at the 12-doc baseline. Ephemeral ingest writes won't persist in prod; with `ALLOW_INGEST=false` they won't be attempted. No action required.

### Deploy caveats introduced by MUST-D
- **Disk writes assume a writable repo path.** MUST-D's `ingest.py` writes to `corpus/documents/` and `artifacts/` via relative paths resolved from `__file__`. On a read-only container root (some hardened Railway images), writes will fail. With `ALLOW_INGEST=false` this never executes; call it out.
- **`pdfplumber` pulls `pdfminer.six`** (~10 MB). Install cost matters if Railway's build timeout is tight.
- **`_metadata` mutation at runtime.** MUST-D mutates an in-process Python list. With ingest disabled, the list is initialized once at startup from the committed `corpus/metadata.json` and never changes — deterministic and demo-safe.
- **`threading.Lock` around ingest critical section.** Moot with ingest off; present for dev parity.

### SHOULD-A onboarding
- **Three `.onboard-card` buttons** call into `runCompare()` → `fetch(${API_BASE}/compare)`. They must still work after the `API_BASE` rewrite. Verification covers this.
- **Empty-state renders before first fetch.** Independent of API_BASE resolution timing. No risk.

---

## 3. Verification gaps to close

The prompt's only verify line is step 7 (`uvicorn … → http://localhost:8000/app/`). Gaps that must be explicitly asserted:

- `GET /health` returns `ingest_enabled: true` locally; `false` when `ALLOW_INGEST=false`.
- `POST /ingest` returns 200 locally; returns 403 when `ALLOW_INGEST=false`.
- `tests/test_ingest.py` still passes (default-enabled).
- `GET /app/` serves `index.html`.
- `GET /app/app.js` serves JS with `Content-Type: application/javascript` (or `text/javascript`).
- Same-origin `POST /query` works when the page is loaded at `/app/` (i.e., `API_BASE === ''`).
- `file://` → `localhost:8000` still works locally (API_BASE falls back to absolute).
- Admin tab hidden when `/health.ingest_enabled === false`.
- All three onboard scenario buttons still fire Compare mode with correct role + query.

---

## 4. Explicit assessments

### Static file serving in FastAPI
- Mount line: `app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")`.
- `directory="frontend"` is resolved relative to the CWD at app-start. Matches the documented run command (`python3 -m uvicorn src.main:app` from repo root). If a deploy runs from a different CWD, resolution breaks. Decision: compute the path with `os.path.join(os.path.dirname(__file__), "..", "frontend")` to be CWD-independent, mirroring the pattern already used for `_ROLES_PATH` / `_METADATA_PATH` / `_EVALS_PATH`.
- `html=True` enables `index.html` fallback for directory requests. Required for `/app/` → `frontend/index.html`.
- No additional router is needed; `StaticFiles` is an ASGI sub-app and slots under the existing FastAPI instance without middleware reordering.

### API_BASE local vs deployed
- Current: `const API_BASE = "http://localhost:8000"` (hardcoded, cross-origin by definition).
- Target: `const API_BASE = (['localhost','127.0.0.1'].includes(window.location.hostname)) ? 'http://localhost:8000' : '';`
- Behavior matrix:
  | Page origin | `API_BASE` | Fetch URL for `/query` |
  |---|---|---|
  | `file://…/frontend/index.html` | `'http://localhost:8000'` | `http://localhost:8000/query` (cross-origin, CORS-permitted) |
  | `http://localhost:8000/app/` | `'http://localhost:8000'` | `http://localhost:8000/query` (same origin; CORS moot) |
  | `https://app.railway.app/app/` | `''` | `https://app.railway.app/query` (same origin) |
- Only one line in `app.js` changes (line 3). All four call sites at 205 / 235 / 701 / 1121 remain unchanged.

### ALLOW_INGEST for read-only deploys
- Read per-request via `os.getenv("ALLOW_INGEST", "true").strip().lower() not in {"false", "0"}`.
- When disabled, the `/ingest` handler raises `HTTPException(403, "Ingest is disabled on this deployment.")` **before** reading the request body.
- Frontend Admin mode entirely hidden when `/health.ingest_enabled === false`; the mode toggle button is `hidden`-classed and the `#admin-section` is skipped during `switchMode`.
- `tests/test_ingest.py` is unaffected because `ALLOW_INGEST` is unset during pytest runs and default is enabled.
- Set explicitly in the host's env config: `ALLOW_INGEST=false`.

### artifacts/ + .gitignore + sensitive files
- Tracked: `artifacts/querytrace.index`, `artifacts/index_documents.json`, `artifacts/bm25_corpus.json` (confirmed via `git ls-files artifacts/`).
- `.gitignore` patterns: only `artifacts/*.faiss`, `artifacts/*.pkl`, `artifacts/*.npy` — no collision.
- No secrets scan needed at implement-time; a one-line pre-push check (`git ls-files | grep -Ei '\\.env|\\.pem|\\.key|credentials'`) is documented in the verification plan.

### MUST-D deploy caveats
- Ingest writes (corpus + artifacts) are neutralized by `ALLOW_INGEST=false`.
- Ephemeral-fs limitation is already documented in CLAUDE.md.
- No MUST-D code paths execute at startup on a prod deploy beyond `_metadata` being loaded once.
- Admin UI tab must be hidden in prod to avoid dead affordances.

---

## 5. Execution order

Phase 0 — Preflight (read-only)
1. Confirm `artifacts/` tracked + sized (<100 KB total ✅).
2. Confirm `.gitignore` has no deploy-blocking exclusions.
3. `grep` for accidental secrets in tracked files.

Phase 1 — Backend
4. `src/main.py`: import `StaticFiles`, compute `_FRONTEND_DIR` via `os.path.dirname(__file__)`, add `/app` mount after existing routes, extend `/health` to include `ingest_enabled`, gate `/ingest` with `_ingest_enabled()` helper that reads `os.getenv("ALLOW_INGEST", "true")`.

Phase 2 — Frontend
5. `frontend/app.js` line 3: replace hardcoded `API_BASE` with env-aware expression.
6. `frontend/app.js`: on page load, `fetch('/health')` (via `API_BASE`) and hide the Admin mode button + `#admin-section` when `ingest_enabled === false`. Failure of the probe is non-fatal (leave Admin visible). Wrap in a `try/catch` — no console spam on offline.

Phase 3 — Deploy artifacts
7. New `Procfile` at repo root: `web: uvicorn src.main:app --host 0.0.0.0 --port $PORT`.
8. Optional: `.python-version` pin (defer unless Railway build fails).

Phase 4 — Verification
9. Run full pytest (expect 172/14/0).
10. Uvicorn smoke at `http://localhost:8000/app/`; curl health, ingest 403 with env flag set.
11. Playwright re-run of the Compare scenarios + onboard cards at `/app/` origin.

Phase 5 — Docs
12. CLAUDE.md: add "Deploy" section (Procfile, `/app/` URL, `ALLOW_INGEST`, trailing-slash note, ephemeral-fs reminder).
13. `docs/HANDOFF.md`: new session entry for NICE-B.
14. Finalize this file with commit SHA + evidence.

---

## 6. Acceptance criteria

- `GET /app/` returns `frontend/index.html` with status 200.
- `GET /app/app.js`, `/app/styles.css` return 200 with correct MIME.
- `GET /health` returns `{"status": "ok", "ingest_enabled": <bool>}`.
- `POST /ingest` returns 200 when env unset; returns 403 (with a human-readable detail) when `ALLOW_INGEST=false`.
- Page loaded at `http://localhost:8000/app/` runs Single query → 200, Compare → 200, Evals → 200, all rendering same as today.
- Page loaded from `file://` still hits `http://localhost:8000` via absolute `API_BASE` (no regression).
- Admin tab is hidden in the UI when `/health.ingest_enabled === false`.
- `Procfile` exists at repo root; uvicorn starts successfully when run as `PORT=8000 bash -c "$(cat Procfile | sed 's/^web: //')"` (i.e., the Procfile command boots).
- `python3 -m pytest -q` → 172 / 14 / 0 (unchanged).
- No new JS console errors in any mode (probed in browser).
- `.gitignore` unchanged in any way that would exclude the three artifacts.
- No `.env*`, `*.pem`, `*.key` files pushed; `git ls-files` pre-push scan clean.
- CLAUDE.md deploy section present and accurate.

---

## 7. Verification commands

```bash
# Phase 0
git ls-files artifacts/
git ls-files | grep -Ei '\\.env|\\.pem|\\.key|credentials' || echo "no secrets"

# Phase 4a — pytest (ingest enabled by default)
python3 -m pytest -q

# Phase 4b — uvicorn smoke (local, ingest enabled)
python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000 &
UVICORN_PID=$!
sleep 2
curl -s http://localhost:8000/health
curl -s -I http://localhost:8000/app/ | head -1
curl -s -I http://localhost:8000/app/app.js | head -5
curl -s -X POST http://localhost:8000/query -H 'Content-Type: application/json' \
  -d '{"query":"ARR growth","role":"analyst"}' | head -c 200
kill $UVICORN_PID

# Phase 4c — ingest disabled
ALLOW_INGEST=false python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000 &
UVICORN_PID=$!
sleep 2
curl -s http://localhost:8000/health    # expect ingest_enabled: false
curl -s -o /dev/null -w '%{http_code}\\n' -X POST http://localhost:8000/ingest \
  -F 'file=@/dev/null' -F 'title=x' -F 'date=2024-01-01' -F 'min_role=analyst' \
  -F 'doc_type=research_note' -F 'sensitivity=low' -F 'tags='
# expect 403
kill $UVICORN_PID

# Phase 4d — Procfile smoke (host-style invocation)
PORT=8000 $(cat Procfile | sed 's/^web: //') &
PROCFILE_PID=$!
sleep 2
curl -s http://localhost:8000/health
kill $PROCFILE_PID

# Phase 4e — Playwright via webapp-testing skill at http://localhost:8000/app/
# - Single mode query: "ARR growth" / analyst / Full Pipeline → results + trace
# - Compare scenarios: Analyst wall / VP deal / Partner view → 3 columns each
# - Evals mode: loads narrative + 10 metrics + 8-row table
# - Admin tab: hidden when ingest disabled; visible otherwise
# - 0 JS console errors
```

---

## 8. Docs to update at end of batch

- `CLAUDE.md` — new **Deploy** section: Procfile, `/app/` URL, `ALLOW_INGEST` flag, `/health.ingest_enabled` probe, trailing-slash quirk, ephemeral-fs reminder, CORS still required for `file://` dev.
- `docs/HANDOFF.md` — new session entry (NICE-B / IDEA 11) with files changed, verification evidence, and commit SHA.
- `docs/plans/2026-04-17-nice-b-idea-11-plan.md` (this file) — finalize with commit SHA + verification summary.
- No changes to prior IDEA plans.
- No README changes in this batch (optional follow-up if reviewers ask for a deploy quickstart).

---

## 9. Priority-banded task list

**P0 — must ship for a working deploy**
- Add `/app` static mount in `src/main.py`.
- Create `Procfile`.
- Make `API_BASE` environment-aware in `frontend/app.js`.
- Gate `/ingest` with `ALLOW_INGEST` (default enabled to preserve tests).
- Update `/health` to include `ingest_enabled`; hide Admin tab in frontend when false.

**P1 — deploy hygiene**
- Verify `.gitignore` isn't excluding artifacts (read-only check, no change needed).
- Pre-push secrets scan.
- Document deploy section in CLAUDE.md.

**P2 — optional polish**
- Pin Python runtime (`.python-version`) if Railway's default triggers build issues.
- Add a redirect from `/` to `/app/` so the bare host URL lands on the demo.

**P3 — deferred**
- Per-host config (`railway.toml`, `render.yaml`, `fly.toml`) — out of scope this batch.
- Rate limiting / auth for future non-demo deploys.
- Background reindex for ingest (would lift the 5–10 s blocking UX).

**Counts:** P0 = 5 · P1 = 3 · P2 = 2 · P3 = 3

---

## 10. Execution outcome (2026-04-17)

Status: **EXECUTED (P0 + P1)**. Target: Render web service.

- `src/main.py`: `StaticFiles` import, `_FRONTEND_DIR` constant, `_ingest_enabled()` helper, `/health` shape extension, `/ingest` 403 gate, `/app` static mount at EOF.
- `frontend/app.js`: hostname-aware `API_BASE` resolver; boot-time `/health` capability probe hides the Admin tab when `ingest_enabled === false`. Probe failures are non-fatal.
- `Procfile` (new) at repo root: `web: uvicorn src.main:app --host 0.0.0.0 --port $PORT`. Consumable by Render (Start Command) and Railway (buildpack) unchanged.
- `CLAUDE.md`: new **Deploy (read-only, Render-first)** section.
- `docs/HANDOFF.md`: Session 27 entry (this batch).

Evidence:
- `python3 -m pytest -q` → **172 passed, 14 skipped, 0 failed** (unchanged).
- `node --check frontend/app.js` → OK.
- Local uvicorn (ingest enabled): `/health` returns `ingest_enabled: true`; `/app/`, `/app/app.js`, `/app/styles.css` return 200 with correct MIME; `/query` returns 200 for a sample query.
- Local uvicorn with `ALLOW_INGEST=false`: `/health.ingest_enabled === false`; `/ingest` returns 403 with `"Ingest is disabled on this deployment."`; `/query` still 200.
- Procfile command boots cleanly under `PORT=8000`.

Render-specific notes:
- Start command: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`.
- Build command: `pip install -r requirements.txt`.
- Required env: `ALLOW_INGEST=false`. `PORT` is auto-provided.
- Deployed URL: `https://<render-host>/app/` (trailing slash required; `/app` 307-redirects).
- Ephemeral filesystem: with `ALLOW_INGEST=false` no writes happen, so the committed `artifacts/*` are authoritative. For a persistent Admin demo, attach a Render Disk mounted at the repo root (out of scope).

Deviations from plan: none material. P2/P3 items (Python pin, root redirect, per-host config files) remain deferred.

## 11. Residual risks accepted without mitigation

- First-query latency ~3–8 s on cold container (MiniLM lazy-load).
- Build image size may clip Railway free-tier memory ceiling.
- Ingest writes are ephemeral on most container hosts (documented).
- Trailing-slash redirect `/app` → `/app/` (Starlette default).
- No auth anywhere; the demo is intentionally public read-only.
