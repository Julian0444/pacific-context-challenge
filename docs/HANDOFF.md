# Handoff — QueryTrace

---

## Sessions 1–17 — Consolidated Summary (2026-04-05 → 2026-04-12)

### Build Timeline

| Session | Date | What was done | Tests after |
|---------|------|---------------|-------------|
| 1 | 04-05 | Project bootstrap: repo scaffolding, 12-doc financial corpus (Atlas Capital / Meridian "Project Clearwater"), FAISS indexer + retriever | 0 |
| 2 | 04-05 | Full pipeline (TDD): `policies.py`, `freshness.py`, `context_assembler.py`, wired `POST /query` | 24 |
| 3 | 04-05 | Evaluation harness: `evaluator.py` + 8 corpus-grounded test queries | 40 |
| 4 | 04-05 | Corpus-relative freshness (time-independent scores, 0.5–1.0 range), half_life_days 30→365 | 46 |
| 5 | 04-06 | Commit & consolidation (no code changes) | 46 |
| 6 | 04-06 | Frontend redesign: "Midnight Analysis Desk" dark theme, result cards with score/freshness bars, tags, example query buttons, loading/error states | 46 |
| 7 | 04-10 | Pydantic contract layer: 13 typed models in `models.py`, 3 Protocol classes in `protocols.py` | 70 |
| 8 | 04-11 | Pipeline orchestrator: `pipeline.py` with StageOk/StageErr, 3 policy presets (`naive_top_k`, `permission_aware`, `full_policy`), rewired `main.py` | 88 |
| 9 | 04-11 | Typed stages in `src/stages/` (4 modules), `DecisionTrace` hardened (renamed fields, added `DroppedByBudget`, `ttft_proxy_ms`, `budget_utilization`) | 117 |
| 10 | 04-11 | Hybrid retrieval: FAISS + BM25 via RRF, 3× over-retrieval to compensate permission attrition | 137 |
| 11 | 04-12 | Evaluator wired to `run_pipeline()`, removed dead `token_budget` interface, trace-level metrics in evaluator output, legacy dict tests skipped (14) | 138 passed, 14 skipped |
| 12 | 04-12 | Context Policy Lab frontend: Single/Compare modes, `POST /compare` endpoint, structured Decision Trace rendering, 51/51 Playwright checks | 141 passed, 14 skipped |
| 13 | 04-12 | Hostile review clean verdict: empty-policies guard on `/compare`, strengthened compare tests | 142 passed, 14 skipped |
| 14 | 04-12 | `GET /evals` endpoint (cached), Evals dashboard (3rd frontend mode): 10 metric cards + 8-row per-query table | 148 passed, 14 skipped |
| 15 | 04-12 | Light theme migration (warm parchment palette), VP/Partner scenario buttons, freshness N/A fix, POLICY_META fallback fix, README rewrite | 148 passed, 14 skipped |
| 16 | 04-12 | Documentation pass: CLAUDE.md + plan updates (no code) | 148 passed, 14 skipped |
| 17 | 04-12 | Browser verification via Playwright: 44/44 checks, demo status READY | 148 passed, 14 skipped |

### Key Design Decisions (still relevant)

- **Corpus-relative freshness:** Age measured from newest doc in corpus (`2024-04-18`), not calendar date. Time-independent scores.
- **StageOk/StageErr pattern:** Pipeline aborts on first failure. Each stage is a pure-compute function with typed inputs/outputs.
- **3× over-retrieval:** `retrieve_k = policy.top_k * 3` compensates for permission attrition before budget packing.
- **RRF K=60:** Standard constant for fusing FAISS and BM25 ranks. Full-corpus ranking (12 docs is cheap).
- **Module-level `_evals_cache`:** `run_evals()` is ~5–10s cold; cache makes `/evals` usable from browser.
- **`ScoredDocument` uses `extra="ignore"`:** Absorbs extra keys (`rank`, `file_name`, `type`) from retriever without breaking validation.
- **14 legacy tests skipped:** `filter_by_role` (4), `apply_freshness` (5), `assemble()` (5) — all replaced by typed stages. Marked with `@_LEGACY_SKIP` or `pytestmark`.

### Dead Code (noted, not blocking)

