# Handoff — QueryTrace

---

## Session — 2026-04-05 (Session 1: Project Bootstrap)

### Summary

Bootstrapped the QueryTrace project from scratch:

1. **Repo scaffolding** — Created full project structure. All `src/` Python modules created as stubs with docstrings and `raise NotImplementedError`. Frontend files (`index.html`, `app.js`, `styles.css`) created with working markup and JS that calls `POST /query`. Wrote initial `CLAUDE.md`.

2. **Financial corpus** — Built a 12-document fictional corpus about Atlas Capital Partners evaluating the acquisition of Meridian Technologies ("Project Clearwater"). Documents span public filings, research notes, deal memos, financial models, internal emails, board materials, and an LP update. Two explicit stale/superseded pairs (doc_002→doc_003, doc_007→doc_008). Three role levels enforced via `min_role`. `corpus/metadata.json` and `corpus/roles.json` created.

3. **Indexing and retrieval** — Implemented `src/indexer.py` and `src/retriever.py`. The indexer embeds with `all-MiniLM-L6-v2` and builds a FAISS `IndexFlatIP` (cosine similarity via normalized vectors). Artifacts persisted to `artifacts/`. Retriever loads the index and returns top-k results with full metadata.

### Current State

- **Branch:** `main`, commit `6e55da7` (Initial commit)
- All work was uncommitted at end of session.

---

## Session — 2026-04-05 (Session 2: Pipeline Implementation)

### Summary

Implemented the full retrieval pipeline using TDD (test-first for each module), wired the API endpoint, and updated `CLAUDE.md` to reflect the implemented state.

**What was done:**

1. **Fixed role default** in `src/models.py` — changed `QueryRequest.role` default from `"viewer"` to `"analyst"` to match corpus role definitions.

2. **Implemented `src/policies.py`** — `load_roles()` reads `corpus/roles.json` and returns the roles dict. `filter_by_role()` compares the requesting role's `access_rank` against each document's `min_role` rank. Unknown roles raise `ValueError`. (6 tests)

3. **Implemented `src/freshness.py`** — `compute_freshness()` uses exponential decay (`exp(-ln2 × age_days / half_life_days)`). `apply_freshness()` attaches `freshness_score` to each chunk and applies a 0.5× multiplicative penalty for superseded documents (`superseded_by != null`). Stale docs are demoted, not removed. (7 tests)

4. **Implemented `src/context_assembler.py`** — Ranks chunks by a 50/50 weighted combination of similarity score and freshness score. Greedily packs chunks into a token budget (default 2048) using `tiktoken` (`cl100k_base` encoding). Falls back from `content` to `excerpt` key. Returns `(context_list, total_tokens)`. (5 tests)

5. **Wired `src/main.py`** — Connected `POST /query` to the full pipeline: `retrieve → filter_by_role → apply_freshness → assemble`. Added CORS middleware. Roles and metadata loaded once at startup. Invalid roles return HTTP 400. (6 tests)

6. **Updated `CLAUDE.md`** — Rewrote to reflect actual implemented architecture, commands, and remaining stubs.

**Key design decisions:**

- Data flows as plain dicts between pipeline stages (not Pydantic models). Conversion to `DocumentChunk` happens only at the response boundary in `main.py`.
- The assembler uses `excerpt` (first 500 chars from indexer) when full `content` is not in the chunk — this is the case for retriever results.
- Stale penalty is a constant `STALE_PENALTY = 0.5` in `freshness.py`.

### Current State

- **Branch:** `main`
- **Commits:** `6e55da7` (Initial commit), `24c34a8` (Initial implementation)
- **Working tree:** clean (all changes committed)
- **Tests:** 24 passing (0 failing)
  - `tests/test_policies.py` — 6 tests
  - `tests/test_freshness.py` — 7 tests
  - `tests/test_context_assembler.py` — 5 tests
  - `tests/test_main.py` — 6 tests
- **Server:** `POST /query` verified working end-to-end via `curl`
- **FAISS index:** built and persisted in `artifacts/` (12 vectors, 384 dimensions)

### Remaining Tasks (ordered)

1. **Fix frontend role dropdown** — `frontend/index.html` has stale options (`viewer`, `analyst`, `admin`). Should be `analyst`, `vp`, `partner` to match `corpus/roles.json`. The `app.js` already sends the selected value correctly.

