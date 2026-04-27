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

---

## Session — 2026-04-16 (Session 23 / **IDEAs Follow-up Closure — P2 + P3**)

### Summary

Documentation-only pass. Closed the two remaining follow-up items from `docs/plans/2026-04-16-ideas-execution-plan.md`. No code, test, or product changes.

**P2 — Restore flow consolidation (resolved):**
Added a 6-line `[ARCHIVED — 2026-04-16]` banner to the header of `docs/plans/2026-04-10-pipeline-integration-plan.md`. The banner explicitly states the file is not part of the default restore flow, kept on disk as audit record only, and documents the canonical restore sequence: `HANDOFF.md` → `CLAUDE.md` (extended: + `docs/plans/2026-04-16-ideas-execution-plan.md`).

**P3 — Compare column-header label verification (resolved):**
Ran an explicit Playwright assertion via the `webapp-testing` skill:
- Loaded `frontend/index.html` (file://) with the uvicorn API server running on port 8000
- Clicked the "Analyst wall ↔" scenario button (auto-switches to Compare mode, fires `POST /compare`)
- Waited for `.col-badge` elements; asserted exactly 3 present with text in order

```
Found 3 .col-badge elements: ['No Filters', 'Permissions Only', 'Full Pipeline']
PASS — Compare column headers match expected labels exactly.
```

This closes the lone `unclear` item from the MUST-A IDEA 1 consistency review. The code path was correct by construction (`buildCompareColumnHTML` reads `POLICY_META[policyName].label`), but the assertion was never itemized explicitly until now.

**Execution plan updated:** Both P2 and P3 entries rewritten as resolved with evidence. Count line updated to `P0=0, P1=0, P2=0 (resolved), P3=0 (resolved). All follow-ups closed.`

---

### Current State

- **Branch:** `codex/must-a-idea1-2`
- **Last commit:** `6122d94` (MUST-B2) — all subsequent changes are doc-only and uncommitted
- **Working tree — uncommitted doc files:**
  - `docs/HANDOFF.md` — this session entry
  - `docs/plans/2026-04-10-pipeline-integration-plan.md` — ARCHIVED banner added (P2)
  - `docs/plans/2026-04-16-ideas-execution-plan.md` — new canonical plan file (untracked; replaces deleted summary)
  - `docs/plans/2026-04-16-ideas-1-2-3-5-7-execution-summary.md` — deleted (unstaged; superseded by execution plan)
- **Tests:** 149 passed, 14 skipped, 0 failed (last verified Session 22; no code touched this session)
- **Evaluator:** precision@5=0.3000, recall=1.0000, permission_violation_rate=0% (unchanged)
- **Browser verification:** P3 assertion PASS (this session)
- **Demo status:** READY
- **IDEAs follow-up thread:** FULLY CLOSED — `docs/plans/2026-04-16-ideas-execution-plan.md` is the canonical artifact; all P-items resolved

### Remaining Tasks

1. **Commit doc cleanup** — 4 files: `docs/HANDOFF.md`, `docs/plans/2026-04-10-pipeline-integration-plan.md` (modified), `docs/plans/2026-04-16-ideas-execution-plan.md` (new, untracked), `docs/plans/2026-04-16-ideas-1-2-3-5-7-execution-summary.md` (deleted)
2. **(Optional) Remove dead code** — `apply_freshness()` in `freshness.py` and `filter_by_role()` in `policies.py` are unreachable; 14 tests already skipped. Safe to delete; no urgency.
3. **(Optional) Evaluator corpus re-read** — `run_evals()` loads roles/metadata independently of `main.py`'s copies. Cosmetic; no correctness impact.

### Blockers and Warnings

None. The IDEAs follow-up thread has no open items. No code was touched.

- **Branch note:** Working branch is `codex/must-a-idea1-2`, not `main`. All MUST-A/B1/B2 work plus doc cleanup lives here. Merge/PR decision is deferred.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility.

### Suggested First Action

Commit the 4 uncommitted doc files as a single "doc cleanup" commit.

---

## Session — 2026-04-17 (Session 24 / **MUST-C — IDEA 4 + IDEA 6**)

### Summary

**Batch label: MUST-C — IDEA 4 + IDEA 6**

Two frontend-only explainability passes. No backend, test, or model changes. All added UI is additive and conditionally rendered; existing chips, tables, and layouts untouched.

---

#### IDEA 4 — Natural-language Decision Trace summary + metric tooltips

**Files modified (2):** `frontend/app.js`, `frontend/styles.css`

- **`buildTraceSummary(trace, userRole, compact)`** helper added above `buildTracePanelHTML`. Returns an HTML string composed of up to four sentences — included / blocked / stale / dropped — with conditional rules (blocked and stale omitted when counts are zero; dropped omitted in compact mode when zero). Grammatical guards for `included === 0` and singular/plural nouns. `<strong>` used for emphasis on counts, roles, and doc IDs. All interpolated values pass through `escapeHTML`.
- **`buildTracePanelHTML(trace, startOpen, userRole)`** signature extended with `userRole`. Inserts `<div class="trace-summary">` as the first child of `.trace-body`. Adds `trace-summary-compact` class when `startOpen === true` (Compare mode). The compact variant collapses the stale clause to a one-line count and drops the zero-dropped sentence.
- **Four tooltips** added via `title=` attributes: `.budget-label` (Budget), and three spans in `.trace-numbers` (avg score, avg freshness, ttft). Prompt typos corrected: `"gng" → "generating"`, `"rey" → "recency"`.
- **Call sites threaded:** `renderSingleResult` passes `role`; `buildCompareColumnHTML` signature extended with `userRole` and forwards it; `renderCompare` passes `data.role` into each column.
- **CSS:** new `.trace-summary` (accent left border, `bg-surface`, readable `text-primary`) + `.trace-summary-compact` (tighter padding/size for Compare columns) + `.trace-summary strong`.

Compact-mode rule choice: instead of stripping the budget-% clause, the compact variant drops the zero-dropped sentence and collapses per-doc stale details to a count. This preserves the informative "N tokens, M% of budget" clause in all modes while visibly shortening the paragraph on small columns.

---

#### IDEA 6 — Evals narrative banner + per-card hints + query-text column

**Files modified (2):** `frontend/app.js`, `frontend/styles.css`

- **`buildEvalsNarrative(agg)`** helper added below `renderEvals`. Returns `<div class="evals-narrative">` with three sentences: (1) permission-violations line (congratulatory or warning form); (2) recall line (100% form or fallback for less-than-perfect recall); (3) budget-utilization tier line (`< 0.60 → efficient`, `[0.60, 0.80] → moderate`, `> 0.80 → heavy`). Guarded on `queries_run > 0` — returns empty string otherwise.
- **`METRIC_HINTS`** added inline as a `hint` field on each card entry in `renderEvals`. Each `.metric-card` now renders three spans: label / value / hint. Typos from prompt fixed.
- **Query cell redesign:** the per-query table's first cell now contains `<span class="evals-qid">${q.id}</span><span class="evals-qtext" title="${full}">${truncated}</span>`, with truncation at 50 chars + `…`. Existing 12-column layout preserved; `.evals-query-cell` allows wrapping (overrides the global `white-space: nowrap` on `td`). Full query text surfaced via `title=` tooltip.
- **CSS:** new `.evals-narrative` (parchment card with accent left border + shadow), `.metric-card-hint` (small tertiary text as third flex child; no grid disruption), `.evals-query-cell` / `.evals-qid` (accent pill) / `.evals-qtext` (display-font, secondary color).

---

### Current State

- **Branch:** `codex/must-a-idea1-2`
- **Last commit:** `2d58d05` (MUST-B2 DOCS) — MUST-C changes are **uncommitted** (2 modified files + 1 new plan doc)
- **Working tree:**
  - `frontend/app.js` (modified) — IDEA 4 + IDEA 6
  - `frontend/styles.css` (modified) — IDEA 4 + IDEA 6 styles
  - `docs/plans/2026-04-17-must-c-ideas-4-6-plan.md` (new, untracked) — the approved batch plan
- **Tests:** 149 passed, 14 skipped, 0 failed (fresh run this session)
- **Evaluator:** fresh `python3 -m src.evaluator` run this session matches baseline — **precision@5=0.3000, recall=1.0000, permission_violation_rate=0%**, queries run 8/8, avg budget util 53%, avg freshness 0.768. No pipeline changed.
- **Browser verification:** COMPLETE — **15/15 Playwright checks passed** (IDEA 4 × 8 incl. separate analyst/partner blocked-clause checks; IDEA 6 × 7). 0 JS console errors across Single, Compare, and Evals modes.
- **JS syntax:** `node --check frontend/app.js` → OK.
- **Hostile review:** not performed this session (last clean verdict: Session 18)
- **Demo status:** READY

### Stale Docs Updated This Session

- **`CLAUDE.md` frontend section** — Single, Compare, and Evals mode descriptions amended to mention the trace narrative paragraph + tooltips (Single/Compare) and the narrative banner + card hints + query text column (Evals).
- **`docs/plans/2026-04-16-ideas-execution-plan.md`** — not modified. MUST-C is a separate batch with its own canonical plan; the 2026-04-16 plan remains the canonical MUST-A/B1/B2 artifact.
- **`docs/plans/2026-04-10-pipeline-integration-plan.md`** — ARCHIVED; not touched.

### Remaining Tasks

1. **Commit MUST-C** — 3 files: `frontend/app.js`, `frontend/styles.css`, `docs/plans/2026-04-17-must-c-ideas-4-6-plan.md`, plus `docs/HANDOFF.md` + `CLAUDE.md` for this session's doc updates.
2. **(Optional) Remove dead code** — `apply_freshness()` in `freshness.py` and `filter_by_role()` in `policies.py` are unreachable; 14 tests already skipped. Safe to delete; no urgency.
3. **(Optional) Evaluator corpus re-read** — `run_evals()` loads roles/metadata independently of `main.py`'s copies. Cosmetic; no correctness impact.

### Blockers and Warnings

None. All additions are conditional (narrative guarded on `queries_run > 0`; summary emits only non-empty clauses). `userRole` threading has default-undefined fallback; missing role degrades gracefully (the blocked clause uses generic phrasing).

- **Branch note:** Working branch is `codex/must-a-idea1-2`. MUST-A + MUST-B1 + MUST-B2 + MUST-C all live here.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility.

### Suggested First Action

Commit the MUST-C batch (2 frontend files + new plan doc + this HANDOFF update + CLAUDE.md update).

---

## Session — 2026-04-17 (Session 25 / **MUST-D — IDEA 8 · PDF Ingestion + Admin Panel**)

### Summary

**Batch label: MUST-D — IDEA 8**

First backend-expanding batch since MUST-A. Adds a runtime PDF ingestion path (new `POST /ingest` endpoint, new `src/ingest.py`, new frontend Admin mode) plus two new runtime dependencies. Writes to `corpus/documents/`, `corpus/metadata.json`, and `artifacts/*` at request time. 23 new tests.

---

#### Backend (6 files)

1. **`requirements.txt`** — added `pdfplumber` and `python-multipart`.

2. **`src/ingest.py` (new, ~210 lines)** — orchestrator `ingest_document(pdf_bytes, title, date, min_role, doc_type, sensitivity, tags, superseded_by=None, metadata_path=None, corpus_dir=None)` plus helpers `extract_text_from_pdf`, `generate_next_doc_id`, `sanitize_filename`, `_validate_inputs`, `_unique_filename`. Module-level `threading.Lock` (`_INGEST_LOCK`) wraps doc_id generation + `.txt` write + metadata append + `indexer.build_and_save()` call. Enum sets mirror existing corpus values: `VALID_MIN_ROLES={analyst,vp,partner}`, `VALID_DOC_TYPES={10 values}`, `VALID_SENSITIVITY={low,medium,high,confidential}`. `IngestError(ValueError)` carries a `status_code` attribute for clean FastAPI mapping. `MAX_PDF_BYTES=10*1024*1024`, `MIN_EXTRACTED_CHARS=50`. `metadata_path` / `corpus_dir` default to `None` with runtime fallback to module-level constants — enables monkeypatching in tests.

3. **`src/retriever.py`** — new `invalidate_caches()` resets only the `_bm25` singleton (FAISS is re-read from disk per request, embeddings model is corpus-independent).

4. **`src/models.py`** — new `IngestResponse(BaseModel)` with `extra="forbid"`: `status`, `doc_id`, `title`, `file_name`, `type`, `date`, `min_role`, `sensitivity`, `tags`, `total_documents`.

5. **`src/main.py`** — new `POST /ingest` handler. Maps `UploadFile` + 6 `Form(...)` fields → `ingest_document()`. Catches `IngestError` → `HTTPException(e.status_code)`. Rejects non-PDF content-types with 415 before calling ingest. On success, mutates `_metadata["documents"]` in place (so `run_pipeline` closures see the update), clears `_evals_cache`, and calls `retriever.invalidate_caches()`.

6. **`tests/test_ingest.py` (new, 23 tests)** — `sanitize_filename` (basic/nonword/path-traversal/empty/length-cap), `generate_next_doc_id` (advance/empty/malformed), `extract_text_from_pdf` (empty/unreadable), `ingest_document` validation (oversize 413, bad-date, bad-role, bad-doc_type, bad-sensitivity, empty-title), happy path (tmp_path + monkeypatched `indexer.build_and_save` + monkeypatched `extract_text_from_pdf`), duplicate-filename suffix. Five endpoint tests via `TestClient`: 415/400/400/422 error paths plus happy-path with patched `ingest_document` + `invalidate_caches` verifying response shape and that `_evals_cache is None` after the call.

---

#### Frontend (3 files)

7. **`frontend/index.html`** — fourth `<button data-mode="admin">Admin</button>` in the mode-toggle; new `<section id="admin-section" hidden>` with file / title / date / min_role select (3 values) / doc_type select (10 values) / sensitivity select (4 values) / tags inputs, submit button with spinner, status div, and demo-only advisory note.

8. **`frontend/app.js`** — `adminSection` DOM ref; `switchMode` branch for `isAdmin` (hides search, results, admin when appropriate); `setAdminStatus` / `clearAdminStatus` / `uploadDocument(event)` helpers. `uploadDocument` POSTs `FormData` to `${API_BASE}/ingest`, disables the submit button with `.loading` during the call, then renders success/error via `escapeHTML`-hardened status messages.

9. **`frontend/styles.css`** — `.admin-section`, `.admin-form`, `.admin-row` (grid), `.admin-field`, `.admin-btn` with spinner, `.admin-status-loading/success/error` colored left borders, `.admin-note`, responsive `@media (max-width: 640px)` fallback.

---

### Verification

**Tests:** 172 passed, 14 skipped, 0 failed (`python3 -m pytest -q`). 23 new tests vs. 149 baseline.

**Server smoke:** `python3 -m uvicorn src.main:app --port 8000` → `/docs` responds 200. Clean startup, no regressions.

**curl end-to-end:**

| Case | Request | Response |
|------|---------|----------|
| 415 — non-PDF | `text/plain` upload | `415 {"detail":"Expected a PDF upload; got content-type 'text/plain'."}` |
| 400 — bad role | `min_role=god` | `400 {"detail":"min_role must be one of ['analyst', 'partner', 'vp']."}` |
| 400 — bad date | `date=05/01/2024` | `400 {"detail":"date must be in YYYY-MM-DD format."}` |
| 422 — unreadable PDF | `%PDF-` only | `422 {"detail":"Unreadable PDF: No /Root object! - Is this really a PDF?"}` |
| 413 — oversize | 10 MB + 100 bytes | `413 {"detail":"PDF exceeds 10 MB size limit."}` |
| 200 — happy path | real reportlab PDF | `200 {"status":"ok","doc_id":"doc_013","file_name":"verification_smoke_doc.txt","total_documents":13,...}` |

**Search-after-ingest:** `POST /query {"query":"LIMINAL_ECHO_SENTINEL_7742","role":"analyst","top_k":5}` → `doc_013` ranked #1 in context. Cache invalidation + reindex confirmed working end-to-end.

**Playwright Admin flow (via `webapp-testing` skill):** Loaded frontend via `file://` with uvicorn on :8000 for the API. Clicked Admin tab → filled all fields → `set_input_files('/tmp/real.pdf')` → clicked Upload. Status area reached `admin-status-success` class with text: `"Indexed doc_014 — Playwright Admin Flow Doc. Corpus now contains 14 documents. It is searchable in Single and Compare modes."`. PASS.

**Rollback:** Corpus restored to pre-test state (12 docs, 12 `.txt` files, `artifacts/*` restored from snapshots).

**Addendum 2026-04-22 (UI-A — demo data cleanup).** A follow-up audit found the rollback above was not actually applied to the working tree: `corpus/documents/agenda.txt` + a `doc_013` `Agenda` metadata entry had leaked into the committed corpus from a separate verification-smoke ingest, leaving the corpus at 13 docs and polluting partner-role Compare results. UI-A removed `agenda.txt`, deleted the `doc_013` entry from `corpus/metadata.json`, rebuilt all three `artifacts/*` files (FAISS index + `index_documents.json` + `bm25_corpus.json`, now 12 rows each), and re-ran the evaluator + pytest baseline. Corpus is back to the intended 12-doc Meridian / Atlas Capital narrative. Evaluator aggregates post-cleanup: `P@5=0.3000, Recall=1.0000, perm_viol=0%, avg_blocked=3.38, avg_stale=1.62, avg_budget_util=53%`. `pytest: 172 passed / 14 skipped / 0 failed`.

---

### Current State

- **Branch:** `codex/must-a-idea1-2`
- **Last commit:** `3da04cd` (MUST-D docs follow-up) on top of `a6d1daa` (MUST-D: IDEA 8 — PDF ingestion + Admin panel)
- **Working tree:** clean. All 12 MUST-D files (9 code + 3 doc) landed in `a6d1daa`; `3da04cd` is a docs-only follow-up commit. No modified, staged, or untracked files remain at handoff time.
- **Files in the MUST-D commit (`a6d1daa`, 12 files, +1323 / −11):**
  - Code: `requirements.txt`, `src/ingest.py` (new), `src/retriever.py`, `src/models.py`, `src/main.py`, `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, `tests/test_ingest.py` (new)
  - Docs: `docs/HANDOFF.md`, `CLAUDE.md`, `docs/plans/2026-04-17-must-d-idea-8-plan.md` (new)
- **Tests:** 172 passed, 14 skipped, 0 failed (this session)
- **Evaluator:** unchanged on the original 12-doc corpus (no pipeline logic changed)
- **Browser verification:** COMPLETE — Admin flow end-to-end PASS; prior MUST-C Playwright coverage unchanged
- **Hostile review:** Not performed this session (last clean verdict: Session 18)
- **Demo status:** READY

### Stale Docs Updated This Session

- **`CLAUDE.md`** — added `POST /ingest` endpoint section, Admin mode bullet under Frontend, `IngestResponse` in Contract models key types, dependency note under Environment note. `Three modes controlled by a header toggle:` → `Four modes controlled by a header toggle:`.
- **`docs/plans/2026-04-17-must-d-idea-8-plan.md`** — kept as the canonical MUST-D artifact; no content rewrite needed (plan matches execution).
- **`docs/plans/2026-04-16-ideas-execution-plan.md`** — unchanged. Different batch scope.
- **`docs/plans/2026-04-17-must-c-ideas-4-6-plan.md`** — unchanged. Different batch.

### Remaining Tasks

No MUST-D work remains. The batch is fully implemented, verified, and committed (`a6d1daa` + `3da04cd`). All long-standing optional follow-ups from prior sessions are unchanged and still optional:

1. **(Optional) Remove dead code** — `apply_freshness()` in `freshness.py` and `filter_by_role()` in `policies.py` remain unreachable; 14 tests skipped. Safe to delete; no urgency.
2. **(Optional) Evaluator corpus re-read** — unchanged from prior sessions; cosmetic.
3. **(Optional) Deploy posture** — if hosting the demo, note the ephemeral-fs limitation: uploads via `/ingest` will not survive container restarts on most hosts.
4. **(Optional) Hostile review** — last clean verdict was Session 18; MUST-A/B/C/D have not been rereviewed. No known issues.

### Blockers and Warnings

None. All validation boundaries covered by tests. The only persistent-state mutation (`metadata.json` + `artifacts/*`) is serialized by `_INGEST_LOCK` and restorable from git.

- **Branch note:** Working branch is `codex/must-a-idea1-2`. MUST-A + MUST-B1 + MUST-B2 + MUST-C + MUST-D all live here.
- **Python 3.9 / LibreSSL:** unchanged; `pdfplumber` installs cleanly on this stack.
- **Ephemeral hosting:** uploads via `/ingest` write to repo-relative paths; on ephemeral container filesystems they will vanish on restart. Documented in the Admin panel and in CLAUDE.md.

### Suggested First Action

None strictly required — MUST-D is complete and committed. If the next session needs direction, choose from the optional follow-ups above, or start a new IDEA / MUST-X batch.

---

## Session — 2026-04-17 (Session 26 / **SHOULD-A — IDEA 9 + IDEA 10**)

### Summary

**Batch label: SHOULD-A — IDEA 9 + IDEA 10**

Frontend-only onboarding pass. Two additive changes: a live role description under the role selector (IDEA 9), and a guided onboarding scenario grid replacing the passive empty state (IDEA 10). No backend, test, or model files touched. Reuses the existing `.example-btn` click handler and mirrors the MUST-A `updatePolicyDescription` pattern — no parallel state.

---

#### IDEA 9 — Role description

**Files modified (3):** `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`

- **`index.html`** — wrapped the role selector in a new `<div class="role-selector-group">` (mirroring `.policy-selector-group`) and added `<p class="role-description" id="role-description"></p>` below `.role-options`.
- **`app.js`** — added `ROLE_DESCRIPTIONS` constant (analyst / vp / partner copy exactly per prompt, with the typo "internamos" corrected to "internal memos"); added `updateRoleDescription(role)` using the same 80ms opacity fade as `updatePolicyDescription`; wired `change` listeners on all role radios; initialized on page load with the default checked role. In the existing `.example-btn` handler, called `updateRoleDescription(role)` right after `roleRadio.checked = true` — programmatic checked sets don't fire `change`, so scenarios/example clicks would otherwise leave the description stale.
- **`styles.css`** — added `.role-selector-group` (flex-column, `align-self: flex-start`) and `.role-description` (mono, 0.61rem, tertiary, `max-width: 500px`, 80ms opacity transition).

#### IDEA 10 — Guided empty state

**Files modified (2):** `frontend/index.html`, `frontend/styles.css` (no new JS)

- **`index.html`** — replaced the `#empty-state` interior. Dropped the decorative hexagon SVG. New headline "How different policies change context assembly", an expanded subtitle, a `.onboard-grid` of three `<button class="example-btn onboard-card">` scenarios ("Permission Wall"/analyst, "Stale Detection"/VP, "Full Access"/partner), and a closing hint "Or type your own query above and choose a role to explore." Each card has role-color `.onboard-dot`, `.onboard-card-subtitle` tier label, `.onboard-card-title`, and `.onboard-hint`. Reused existing `.dot-analyst` / `.dot-vp` / `.dot-partner` color vars.
- **`app.js`** — no changes. The pre-existing `document.querySelectorAll(".example-btn").forEach(...)` at app.js:138 picks up the onboard cards at page load because they share the class. One query-trigger path, no fork.
- **`styles.css`** — added `.onboard-grid` (3-col grid, responsive 1-col ≤720px), `.onboard-card` (overrides `.example-btn`'s inline-flex row layout with column layout, card shadow, hover lift), `.onboard-dot`, `.onboard-card-head`, `.onboard-card-title`, `.onboard-card-subtitle`, `.onboard-hint`.

---

### Verification

**Tests:** 172 passed, 14 skipped, 0 failed (unchanged — no backend files touched).

**JS syntax:** `node --check frontend/app.js` clean.

**Diff stat:** `frontend/app.js` +34 lines, `frontend/index.html` +62/−25, `frontend/styles.css` +110. Three files; no backend.

**Playwright (via `webapp-testing` skill) — 15/15 passed, 0 console errors:**

| # | Assertion | Evidence |
|---|-----------|----------|
| 1 | role-description on load shows analyst copy | text starts "Entry-level deal team…" (len 158) |
| 2 | VP radio click → "Vice President" | text begins "Vice President. Extended access…" |
| 3 | Partner radio click → Partner copy | text begins "Partner-level. Full corpus access…" |
| 4 | `.example-btn` (partner) updates role-description | after-click mentions "Partner"; stale "analyst" absent |
| 5 | "internamos" typo absent from rendered HTML | substring not found |
| 6 | Evals mode hides search-section + role-description | `search_hidden=True`, `role_desc_visible=False` |
| 7 | Admin mode hides role-description | `role_desc_visible=False` |
| 8 | `#empty-state` has exactly 3 `.onboard-card` | count=3 |
| 9 | onboard cards have valid `data-query`/`role`/`mode` | roles=['analyst','vp','partner'], all `mode=compare` |
| 10 | Analyst onboard card → 3-col compare + ≥7 `.flag-blocked` in NAIVE | `compare_active=True`, `cols=3`, `naive_flag_blocked=7` |
| 11 | VP onboard card → VP banner + ≥1 `.compare-stale-badge` in FULL | banner "policy comparison — vp role"; `stale_badges=2` |
| 12 | Partner onboard card → FULL column shows `0 BLOCKED` | regex `0\s*\n\s*BLOCKED` matched |
| 13 | 0 JS console errors across all interactions | errors=[] |
| 14 | Compare column headers exact | ['No Filters','Permissions Only','Full Pipeline'] (MUST-A P3 regression clean) |
| 15 | Evals `.evals-narrative` ≥3 sentences | n=3, first "Zero permission violations across 8 test queries…" (MUST-C regression clean) |

---

### Current State

- **Branch:** `codex/must-a-idea1-2`
- **Last commit before this session:** `e1e3513` (MUST-D docs). SHOULD-A code + docs committed in this session.
- **Working tree:** clean after commit.
- **Tests:** 172 passed, 14 skipped, 0 failed.
- **Evaluator:** unchanged (no pipeline touched).
- **Browser verification:** COMPLETE — 15/15 Playwright checks, 0 JS console errors.
- **Hostile review:** not performed (last clean verdict: Session 18).
- **Demo status:** READY.

### Known non-blocking behavior

- **Empty-state destroyed on first query.** `document.getElementById("empty-state")?.remove()` (app.js:setLoadingSingle) is pre-existing behavior — now the removed surface is the onboarding grid. Not newly broken by this batch; call out in case a reviewer flags it. Cards live for a session until the first query runs.

### Stale Docs Updated This Session

- **`CLAUDE.md`** — Single mode description amended to describe the onboard-card grid (3-col → 1-col responsive), the role description paragraph, and the first-query removal behavior.
- **`docs/plans/2026-04-17-should-a-ideas-9-10-plan.md`** — canonical SHOULD-A plan (committed this session).

### Remaining Tasks

No SHOULD-A work remains. Long-standing optional follow-ups from prior sessions unchanged:

1. **(Optional) Remove dead code** — `apply_freshness()` and `filter_by_role()`.
2. **(Optional) Evaluator corpus re-read** — cosmetic.
3. **(Optional) Ephemeral-fs caveat** for MUST-D uploads — already documented.
4. **(Optional) Hostile review** — last clean verdict Session 18; MUST-A/B/C/D + SHOULD-A not rereviewed.

### Suggested First Action

None strictly required — SHOULD-A is complete and committed. If continuing, start the next IDEA / SHOULD-X batch.

---

## Session — 2026-04-17 (Session 27 / **NICE-B — IDEA 11 · Render-style Read-Only Deploy**)

### Summary

Packaging pass. Makes the repo deployable as a single Render web service: FastAPI JSON API + the static `frontend/` served at `/app/`. No business-logic changes. One env flag (`ALLOW_INGEST`) gates the write path; the frontend hides the Admin tab when the server reports it off. All edits are additive or defensive; `tests/test_ingest.py` stays green because the gate defaults to enabled.

### What was done

1. **`src/main.py`**
   - Imported `StaticFiles`. Added `_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")` (CWD-independent resolution, mirroring `_ROLES_PATH`).
   - Added `_ingest_enabled()` helper: reads `os.getenv("ALLOW_INGEST", "true")` per-request, disabled only when the value is `"false"` or `"0"` (case-insensitive).
   - Extended `GET /health` to return `{"status": "ok", "ingest_enabled": <bool>}`.
   - `POST /ingest` now fails fast with `HTTPException(403, "Ingest is disabled on this deployment.")` before reading the request body when ingest is off.
   - Mounted `app.mount("/app", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")` at the bottom of the module — after all JSON routes so nothing is shadowed.
2. **`frontend/app.js`**
   - Replaced hardcoded `API_BASE` with a hostname-aware expression: `localhost` / `127.0.0.1` / empty → `http://localhost:8000`; anything else → `""` (same-origin).
   - Added a non-fatal `/health` probe on page load. When `ingest_enabled === false`, hides the Admin mode button (`.mode-btn[data-mode="admin"]`) and `#admin-section`. Probe failures silently leave Admin visible (keeps `file://` dev working when the server is off).
3. **`Procfile`** (new) — `web: uvicorn src.main:app --host 0.0.0.0 --port $PORT`. Consumable by Render's Start Command and by Railway's buildpack.
4. **`CLAUDE.md`** — new **Deploy (read-only, Render-first)** section covering build/start commands, env vars, `/app/` URL, `/health` capability probe, `API_BASE` matrix, ephemeral-fs caveat, and local quickstart.
5. **`docs/plans/2026-04-17-nice-b-idea-11-plan.md`** — canonical NICE-B plan (added this session).

Not done (explicitly out of scope per plan, P2/P3): no `.python-version` pin, no root redirect to `/app/`, no host-specific config (`render.yaml`, `railway.toml`, `fly.toml`).

### Files affected

- `src/main.py` (static mount, `/health` shape, `/ingest` gate, `_FRONTEND_DIR`, `_ingest_enabled()`)
- `frontend/app.js` (API_BASE resolver + /health capability probe)
- `Procfile` (new)
- `CLAUDE.md` (deploy section)
- `docs/HANDOFF.md` (this entry)
- `docs/plans/2026-04-17-nice-b-idea-11-plan.md` (new)

### Verification evidence

- **Preflight**: `git ls-files artifacts/` confirms three artifacts tracked; `git ls-files | grep -Ei '\\.env|\\.pem|\\.key|credentials|secret'` → empty.
- **JS**: `node --check frontend/app.js` → OK.
- **Tests**: `python3 -m pytest -q` → **172 passed, 14 skipped, 0 failed** (unchanged from baseline).
- **Uvicorn smoke (ingest enabled)**:
  - `GET /health` → `{"status":"ok","ingest_enabled":true}`
  - `GET /app/` → 200, `text/html; charset=utf-8`
  - `GET /app/app.js` → 200, `text/javascript; charset=utf-8`
  - `GET /app/styles.css` → 200, `text/css; charset=utf-8`
  - `POST /query` → 200 with expected `doc_id`s for "ARR growth" / analyst
- **Uvicorn smoke (`ALLOW_INGEST=false`)**:
  - `GET /health` → `{"status":"ok","ingest_enabled":false}`
  - `POST /ingest` → `403 {"detail":"Ingest is disabled on this deployment."}`
  - `POST /query` → 200 (unaffected)
- **Procfile smoke**: `PORT=8000 sh -c "$(grep '^web:' Procfile | sed 's/^web: //')"` → server up, `/health` returns 200.

### Current State (end of Session 27 / handoff)

- **Branch:** `codex/must-a-idea1-2`
- **Last commit:** `0315c59` (SHOULD-A). **NICE-B is still uncommitted** — no commit SHA yet.
- **Working tree (uncommitted NICE-B batch):**
  - Modified: `src/main.py`, `frontend/app.js`, `CLAUDE.md`, `docs/HANDOFF.md`
  - New: `Procfile`, `docs/plans/2026-04-17-nice-b-idea-11-plan.md`
- **Tests:** 172 / 14 / 0 (verified this session, ingest gate default-enabled).
- **Smoke checks:** all green this session — uvicorn default (`/health`, `/app/`, `/app/app.js`, `/app/styles.css`, `/query`), uvicorn with `ALLOW_INGEST=false` (`/health.ingest_enabled=false`, `/ingest` → 403, `/query` → 200), Procfile boot via `PORT=8000 sh -c "$(grep '^web:' Procfile | sed 's/^web: //')"`.
- **JS:** `node --check frontend/app.js` → OK.
- **Browser / Playwright verification:** NOT run this session. The `/app/` static-serving path + the `/health` capability probe (Admin tab hidden when `ingest_enabled=false`) are covered only by curl smokes, not by a full Playwright sweep. Carry forward as the first verification step after commit/deploy.
- **Review verdict:** No hostile review run this session (last clean verdict: Session 18; MUST-A/B/C/D/SHOULD-A/NICE-B not re-reviewed).
- **Demo status:** READY. Local URL: `http://localhost:8000/app/`. Production URL once deployed: `https://<render-host>/app/`.

### Render quick-reference

- **Start command:** `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
- **Build command:** `pip install -r requirements.txt`
- **Env vars:** `ALLOW_INGEST=false` (required for read-only); `PORT` is auto-provided.
- **Deployed route:** `https://<render-host>/app/` (trailing slash required).
- **Caveat:** `/app` without trailing slash 307-redirects; ephemeral filesystem means Admin uploads would not survive redeploys even if enabled.

### Remaining / next steps

1. **Commit NICE-B** — 4 modified + 2 new files listed above. Suggested message mirrors prior batches, e.g. `NICE-B: IDEA 11 — Render-style read-only deploy (/app mount, Procfile, ALLOW_INGEST gate)`.
2. **Playwright sweep at `http://localhost:8000/app/`** — scenarios + Admin-hidden probe with `ALLOW_INGEST=false`. Intentionally deferred from this session.
3. **Deploy to Render** — create web service, set Start/Build commands and `ALLOW_INGEST=false`, verify `https://<host>/app/` reaches the demo.
4. **(Optional, P2 from NICE-B plan)** `.python-version` pin + root (`/`) → `/app/` redirect. Defer unless Render build or UX requires.
5. **Long-standing optional follow-ups (carried forward, unchanged):** remove dead `apply_freshness()` / `filter_by_role()`; cosmetic evaluator corpus re-read; hostile review refresh on MUST-A..NICE-B.

### Doc status at end of Session 27

- `docs/HANDOFF.md` — current (this update).
- `CLAUDE.md` — current (Deploy section added this session under NICE-B).
- `docs/plans/2026-04-17-nice-b-idea-11-plan.md` — current (Execution outcome section present; scope line clarified to Render-first).
- `docs/plans/2026-04-17-should-a-ideas-9-10-plan.md` — updated this session with an Execution outcome section (previously still read as preflight).
- `docs/plans/2026-04-17-must-d-idea-8-plan.md`, `docs/plans/2026-04-17-must-c-ideas-4-6-plan.md`, `docs/plans/2026-04-16-ideas-execution-plan.md` — unchanged, still accurate.
- `docs/plans/2026-04-10-pipeline-integration-plan.md` — unchanged, ARCHIVED banner from 2026-04-16 still holds.
- `roadmap.md` — does not exist in this repo; not referenced anywhere in the plan sequence.

---

## Session — 2026-04-18 (Session 28 / **NICE-A — IDEA 12 + IDEA 13**)

### Summary

Frontend-only polish pass. IDEA 12 adds an `.export-btn` (`⤓ Export JSON`) in Single mode (`.summary-bar`) and Compare mode (`#compare-banner`) that downloads the verbatim `/query` and `/compare` responses as pretty-printed JSON via Blob + `URL.createObjectURL` with a paired revoke. IDEA 13 adds subtle motion: mode-switch fade, result-card + metric-card hover lifts, spinner opacity pulse, and a smooth `max-height` transition on the Decision Trace panel (replacing the old `display: none↔block` toggle). All new motion respects `@media (prefers-reduced-motion: reduce)`. Reuses the existing `--dur: 180ms` / `--ease` tokens.

### Files changed

- `frontend/app.js` — `downloadJSON(data, filename)` helper, Single export button + handler in `renderSingleResult()`, Compare export button append-with-dedupe in `renderCompare()`, `playModeEnter()` + `switchMode()` integration for `.mode-enter` fade-in.
- `frontend/styles.css` — `.export-btn` rules; `.result-card` entrance switched to `@keyframes result-card-in` (translateY 8→0) with hover translateY(-1px); `.trace-body` migrated to max-height + padding transition; `.metric-card` hover translateY(-2px) + shadow; `.btn-spinner` opacity pulse `@keyframes btn-spinner-pulse`; `.mode-enter` + `@keyframes mode-fade`; `@media (prefers-reduced-motion: reduce)` safety net.
- `docs/plans/2026-04-18-nice-a-ideas-12-13-plan.md` (new) — preflight plan committed at the start of this session.
- `CLAUDE.md` — appended NICE-A paragraph under Frontend (export behavior + motion polish + reduced-motion).
- `docs/HANDOFF.md` — this entry.

No backend files, no test files, no deps, no HTML changes. `tests/` untouched.

### Verification

**Baseline + post-edit pytest:** 172 passed, 14 skipped, 0 failed (both runs this session).

**JS syntax:** `node --check frontend/app.js` → OK. **CSS brace balance:** 363 open / 363 close.

**Server freshness check:** `curl -s http://localhost:8000/app/app.js | grep -c downloadJSON` → `3` (helper + 2 call sites; static mount reads from disk per request, no reload needed).

**Playwright sweep (via `webapp-testing` skill) at http://localhost:8000/app/ — 35/35 PASS, 0 JS console errors:**

| Area | Checks |
|---|---|
| Navigate | `/app/` loads with network-idle |
| Single mode | result-card rendered (5 cards for ARR/analyst/full); `.summary-bar` visible; `#export-single` visible with icon + label; download triggers filename `querytrace_analyst_full_policy.json`; payload has `context`, `decision_trace`, `total_tokens` |
| Trace panel | toggle exists; click adds `.open`; `.trace-body` computed `max-height: 4000px` when open; second click removes `.open` (smooth transition observed) |
| Result-card hover | computed transform `matrix(1, 0, 0, 1, 0, -1)` on hover |
| Compare mode | 3 compare columns; `#compare-banner` visible; `#export-compare` visible; exactly 1 `.export-btn` in banner; download filename `querytrace_compare_analyst.json`; payload has `results` (3 policies) + `role`; re-run with VP and Partner scenarios → still exactly 1 export button per render; banner strong text matches new role |
| Evals | 10 `.metric-card`; hover computed transform `matrix(1, 0, 0, 1, 0, -2)` |
| Mode fade | MutationObserver captures `.mode-enter` class add/remove across 3 mode swaps (≥2 events per swap) |
| Blob cleanup | After 10 exports in a row: 10 `createObjectURL` calls, 10 `revokeObjectURL` calls, 0 live URLs left (instrumented at `add_init_script` level before any page JS ran) |
| Console errors | 0 across entire session |
| `prefers-reduced-motion: reduce` | In a fresh context with `reduced_motion="reduce"`, `.mode-enter` computed `animation-name === "none"`; mode switching still works; 0 JS errors |

Saved download artifacts at `/tmp/nicea_downloads/` for both filenames.

### Current State

- **Branch:** `codex/must-a-idea1-2`
- **Last commit before this session:** `d72e5da` (NICE-B). NICE-A commit added in this session.
- **Tests:** 172 / 14 / 0.
- **Evaluator:** unchanged (no pipeline touched).
- **Browser verification:** COMPLETE — 35/35 Playwright assertions, 0 JS console errors, Blob URL pairing verified by instrumentation.
- **Hostile review:** not performed this session (last clean verdict: Session 18).
- **Demo status:** READY.

### Known non-blocking behavior

- **Trace panel `max-height: 4000px` cap.** Current traces observed well under this (a few hundred px); if a reviewer constructs a pathological query with hundreds of blocked docs the body could clip. Acceptable for the demo corpus.
- **Compare-col entrance animation still uses the shared `card-in` keyframe** (`to`-only) with `forwards` — unchanged from before this batch. Only `.result-card` and `.metric-card` were migrated off `forwards`/`both` to let the new hover transforms take effect.

### Remaining Tasks

No NICE-A work remains. Long-standing optional follow-ups unchanged:

1. **(Optional) Remove dead code** — `apply_freshness()` / `filter_by_role()`.
2. **(Optional) Evaluator corpus re-read** — cosmetic.
3. **(Optional) Ephemeral-fs caveat** for MUST-D uploads — already documented.
4. **(Optional, P2 from NICE-B plan)** `.python-version` pin + `/` → `/app/` redirect.
5. **(Optional) Hostile review refresh** on MUST-A..NICE-A.

### Doc status at end of Session 28

- `docs/HANDOFF.md` — current (this entry).
- `CLAUDE.md` — current (NICE-A paragraph appended under Frontend).
- `docs/plans/2026-04-18-nice-a-ideas-12-13-plan.md` — preflight plan from this session; Execution outcome section can be added as a follow-up if desired (not required — this HANDOFF entry carries the evidence).
- All other plan docs — unchanged and still accurate.

---

## Session — 2026-04-23 (Session 30 / **UI-B — Single state coherence**)

### Summary

Frontend-only UX fix. Before this batch, changing the role or policy radio in Single mode updated the controls + descriptive copy but left the previously rendered result on screen, so the `.summary-bar` role/policy chips contradicted the radio selection. Single example buttons also inherited whatever policy radio was checked, making the demo non-deterministic.

UI-B implements two coordinated changes:

1. **Mark-stale banner + require Run** (not auto-rerun, not clear-on-change). When either radio diverges from the `(role, policy)` pair tied to the rendered result, a `#stale-results-banner` (`role="status"` / `aria-live="polite"` / `aria-atomic="true"`) is prepended to `#results-section` reading "Controls changed — press **Run** to refresh these results.", and the section gets a `results-stale` class that fades the summary bar / result cards / blocked section / trace panel to 60% opacity. Cleared on Run, on Single preset click, on mode switch out of Single, and whenever radios match the last-rendered pair. On mode switch into Single, `evaluateSingleStale()` re-runs so round trips (Single → Compare → Single) with a diverged role radio surface the banner on return. All banner logic is gated on the presence of `.summary-bar` in `#results-section` — empty state, skeleton, error, and "no results" views never trigger it.
2. **Deterministic Single example buttons.** The shared `.example-btn` handler now branches on `data-mode`: for `data-mode="single"` it forces `policy=full_policy`, toggles the matching radio, and calls `updatePolicyDescription("full_policy")` so the `#policy-warning` clears if the user previously had "No Filters" selected. Manual form submit still honors the user-selected policy radio; Compare shortcuts and onboard cards (`data-mode="compare"`) are untouched (UI-C scope).

### Files changed

- `frontend/app.js` — module state `_lastRenderedRole` / `_lastRenderedPolicy`; helpers `buildStaleBannerHTML()` / `clearSingleStale()` / `evaluateSingleStale()`; role and policy radio `change` listeners now call `evaluateSingleStale()` after the description update; `.example-btn` click handler forces `full_policy` and syncs the radio for `data-mode="single"` presets and calls `clearSingleStale()` before dispatch; `setLoadingSingle(true)` drops the `results-stale` class before injecting the skeleton; `renderSingleResult` records `_lastRenderedRole/Policy` on successful non-empty render; `switchMode` tracks `leavingSingle` / `enteringSingle` and calls `clearSingleStale` / `evaluateSingleStale` accordingly at the end.
- `frontend/styles.css` — new `.stale-results-banner` block (flex row, icon + text, `--accent-subtle` bg, 3px `--accent` left-border, `--radius-md`, `--font-display` text with `--font-mono` bold "Run"); `@keyframes stale-banner-in` (opacity + translateY(-2px) → 0); `#results-section.results-stale` descendant rules (`opacity: 0.6; transition: opacity var(--dur) var(--ease)`); reduced-motion block extended to disable the banner animation and the opacity transition on dim descendants.
- `CLAUDE.md` — Frontend Single-mode paragraph appended with the deterministic-preset + stale-banner behavior.
- `demo.md` — Section 3 Single bullet gains a "Coherencia de estado (UI-B)" line; Demo D "Cómo llegar" note clarifies that the ARR growth preset forces Full Pipeline.
- `summaryUserExp.md` — Section 4.1 Single mode gains a "Coherencia de controles y resultados (UI-B)" paragraph.
- `docs/plans/2026-04-23-ui-b-single-state-coherence-plan.md` (new) — preflight plan saved at the start of this session.
- `docs/HANDOFF.md` — this entry.

No HTML, backend, test, or dep changes. `tests/` untouched.

### Verification

**Baseline + post-edit pytest (via `.venv/bin/python`):** 172 passed, 14 skipped, 0 failed (both runs this session).

Note: system `python3` runs against a misconfigured global install (`torch.library has no attribute 'register_fake'`), which yields 49 unrelated failures. The project venv is authoritative; out of scope for this batch.

**Playwright sweep at `http://127.0.0.1:8000/app/` — 34/34 PASS, 0 console errors** (script at `/tmp/ui_b_verify.py`, run via `.venv/bin/python`):

| AC | Check | Result |
|---|---|---|
| AC8 | Empty state + role change → no banner | PASS |
| AC5 | Single preset with `naive_top_k` pre-selected: policy radio snaps to `full_policy`, `#policy-warning` hidden, summary-bar reads "Full Pipeline" / "analyst" | PASS (5 sub-checks) |
| AC6 | No banner after Single preset click | PASS |
| AC1 | Role change with rendered result → banner visible, `.results-stale` class set, summary-bar role chip still shows the old role | PASS (3 sub-checks) |
| AC10 | Banner has `role="status"`, `aria-live="polite"`, `aria-atomic="true"` | PASS (3 sub-checks) |
| AC3 | Revert role to match last-rendered → banner gone | PASS |
| AC2 | Policy change → banner visible, `.results-stale` set, summary-bar policy chip still shows old policy | PASS (3 sub-checks) |
| AC4 | Run clears banner; summary-bar policy chip updates to the newly-selected policy | PASS (2 sub-checks) |
| AC7a | Mode switch out of Single while banner visible → banner + class cleared on leave | PASS (2 sub-checks) |
| AC7b | Return to Single with diverged controls → banner re-inserted on entry; Run clears it; summary-bar role chip updated | PASS (3 sub-checks) |
| Regress | Compare: 3 columns + `#export-compare` present | PASS (2 sub-checks) |
| Regress | Evals: 10 metric cards | PASS |
| Regress | Admin tab visible (ingest enabled) | PASS |
| Admin→Single | Prior rendered result still on screen; banner correctly re-inserted when controls diverged (role had been changed to `analyst` by a prior Compare preset) | PASS (2 sub-checks) |
| Admin→Single | After reverting role to match last-rendered, banner cleared; round-trip through Evals → Single with matching controls keeps it clear | PASS (2 sub-checks) |

No backend endpoints were touched. `GET /health` → `{"status":"ok","ingest_enabled":true}` (Admin tab hide logic via `ingest_enabled` probe untouched).

### Current State

- **Branch:** `codex/must-a-idea1-2`
- **Last commit before this session:** `eec9dfd` (Batch UI-A).
- **Tests:** 172 / 14 / 0 under `.venv/bin/python`.
- **Evaluator:** unchanged (no pipeline touched).
- **Browser verification:** COMPLETE — 34/34 Playwright assertions, 0 console errors.
- **Hostile review:** not performed this session.
- **Demo status:** READY.

### Known non-blocking behavior

- **Compare-mode staleness asymmetry.** Changing the role radio while in Compare mode does not dim the Compare columns. Out of scope for UI-B (Compare is UI-C territory). Noted for follow-up.
- **Banner inserted into a hidden `#results-section`** while the user is in Compare mode and changes the role radio. Harmless — the section is `hidden` — and materializes correctly on return to Single via the `enteringSingle` re-evaluation.

### Doc status at end of Session 30

- `docs/HANDOFF.md` — current (this entry).
- `CLAUDE.md` — Frontend Single-mode paragraph updated.
- `demo.md` — Section 3 Single bullet + Demo D row updated.
- `summaryUserExp.md` — Section 4.1 updated with the UI-B coherence paragraph.
- `docs/plans/2026-04-23-ui-b-single-state-coherence-plan.md` — preflight plan; Execution outcome can be appended later if desired (this HANDOFF entry carries the evidence).
- All other plan docs — unchanged and still accurate.

---

## Session — 2026-04-23 (Session 31 / **UI-C — Scenario clarity, navigation, and Compare onboarding**)

### Summary

Frontend-only UX cleanup. Addressed four issues surfaced by the UI-B review and the scenario audit:

1. **Silent mode teleport.** Onboard-cards in the Single empty state carried `data-mode="compare"`, so clicking them switched mode without any affordance. Fixed by splitting each card into a non-interactive `<div>` wrapper with a dual-action row: `Run in Single` (primary, `data-mode="single"`, `full_policy` preset) and `Open in Compare →` (secondary, `data-mode="compare"`). Mode transitions are now always explicit.
2. **Scenario duplication.** The three base stories (Permission Wall / Financial model access / Stale Detection) were repeated across 9 UI entry points. Deduped to 6: 3 empty-state cards + 2 Single row buttons (`Diligence risks`, `IC recommendation` — distinct queries) + 1 Compare row button (`Stale detection →`). Removed: `ARR growth` (Single row), `Analyst wall ↔` and `VP deal view ↔` (Compare row).
3. **Compare had no empty state.** Entering Compare without a prior query showed an empty banner + blank grid. Added `#compare-empty-state` (first child of `#compare-section`) with three preview cards mirroring Single's layout — single-click whole-card affordance (`button.onboard-card.onboard-card-compact`), qualitative hints ("Naive surfaces 12 · RBAC + Full block 7"). `.compare-banner` starts `hidden`; `setLoadingCompare(true)` removes the empty state, reveals the banner, and injects the skeleton.
4. **"Partner view" was narratively weak.** Partner has full corpus access, so the three-column contrast collapsed at "0 blocked everywhere". Renamed and reframed as "Stale Detection" (card title) and `Stale detection →` (shortcut). **Query and role unchanged** (`"What is the investment committee recommendation and LP update for the Meridian acquisition?"` + `role=partner`). The narrative now focuses on the 2 superseded documents (doc_002, doc_007) that the full pipeline demotes 0.5×. Confirmed at runtime: `POST /compare` with this payload returns `demoted_as_stale: ['doc_007', 'doc_002']` in `full_policy`.

Minor interpretive call: Card 2 (VP) renamed from "Stale Detection" → "VP Deal View" (later → "Financial model access" in UI-D3) to resolve the naming collision introduced by the partner-card rename. Query unchanged. Flagged in the preflight plan.

### Files changed

- `frontend/index.html` — restructured three Single empty-state `.onboard-card` entries into `<div>` wrappers with `.onboard-actions` rows containing `.onboard-primary` + `.onboard-secondary` buttons; renamed cards to Permission Wall / Financial model access / Stale Detection with updated hints; dedup shortcut rows (removed `ARR growth`, `Analyst wall ↔`, `VP deal view ↔`; renamed `Partner view ↔` → `Stale detection →`); added `#compare-empty-state` block inside `#compare-section` with three compact preview cards; added `hidden` attribute to `#compare-banner`.
- `frontend/app.js` — `setLoadingCompare(true)` now removes `#compare-empty-state` and reveals the banner (`compareBanner.hidden = false`). No other JS changes; existing `.example-btn` click handler covers both new `.onboard-primary` and `.onboard-secondary` buttons via `data-mode` dispatch with zero branching.
- `frontend/styles.css` — moved `cursor: pointer` and hover-lift off `.onboard-card` base to `button.onboard-card` (scoped to Compare variant only); added `div.onboard-card { cursor: default; }`; added `.onboard-actions` (flex row, 0.5rem gap), `.onboard-primary` (filled accent button), `.onboard-secondary` (outlined ghost button with `→`), `.onboard-card-compact` (tighter padding for Compare variant), `.compare-empty-state` (top/bottom padding). Existing reduced-motion block unchanged (already covers `.onboard-card`).
- `CLAUDE.md` — Single-mode paragraph rewritten to document the dual-action structure; Compare-mode paragraph appended with `#compare-empty-state` behavior; scenario-list paragraph rewritten to document the dedup + entry-point count.
- `demo.md` — Section 2 empty-state + shortcut-row descriptions rewritten; Demo A/B "Cómo llegar" rows point at `Open in Compare →`; Demo C renamed "Partner view" → "Stale detection" with updated narrative; Demo D "Cómo llegar" updated (ARR growth preset removed); Section 5 guión updated; checklist updated.
- `summaryUserExp.md` — §4.2 Compare scenarios block rewritten; §6.1 item 6 updated with new scenario names; §7.1 item 7 updated with the UI-C empty state description.
- `docs/plans/2026-04-23-ui-c-scenarios-and-compare-clarity-plan.md` (new) — preflight plan saved at the start of this session.
- `docs/HANDOFF.md` — this entry.

No HTML template changes outside the onboarding + compare sections. No backend, test, evaluator, or dep changes. `src/` untouched.

### Verification

**Baseline and post-edit pytest (via `.venv/bin/python`):** 172 passed, 14 skipped, 0 failed (both runs this session). System `python3` still produces the out-of-scope 49-failure phantom baseline — do not use it.

**Backend runtime smoke (via `.venv/bin/python -m uvicorn`):**

- `GET /health` (default) → `{"status":"ok","ingest_enabled":true}` · `GET /health` with `ALLOW_INGEST=false` → `{"status":"ok","ingest_enabled":false}`. Admin-hide probe (`probeIngestCapability()`) untouched; logic verified unchanged.
- `POST /query` — analyst + ARR + `full_policy` → `included=5, blocked=7, tokens=571` (UI-B baseline preserved).
- `POST /compare` — partner + IC + LP query (Stale detection shortcut payload) → `full_policy` column reports `inc=12 blk=0 stl=2 drp=0` with `demoted_as_stale: ['doc_007', 'doc_002']`. Both superseded docs surfaced in context and correctly demoted. Verification step 5 satisfied.
- `GET /evals` — returns the full aggregate block (`avg_precision_at_5=0.3`, `avg_recall=1.0`, `permission_violation_rate=0.0`).

**Static DOM / copy audit:**

- Onboard DOM confirmed via `curl /app/`: three `<div class="onboard-card">` containers, six `.example-btn` buttons (3 `.onboard-primary` + 3 `.onboard-secondary`), titles read Permission Wall / Financial model access / Stale Detection, subtitles Analyst / VP / Partner.
- Compare empty state confirmed: three `button.onboard-card.onboard-card-compact` entries, titles match the three base stories, subtitles include the role + query-hint.
- Shortcut-row dedup confirmed: Single row reads `Diligence risks`, `IC recommendation` (no `ARR growth`); Compare row reads `Stale detection →` only (no `Analyst wall ↔`, no `VP deal view ↔`).

**Grep consistency checks:**

- `grep -rn "Partner view" demo.md summaryUserExp.md CLAUDE.md README.md` → references only survive as history notes ("antes: Partner view", "antigua \"Partner view\""). No live UI strings.
- `grep -rn "auto-switch\|teleport" docs/ CLAUDE.md` → only the HANDOFF / plan entries describing the UI-C fix; no stale "auto-switch" descriptions in CLAUDE.md/demo.md.

**Scope-budget check:** `git diff --name-only` shows only `frontend/index.html`, `frontend/app.js`, `frontend/styles.css` plus docs (CLAUDE.md, demo.md, summaryUserExp.md, docs/HANDOFF.md, docs/plans/2026-04-23-ui-c-*.md). Budget respected — 3 frontend files.

**Post-Claude corroboration (Codex):** Playwright smoke passed against a same-origin local server: Single onboard card body does not run or switch modes; `Run in Single` stays in Single with `full_policy`; `Open in Compare →` and Compare preview cards run `/compare`; stale-detection payload returns exactly doc_002 + doc_007 in `decision_trace.demoted_as_stale`; UI-B stale banner still appears after a role divergence; Evals loads; Admin renders by default. Separate `ALLOW_INGEST=false` browser smoke passed: `/health` returns `ingest_enabled:false` and the Admin tab/section are hidden. Docs were also patched to remove stale live instructions that still referenced the removed `ARR growth` button.

### Current State

- **Branch:** `codex/must-a-idea1-2`
- **Last commit before this session:** `063afa3` (Batch UI-B — Single mode state coherence).
- **Tests:** 172 / 14 / 0 under `.venv/bin/python`.
- **Evaluator:** unchanged (no pipeline touched).
- **Browser verification:** backend endpoints + static DOM verified during execution; post-run Codex Playwright corroboration also passed for the critical UI-C flows and `ALLOW_INGEST=false` Admin hide path.
- **Demo status:** READY.

### Known non-blocking behavior

- **Compare row orphan chrome.** The Compare shortcut row now contains a single button (`Stale detection →`). The row label + lone button is coherent but visually sparser than before. Not a regression; noted for future cleanup if another Compare shortcut is ever re-added.
- **Empty states are one-shot.** Both `#empty-state` (Single) and `#compare-empty-state` (Compare) are removed on first query and do not restore for the session. Consistent with UI-A/UI-B behavior.
- **Compare-mode staleness asymmetry** (UI-B note, still open): changing radios in Compare mode does not dim columns. Out of scope for UI-C.

### Doc status at end of Session 31

- `docs/HANDOFF.md` — current (this entry).
- `CLAUDE.md` — Frontend Single + Compare paragraphs + scenario list updated.
- `demo.md` — Sections 2, 4 (A/B/C/D), 5, and 9 updated.
- `summaryUserExp.md` — §4.2, §6.1, §7.1 updated.
- `docs/plans/2026-04-23-ui-c-scenarios-and-compare-clarity-plan.md` — preflight plan for this batch.
- All other plan docs — unchanged and still accurate.

---

## Session — 2026-04-25 (Session 32 / **UI-E — Demo corpus narrative upgrade**)

### Summary

Expanded the authored Meridian / Project Clearwater demo corpus from 12 to 16 documents so the live demo has sharper narrative contrast without changing retrieval or policy logic.

The batch adds four substantive documents:

1. `doc_013` — partner-only legal diligence memo on a pending regulatory inquiry.
2. `doc_014` — partner-only draft IC memo v0.9 recommending defer, superseded by `doc_010`.
3. `doc_015` — public tech-press article with a `$500M` rumored valuation that contrasts with the internal `$340M` model.
4. `doc_016` — VP memo explaining the CTO departure and integration risk.

It also adds a visible `PARTNER-ONLY · DO NOT DISTRIBUTE` header to `doc_010` and `doc_011`, while keeping their core recommendation / LP-update facts inside the first 500 characters consumed by the indexer excerpt path.

### Files changed

- `corpus/documents/` — four new source `.txt` files plus first-line headers on `doc_010` / `doc_011`.
- `corpus/metadata.json` — 16 documents, role visibility now analyst 6 / VP 12 / partner 16, and three stale pairs (`doc_002 -> doc_003`, `doc_007 -> doc_008`, `doc_014 -> doc_010`).
- `evals/test_queries.json` — 12 corpus-grounded queries, adding regulatory, IC draft/final, valuation, and CTO scenarios.
- `artifacts/` — rebuilt FAISS, BM25, and `index_documents.json` from the 16-doc corpus.
- `frontend/app.js`, `frontend/index.html` — role descriptions and live copy updated to 6/16, 12/16, 16/16; eval copy updated to 12 queries; admin doc_type options include the new corpus categories.
- `src/ingest.py`, `tests/test_ingest.py` — upload validation accepts the new seeded doc types (`internal_memo`, `legal_memo`, `news_article`) and tests cover them.
- `tests/test_main.py`, `tests/test_evaluator.py` — evaluator count / precision baseline updated for the 12-query corpus.
- `README.md`, `CLAUDE.md`, `demo.md`, `summaryUserExp.md`, `script_es.md`, `script_en.md`, `docs/backendSummary.md`, `docs/backendSummarySpanish.md` — demo-facing counts, narratives, and metrics updated.
- `docs/plans/2026-04-25-ui-e-demo-corpus-upgrade-plan.md` — execution plan and evidence for this batch.

### Verification

- `.venv/bin/python -m src.indexer` — loaded 16 docs; saved 16 FAISS vectors; saved 16 BM25 docs.
- `.venv/bin/python -m src.evaluator` — 12 queries, 0 failures, `avg_precision_at_5=0.3333`, `avg_recall=1.0000`, `permission_violation_rate=0.0`, `avg_context_docs=11.83`, `avg_total_tokens=1448`, `avg_blocked_count=4.17`, `avg_stale_count=2.08`, `avg_dropped_count=0.0`, `avg_budget_utilization=0.71`.
- `.venv/bin/python -m pytest` — 175 passed, 14 skipped.
- FastAPI smoke via `TestClient`:
  - Analyst ARR compare: No Filters includes 16; Permissions Only / Full Pipeline include 6 and block 10; Full demotes 1 stale doc.
  - VP financial model compare: No Filters includes 16; Permissions Only / Full Pipeline include 12 and block 4; Full demotes 2 stale docs.
  - Partner IC/LP compare: Full Pipeline demotes all 3 stale pairs.
  - Partner draft/final query surfaces `doc_014` with `superseded_by=doc_010`.
  - `/evals` reports `queries_run=12`, `queries_failed=0`, `avg_recall=1.0`, `permission_violation_rate=0.0`.

### Known non-blocking behavior

- `dropped_by_budget` remains `0.0` in the evaluator. The corpus upgrade improves narrative contrast and raises budget utilization, but it does not force budget drops without code or more high-scoring long excerpts.
- Historical plan and handoff entries still mention the older 12-doc / 8-query state as audit history. Current live docs and UI copy reflect the 16-doc / 12-query baseline.
- `top_k * 3` over-retrieval and historical dead-code notes are unchanged.

### Current State

- **Branch:** `codex/must-a-idea1-2`
- **Last commit before this session:** `7a6c6de` (Batch UI-D3 — scenario labels and tooltips reframed).
- **Tests:** 175 passed, 14 skipped under `.venv/bin/python`.
- **Evaluator:** 12 queries, 0 failures, recall 1.0, permission violations 0%.
- **Demo status:** READY for a 16-doc narrative demo after optional browser spot-check.

---

## Session — 2026-04-27 (MET-A: In-Memory Session Query Audit Backend)

### Summary

Added backend support for live session query auditing. Every successful `POST /query` is logged to an in-memory audit store with auto-incrementing IDs starting at q013 (after the 12 benchmark queries). A new `GET /session-audit` endpoint exposes the log.

**What was done:**

1. **Thread-safe audit store** — Module-level `_session_audit` list, `_session_audit_lock` (threading.Lock), `_session_started_at` (UTC timestamp), and `_BENCHMARK_COUNT` (derived from `evals/test_queries.json` at startup, currently 12). All in `src/main.py`.

2. **Audit logging in /query** — After successful pipeline execution and QueryResponse construction, the trace is extracted into an audit entry dict and appended under the lock. ID formula: `q{benchmark_count + live_index:03d}`. Wrapped in try/except with `logger.warning()` — audit failure never breaks the user's query response. `/compare` and `/evals` do not log.

3. **GET /session-audit endpoint** — Returns `{session_started_at, benchmark_count, entries}`. Returns a snapshot copy under the lock. Each entry includes: id, created_at, query, role, policy_name, precision_at_5 (null), recall (null), metrics (included_count, total_tokens, avg_score, avg_freshness_score, blocked_count, stale_count, dropped_count, budget_utilization), doc_ids (included, blocked, stale, dropped).

4. **9 tests** — With a `reset_session_audit` pytest fixture that clears module-level state before each session-audit test. Tests cover: endpoint shape, benchmark_count, q013 start, q013/q014 increment, one-entry-per-query, compare-does-not-append, evals-does-not-append, entry shape, null precision/recall.

5. **Docs** — Updated `CLAUDE.md` with session-audit endpoint documentation. Updated `docs/HANDOFF.md`.

**Key design decisions:**

- In-memory only, no disk persistence. Resets on process restart. Matches existing `_evals_cache` pattern.
- `threading.Lock` (not asyncio.Lock) because FastAPI sync endpoints run on a threadpool.
- ID assignment and append are atomic under the lock.
- Globally shared across all demo visitors in a single process — documented as a demo caveat.
- Audit failures logged as warnings, never propagated to the client.

### Current State

- **Branch:** `main`
- **Tests:** 184 passed, 14 skipped (175 existing + 9 new session-audit tests)
- **Evaluator:** 12 queries, 0 failures, recall 1.0, permission violations 0%
- **No disk artifacts:** No SQLite, no log files, no audit DB created
- **MET-B ready:** Frontend can now fetch `GET /session-audit` to render live queries in the Metrics tab after q001–q012

---

## MET-B: Metrics Dashboard — Benchmark + Session Audit UI

**Commit:** `3567b1d`
**Scope:** Frontend-only — `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`
**Depends on:** MET-A (commit `2513838`)

### What Changed

1. **Benchmark questions fully readable** — Removed 50-char truncation from the per-query table (app.js line 936). Removed `max-width: 320px` from `.evals-query-cell`, set `min-width: 280px`. All 12 benchmark queries now display their full text with natural wrapping.

2. **"Benchmark Questions" section label** — `<h3>` label inserted between metric cards and benchmark table to frame the 12 rows as a labeled test suite.

3. **Session Audit section** — New `#session-audit-content` container in `index.html`, rendered by `fetchSessionAudit()` + `renderSessionAudit()` in `app.js`. Fetches `GET /session-audit` on every Metrics tab switch (not gated by a loaded flag). Shows:
   - "Session Audit" heading with session start timestamp and query count
   - Public-demo disclaimer banner
   - Table with columns: Query (full text), Time (relative with ISO tooltip), Role, Policy (human label from `POLICY_META`), Docs, Tokens, Freshness (N/A for `naive_top_k`/`permission_aware`), Blocked, Stale, Dropped, Budget
   - Expandable doc ID chips per entry (▸ docs / ▾ docs toggle) with color-coded included/blocked/stale/dropped chips
   - Empty state: "Run a query in Query mode and it will appear here as q013."

4. **Copy affordances** — Hover-reveal `⎘` copy button on every query cell (benchmark and session audit). Uses `navigator.clipboard.writeText()` with `✓` feedback.

5. **Visual structure** — `<hr class="evals-divider">` separates benchmark footer from session audit. Narrative banner + metric cards + benchmark table remain tied to `/evals` data only.

### Fetch Strategy

- `/evals` fetched once (existing `evalsLoaded` gate, unchanged)
- `/session-audit` fetched on every Metrics tab switch (unconditional)
- No polling
- Failures in `/session-audit` do not break benchmark rendering (independent containers)

### No Backend Changes

MET-A backend is complete and untouched. 184 passed, 14 skipped — identical to pre-MET-B baseline.

### Current State

- **Branch:** `main`
- **Tests:** 184 passed, 14 skipped (no new backend tests — frontend-only batch)
- **Verified:** Desktop (1440px) and mobile (375px) layouts, doc expansion, copy buttons, empty state, freshness N/A, query accumulation (q013→q014→q015)