- `apply_freshness()` in `freshness.py` — replaced by `stages/freshness_scorer.py`
- `filter_by_role()` in `policies.py` — replaced by `stages/permission_filter.py`
- `run_evals()` reloads roles/metadata independently of `main.py`'s copies — cosmetic, no correctness impact

### Persistent Environment Notes

- **Python 3.9.6 / LibreSSL 2.8.3:** `tf-keras` installed for `sentence-transformers` compatibility. Upgrading deps may break this.
- **Google Fonts:** Bricolage Grotesque + IBM Plex Mono from CDN; falls back to system fonts offline.

---

## Session — 2026-04-13 (Session 18 / Prompt 8: Final Hardening & Submission-Readiness)

### Summary

End-to-end reviewer pass across the full product experience. Four targeted fixes applied; one real bug (silent 500 on invalid policy for `/query`) caught and resolved. Browser verification confirmed all demo flows intact.

**What was done:**

1. **Fixed `/query` invalid-policy returns 500** (`src/main.py`) — `ValueError` raised by `resolve_policy()` inside `run_pipeline()` was not caught by the `/query` handler (only `/compare` had the `except ValueError` guard). Added `except ValueError as e: raise HTTPException(400, ...)` to `/query`. Before the fix: `POST /query` with `policy_name="bogus"` returned `500 Internal Server Error`. After: returns `400` with `"Unknown policy: 'bogus'. Valid policies: [...]"`.

2. **Added test for the above** (`tests/test_main.py`) — `test_query_invalid_policy_returns_400` added (tests: 17 → 18 total in that file; suite total: 148 → 149 passed).

3. **Fixed XSS in trace chip `title` attributes** (`frontend/app.js`) — Two `title="..."` attributes in `buildTracePanelHTML()` used unescaped API data:
   - Blocked chip: `title="requires: ${d.required_role}"` → `title="requires: ${escapeHTML(d.required_role)}"`
   - Stale chip: `title="superseded by: ${d.superseded_by} · ..."` → `title="superseded by: ${escapeHTML(d.superseded_by)} · ..."`
   (The `<em>` inline text in both chips was also fixed to use `escapeHTML`.)

4. **Fixed stale docstring in `src/protocols.py`** — `MetadataStoreProtocol` docstring still said "matches the shape that `freshness.apply_freshness` expects" — updated to reference `stages.freshness_scorer.score_freshness`, which is the actual live caller.

5. **Fixed stale comment in `src/freshness.py`** — `compute_freshness()` docstring said "In practice, `apply_freshness` passes the newest corpus date" — updated to "the stages layer passes the newest corpus date".

**Browser verification (Playwright, 65 checks):**

All 11 sections passed. 62/65 raw checks reported as passed; the 3 "failed" were test-script logic bugs (case-sensitive string comparisons against ALL-CAPS UI labels), confirmed as UI-correct in a targeted follow-up pass:
- Partner FULL column shows `"0\nBLOCKED"` (correct format; test checked wrong order)
- Evals "RECALL" label is ALL-CAPS (test checked mixed-case `"Recall"`)
- Evals "PERMISSION VIOLATIONS" label is ALL-CAPS (test checked `"Violation"` against `.lower()`)

**What was verified end-to-end:**
- Light theme: `rgb(245, 241, 234)` warm cream background
- Single mode: result cards, summary bar, relevance + freshness bars, tags, doc-id labels, Decision Trace expand/collapse, blocked chips, budget bar
- Naive policy: 12 `.metric-na` elements show "N/A — skipped by policy"; 0 freshness bars; 12 docs returned
- Analyst wall ↔: 3 compare columns (NAIVE/RBAC/FULL), 7 `flag-blocked` annotations, 3 open trace panels, analyst banner
- VP deal view ↔: 3 columns, VP role in banner
- Partner view ↔: 3 columns, partner banner, FULL column `"0\nBLOCKED"` confirmed
- Mode switching: Compare → Single, Evals → Single, all clean
- Evals dashboard: PRECISION@5=0.3000, RECALL=1.0000, PERMISSION VIOLATIONS=0.0%, 8-row table, "Queries run: 8 · Failed: 0"
- 0 JS console errors

### Current State