2. **Implement `src/evaluator.py`** — All three functions (`load_test_queries`, `precision_at_k`, `run_evals`) still raise `NotImplementedError`. Should load queries from `evals/test_queries.json`, run them through the pipeline, and compute precision@k.

3. **Populate `evals/test_queries.json`** — Current file has two placeholder entries with empty `expected_doc_ids` and one uses the invalid role `"viewer"`. Needs real test queries with expected document IDs based on the corpus and role access rules.

4. **Decide on `artifacts/` gitignore** — The FAISS index and payloads are binary/generated files (~2MB). Either commit them for convenience or add to `.gitignore` and require `python3 -m src.indexer` after clone.

5. **Frontend polish** — `app.js` renders `chunk.content` (which is the 500-char excerpt) and shows similarity `score`, but doesn't display `freshness_score` or `tags`. Consider showing these for debugging/demo purposes.

### Blockers and Warnings

- **Python 3.9 environment:** System Python is 3.9.6 with LibreSSL 2.8.3. `tf-keras` was installed to work around a Keras 3 incompatibility in `sentence-transformers`. Upgrading dependencies may break this.
- **Freshness scores are very small:** All corpus documents are from 2023–2024, so with the default `half_life_days=30` and a current date in 2026, freshness scores are near zero (e.g., `2.1e-08`). This means the assembler ranking is dominated by similarity score in practice. Consider increasing `half_life_days` or using the document dates relative to each other rather than absolute age.
- **No `__init__.py` in `src/`:** The package works because imports use `src.module` syntax and the repo root is on `sys.path`, but adding one may be needed for certain tooling.

### Suggested First Action

Fix the frontend role dropdown in `frontend/index.html` (change options to `analyst`/`vp`/`partner`) — it's a one-minute fix and makes the UI functional for demos. Then tackle the evaluator.

---

## Session — 2026-04-05 16:30 (Session 3: Evaluation Harness)

### Summary

Implemented the full evaluation harness (`src/evaluator.py`) and replaced placeholder eval queries with 8 realistic, corpus-grounded test cases covering all required scenario types.

**What was done:**

1. **Implemented `src/evaluator.py`** — Three functions fully implemented:
   - `load_test_queries(path)` — loads and validates query dicts from JSON.
   - `precision_at_k(retrieved_ids, expected_ids, k)` — standard P@k with denominator clamped to `min(k, len(retrieved))` to avoid penalizing short results caused by role filtering or budget.
   - `run_evals(queries, k, top_k, token_budget)` — runs the full pipeline (`retrieve → filter_by_role → apply_freshness → assemble`) for each query and returns per-query and aggregate metrics.
   - Metrics computed: precision@k, recall, permission_violation_rate, avg_context_docs, avg_total_tokens, avg_freshness_score.
   - CLI entry point: `python3 -m src.evaluator` (with `--k`, `--top-k`, `--token-budget` flags).

2. **Replaced `evals/test_queries.json`** — 8 real queries based on the Atlas Capital / Meridian corpus, each with `expected_doc_ids`, `forbidden_doc_ids` (where relevant), and a `notes` field explaining the intent:
   - q001: ARR/NRR normal retrieval (analyst)
   - q002: Summit Financial estimate revision / stale doc (analyst)
   - q003: Permissions wall — analyst blocked from 5 vp/partner docs in raw top-8 (analyst)
   - q004: Customer concentration breakdown (vp)
   - q005: Financial model v1 vs v2 revision (vp)
   - q006: IC recommendation and deal structure (partner)
   - q007: Integration risks and CTO departure (vp)
   - q008: LP quarterly update / partner-only reporting (partner)

3. **Added `tests/test_evaluator.py`** — 16 tests: 6 unit tests for `precision_at_k`, 4 for `load_test_queries`, and 6 integration tests running the full pipeline.

**Key design decisions:**

- Evaluates against the **final assembled context** (not raw retriever candidates), since that is what QueryTrace surfaces to users.
- `precision_at_k` clamps k to `len(retrieved)` — a context of 3 docs (due to analyst filtering) should not be scored as if 5 were expected.
- `forbidden_doc_ids` used only where a role boundary is meaningfully tested (q003 analyst, q004/q007 vp). Partner queries have no forbidden docs since partner sees everything.
- Pipeline imports are deferred inside `run_evals()` to avoid loading the sentence-transformer model at import time.

