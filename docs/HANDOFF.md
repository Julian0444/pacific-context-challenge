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

## Session — 2026-04-15 (Session 19 / **IDEA 2 — Enrich DocumentChunk with Metadata**)

### Summary

**Batch label: IDEA 2 — Enrich DocumentChunk with Metadata**

Metadata enrichment pass: propagated `title`, `doc_type`, `date`, and `superseded_by` through the full data chain so the frontend `context[]` array receives those fields on every response. No business logic changed. No tests added or removed.

> **IDEA numbering convention:** Prompts labelled "IDEA N" track discrete feature/enrichment batches applied after the core build. IDEA 1 = (reserved / pre-existing). IDEA 2 = this batch (metadata fields on DocumentChunk).

**What was done:**

1. **`src/retriever.py`** — `_build_results()` now emits `"doc_type": p.get("type")` in addition to the existing `"type"` key. `ScoredDocument` uses `extra="ignore"` so `"type"` was always silently dropped; `doc_type` is the correctly-named key that the model picks up.

2. **`src/models.py`** — Four model additions, all `Optional[str] = None`:
   - `ScoredDocument`: added `doc_type`
   - `FreshnessScoredDocument`: added `doc_type`
   - `IncludedDocument`: added `title`, `doc_type`, `date`, `superseded_by`
   - `DocumentChunk`: added `title`, `doc_type`, `date`, `superseded_by`

3. **`src/stages/freshness_scorer.py`** — `FreshnessScoredDocument(...)` constructor now passes `doc_type=doc.doc_type`.

4. **`src/stages/budget_packer.py`** — `IncludedDocument(...)` constructor now passes `title`, `doc_type`, `date`, `superseded_by`.

5. **`src/main.py`** — Both `DocumentChunk(...)` constructors (in `query()` and `compare()`) now pass `title`, `doc_type`, `date`, `superseded_by` from `inc`.

**Note:** `roadmap.md` was deleted before this session (shows `D` in git status). No further work items are carried forward from it.

### Current State

- **Branch:** `main`
- **Last commit:** `10a5395` (Next steps)
- **Working tree (uncommitted):**
  - `docs/HANDOFF.md` — this update
  - `src/retriever.py` — `doc_type` field added to `_build_results()`
  - `src/models.py` — `doc_type` on `ScoredDocument`/`FreshnessScoredDocument`; four new fields on `IncludedDocument`/`DocumentChunk`
  - `src/stages/freshness_scorer.py` — `doc_type` passed through
  - `src/stages/budget_packer.py` — four fields passed through to `IncludedDocument`
  - `src/main.py` — both `DocumentChunk` constructors updated
  - `roadmap.md` — deleted
- **Tests:** 149 passed, 14 skipped, 0 failed (verified this session)
- **Evaluator:** precision@5=0.3000, recall=1.0000, permission_violation_rate=0% (unchanged)
- **Browser verification:** Not performed this session (last verified in Session 18 — 65/65 Playwright checks)
- **Hostile review:** Not performed this session (last verdict: `clean`, Session 18)
- **Demo status:** READY (no regressions; all new fields are Optional with default None)

### Remaining Tasks

1. **Commit this batch** — 6 working-tree entries above.
2. **(Optional) Remove dead code** — `apply_freshness()` in `freshness.py` and `filter_by_role()` in `policies.py` are unreachable on the request path; 14 tests already skipped. Safe to delete; no urgency.
3. **(Optional) Evaluator corpus re-read** — `run_evals()` loads roles/metadata independently of `main.py`'s copies. Cosmetic; no correctness impact.

### Suggested First Action

Commit the batch (7 modified/deleted files). No further work is required before submission.