- **Branch:** `main`
- **Last commit:** `3d2738a` (Task 7B DONE)
- **Working tree:** 5 modified files (uncommitted — this session's work):
  - `frontend/app.js` — escapeHTML fixes on blocked + stale chip title attributes
  - `src/main.py` — `except ValueError` guard added to `/query`
  - `src/protocols.py` — stale docstring updated
  - `src/freshness.py` — stale comment updated
  - `tests/test_main.py` — `test_query_invalid_policy_returns_400` added
- **Tests:** 149 passed, 14 skipped, 0 failed (verified fresh run this session)
- **Evaluator:** precision@5=0.3000, recall=1.0000, permission_violation_rate=0% (verified fresh run this session)
- **Browser verification:** COMPLETE — 65/65 checks, 0 UI failures (3 false negatives were test-script bugs)
- **Hostile review:** `clean` (Prompt 7A — no new review this session; changes are targeted bug fixes only)
- **Demo status:** READY

### DOCX Scope Match

The project delivers the full promised scope of a **Permission-Aware Context Gateway / Context Policy Lab**:

| Deliverable | Status |
|-------------|--------|
| Hybrid retrieval (FAISS semantic + BM25 lexical via RRF) | ✅ Done |
| RBAC permission filtering (analyst < vp < partner) | ✅ Done |
| Freshness scoring with stale-pair demotion (0.5× penalty) | ✅ Done |
| Token budget packing | ✅ Done |
| Full `DecisionTrace` audit (included/blocked/stale/dropped + metrics) | ✅ Done |
| Four policy presets (`naive_top_k`, `permission_aware`, `full_policy`, `default`) | ✅ Done |
| `POST /query` endpoint with policy selector | ✅ Done |
| `POST /compare` endpoint for side-by-side policy comparison | ✅ Done |
| `GET /evals` endpoint with cached evaluator results | ✅ Done |
| Three-mode frontend (Single / Compare / Evals) | ✅ Done |
| Three one-click compare scenarios (Analyst / VP / Partner) | ✅ Done |
| Evaluation harness (8 queries, P@5, recall, violation rate, trace metrics) | ✅ Done |

### Remaining Tasks

1. **Commit this batch** — 5 modified files: `frontend/app.js`, `src/main.py`, `src/protocols.py`, `src/freshness.py`, `tests/test_main.py`

2. **(Optional) Remove dead code** — `apply_freshness()` in `freshness.py` and `filter_by_role()` in `policies.py` are unreachable on the request path; 14 tests already skipped and labelled as legacy. Safe to delete when convenient; no urgency.

3. **(Optional) Evaluator corpus re-read** — `run_evals()` loads roles/metadata independently of `main.py`'s already-loaded copies. Cosmetic only; no correctness impact.

### Blockers and Warnings

None. Project is submission-ready.

- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility on this Python version.
- **Google Fonts dependency:** Frontend loads Bricolage Grotesque and IBM Plex Mono from CDN; falls back to system fonts if offline.

### Suggested First Action

Commit the 5 modified files. No further work is required before submission.

---

## Session — 2026-04-15 (Session 19 / **MUST-A — IDEA 2 + IDEA 1**)

> **IDEA numbering convention:** Prompts labelled "IDEA N" track discrete feature/enrichment batches applied after the core build. Batches labelled "MUST-X" group multiple IDEAs into a single commit unit.

### Summary

**Batch label: MUST-A — IDEA 2 + IDEA 1**

Two enrichment passes in one session: backend metadata plumbing (IDEA 2) followed by frontend policy-selector polish (IDEA 1), plus a targeted visual review/rescue pass on the policy-selection block.

---

#### IDEA 2 — Enrich DocumentChunk with Metadata

Propagated `title`, `doc_type`, `date`, and `superseded_by` through the full data chain so the frontend `context[]` array receives those fields on every response. No business logic changed. No tests added or removed.

**Files modified (5):**

1. **`src/retriever.py`** — `_build_results()` now emits `"doc_type": p.get("type")` in addition to the existing `"type"` key. `ScoredDocument` uses `extra="ignore"` so `"type"` was always silently dropped; `doc_type` is the correctly-named key that the model picks up.

2. **`src/models.py`** — Four model additions, all `Optional[str] = None`:
   - `ScoredDocument`: added `doc_type`
   - `FreshnessScoredDocument`: added `doc_type`
   - `IncludedDocument`: added `title`, `doc_type`, `date`, `superseded_by`
   - `DocumentChunk`: added `title`, `doc_type`, `date`, `superseded_by`

3. **`src/stages/freshness_scorer.py`** — `FreshnessScoredDocument(...)` constructor now passes `doc_type=doc.doc_type`.

4. **`src/stages/budget_packer.py`** — `IncludedDocument(...)` constructor now passes `title`, `doc_type`, `date`, `superseded_by`.

5. **`src/main.py`** — Both `DocumentChunk(...)` constructors (in `query()` and `compare()`) now pass `title`, `doc_type`, `date`, `superseded_by` from `inc`.

---

#### IDEA 1 — Improve Policy Names + Policy Description Area

Frontend-only visual changes to the policy selector. No backend changes.

**Files modified (3):**

1. **`frontend/app.js`** — `POLICY_META` labels updated:
   - `naive_top_k`: `"NAIVE"` → `"No Filters"`, desc updated to full sentence
   - `permission_aware`: `"RBAC"` → `"Permissions Only"`, desc updated
   - `full_policy`: `"FULL"` → `"Full Pipeline"`, desc updated
   - **Bug fix:** `permission_aware.skipFreshness` changed from `false` → `true` (backend skips freshness for this policy; was showing `0.00` bars instead of N/A)
   - Added `updatePolicyDescription()` function with 80ms opacity fade transition
   - Event listeners wired to all `[name="policy"]` radios; init call on page load

2. **`frontend/index.html`** — `#single-policy-selector` restructured:
   - Outer wrapper: new class `policy-selector-group` (flex-column container)
   - Inner `.selector-group` div: holds label + chips horizontally
   - `<p id="policy-description">` added below chips — shows `POLICY_META.desc` for selected policy
   - `<div id="policy-warning" hidden>` added — amber banner with ⚠ icon, shown only when "No Filters" is selected
   - Chip labels: `naive` → `No Filters`, `rbac` → `Permissions Only`, `full` → `Full Pipeline`

3. **`frontend/styles.css`** — New rules added:
   - `.policy-selector-group`: `flex-direction: column; align-self: flex-start` (prevents vertical misalignment against shorter Role group in `.controls-row`)
   - `.policy-description`: mono, `0.61rem`, tertiary color, `opacity 80ms` transition
   - `.policy-warning`: `rgba(251,191,36,0.13)` background, amber left border, compact padding
   - `.policy-warning > span`: `flex-shrink: 0; line-height: 1` (emoji alignment fix)

---

#### Visual Review Pass (policy-selection block only)

A targeted `/frontend-design` review of the policy selector hierarchy. Five polish fixes applied:

| # | Issue | Fix |
|---|-------|-----|
| 1 | `.controls-row { align-items: center }` misaligned Role and Policy chips when Policy group grew taller | `align-self: flex-start` on `.policy-selector-group` |
| 2 | ⚠ emoji floated high on some systems | `.policy-warning > span { flex-shrink: 0; line-height: 1 }` |
| 3 | `padding-left: 0.1rem` on description (meaningless 1.6px) | Removed |
| 4 | Warning background 10% opacity nearly invisible on parchment | Bumped to 13% |
| 5 | `transition: opacity` declared in CSS but never fired in JS | Added 80ms fade in `updatePolicyDescription()` |

---

**Note:** `roadmap.md` was deleted before this session (shows `D` in git status). No further work items are carried forward from it.

### Current State

- **Branch:** `main`
- **Last commit:** `78cdaf1` (WIP: MUST-A idea 1 and 2)
- **Working tree:** Clean (all MUST-A changes committed)
- **Tests:** 149 passed, 14 skipped, 0 failed (verified this session)
- **Evaluator:** precision@5=0.3000, recall=1.0000, permission_violation_rate=0% (unchanged)
- **Browser verification:** PENDING — IDEA 1 and IDEA 2 changes have not been visually verified in-browser. Last full verification was Session 18 (65/65 Playwright checks). The policy description area, warning banner, N/A freshness fix for `permission_aware`, and new chip labels are unverified.
- **Hostile review:** Not performed this session (last verdict: `clean`, Session 18)
- **Demo status:** READY (backend: no regressions; frontend: unverified but low-risk — all new fields are Optional, all label changes are display-only)

### What MUST-A Unblocks

- Frontend work that consumes `title`, `doc_type`, `date`, or `superseded_by` from `context[]` can proceed without additional backend changes.
- The policy selector now has product-grade labels and descriptions; compare-mode column headers inherit these automatically via `POLICY_META`.
- `permission_aware` freshness now correctly renders as N/A in both Single and Compare modes.

### Remaining Tasks

1. **Browser-verify MUST-A** — Confirm policy description area, warning banner, N/A freshness for `permission_aware`, and new chip labels render correctly in Single and Compare modes.
2. **(Optional) Remove dead code** — `apply_freshness()` in `freshness.py` and `filter_by_role()` in `policies.py` are unreachable on the request path; 14 tests already skipped. Safe to delete; no urgency.
3. **(Optional) Evaluator corpus re-read** — `run_evals()` loads roles/metadata independently of `main.py`'s copies. Cosmetic; no correctness impact.

### Suggested First Action

Browser-verify the MUST-A frontend changes before starting MUST-B1.

---

## Session — 2026-04-16 (Session 20 / **MUST-B1 — IDEA 3 + IDEA 7**)

> **IDEA numbering convention:** Batches labelled "MUST-X" group multiple IDEAs into a single commit unit.

### Summary

**Batch label: MUST-B1 — IDEA 3 + IDEA 7**

Three passes in one session: MUST-A browser verification, IDEA 3 (card redesign), and IDEA 7 (stale/superseded badges). All frontend-only — no backend, no test, no model changes.

---

#### MUST-A Browser Verification (completed this session)

Confirmed all MUST-A changes correct via Playwright (20/20 checks):
- Policy chips show "No Filters" / "Permissions Only" / "Full Pipeline" (old NAIVE/RBAC/FULL gone)
- Policy description updates on radio switch; all three descriptions are distinct
- Amber warning banner appears only for No Filters
- Permissions Only freshness renders as "N/A — skipped by policy" (12 elements); no 0.00 bars
- Full Pipeline query returns result cards; trace panel expands correctly
- 0 JS console errors

---

#### IDEA 3 — Document Card Redesign + Excerpt Expand/Collapse

Frontend-only. No backend or test changes.

**Files modified (2):** `frontend/app.js`, `frontend/styles.css`

**`singleCardHTML` changes:**
- Card header now shows document `title` (fallback: `doc_id`) as main heading (`.card-title`) with rank on the right
- New `.card-meta` line below title: `doc_id` badge (`.card-meta-badge`, light gray bg, mono font) · formatted doc type (e.g. "Public Filing") · formatted date (e.g. "Mar 2024")
- Default excerpt shortened from 480 → 200 chars
- Expand/collapse button ("Show more ▾" / "Hide ▴") toggles to full ~500-char indexer excerpt
- **Security hardening:** raw content stored in `_cardExcerpts` Map keyed by `data-card-idx`; toggle uses `textContent`, not `innerHTML` from data attributes
- **Date timezone fix:** `new Date(dateStr)` → manual `new Date(year, month-1, 1)` to avoid UTC offset shifting months (e.g. "2024-03-01" was rendering as "Feb 2024")

**`buildCompareCardHTML` changes:**
- Title heading (`.compare-card-title`, truncated to 60 chars) replaces bare doc_id
- Same `.card-meta` line (badge + type + date) added below title
- Snippet shortened from 160 → 120 chars
- No expand button (columns are narrow)

**New CSS:** `.card-title`, `.card-meta`, `.card-meta-badge`, `.compare-card-title`, `.card-content` (max-height transition: collapsed 4.8em → expanded 600px), `.card-content-text`, `.card-expand-btn`, `.compare-card-meta`

**New JS helpers:** `formatDocType(raw)`, `formatDate(dateStr)`, `_cardExcerpts` Map, `wireExpandButtons(container)`

---

#### IDEA 7 — Stale/Superseded Badge

Frontend-only. No backend or test changes.

**Files modified (2):** `frontend/app.js`, `frontend/styles.css`

**Detection:** Two-method with fallback:
- **Primary (Option A):** `chunk.superseded_by != null` — available because IDEA 2 already propagates this field through the full chain
- **Fallback (Option B):** cross-reference `chunk.doc_id` against `trace.demoted_as_stale` (built into a `staleMap` in `renderSingleResult()`)

**Single mode badge (`.stale-badge`):** Amber-tinted box with ⚠ icon, "Superseded by **doc_XXX** — freshness penalized 0.5×". Inserted between `.card-meta` and `.card-content`. Penalty value pulled from `staleInfo.penalty_applied` (falls back to `0.5×`).

**Compare mode badge (`.compare-stale-badge`):** Compact inline "⚠ Superseded" chip (option A only — `doc.superseded_by != null`). Inserted between `.card-meta` and content snippet.

**New CSS:** `.stale-badge`, `.stale-icon`, `.stale-text`, `.stale-text strong`, `.compare-stale-badge`

---

### Current State

- **Branch:** `codex/must-a-idea1-2`
- **Last commit:** `719e03f` (MUST-A idea 1 and 2) — MUST-B1 changes are **uncommitted** (2 modified files)
- **Working tree:** 2 modified files (uncommitted — this session's work):
  - `frontend/app.js` — IDEA 3 + IDEA 7 changes
  - `frontend/styles.css` — IDEA 3 + IDEA 7 styles
- **Tests:** 149 passed, 14 skipped, 0 failed (verified this session — `python3 -m pytest -q`)
- **Evaluator:** precision@5=0.3000, recall=1.0000, permission_violation_rate=0% (unchanged; no pipeline changes)
- **Browser verification:** COMPLETE — 19/19 MUST-B1 Playwright checks passed (IDEA 3 × 8, IDEA 7 × 5, Compare × 4, Evals regression × 1, JS errors × 1). 0 JS console errors.
- **Hostile review:** Not performed this session (last clean verdict: Session 18)
- **Demo status:** READY (all three modes functional; stale badges correct on both known stale pairs)

### Stale Docs Updated This Session

- **`CLAUDE.md` frontend section** — updated Single mode and Compare mode descriptions to reflect card redesign (title, metadata line, excerpt expand/collapse) and stale badges. Previously described card rendering did not mention these fields.
- **`docs/plans/2026-04-10-pipeline-integration-plan.md`** — historical/archived; no update needed. All items have been complete since Session 16.

### Remaining Tasks

1. **Commit MUST-B1** — 2 modified files: `frontend/app.js`, `frontend/styles.css`
2. **(Optional) Remove dead code** — `apply_freshness()` in `freshness.py` and `filter_by_role()` in `policies.py` are unreachable on the request path; 14 tests already skipped. Safe to delete; no urgency.
3. **(Optional) Evaluator corpus re-read** — `run_evals()` loads roles/metadata independently of `main.py`'s copies. Cosmetic; no correctness impact.

### Blockers and Warnings

None. Backend is unchanged. All new frontend fields are `Optional` — no risk of null-pointer regressions.

- **Branch mismatch note:** Working branch is `codex/must-a-idea1-2`, not `main`. MUST-A and MUST-B1 work lives here. Merge/PR decision is deferred.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility.

### Suggested First Action

Commit the 2 modified files (`frontend/app.js`, `frontend/styles.css`) as the MUST-B1 batch.

---

## Session — 2026-04-16 (Session 21 / **MUST-B2 — IDEA 5**)

> **IDEA numbering convention:** Batches labelled "MUST-X" group multiple IDEAs into a single commit unit.

### Summary

**Batch label: MUST-B2 — IDEA 5**

One enrichment pass: backend `BlockedDocument` metadata plumbing + frontend collapsible blocked-documents section in Single mode.

---

#### IDEA 5 — Blocked Documents Section in Single Mode

**Backend (2 files modified):**

1. **`src/models.py`** — `BlockedDocument` gained two optional fields:
   - `title: Optional[str] = None`
   - `doc_type: Optional[str] = None`

2. **`src/stages/permission_filter.py`** — Both `BlockedDocument(...)` constructors (unknown-role path and insufficient-role path) now pass `title=doc.title, doc_type=doc.doc_type`.

**Frontend (2 files modified):**

3. **`frontend/app.js`** — Three additions:
   - `buildBlockedSectionHTML(blocked, userRole)` — returns `<section class="blocked-section">` with a collapsible header ("🔒 N document(s) blocked by permissions ▾") and body with per-document `.blocked-card` entries showing title (fallback to `doc_id`), `doc_id` badge, doc type, and a human-readable reason (`"Requires X role — you are Y"` for `insufficient_role`; `"Unknown role requirement: X"` for `unknown_min_role`). Section omitted entirely when `blocked` is empty.
   - `wireBlockedSectionToggle(container)` — toggles `.open` class on `.blocked-section` header click.
   - `renderSingleResult()` updated: `blockedSectionHTML` computed from `trace?.blocked_by_permission || []` and inserted between `cardsHTML` and `traceHTML`.

4. **`frontend/styles.css`** — New block `/* ─── Blocked Documents Section (single mode) ─── */`:
   - `.blocked-section`, `.blocked-header` (amber left border `var(--trace-blocked)`, `var(--trace-blocked-bg)` background), `.blocked-header-icon`, `.blocked-caret` (rotates 180° when `.open`), `.blocked-body` (max-height 0 → 2000px transition), `.blocked-body-inner`, `.blocked-card`, `.blocked-card-title`, `.blocked-card-meta`, `.blocked-card-reason`.

---

### Current State

- **Branch:** `codex/must-a-idea1-2`
- **Last commit:** `719e03f` (MUST-A idea 1 and 2) — MUST-B1 and MUST-B2 changes are both **uncommitted** (4 modified files)
- **Working tree:** 4 modified files (uncommitted — MUST-B1 + MUST-B2):
  - `frontend/app.js` — IDEA 3 + IDEA 7 + IDEA 5 changes
  - `frontend/styles.css` — IDEA 3 + IDEA 7 + IDEA 5 styles
  - `src/models.py` — IDEA 5: `title`/`doc_type` added to `BlockedDocument`
  - `src/stages/permission_filter.py` — IDEA 5: both constructors pass `title`/`doc_type`
- **Tests:** 149 passed, 14 skipped, 0 failed (verified after IDEA 5 backend changes)
- **Evaluator:** precision@5=0.3000, recall=1.0000, permission_violation_rate=0% (unchanged; no pipeline logic changed)
- **Browser verification (IDEA 5):** COMPLETE — 4/4 Playwright checks passed:
  - Analyst + ARR query → blocked section renders with "🔒 7 documents blocked by permissions ▾"
  - Collapse/expand toggles correctly (closed by default → opens → closes again)
  - First blocked card shows correct title and reason: "Requires vp role — you are analyst"
  - Partner + same query → no blocked section rendered (correctly hidden)
  - Trace panel still renders below blocked section; no regression
  - 0 JS console errors
- **JS syntax:** `node --check frontend/app.js` → OK
- **Hostile review:** Not performed this session (last clean verdict: Session 18)
- **Demo status:** READY

### Stale Docs Updated This Session

- **`CLAUDE.md` frontend section** — Single mode description updated to include blocked-documents section; `BlockedDocument` contract model description updated to mention `title`/`doc_type` fields.
- **`docs/plans/2026-04-10-pipeline-integration-plan.md`** — historical/archived; no update needed. All items complete since Session 16.

### Remaining Tasks

1. **Commit MUST-B1 + MUST-B2** — 4 modified files: `frontend/app.js`, `frontend/styles.css`, `src/models.py`, `src/stages/permission_filter.py`
2. **(Optional) Remove dead code** — `apply_freshness()` in `freshness.py` and `filter_by_role()` in `policies.py` are unreachable on the request path; 14 tests already skipped. Safe to delete; no urgency.
3. **(Optional) Evaluator corpus re-read** — `run_evals()` loads roles/metadata independently of `main.py`'s copies. Cosmetic; no correctness impact.

### Blockers and Warnings

None. All new backend fields are `Optional` — existing tests unaffected. Frontend section is conditionally rendered (no display when zero blocked).

- **Branch mismatch note:** Working branch is `codex/must-a-idea1-2`, not `main`. MUST-A + MUST-B1 + MUST-B2 work lives here. Merge/PR decision is deferred.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility.

### Suggested First Action

Commit the 4 modified files as a combined MUST-B1 + MUST-B2 batch (or as two sequential commits if separate provenance is preferred).

---

## Session — 2026-04-16 (Session 22 / **MUST-B2 Verification + Documentation Pass**)

### Summary

Documentation and verification pass only. No code changes made. Confirmed MUST-B1 was committed as `6ac80a6` (correcting the Session 21 state which incorrectly described it as uncommitted). Ran `python3 -m pytest -q` and a thorough 7-criterion Playwright verification of the MUST-B2 blocked-documents section.

---

#### What was verified

**Tests (`python3 -m pytest -q`):** 149 passed, 14 skipped, 0 failed.

**Browser verification (7/7 Playwright checks — expanded from Session 21's 4/4):**

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Analyst + ARR query → blocked section appears (N > 0) | ✅ Header: "7 documents blocked by permissions" |
| 2 | Section collapsed by default | ✅ Body height = 0 on load |
| 3 | Click header → expands, blocked cards visible | ✅ 7 cards rendered |
| 4 | Blocked card reason is human-readable | ✅ "Requires vp role — you are analyst" |
| 5 | Click header again → collapses | ✅ Confirmed collapsed |
| 6 | Partner + same query → NO blocked section | ✅ `blocked-section` count = 0 |
| 7 | No JS console errors | ✅ 0 errors |

**Additive-only checks (all confirmed):**
- `buildBlockedSectionHTML` returns `""` when blocked list is empty — section is never rendered for partner or zero-blocked cases.
- No document content, excerpts, or scores are exposed in the blocked section — only `doc_id`, `title`, `doc_type`, and the reason string.

---

#### Stale docs corrected this session

- **`docs/HANDOFF.md` Session 21 "Current State"** — said last commit was `719e03f` and MUST-B1 was uncommitted. Corrected here: MUST-B1 was committed as `6ac80a6` before this session. MUST-B2 code remains uncommitted.
- **`CLAUDE.md`** — already fully up to date (lines 94, 135 describe MUST-B2 correctly). No changes needed.
- **`docs/plans/2026-04-10-pipeline-integration-plan.md`** — historical/archived. All plan items complete since Session 16. No update needed.

---

### Current State

- **Branch:** `codex/must-a-idea1-2`
- **Last commit:** `6ac80a6` (MUST-B1) — MUST-B2 code changes are **uncommitted**
- **Working tree — uncommitted code files (MUST-B2):**
  - `frontend/app.js` — IDEA 5: `buildBlockedSectionHTML`, `wireBlockedSectionToggle`, `renderSingleResult` wiring
  - `frontend/styles.css` — IDEA 5: `.blocked-section`, `.blocked-header`, `.blocked-body`, `.blocked-card` styles
  - `src/models.py` — IDEA 5: `title`/`doc_type` added to `BlockedDocument`
  - `src/stages/permission_filter.py` — IDEA 5: both `BlockedDocument` constructors pass `title`/`doc_type`
- **Working tree — uncommitted doc files (this session):**
  - `docs/HANDOFF.md` — this session entry
  - `CLAUDE.md` — already correct; modified in a prior pass
  - `docs/plans/2026-04-10-pipeline-integration-plan.md` — already correct; modified in a prior pass
- **Tests:** 149 passed, 14 skipped, 0 failed (verified this session)
- **Evaluator:** precision@5=0.3000, recall=1.0000, permission_violation_rate=0% (unchanged; no pipeline logic changed)
- **Browser verification:** COMPLETE — 7/7 checks (this session)
- **Hostile review:** Not performed this session (last clean verdict: Session 18)
- **Demo status:** READY

### Remaining Tasks

1. **Commit MUST-B2** — 4 uncommitted code files: `frontend/app.js`, `frontend/styles.css`, `src/models.py`, `src/stages/permission_filter.py`
2. **(Optional) Remove dead code** — `apply_freshness()` in `freshness.py` and `filter_by_role()` in `policies.py` are unreachable; 14 tests already skipped. Safe to delete; no urgency.
3. **(Optional) Evaluator corpus re-read** — `run_evals()` loads roles/metadata independently of `main.py`'s copies. Cosmetic; no correctness impact.

### Blockers and Warnings

None.

- **Branch note:** Working branch is `codex/must-a-idea1-2`, not `main`. MUST-A + MUST-B1 + MUST-B2 work lives here. Merge/PR decision is deferred.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility.

### Suggested First Action

Commit the 4 MUST-B2 code files.