**Observed eval results (actual pipeline output):**
- Avg Precision@5: **0.3354** — low because assembled context contains many semantically adjacent docs beyond the narrow expected set.
- Avg Recall: **1.0000** — all expected docs are found within the 2048-token budget.
- Permission violation rate: **0%** — role filtering is working correctly across all 8 queries.
- Avg freshness score: **2.0e-08** — confirms the freshness-dominates-nothing issue (see Blockers).

### Current State

- **Branch:** `main`
- **Commits:** `6e55da7` (Initial commit), `24c34a8` (Initial implementation)
- **Working tree:** uncommitted changes in `src/evaluator.py`, `evals/test_queries.json`, `docs/HANDOFF.md`; untracked `tests/test_evaluator.py`
- **Tests:** 40 passing (0 failing)
  - `tests/test_policies.py` — 6 tests
  - `tests/test_freshness.py` — 7 tests
  - `tests/test_context_assembler.py` — 5 tests
  - `tests/test_main.py` — 6 tests
  - `tests/test_evaluator.py` — 16 tests

### Remaining Tasks (ordered)

1. **Fix frontend role dropdown** — `frontend/index.html` has options `viewer`, `analyst`, `admin`. Change to `analyst`, `vp`, `partner`.

2. **Fix freshness half-life** — With `half_life_days=30` and a corpus from 2023–2024, all freshness scores are ~1e-8 by 2026. The stale demotion (0.5× penalty) is invisible at this scale. Options: (a) increase `half_life_days` to ~365 so scores are distinguishable, or (b) compute freshness relative to the newest document in the corpus rather than absolute calendar time. This is the highest-impact quality fix.

3. **Commit all uncommitted work** — `src/evaluator.py`, `evals/test_queries.json`, `tests/test_evaluator.py`, `docs/HANDOFF.md` are all modified/untracked and need a commit.

4. **Decide on `artifacts/` gitignore** — FAISS index and payloads are binary/generated. Either commit them (convenience) or add to `.gitignore` and document `python3 -m src.indexer` as a setup step.

5. **Frontend polish** — `app.js` shows `score` but not `freshness_score` or `tags`. Low priority but useful for demos.

### Blockers and Warnings

- **Freshness scores are effectively zero:** `half_life_days=30` with 2-year-old corpus makes all freshness scores ~1e-8. The 0.5× stale penalty in `freshness.py` has no observable effect on ranking since `0.5 × 1e-8 ≈ 1e-8`. Fix by raising `half_life_days` to ~365 in `freshness.py` (`STALE_PENALTY` and decay both need updating for the effect to be visible in evals).
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed to work around Keras 3 incompatibility. Upgrading deps may break this.
- **No `__init__.py` in `src/`:** Works via `src.module` import style with repo root on `sys.path`. Certain tooling (e.g., mypy, some IDEs) may need it.

### Suggested First Action

Fix the freshness half-life in `src/freshness.py` — change `half_life_days=30` default to `365` (or make it corpus-relative). Re-run `python3 -m src.evaluator` and confirm that stale docs (doc_002, doc_007) rank visibly below their current replacements (doc_003, doc_008) in the assembled context output. This is the single change that makes the freshness feature meaningful.

---

## Session — 2026-04-05 (Session 4: Corpus-Relative Freshness)

### Summary

Fixed the freshness scoring problem so stale-document demotion is meaningful and visible in eval output.

**What was done:**

1. **Switched to corpus-relative freshness** in `src/freshness.py` — age is now measured from the newest document in the corpus (`max(doc dates)` = `2024-04-18`), not from the current calendar date. This makes freshness scores time-independent: they remain in a useful 0.5–1.0 range regardless of when the eval runs. Added a `reference_date` parameter to `compute_freshness()`; `apply_freshness()` derives it automatically from the metadata.

2. **Changed `half_life_days` default** from 30 to 365 — appropriate for a corpus spanning ~10 months (2023-06 to 2024-04).

3. **Updated `tests/test_freshness.py`** — added 5 new tests for corpus-relative behavior: explicit reference_date, newer-vs-older comparison, meaningful score range, and visible stale-pair demotion gap (>0.3). All 7 original tests still pass unchanged (they explicitly passed `half_life_days=30`).

4. **Added evaluator freshness assertion** in `tests/test_evaluator.py` — `test_run_evals_freshness_is_meaningful` asserts `avg_freshness_score > 0.1` to prevent regression.

**Impact on eval output:**

| Metric | Before | After |
|--------|--------|-------|
| avg_freshness_score | 2.0e-08 | **7.58e-01** |
| Stale doc ranking | indistinguishable from fresh | visibly demoted |

Concrete ranking improvements:
- q001: `doc_003` (current Q4 note) now ranks above `doc_002` (stale Q3 note)
- q003: `doc_005` (correct answer) now ranks first (freshness tiebreak)
- q007: `doc_009` + `doc_006` now rank 1st/2nd instead of stale `doc_002` being ahead

**Key design decision:** Corpus-relative dating was chosen over simply increasing `half_life_days` because it produces time-independent scores. Running the evaluator in 2026 or 2030 yields the same results.

### Current State

- **Branch:** `main`
- **Commits:** `6e55da7` (Initial commit), `24c34a8` (Initial implementation)
- **Working tree:** uncommitted changes in `src/freshness.py`, `src/evaluator.py`, `evals/test_queries.json`, `tests/test_freshness.py`, `docs/HANDOFF.md`; untracked `tests/test_evaluator.py`
- **Tests:** 46 passing (0 failing)
  - `tests/test_policies.py` — 6 tests
  - `tests/test_freshness.py` — 12 tests
  - `tests/test_context_assembler.py` — 5 tests
  - `tests/test_main.py` — 6 tests
  - `tests/test_evaluator.py` — 17 tests

### Remaining Tasks (ordered)

1. ~~Fix freshness half-life~~ — **Done.** Corpus-relative freshness implemented, stale demotion is visible.

2. **Fix frontend role dropdown** — `frontend/index.html` has options `viewer`, `analyst`, `admin`. Change to `analyst`, `vp`, `partner`.

3. **Commit all uncommitted work** — Everything from Sessions 3 and 4 is uncommitted: `src/evaluator.py`, `src/freshness.py`, `evals/test_queries.json`, `tests/test_evaluator.py`, `tests/test_freshness.py`, `docs/HANDOFF.md`.

4. **Decide on `artifacts/` gitignore** — FAISS index and payloads are binary/generated. Either commit them (convenience) or add to `.gitignore` and document `python3 -m src.indexer` as a setup step.

5. **Frontend polish** — `app.js` shows `score` but not `freshness_score` or `tags`. Low priority but useful for demos.

### Blockers and Warnings

- ~~**Freshness scores are effectively zero**~~ — **Resolved.** Corpus-relative dating produces scores in 0.5–1.0 range.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed to work around Keras 3 incompatibility. Upgrading deps may break this.
- **No `__init__.py` in `src/`:** Works via `src.module` import style with repo root on `sys.path`. Certain tooling (e.g., mypy, some IDEs) may need it.

### Suggested First Action

Fix the frontend role dropdown (`frontend/index.html` — change `viewer`/`analyst`/`admin` to `analyst`/`vp`/`partner`), then commit all uncommitted work from Sessions 2–4.

---

## Session — 2026-04-06 (Session 5: Commit & Consolidation)

### Summary

All work from Sessions 3 and 4 (evaluator harness, test queries, corpus-relative freshness) was committed in a single commit.

- **Commit `5e2db23`** — "Task 5": includes `src/evaluator.py`, `src/freshness.py`, `evals/test_queries.json`, `tests/test_evaluator.py`, `tests/test_freshness.py`, `docs/HANDOFF.md`.

No code changes were made in this session beyond the commit.

### Current State

- **Branch:** `main`
- **Commits:** `6e55da7` (Initial commit) → `24c34a8` (Initial implementation) → `5e2db23` (Task 5)
- **Working tree:** clean (untracked files are only auto-generated skill definitions in `.claude/skills/` and `.agents/`, not project code)
- **Tests:** 46 passing (0 failing)
  - `tests/test_policies.py` — 6 tests
  - `tests/test_freshness.py` — 12 tests
  - `tests/test_context_assembler.py` — 5 tests
  - `tests/test_main.py` — 6 tests
  - `tests/test_evaluator.py` — 17 tests

### Remaining Tasks (ordered)

1. **Fix frontend role dropdown** — `frontend/index.html` has options `viewer`, `analyst`, `admin`. Change to `analyst`, `vp`, `partner`. One-minute fix.

2. **Decide on `artifacts/` gitignore** — FAISS index and payloads are binary/generated (~2MB). Either commit them or add to `.gitignore` and require `python3 -m src.indexer` after clone.

3. **Frontend polish** — `app.js` shows `score` but not `freshness_score` or `tags`. Low priority but useful for demos.

### Blockers and Warnings

- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed to work around Keras 3 incompatibility. Upgrading deps may break this.
- **No `__init__.py` in `src/`:** Works via `src.module` import style with repo root on `sys.path`. Certain tooling (e.g., mypy, some IDEs) may need it.

### Suggested First Action

Fix the frontend role dropdown in `frontend/index.html` — change the three `<option>` values from `viewer`/`analyst`/`admin` to `analyst`/`vp`/`partner`. Then open the page in a browser and verify `POST /query` works with each role.

---

## Session — 2026-04-06 (Session 6: Frontend Redesign)

### Summary

Complete frontend redesign from the basic scaffold into a polished, demo-ready interface. Fixed the stale role dropdown and rebuilt all three frontend files from scratch.

**What was done:**

1. **Fixed role alignment** — Replaced `viewer`/`analyst`/`admin` with `analyst`/`vp`/`partner` as radio-chip toggles. Zero occurrences of old invalid roles remain.

2. **Redesigned the UI** — "Midnight Analysis Desk" aesthetic: dark navy-black base (`#08090d`), warm amber/gold accent (`#c8a55a`), Bricolage Grotesque display font, IBM Plex Mono for data. Designed as an internal analysis/context-inspection tool, not a generic search page.

3. **Added rich data display** — Each result card now shows:
   - `doc_id` with rank number
   - Content excerpt (4-line clamp)
   - Relevance score as horizontal bar + numeric value
   - Freshness score as horizontal bar + numeric value
   - Tags as muted pills
   - Left accent stripe colored by score quality (green/amber/red)
   - Summary bar above results: document count, token count, role

4. **Added UX improvements:**
   - 3 example query buttons ("ARR growth", "DD risks", "IC memo") that auto-fill query + role and submit
   - Loading state with skeleton cards and shimmer animation
   - Network-specific error messaging ("Backend unavailable" with start command vs API errors)
   - Empty state with hexagon icon and description of what QueryTrace does
   - No-results state for empty context arrays
   - Spinner on submit button during loading
   - `top_k=8` default aligned with project direction

5. **Verified end-to-end** — Server started, `POST /query` tested with all three roles, invalid role returns 400, all data fields (score, freshness_score, tags, total_tokens, doc_id) rendered correctly. 46 tests still passing.

**Design decisions:**
- Static HTML + CSS + vanilla JS (no frameworks, no build step)
- Google Fonts loaded from CDN (Bricolage Grotesque, IBM Plex Mono)
- CSS variables for full theme consistency
- Responsive layout (mobile stacks search row and metrics)
- `escapeHTML()` used for all user/API content to prevent XSS

### Current State

- **Branch:** `main`
- **Commits:** `6e55da7` → `24c34a8` → `5e2db23` (Task 5)
- **Working tree:** modified `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, `docs/HANDOFF.md`
- **Tests:** 46 passing (0 failing)

### Remaining Tasks (ordered)

1. ~~Fix frontend role dropdown~~ — **Done.** Roles are `analyst`/`vp`/`partner`.

2. ~~Frontend polish~~ — **Done.** Score, freshness_score, tags, total_tokens all rendered with metric bars and pills.

3. **Commit frontend work** — `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, `docs/HANDOFF.md` are modified and uncommitted.

4. **Decide on `artifacts/` gitignore** — FAISS index and payloads are binary/generated (~2MB). Either commit them or add to `.gitignore` and require `python3 -m src.indexer` after clone.

### Blockers and Warnings

- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed to work around Keras 3 incompatibility. Upgrading deps may break this.
- **No `__init__.py` in `src/`:** Works via `src.module` import style with repo root on `sys.path`. Certain tooling may need it.
- **Google Fonts dependency:** Frontend loads Bricolage Grotesque and IBM Plex Mono from `fonts.googleapis.com`. If offline, falls back to `system-ui` and `Menlo`/`monospace`.

### Suggested First Action

Commit the frontend changes, then open `frontend/index.html` in a browser with the server running (`uvicorn src.main:app --reload`) and click each example query button to confirm the full demo flow works visually.
