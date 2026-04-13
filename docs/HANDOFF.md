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

---

## Session — 2026-04-10 (Session 7: Contract Models & Protocols)

### Summary

Introduced the full Pydantic contract layer (`src/models.py`) and the Protocol interface file (`src/protocols.py`) that will underpin `pipeline.py` + `stages/`. No existing pipeline logic was changed — this session is pure contracts.

**What was done:**

1. **Rewrote `src/models.py`** — 13 typed models covering the full pipeline from upstream to downstream:
   - `UserContext`, `PolicyConfig` — request context and run-time knobs
   - `ScoredDocument` — typed shape for retriever output (`extra="ignore"` to absorb `rank`, `file_name`, `type` keys the retriever adds)
   - `FreshnessScoredDocument` — after `apply_freshness`; adds `freshness_score` + `is_stale`
   - `BlockedDocument`, `StaleDocument`, `IncludedDocument` — decision outcomes for the trace
   - `TraceMetrics`, `DecisionTrace` — observability layer; `DecisionTrace` nests all three outcome lists + metrics
   - `PipelineResult` — internal result before API serialisation; holds `context`, `total_tokens`, optional `trace`
   - `QueryRequest` — backward compat; adds `policy_name: str = "default"` alongside existing `query`/`role`/`top_k`
   - `QueryResponse` — backward compat; adds `decision_trace: Optional[DecisionTrace] = None`; `context` + `total_tokens` unchanged
   - `DocumentChunk` — preserved verbatim; used by the live endpoint

   All domain models: `frozen=True + extra="forbid"`. `ScoredDocument`: `frozen=True + extra="ignore"`. API boundary models: `extra="forbid"` only (no frozen, FastAPI handles construction).

2. **Created `src/protocols.py`** — three `@runtime_checkable` Protocol classes:
   - `RetrieverProtocol` — `(query: str, top_k: int) → List[Dict]`; satisfied by `src.retriever.retrieve` and any BM25/stub alternative
   - `RoleStoreProtocol` — dict-like access to roles; decouples `main.py` load from pipeline stages
   - `MetadataStoreProtocol` — dict-like access to corpus metadata

3. **Created `tests/test_models.py`** — 24 contract tests covering required fields, defaults, immutability, `extra` rejection, and backward-compat API fields.

### Compatibility Decisions

| Decision | Reason |
|----------|--------|
| `ScoredDocument` uses `extra="ignore"` | Retriever returns `rank`, `file_name`, `type` — strict rejection would break ingestion |
| `FreshnessScoredDocument` does NOT inherit `ScoredDocument` | Avoids Pydantic v2 frozen-model inheritance complexity; conversion via `model_dump() \| {...}` |
| `policy_name` added to `QueryRequest` | New field with safe default — existing clients unaffected |
| `decision_trace` is `Optional` in `QueryResponse` | Currently always `null`; existing frontend ignores unknown keys |
| `DocumentChunk` left without frozen/forbid | Active in the live response path — hardening deferred until pipeline.py lands |

### Current State

- **Branch:** `main`
- **Last commit:** `ae7766f` (Task 6 and backend almost done)
- **Working tree:** modified `src/models.py`, `CLAUDE.md`; untracked `src/protocols.py`, `tests/test_models.py`, `docs/HANDOFF.md`
- **Tests:** 70 passing, 0 failing (46 original + 24 new contract tests)
- **Verified:** `POST /query` returns `query`, `context`, `total_tokens` — frontend unbroken

### Remaining Tasks (ordered)

1. **Commit this session's work** — `src/models.py`, `src/protocols.py`, `tests/test_models.py`, `docs/HANDOFF.md`.

2. **Implement `src/pipeline.py`** — Orchestrator that wires `RetrieverProtocol → filter_by_role → apply_freshness → assemble` using the new typed models; replaces the inline logic in `main.py`. Should populate `DecisionTrace` as it runs.

3. **Implement `src/stages/`** — Individual stage functions typed against the new models (input/output as Pydantic models, not dicts).

4. **Wire `main.py` to `pipeline.py`** — Replace the current inline pipeline with a call to the new orchestrator; `decision_trace` in the response will then be non-null.

5. **Hybrid retrieval** — BM25 + semantic fusion (satisfies `RetrieverProtocol`; no changes to downstream stages needed).

6. **Decide on `artifacts/` gitignore** — FAISS index is ~2MB binary. Commit for convenience or `.gitignore` + document `python3 -m src.indexer`.

### Blockers and Warnings

- **`ScoredDocument` not yet used by live pipeline** — The retriever still returns raw dicts; `pipeline.py` will need `ScoredDocument.model_validate(raw_dict)` at the ingestion boundary.
- **`CLAUDE.md` stale** — Says `evaluator.py` is not implemented and `evals/test_queries.json` has placeholders. Both are wrong. Needs a one-time cleanup.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed to work around Keras 3 incompatibility.
- **Google Fonts dependency:** Frontend loads from CDN; falls back to system fonts offline.

### Suggested First Action

Commit the session work, then start `src/pipeline.py`: define `run_pipeline(request: QueryRequest, retriever: RetrieverProtocol, roles: RoleStoreProtocol, metadata: MetadataStoreProtocol) → PipelineResult` and move the inline logic from `main.py` into it, converting each stage's dict output to the appropriate typed model.

---

## Session — 2026-04-11 (Session 8: Pipeline Orchestrator)

### Summary

Implemented the explicit pipeline orchestrator (`src/pipeline.py`), introduced policy presets, and rewired `main.py` to be a minimal HTTP boundary. All existing tests pass unchanged alongside 18 new pipeline integration tests.

**What was done:**

1. **Created `src/pipeline.py`** — Five-stage orchestrator with abort-on-first-failure semantics:
   - `_retrieve_stage` — calls `RetrieverProtocol`, validates each result into `ScoredDocument`
   - `_permission_stage` — compares access ranks, produces `(permitted, List[BlockedDocument])`
   - `_freshness_stage` — wraps existing `apply_freshness`, produces `(List[FreshnessScoredDocument], List[StaleDocument])`
   - `_assemble_stage` — wraps existing `assemble()` or bypasses budget when `skip_budget=True`
   - `_build_trace` — assembles `DecisionTrace` from all stage outputs
   - Each stage returns `StageOk | StageErr`. `_unwrap()` raises `PipelineError` on `StageErr`.
   - `run_pipeline()` is the single public entry point.

2. **Introduced policy presets in `src/policies.py`**:
   - `naive_top_k` — dangerous baseline: retrieval only, no permission filter, no freshness, no budget enforcement (`skip_permission_filter=True`, `skip_freshness=True`, `skip_budget=True`)
   - `permission_aware` — retrieval + RBAC, no freshness, budget enforced (`skip_freshness=True`)
   - `full_policy` — full pipeline: RBAC + freshness + budget
   - `default` — alias for `full_policy`
   - `resolve_policy(name, top_k)` resolves a preset and applies the request's `top_k` override

3. **Extended `PolicyConfig`** in `src/models.py` — added `skip_permission_filter`, `skip_freshness`, `skip_budget` (all default `False`, backward-compatible)

4. **Rewired `src/main.py`** — Now a minimal HTTP boundary: validate role → `run_pipeline()` → map `PipelineResult` to `QueryResponse`. No pipeline business logic remains. `decision_trace` is now populated in every response.

5. **Fixed protocol definitions** (P0-1, P0-2 from integration plan):
   - `MetadataStoreProtocol` — updated to match actual raw metadata shape (`metadata["documents"]` → list)
   - `RoleStoreProtocol.keys()` — return type changed from `List[str]` to `Iterable[str]`

6. **Added `token_count` to assembler output** (P1-1) — `context_assembler.py` now includes `token_count` in each output dict, required by `IncludedDocument`

7. **Created `tests/test_pipeline.py`** — 18 integration tests covering:
   - Happy path (default, full_policy)
   - Trace metrics, user context, policy config in trace
   - Analyst blocked docs in trace, partner sees all
   - Stale docs in trace
   - Token budget enforcement, small budget limits context
   - All three policy presets (naive_top_k, permission_aware, full_policy)
   - Retriever failure → PipelineError, empty retrieval, invalid policy name

**Key design decisions:**

| Decision | Reason |
|----------|--------|
| Wrap existing stage functions, don't rewrite | Avoid breaking existing tests; typed stages deferred to P3 |
| `StageOk` / `StageErr` dataclasses, not exceptions | Each stage result is inspectable; pipeline controls flow, not exceptions |
| `PipelineError` exception for abort | Clean for the HTTP boundary to catch and map to 500 |
| Permission check reimplemented in pipeline (not calling `filter_by_role`) | Avoids model→dict→model roundtrip; logic is 3 lines |
| `naive_top_k` skips budget | Spec requires it as the dangerous baseline — retrieval only |
| `resolve_policy` uses `model_copy(update=...)` for top_k override | PolicyConfig is frozen; can't mutate |

### Current State

- **Branch:** `main`
- **Last commit:** `ae7766f` (Task 6 and backend almost done)
- **Working tree:** modified `src/models.py`, `src/protocols.py`, `src/policies.py`, `src/context_assembler.py`, `src/main.py`, `CLAUDE.md`, `docs/HANDOFF.md`; untracked `src/pipeline.py`, `tests/test_pipeline.py`, `tests/test_models.py`, `docs/plans/`
- **Tests:** 88 passing (0 failing)
  - `tests/test_policies.py` — 6 tests
  - `tests/test_freshness.py` — 12 tests
  - `tests/test_context_assembler.py` — 5 tests
  - `tests/test_main.py` — 6 tests
  - `tests/test_evaluator.py` — 17 tests
  - `tests/test_models.py` — 24 tests
  - `tests/test_pipeline.py` — 18 tests
- **Endpoint verified:** `POST /query` returns `query`, `context` (with doc_id/content/score/freshness_score/tags), `total_tokens`, and `decision_trace`
- **Frontend compatible:** response shape unchanged for existing fields; `decision_trace` is additive

### Remaining Tasks (ordered)

1. **Commit all uncommitted work** — Session 7 (models, protocols, test_models) and Session 8 (pipeline, policies, main rewire, assembler fix, test_pipeline, plans).

2. **Wire `evaluator.py` to `pipeline.py`** (P2-3) — Replace the duplicated inline pipeline in `run_evals()` with calls to `run_pipeline()`. Extract metrics from `PipelineResult.trace`.

3. **Create `src/stages/`** with typed stage functions (P3-1) — Each function accepts and returns Pydantic models, replacing dict↔model conversion in pipeline.py.

4. **Refactor `freshness.py`** to return new dicts instead of mutating in-place (P3-2) — Required before P3-1 can fully land.

5. **Clean up `CLAUDE.md`** (P3-3) — Remove stale claims about evaluator and test_queries.

6. **Decide on `artifacts/` gitignore** — FAISS index is ~2MB binary.

### Blockers and Warnings

- **`evaluator.py` still has its own inline pipeline** — Runs retrieve → filter → freshness → assemble independently. Should be wired to `run_pipeline()` to avoid logic divergence.
- **`freshness.py` mutates dicts in-place** — Incompatible with frozen Pydantic models. The pipeline works around this by converting to/from dicts at the boundary, but typed stages (P3-1) require this to be fixed first.
- **`CLAUDE.md` stale** — Still says `evaluator.py` is not implemented and `evals/test_queries.json` has placeholders.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility.
- **Google Fonts dependency:** Frontend loads from CDN; falls back to system fonts offline.

### Suggested First Action

Commit all uncommitted work from Sessions 7 and 8. Then wire `evaluator.py` to `run_pipeline()` (P2-3) — this eliminates the last copy of inline pipeline logic.

---

## Session — 2026-04-11 (Session 9 / Prompt 3: Typed Stages & Trace Hardening)

### Summary

Created `src/stages/` with four typed, pure-compute stage modules, refactored `pipeline.py` to delegate to them, and hardened the `DecisionTrace` model with missing observability fields. A hostile review pass identified gaps that were fixed before closing the session.

**What was done:**

1. **Created `src/stages/`** — four typed stage modules with named result dataclasses (no I/O, no side effects):
   - `permission_filter.py` — `filter_permissions(docs, user_ctx, roles) → PermissionResult`; handles unknown `min_role` values by blocking rather than aborting.
   - `freshness_scorer.py` — `score_freshness(docs, metadata, half_life_days) → FreshnessResult`; calls `compute_freshness()` directly and constructs new typed objects (no in-place mutation). Tracks stale docs with `penalty_applied` field.
   - `budget_packer.py` — `pack_budget(docs, token_budget, enforce_budget) → BudgetResult`; ranks by 50/50 combined score, tracks documents dropped by budget as `DroppedByBudget`.
   - `trace_builder.py` — `build_trace(...) → DecisionTrace`; aggregates all stage outputs including `ttft_proxy_ms` and `budget_utilization`.

2. **Refactored `src/pipeline.py`** — Stage wrapper functions now delegate entirely to `src/stages/`. Stage results are named dataclasses (`PermissionResult`, `FreshnessResult`, `BudgetResult`) instead of raw tuples. Added `time.monotonic()` timing for `ttft_proxy_ms`.

3. **Hardened `src/models.py`** (hostile review fixes):
   - Added `DroppedByBudget` model — docs that scored well but were cut by the token budget.
   - Renamed `DecisionTrace.blocked` → `blocked_by_permission` and `stale` → `demoted_as_stale` for unambiguous field names.
   - Added `DecisionTrace.dropped_by_budget`, `total_tokens`, and `ttft_proxy_ms`.
   - Added `TraceMetrics.dropped_count` and `budget_utilization`.

4. **Added `tests/test_stages.py`** — 435-line test file with unit tests for each stage in isolation (synthetic inputs, no FAISS) and pipeline-level integration tests for blocked/stale/dropped-by-budget scenarios.

5. **Updated `tests/test_models.py`** and **`tests/test_pipeline.py`** — Added coverage for new model fields and updated assertions for renamed `DecisionTrace` fields.

**Hostile review findings and fixes:**

| Finding | Fix |
|---------|-----|
| `DecisionTrace.blocked` and `stale` were ambiguous — same names used in `policies.py` for different semantics | Renamed to `blocked_by_permission` and `demoted_as_stale` |
| No tracking of documents dropped by the token budget | Added `DroppedByBudget` model + `dropped_by_budget` list on `DecisionTrace` |
| `TraceMetrics` had no `dropped_count` or `budget_utilization` | Both fields added |
| No latency signal on the trace | Added `ttft_proxy_ms` (wall-clock time of `run_pipeline()`) |
| Pipeline stage functions had logic inline instead of delegating to typed stages | Extracted into `src/stages/`; pipeline wrappers are now thin error boundaries only |
| Stage results were raw tuples — fragile destructuring | Replaced with frozen dataclasses (`PermissionResult`, `FreshnessResult`, `BudgetResult`) |

**Key design decisions:**

- `freshness_scorer.py` calls `compute_freshness()` directly (bypasses `apply_freshness()` which mutates dicts). The mutation API in `freshness.py` is preserved for backward-compat with `evaluator.py` but is no longer on the critical path.
- `budget_packer.py` handles `enforce_budget=False` (the `naive_top_k` preset) via the same function — no separate code path.
- Unknown `min_role` values in `permission_filter.py` produce a blocked entry instead of raising, preventing a bad corpus doc from aborting an otherwise valid query.

### Current State

- **Branch:** `main`
- **Last commit:** `71f0258` (Task 2 completed)
- **Working tree:** modified `src/models.py` (staged), `src/pipeline.py` (unstaged), `tests/test_models.py` (staged), `tests/test_pipeline.py` (unstaged), `CLAUDE.md` (unstaged), `docs/HANDOFF.md` (unstaged), `docs/plans/2026-04-10-pipeline-integration-plan.md` (unstaged); untracked `src/stages/`, `tests/test_stages.py`
- **Tests:** 117 passing (0 failing)
  - `tests/test_policies.py` — 6 tests
  - `tests/test_freshness.py` — 12 tests
  - `tests/test_context_assembler.py` — 5 tests
  - `tests/test_main.py` — 6 tests
  - `tests/test_evaluator.py` — 17 tests
  - `tests/test_models.py` — updated (staged)
  - `tests/test_pipeline.py` — updated (unstaged)
  - `tests/test_stages.py` — 29 new tests (untracked)

### Remaining Tasks (ordered)

1. **Commit all work** — `src/models.py`, `src/pipeline.py`, `src/stages/`, `tests/test_models.py`, `tests/test_pipeline.py`, `tests/test_stages.py`, `CLAUDE.md`, `docs/HANDOFF.md`, `docs/plans/2026-04-10-pipeline-integration-plan.md`.

2. **Wire `evaluator.py` to `pipeline.py`** (P2-3) — `run_evals()` still contains its own inline pipeline. Replace with `run_pipeline()` calls. This eliminates the last copy of duplicated pipeline logic.

3. **`freshness.py` mutation** (P3-2 remainder) — `apply_freshness()` still mutates dicts in-place. The stages layer works around this, but a clean refactor would return new dicts. Low urgency now that stages bypass the mutation.

4. **Decide on `artifacts/` gitignore** — FAISS index is ~2MB binary; either commit or require `python3 -m src.indexer` after clone.

### Blockers and Warnings

- **`evaluator.py` still has its own inline pipeline** — Diverges from `pipeline.py` and won't benefit from future stage improvements. Wire to `run_pipeline()` before adding more policy presets.
- **`freshness.py` `apply_freshness()` still mutates** — Not on the critical request path anymore (stages bypass it) but still called by `evaluator.py`'s inline pipeline.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility.

### Suggested First Action

Commit all uncommitted work from Sessions 7, 8, and 9. Then wire `evaluator.py` to `run_pipeline()` (P2-3).

---

## Session — 2026-04-11 (Session 10 / Prompt 4: Hybrid Retrieval)

### Summary

Replaced the pure semantic (FAISS-only) retriever with a hybrid retriever combining FAISS cosine similarity and BM25 lexical matching via Reciprocal Rank Fusion (RRF). Added 20 retriever tests, regenerated artifacts, and addressed an evaluator regression caused by the changed ranking.

**What was done:**

1. **Rewrote `src/retriever.py`** — Hybrid retrieval replaces semantic-only:
   - `_semantic_ranks()` — FAISS cosine similarity over all corpus docs (1-based rank dict)
   - `_bm25_ranks()` — BM25Okapi over tokenized corpus (1-based rank dict)
   - `_rrf_fuse()` — Reciprocal Rank Fusion: `score(d) = 1/(60+rank_sem) + 1/(60+rank_bm25)`; docs missing from one ranking get worst-case default rank
   - `_normalize_scores()` — min-max normalizes fused scores to [0, 1]
   - `retrieve()` is now the hybrid entry point; `semantic_retrieve()` preserved for comparison and backward-compat testing
   - Both satisfy `RetrieverProtocol` — no downstream stage changes needed
   - Lazy-loaded singletons for both the sentence-transformers model and the BM25 object

2. **Extended `src/indexer.py`** — Added BM25 corpus building:
   - `tokenize_for_bm25()` — lowercase, stopword-filtered, min-length-2 tokenizer
   - `build_bm25_corpus()` — tokenizes all docs in corpus order (same row order as FAISS)
   - `save_bm25_corpus()` / `load_bm25_corpus()` — persist to/from `artifacts/bm25_corpus.json`
   - `build_and_save()` updated to also build and save the BM25 corpus

3. **Added `rank_bm25` to `requirements.txt`**

4. **Generated and committed `artifacts/bm25_corpus.json`** — Built by running `python3 -m src.indexer`. The FAISS index (`querytrace.index`, `index_documents.json`) was already present from a prior session; only the BM25 corpus was new.

5. **Added `tests/test_retriever.py`** — 20 tests across four classes:
   - `TestProtocol` (2) — both `retrieve` and `semantic_retrieve` satisfy `RetrieverProtocol`
   - `TestResultShape` (6) — result is a list of dicts, required keys present, scores in [0,1], top score = 1.0, ranks sequential, top_k clamped to corpus size
   - `TestHybridVsSemantic` (4) — BM25 materially changes ranking for exact-name queries (Rohan Mehta), exact-figure queries ($38.1M), rescues doc_006 for CTO query, promotes doc_012 for customer concentration
   - `TestRRFFusion` (8) — unit tests for `_rrf_fuse` and `_normalize_scores` with synthetic data

6. **Initial evaluator regression and tuning fix** — Switching to hybrid retrieval changed the ranking of raw candidates, causing the permission-filter stage to thin out the candidate set before expected docs could make it into context for analyst queries. Fixed by adding `retrieve_k = policy.top_k * 3` in `pipeline.py` (over-retrieves 3× before filtering). The comment explains: for a 12-doc corpus with analyst access, `top_k=8` leaves only 2–3 candidates after filtering 7 restricted docs. Eval metrics recovered to pre-hybrid levels after this tuning.

**Key design decisions:**

| Decision | Reason |
|----------|--------|
| RRF K=60 | Standard constant from Cormack et al. (2009); dampens rank differences between heterogeneous systems |
| Rank all docs, not just top-k | With 12-doc corpus, full ranking is cheap; avoids missing docs that FAISS would rank poorly but BM25 promotes |
| Stopword filtering in BM25 tokenizer | Prevents corpus-common function words from dominating IDF in small corpora |
| `retrieve_k = policy.top_k * 3` | Over-retrieval compensates for permission attrition; budget packer still enforces final token limit |
| `semantic_retrieve` preserved | Protocol compatibility tests; useful for A/B comparison against hybrid |

### Current State

- **Branch:** `main`
- **Last commit:** `c08ac87` (Task 4 Checkpoint)
- **Working tree:** clean
- **Tests:** 137 passing, 0 failing
  - `tests/test_policies.py` — 6 tests
  - `tests/test_freshness.py` — 12 tests
  - `tests/test_context_assembler.py` — 5 tests
  - `tests/test_main.py` — 6 tests
  - `tests/test_evaluator.py` — 17 tests
  - `tests/test_models.py` — 24 tests (exact count from last counted state; may have been updated in Prompt 3)
  - `tests/test_pipeline.py` — 18 tests
  - `tests/test_stages.py` — 29 tests
  - `tests/test_retriever.py` — 20 tests (new in Prompt 4)
- **Verified command:** `python3 -m pytest tests/ -q --tb=no` → **137 passed** (run during this session)
- **Artifacts:** `artifacts/bm25_corpus.json` committed. FAISS index files were already present.

### Remaining Tasks (ordered)

1. **Wire `evaluator.py` to `run_pipeline()`** (P2-3) — `run_evals()` still contains its own inline pipeline (`retrieve → filter_by_role → apply_freshness → assemble`). Replace with `run_pipeline()` calls. Extract assembled doc IDs and freshness scores from `PipelineResult.trace.included`. This eliminates the last copy of duplicated pipeline logic.

2. **Update `tests/test_evaluator.py`** — Current tests exercise the inline pipeline path. After wiring, assertions about `assembled_ids` format and freshness source need updating to match the `IncludedDocument` interface from `PipelineResult.trace`.

3. **Verify eval metrics after wiring** — Run `python3 -m src.evaluator`. Expect: `avg_recall = 1.0000`, `permission_violation_rate = 0%`, `avg_precision_at_5 ≥ 0.33`.

4. **P3-2 closure** — Once evaluator is wired, `apply_freshness()` will no longer be called anywhere on the request path. Can then safely remove or deprecate the mutation API in `freshness.py`.

5. **Decide on `artifacts/` gitignore** — FAISS index is ~2MB binary. `bm25_corpus.json` is 1 line (minified JSON). Currently all three artifact files are committed (they appear in the working tree). Decision needed: stay committed (convenient for CI) or gitignore + document `python3 -m src.indexer` as setup step.

### Blockers and Warnings

- **`evaluator.py` inline pipeline diverges from `pipeline.py`** — Uses `filter_by_role` (roles as arg 2) and `apply_freshness` (mutation path), whereas `pipeline.py` uses `filter_permissions` (staged) and `score_freshness`. Drift will widen if pipeline is updated without also updating the evaluator.
- **`apply_freshness()` still mutates dicts in-place** — Not on the critical request path (stages bypass it), but still called by `evaluator.py`. Removing it before P2-3 would break the evaluator.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility.

### Suggested First Action

Wire `evaluator.py` to `run_pipeline()` (P2-3). The plan doc (`docs/plans/2026-04-10-pipeline-integration-plan.md`) has a concrete code skeleton showing the replacement. After wiring, run `python3 -m pytest tests/test_evaluator.py -v` to confirm all 17+ tests still pass, then run `python3 -m src.evaluator` to verify metrics.

---

## Session — 2026-04-12 (Session 11 / Prompt 5: Evaluator Wiring & Test Hardening)

### Summary

Wired `src/evaluator.py` to `run_pipeline()`, removed the dead `token_budget` evaluator interface, added trace-level metrics to evaluator output, and hardened both `tests/test_evaluator.py` and `tests/test_pipeline.py`. Legacy dict-plumbing tests were skipped with clear deprecation notices. Two passes of hostile review completed; verdict is `risks_noted` with one MINOR fix pending.

**What was done:**

1. **Wired `src/evaluator.py` to `run_pipeline()`** (P2-3 complete) — Replaced the inline `retrieve → filter_by_role → apply_freshness → assemble` pipeline in `run_evals()` with `run_pipeline(QueryRequest(...), retrieve, roles, metadata)`. Assembled doc IDs and freshness scores now come from typed `PipelineResult.trace.included` (`IncludedDocument` objects), not raw dicts. Pipeline imports deferred inside `run_evals()` to avoid loading sentence-transformers at import time.

2. **Removed dead `token_budget` interface** — `run_evals(token_budget=...)` parameter and `--token-budget` CLI flag were silently ignored (pipeline uses policy budget; `QueryRequest` has no `token_budget` field). Both removed. Module docstring updated to state budget is policy-owned.

3. **Added trace-level metrics to evaluator output** — Per-query records now include `blocked_count`, `stale_count`, `dropped_count`, `budget_utilization` from `result.trace.metrics`. Aggregate adds `avg_blocked_count`, `avg_stale_count`, `avg_dropped_count`, `avg_budget_utilization`.

4. **Added `None` guard for `result.trace`** — After the try/except block, evaluator checks `if result.trace is None` and appends an error record rather than crashing.

5. **Added 5 new tests to `tests/test_evaluator.py`** (17 → 22 total):
   - `test_run_evals_trace_metrics_present` — each per-query result has blocked/stale/dropped/budget_util keys
   - `test_run_evals_aggregate_trace_metrics` — aggregate has avg_* trace keys
   - `test_run_evals_analyst_queries_have_blocked_docs` — q003 shows `blocked_count > 0`
   - `test_run_evals_budget_utilization_bounded` — 0 ≤ budget_util ≤ 1
   - `test_run_evals_precision_floor` — `avg_precision_at_5 ≥ 0.20` regression guard

6. **Added 10 new tests to `tests/test_pipeline.py`** (18 → 28 total):
   - `test_trace_document_accounting_complete` — included+blocked+dropped == retrieved
   - `test_trace_has_all_required_sections` — all trace sections present and correctly typed
   - `test_stale_demotion_half_penalty` — `s.penalty_applied == 0.5` for all stale docs
   - `test_permission_safety_analyst_never_sees_restricted` — blocked_ids disjoint from included_ids
   - `TestAllPoliciesTraceStructure` — parametrized accounting test for all 3 presets + naive-vs-full blocking difference
   - `test_permission_aware_enforces_budget` — budget respected under permission_aware policy
   - `test_trace_included_equals_result_context` — `trace.included == result.context` identity check

7. **Marked legacy dict-plumbing tests as skipped** — 14 tests total across three files:
   - `tests/test_policies.py` — 4 `filter_by_role` tests (`@_LEGACY_SKIP`); 2 `load_roles` tests remain active. Module docstring explains what is live vs deprecated.
   - `tests/test_freshness.py` — 5 `apply_freshness` tests (`@_LEGACY_SKIP`); 7 `compute_freshness` tests remain active.
   - `tests/test_context_assembler.py` — all 5 `assemble()` tests skipped via `pytestmark`; module docstring points to `stages/budget_packer.py` as the replacement.

8. **Hostile review (2 passes):**
   - Pass 1: 2 MAJOR (no precision floor, trace None guard unplaced), 3 MINOR (legacy tests still passing, permission_aware budget test, trace.included identity not tested). All five addressed.
   - Pass 2: 1 MINOR remains — `test_permission_aware_enforces_budget` assertion `result.total_tokens <= token_budget` is trivially true for small corpus (all docs fit in budget). Fix: add `assert result.trace.policy_config.skip_budget is False`. Verdict: `risks_noted`.

**P3-2 closed as side-effect** — `apply_freshness()` is no longer called anywhere on the request path. The mutation API in `freshness.py` exists but is dead code.

**Precision drop explained** — `avg_precision_at_5` dropped from 0.3375 (inline pipeline) to 0.3000 (production pipeline). Not a regression: the production pipeline over-retrieves 3× and fills the entire token budget with all role-visible docs. Recall is unchanged at 1.0. The floor test is set at 0.20 to absorb ranking variance without masking genuine retrieval failures.

### Current State

- **Branch:** `main`
- **Last commit:** `34ade1b` (Task 3 completed)
- **Working tree:** clean
- **Tests:** 138 passed, 14 skipped, 0 failed
  - `tests/test_policies.py` — 2 passed, 4 skipped (filter_by_role legacy)
  - `tests/test_freshness.py` — 7 passed, 5 skipped (apply_freshness legacy)
  - `tests/test_context_assembler.py` — 5 skipped (assemble() legacy, pytestmark)
  - `tests/test_main.py` — 6 passed
  - `tests/test_evaluator.py` — 22 passed
  - `tests/test_models.py` — 24 passed
  - `tests/test_pipeline.py` — 28 passed
  - `tests/test_stages.py` — 29 passed
  - `tests/test_retriever.py` — 20 passed

- **Evaluator metrics** (`python3 -m src.evaluator`, default policy, k=5, top_k=8):
  - Avg Precision@5: **0.3000**
  - Avg Recall: **1.0000**
  - Permission violation rate: **0%**
  - Avg context docs: 8.62
  - Avg total tokens: 1078.0
  - Avg freshness score: 7.68e-01
  - Avg blocked count: 3.38
  - Avg stale count: 1.62
  - Avg dropped count: 0.0
  - Avg budget utilization: 53%

- **Hostile review verdict:** `risks_noted` (Pass 2) — one MINOR pending

### Remaining Tasks (ordered)

1. **Fix hostile review MINOR** — `test_permission_aware_enforces_budget` in `tests/test_pipeline.py`: add `assert result.trace.policy_config.skip_budget is False` before the token count assertion. The current assertion is trivially true for a 12-doc corpus.

2. **Hostile review Pass 3** — After the MINOR fix, re-run hostile review to achieve two consecutive clean passes and reach `clean` verdict.

3. **Frontend comparison view** — Add a toggle or side-by-side panel in the UI to compare `naive_top_k` vs `full_policy` results for the same query. Surfaces the permission filtering and stale demotion differences visually.

4. **Dashboard / observability** — Expose `decision_trace` fields (blocked_by_permission, demoted_as_stale, dropped_by_budget, budget_utilization) in the frontend result view. Currently the frontend only shows per-doc scores and total_tokens.

5. **Demo readiness** — The backend and eval harness are production-ready. Demo blocker is the frontend not yet showing `decision_trace` data. Once the trace fields are surfaced, the full pipeline story (retrieval → permission → freshness → budget → trace) is demonstrable end-to-end in the browser.

6. **Decide on `artifacts/` gitignore** — Three artifact files are currently committed. No change needed urgently.

### Blockers and Warnings

- **Hostile review verdict not yet `clean`** — One MINOR outstanding in `test_pipeline.py`. Low risk: the assertion is correct, just not discriminating enough.
- **`apply_freshness()` and `filter_by_role()` are dead code** — No longer called anywhere on the request path. They can be removed or deprecated when convenient; there is no urgency.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility.

### Suggested First Action

Apply the one-line MINOR fix to `test_permission_aware_enforces_budget` (add `assert result.trace.policy_config.skip_budget is False`), then run `python3 -m pytest tests/test_pipeline.py -v` to confirm. Run hostile review Pass 3 to reach `clean` verdict. Then turn to frontend `decision_trace` display.

---

## Session — 2026-04-12 (Session 12 / Prompt 6: Context Policy Lab Frontend)

### Summary

Upgraded the frontend into a full **Context Policy Lab** — a single/compare mode UI with structured Decision Trace rendering. Added a minimal additive `POST /compare` backend endpoint. No existing backend logic was changed.

**What was done:**

1. **Added `POST /compare` endpoint to `src/main.py`** — Strictly additive; calls `run_pipeline()` for each requested policy and returns one `QueryResponse` per policy keyed by policy name. Role and policy validation: invalid role → 400, unknown policy name → 400 (ValueError from `resolve_policy` propagated). `/query` is fully unchanged.

2. **Added `CompareRequest` and `CompareResponse` models to `src/models.py`** — `CompareRequest` accepts `query`, `role`, `top_k`, and `policies` (default: all three presets). `CompareResponse` returns `query`, `role`, and `results: Dict[str, QueryResponse]`. Added `Dict` to typing imports.

3. **Added 3 tests to `tests/test_main.py`** (6 → 9 tests):
   - `test_compare_returns_all_three_policies` — basic compare returns all three policies with required fields
   - `test_compare_invalid_role_returns_400`
   - `test_compare_unknown_policy_returns_400`

4. **Rewrote `frontend/index.html`** — Structural additions:
   - Mode toggle (Single / Compare) in sticky header
   - Policy selector in controls row (naive / rbac / full chips with color coding) — visible in single mode only
   - `#compare-section` (hidden by default) holds the compare grid
   - "Sarah as Analyst ↔" scenario button triggers compare mode with analyst + ARR query
   - Preserved all existing role chips, example buttons, results section

5. **Rewrote `frontend/styles.css`** — Major additions (preserving all existing visual language):
   - Mode toggle pill, `.mode-btn.active` = gold background
   - Policy chip colors: naive=red (`#b85c5c`), rbac=amber (`#c8a55a`), full=green (`#5a9a6a`)
   - `.compare-grid` — 3-column CSS grid, expands `.main` to `min(1260px, 100vw)`
   - `.compare-col` — header with colored band per policy, stats strip, compact cards, trace panel
   - `.col-badge-{naive,rbac,full}` — severity badges
   - `.col-stat.stat-{blocked,stale,dropped}` — counts colored red/amber/orange
   - `.trace-panel` — collapsible audit drawer (`open` class toggles `.trace-body` display)
   - Four trace chip types: `trace-chip-{included,blocked,stale,dropped}` with per-category colors
   - `.budget-bar-fill` — budget utilization bar
   - `.compare-card` — compact doc card for compare columns with `::before` accent stripe
   - `.doc-flag.flag-blocked` — annotation for docs visible in naive but blocked in full
   - Responsive: 3 columns → 1 column at 960px

6. **Rewrote `frontend/app.js`** — Complete rewrite preserving all existing functionality:
   - `currentMode: 'single' | 'compare'` state; `switchMode()` toggles section visibility and `.main.compare-mode`
   - `runSingleQuery(query, role, policy)` — calls `POST /query` with `policy_name`; renders single result + trace panel
   - `runCompare(query, role)` — calls `POST /compare`; renders 3-column compare view
   - `renderCompare(data)` — builds cross-policy highlights: detects which doc_ids are blocked in `full_policy` and flags them in the `naive_top_k` column with `flag-blocked` annotation
   - `buildTracePanelHTML(trace, startOpen)` — reusable trace panel; starts collapsed in single mode, expanded in compare mode
   - `wireTraceToggles(container)` — delegates expand/collapse after innerHTML injection
   - `COMPARE_ORDER = ['naive_top_k', 'permission_aware', 'full_policy']` — canonical column order
   - Skeleton states for both modes; all error paths route through `renderError(err, container)`
   - `escapeHTML()` applied to all user and API content

**Key design decisions:**

| Decision | Reason |
|----------|--------|
| `POST /compare` calls `run_pipeline()` N times, not a custom path | Guarantees identical semantics to `/query`; single source of truth for pipeline logic |
| Trace starts expanded in compare mode | Side-by-side comparison is only readable if all three traces are immediately visible |
| Cross-policy highlight uses `full_policy`'s `blocked_by_permission` list | Accurately identifies docs that naive wrongly surfaces; avoids client-side RBAC logic |
| `.main.compare-mode` class for wider max-width | Avoids modifying the container on single-mode pages; no layout flash |
| Sarah-as-Analyst button switches mode + submits | The scenario is meaningless in single-mode; compare mode is the correct context |

**Two CSS bugs found and fixed during verification (not present in pre-verification code):**
- `[hidden]` attribute was overridden by `.selector-group { display: flex }` (author stylesheet beats user-agent `[hidden] { display: none }`). Fixed by adding `[hidden] { display: none !important }` to reset.
- No `scroll-padding-top` on `html`, causing sticky header to overlap controls when `scrollIntoView` fired after long compare results. Fixed with `scroll-padding-top: 68px`.

### Current State

- **Branch:** `main`
- **Last commit:** `54f3c60` (Task 5)
- **Working tree:** modified `src/main.py`, `src/models.py`, `tests/test_main.py`, `frontend/index.html`, `frontend/styles.css`, `frontend/app.js`, `docs/HANDOFF.md`
- **Tests:** 141 passed, 14 skipped, 0 failed (confirmed with full output, no truncation)
- **Frontend:** fully verified end-to-end against live server via Playwright — 51/51 checks pass
  - Page load: brand, tagline, mode toggle, role/policy chips, scenario button ✓
  - Single mode: result cards, summary bar, Decision Trace (collapsed→expanded, all 4 categories, chips, budget bar) ✓
  - Compare mode: 3 columns (NAIVE/RBAC/FULL), stats strip, 3 open trace panels, compact cards ✓
  - Sarah-as-Analyst: auto-switch to compare, analyst role, ARR query, 7 `flag-blocked` annotations in naive column, full_policy shows 7 blocked vs naive 0 ✓
  - State recovery: switch back to single, VP query returns results ✓
  - No JS console errors ✓

**Follow-up fix (same session):**
- Applied hostile review MINOR: added `assert result.trace.policy_config.skip_budget is False` to `test_permission_aware_enforces_budget` in `tests/test_pipeline.py`. This ensures the test fails if `permission_aware` is ever misconfigured with `skip_budget=True`. 141 passed, 14 skipped, 0 failed after fix.

### Current State

- **Branch:** `main`
- **Last commit:** `54f3c60` (Task 5) — all Prompt 6 + MINOR fix work is uncommitted
- **Working tree:** modified `src/main.py`, `src/models.py`, `tests/test_main.py`, `tests/test_pipeline.py`, `frontend/index.html`, `frontend/styles.css`, `frontend/app.js`, `docs/HANDOFF.md`, `docs/plans/2026-04-10-pipeline-integration-plan.md`
- **Tests:** 141 passed, 14 skipped, 0 failed
- **Frontend:** verified end-to-end via Playwright — 51/51 checks pass (see details above)

### Remaining Tasks (ordered)

1. **Commit this batch** — All modified files listed above. Suggested message: "Prompt 6: Context Policy Lab frontend + /compare endpoint + MINOR test fix".

2. **Hostile review Pass 3** — Re-run hostile review on backend tests to move from `risks_noted` to `clean` verdict. The MINOR fix is now applied.

3. **Remaining DOCX demo items** — Confirm any outstanding DOCX scenarios not yet surfaced in the UI (permissions demo and compare view are covered; check if DOCX specifies any additional user journeys).

### Blockers and Warnings

- **All Prompt 6 work is uncommitted** — 9 modified files need to be committed.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility.
- **Google Fonts dependency:** Frontend loads Bricolage Grotesque and IBM Plex Mono from CDN; falls back to system fonts offline.

### Suggested First Action

Commit the full batch, then run hostile review Pass 3 to close the `risks_noted` verdict.

---

## Session — 2026-04-12 (Session 13 / Prompt 6 Pass 3: Compare Hardening & Clean Verdict)

### Summary

Closed the hostile review at `clean` verdict. Applied three targeted fixes to the compare endpoint and its tests — no changes to pipeline logic, frontend, or any other module.

**What was done:**

1. **Empty-policies guard in `POST /compare`** (`src/main.py`) — Added `if not request.policies: raise HTTPException(400, "policies list must not be empty")` before the policy loop. Prevents a vacuous 200 with an empty `results` dict when `policies: []` is sent.

2. **`test_compare_returns_all_three_policies` strengthened** (`tests/test_main.py`) — Replaced the generic query with an analyst-role query against restricted documents (`"investment committee memo deal terms LP update"`, `role="analyst"`, `top_k=12`). Added three new assertions:
   - `assert policy_result["decision_trace"] is not None` — rules out null trace serialised as present key
   - `assert naive_trace["metrics"]["blocked_count"] == 0` — naive_top_k skips permission filter
   - `assert full_trace["metrics"]["blocked_count"] > 0` — full_policy enforces RBAC for analyst

3. **`test_compare_empty_policies_returns_400` added** (`tests/test_main.py`) — Covers the degenerate empty-list case end-to-end.

**Hostile review Pass 3 outcome:**
- No CRITICAL, no MAJOR, no MINOR findings
- Two consecutive clean passes (Pass 2 had no new findings; Pass 3 confirmed)
- Verdict: `clean`

**Remaining open items from prior passes (not addressed — acknowledged as display-quality only):**
- m-2: `naive_top_k` freshness scores render as 0.0 (indistinguishable from stale docs) — no fix in this batch; a `N/A` display would remove the misleading signal but correctness is unaffected
- m-3: `POLICY_META` fallback in `app.js` defaults to green FULL-style badge for unknown policy names — cosmetic, no runtime impact
- n-1: `DocumentChunk` mapping loop is copy-pasted between `/query` and `/compare` — a `_to_chunks()` helper would eliminate it; not a defect

### Current State

- **Branch:** `main`
- **Last commit:** `d9350f0` (Task 6) — contains all Prompt 6 frontend + `/compare` + Prompt 5 MINOR fix
- **Working tree:** 2 modified files uncommitted:
  - `src/main.py` — empty-policies guard
  - `tests/test_main.py` — strengthened compare test + new empty-policies test
- **Tests:** 142 passed, 14 skipped, 0 failed (verified: `python3 -m pytest tests/ -q`)
- **Test breakdown:**
  - `tests/test_policies.py` — 2 passed, 4 skipped (filter_by_role legacy)
  - `tests/test_freshness.py` — 7 passed, 5 skipped (apply_freshness legacy)
  - `tests/test_context_assembler.py` — 5 skipped (assemble() legacy)
  - `tests/test_main.py` — 11 passed (was 9; +2 from this session)
  - `tests/test_evaluator.py` — 22 passed
  - `tests/test_models.py` — 24 passed
  - `tests/test_pipeline.py` — 28 passed
  - `tests/test_stages.py` — 29 passed
  - `tests/test_retriever.py` — 20 passed
- **Evaluator metrics** (unchanged from Prompt 5):
  - Avg Precision@5: **0.3000**
  - Avg Recall: **1.0000**
  - Permission violation rate: **0%**
  - Avg freshness score: 7.68e-01
  - Avg blocked count: 3.38, avg stale count: 1.62, avg dropped count: 0.0
  - Avg budget utilization: 53%
- **Hostile review verdict:** `clean` (two consecutive clean passes)
- **Frontend:** unchanged from Prompt 6 — 51/51 Playwright checks pass

### Remaining Tasks (ordered)

1. **Commit this session's work** — `src/main.py`, `tests/test_main.py`. Suggested message: "Prompt 6 Pass 3: harden /compare tests and add empty-policies guard".

2. **Prompt 7A — Evaluator API exposure** — Surface the evaluator as an API endpoint (`GET /evals` or similar) so the frontend can display live eval metrics on the dashboard. Or alternatively, surface the results as a static JSON that the frontend can fetch.

3. **Prompt 7A — Dashboard / observability panel** — Add an Evals or Metrics panel to the frontend showing precision@5, recall, permission_violation_rate, and avg trace counts. This completes the demo story: query → trace → aggregate metrics.

4. **Demo readiness check** — Confirm all intended user journeys are covered: single query + trace, compare mode, Sarah-as-Analyst scenario, and eval metrics view. Document any gaps before declaring demo-ready.

5. **(Low priority) Display quality fixes** — `naive_top_k` freshness bar shows 0.0 (misleading); `POLICY_META` fallback uses green badge for unknown policies. Both are cosmetic; address if time allows.

### Blockers and Warnings

- **Working tree has 2 uncommitted files** — commit before starting Prompt 7A.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility.
- **Google Fonts dependency:** Frontend loads Bricolage Grotesque and IBM Plex Mono from CDN; falls back to system fonts offline.

### Suggested First Action

Commit the 2 modified files (`src/main.py`, `tests/test_main.py`), then plan Prompt 7A scope: decide whether to expose the evaluator via a new API endpoint or as a static artifact, and whether the dashboard panel should show live or cached metrics.

---

## Session — 2026-04-12 (Session 14 / Prompt 7A: Evaluator API + Dashboard)

### Summary

Exposed the evaluator as a structured HTTP endpoint (`GET /evals`) and added a third frontend mode ("Evals" dashboard) that consumes it. Hostile review reached `clean` verdict in two passes. No changes to `/query`, `/compare`, or any pipeline/stage logic.

**What was done:**

1. **Added `GET /evals` to `src/main.py`** — Strictly additive route. Imports `load_test_queries` and `run_evals` from `src/evaluator`. On first call: loads test queries from `evals/test_queries.json`, runs `run_evals(queries, k=5, top_k=8)`, stores result in module-level `_evals_cache`. Subsequent calls return the cached dict immediately (~1.6ms vs. ~5–10s cold). No changes to `/query` or `/compare`.

2. **Added 6 new tests to `tests/test_main.py`** (11 → 17 tests):
   - `test_evals_returns_200` — status + top-level keys
   - `test_evals_has_aggregate_keys` — all 12 aggregate metric keys present
   - `test_evals_has_eight_queries` — per-query list has exactly 8 entries
   - `test_evals_no_permission_violations` — no successful query has violations (skips error records)
   - `test_evals_per_query_has_required_keys` — added during hostile review Pass 1; asserts `{id, role, precision_at_5, recall, permission_violations}` in every non-error record (locks the dynamic `precision_at_{k}` key contract at per-query level)
   - `test_evals_caching_returns_identical_results` — two calls return identical JSON

3. **Added Evals dashboard to frontend** — Third mode "Evals" in the header toggle (Single | Compare | Evals):
   - Mode switch hides the search section and shows `#evals-section`
   - Auto-fetches `GET /evals` on first tab switch (lazy — not on page load)
   - **Aggregate metrics grid** — 10 stat cards (Precision@5, Recall, Permission Violations, Avg Context Docs, Avg Total Tokens, Avg Freshness, Avg Blocked, Avg Stale, Avg Dropped, Avg Budget Util)
   - **Per-query breakdown table** — 8 rows: Query ID | Role | P@5 | Recall | Docs | Tokens | Freshness | Blocked | Stale | Dropped | Budget | Violations
   - Loading spinner while evals run; error state routes to existing `renderError()`
   - All values read from structured `GET /evals` JSON — no CLI output parsing
   - `escapeHTML()` applied to all string content from the API

4. **Hostile review — two passes, `clean` verdict:**
   - Pass 1 findings: M-1 (`test_evals_no_permission_violations` failed misleadingly on error records), M-2 (per-query key `precision_at_5` untested — only aggregate was tested), M-3 (evaluator re-reads corpus files independently — noted, not fixed), N-1 (duplicate `@media (max-width: 640px)` CSS block — noted), N-2 (CSS color vars injected into style attribute — safe, noted)
   - Pass 1 fixes: M-1 resolved (added `if "error" in r: continue`); M-2 resolved (`test_evals_per_query_has_required_keys` added)
   - Pass 2: no new findings above NIT. Verdict: `clean`

**Key design decisions:**

| Decision | Reason |
|----------|--------|
| Module-level `_evals_cache` | `run_evals()` is ~5–10s cold; cache makes endpoint usable from browser without timeout |
| Route calls `load_test_queries()` + `run_evals()` directly | No duplication of evaluation logic — route is a thin dispatch, evaluator owns all metric computation |
| Frontend lazy-fetches on first Evals tab switch | Avoids slow startup; user explicitly requests the metrics view |
| `evalsLoaded` only set on success | Failed fetches retry on re-switch to Evals mode |

### Current State

- **Branch:** `main`
- **Last commit:** `9568cf2` (Hostile review) — all Prompt 7A work is **uncommitted**
- **Modified files (uncommitted):**
  - `src/main.py` — `GET /evals` route + imports + `_evals_cache`
  - `tests/test_main.py` — 6 new `/evals` tests
  - `frontend/app.js` — Evals mode, `runEvals()`, `renderEvals()`, `fmtPct()`
  - `frontend/index.html` — "Evals" mode button + `#evals-section`
  - `frontend/styles.css` — Evals dashboard styles (metrics grid, table, loading spinner)
- **Tests:** 148 passed, 14 skipped, 0 failed
  - `tests/test_main.py` — 17 passed (6 query + 4 compare + 6 evals + 1 health)
  - All other test files unchanged from Prompt 6
- **Evaluator metrics** (unchanged):
  - Avg Precision@5: **0.3000**
  - Avg Recall: **1.0000**
  - Permission violation rate: **0%**
  - Avg context docs: 8.62 | Avg total tokens: 1078.0
  - Avg freshness score: 7.68e-01
  - Avg blocked: 3.38 | avg stale: 1.62 | avg dropped: 0.0 | avg budget util: 53%
- **Hostile review verdict:** `clean` (Pass 2 confirmed no new findings)
- **Browser visual verification:** **Not confirmed.** JS syntax verified (`node --check`), endpoint verified via `curl` (200, correct JSON shape, 1.6ms cached response). Playwright was not available locally. The Evals tab visual rendering requires manual browser check.

### Remaining Tasks (ordered)

1. **Commit this batch** — 5 modified files. Suggested message: "Prompt 7A: GET /evals endpoint + frontend Evals dashboard".

2. **Browser visual verification** — Open `frontend/index.html` with server running (`uvicorn src.main:app --reload`) and click the "Evals" tab. Confirm: loading spinner appears, then 10 metric cards + 8-row table render, numbers display in IBM Plex Mono, switching back to Single/Compare modes works cleanly.

3. **Prompt 7B — Display quality fixes (low priority):**
   - `naive_top_k` freshness scores render as `0.0` in compare mode (freshness is skipped for that policy — a `N/A` display would remove the misleading signal)
   - `POLICY_META` fallback in `app.js` defaults to green FULL-style badge for unknown policy names (cosmetic)
   - Duplicate `@media (max-width: 640px)` CSS block (NITs from hostile review — merge into one)

4. **Demo readiness check** — Confirm all user journeys work end-to-end: single query + trace, compare mode, Sarah-as-Analyst scenario, eval metrics view. Once browser-verified, the full pipeline story is demonstrable without CLI.

5. **`apply_freshness()` and `filter_by_role()` dead code** — Still present in `freshness.py` and `policies.py`. Can be removed when convenient; no urgency.

### Blockers and Warnings

- **All Prompt 7A work is uncommitted** — 5 modified files need a commit before the next session begins.
- **Browser verification pending** — Evals tab was not opened in a real browser. Functional correctness is verified via tests and curl; visual layout is unconfirmed.
- **`run_evals()` re-reads corpus files** — Hostile review M-3 (noted, not fixed): `run_evals()` calls `load_roles()` and `open(metadata)` independently of the already-loaded `_roles`/`_metadata` in `main.py`. Not a correctness issue; noted for future cleanup.
- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility.
- **Google Fonts dependency:** Frontend loads Bricolage Grotesque and IBM Plex Mono from CDN; falls back to system fonts offline.

### Suggested First Action

Commit the 5 uncommitted files, then open `frontend/index.html` in a browser with the server running and click the "Evals" tab to complete the visual verification that was not possible from the CLI.

---

## Session — 2026-04-12 (Session 15 / Prompt 7B: Light Theme + Demo Polish)

### Summary

Light theme migration, VP/Partner scenario triggers, freshness N/A fix, POLICY_META fallback fix, duplicate @media cleanup, and complete README rewrite.

**What was done:**

1. **Light theme migration** (`frontend/styles.css` — full rewrite):
   - `:root` rewritten to warm parchment palette: `--bg-page: #f5f1ea`, `--bg-card: #ffffff`, warm amber accent `#8b6914`, policy colors re-tuned for legibility on light backgrounds
   - Shadow system added (`--shadow-card`, `--shadow-card-hover`, `--shadow-header`) — warm shadows replace dark-theme glow effects; applied to header, result cards, compare columns, compare cards, trace panels, mode toggle, and chips
   - Compare column docs area uses `--bg-surface` tint to separate doc cards from white column background
   - Evals table alternating row direction fixed: `rgba(255,255,255,0.015)` → `rgba(28,26,23,0.02)`
   - Two duplicate `@media (max-width: 640px)` blocks merged; two `@media (max-width: 960px)` blocks merged (4 → 2 total)

2. **Scenario discoverability** (`frontend/index.html`):
   - Examples row redesigned into two labelled groups: "Single" (3 single-mode queries) and "Compare" (3 compare-mode scenarios)
   - Added VP and Partner compare scenarios: "VP deal view ↔" and "Partner view ↔"
   - Role-dot indicators on all example buttons (amber=analyst, teal=VP, green=partner)
   - Scenario buttons styled with per-role color border coding
   - Empty state updated to "Permission-Aware Context Gateway" with `.empty-hint` pointing to "Analyst wall ↔"
   - Evals subtitle made more descriptive

3. **Bug fixes** (`frontend/app.js`):
   - `naive_top_k` freshness shows "N/A — skipped by policy" / "freshness N/A" instead of `0.00` in both single and compare card views (`skipFreshness: true` in POLICY_META, propagated to `singleCardHTML` and `buildCompareCardHTML`)
   - POLICY_META fallback badge changed from `variant: "full"` (misleading green) to `variant: "unknown"` (neutral grey `.col-badge-unknown`)
   - New CSS classes: `.col-badge-unknown`, `.col-header-unknown`, `.metric-na`, `.mini-na`, `.empty-hint`, `.examples-row`, `.ex-role-dot`, `.dot-{analyst,vp,partner}`, `.scenario-btn.dot-*-border`

4. **README rewritten** — old stub with TODO list replaced with:
   - Fastest-path demo table (Analyst wall, VP deal view, Partner view, Evals)
   - Pipeline stage diagram
   - Policy preset table with feature matrix
   - Corpus access control table and stale pair documentation
   - DecisionTrace field documentation
   - All three API endpoints with curl examples
   - Test / evaluator commands with current metrics
   - Artifact regeneration instructions
   - Full project structure

5. **Verification**:
   - 148 passed, 14 skipped, 0 failed
   - Evaluator: precision@5=0.3000, recall=1.0000, violations=0%
   - All three endpoints verified via curl: `/query` (analyst, blocked=7), `/compare` (all 3 policies), `/evals` (8 queries, 0 failed)
   - JS syntax check: OK

### Current State

- **Branch:** `main`
- **Last commit:** `0f9f548` (Task 7A)
- **Working tree:** 5 modified files uncommitted:
  - `frontend/app.js` — freshness N/A, fallback badge, VP/Partner scenario JS
  - `frontend/index.html` — two-row scenarios, VP/Partner buttons, improved empty state
  - `frontend/styles.css` — full light theme rewrite
  - `README.md` — complete rewrite
  - `docs/HANDOFF.md` — this entry
- **Tests:** 148 passed, 14 skipped, 0 failed
- **Evaluator:** precision@5=0.3000, recall=1.0000, violations=0%
- **Hostile review:** `clean` (from Prompt 7A — no new review performed this session, changes are frontend/docs only)
- **Frontend:** JS syntax verified. Browser visual verification not performed from CLI.

### Remaining Tasks (ordered)

1. **Commit this batch** — `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`, `README.md`, `CLAUDE.md`, `docs/HANDOFF.md`, `docs/plans/2026-04-10-pipeline-integration-plan.md`

2. **Browser visual verification** — Open `frontend/index.html` with server running, confirm:
   - Light theme renders correctly (cream background, white cards, warm amber accent)
   - "Single" and "Compare" scenario rows both visible and labelled
   - VP deal view ↔ and Partner view ↔ scenario buttons trigger compare mode with correct role
   - Analyst wall ↔ shows 7 blocked in full/rbac, 0 in naive
   - Naive column freshness shows "freshness N/A" instead of 0.00
   - Evals tab renders 10 metric cards + 8-row table

3. **Optional: Remove dead code** — `apply_freshness()` in `freshness.py` and `filter_by_role()` in `policies.py` are no longer called on the request path. Safe to delete when convenient.

4. **Optional: Evaluator corpus re-read** — `run_evals()` reloads roles and metadata independently of `main.py`'s already-loaded copies. Not a bug; cosmetic cleanup.

### Blockers and Warnings

- **Python 3.9 / LibreSSL:** System is 3.9.6 with LibreSSL 2.8.3. `tf-keras` installed for `sentence-transformers` compatibility.
- **Google Fonts dependency:** Frontend loads Bricolage Grotesque and IBM Plex Mono from CDN; falls back to system fonts offline.

### Suggested First Action

Commit the batch, then open `frontend/index.html` in a browser with `python3 -m uvicorn src.main:app --reload` running. Click "Analyst wall ↔" to verify the permission wall compare scenario, then switch to the Evals tab.

---

## Session — 2026-04-12 (Session 16 / Documentation Pass: Handoff + CLAUDE.md + Plan)

### Summary

Documentation-only pass after Prompt 7B code was committed as `df2c929 Task 7B almost`. No code changes. Updated CLAUDE.md, integration plan, and HANDOFF.md to reflect the completed Prompt 7B state.

**What was done:**

1. **CLAUDE.md** — two stale items fixed:
   - `uvicorn src.main:app --reload` → `python3 -m uvicorn src.main:app --reload` (uvicorn not on PATH on this system)
   - Frontend scenario reference updated: "Sarah as Analyst ↔" → correct three-scenario description with "Analyst wall ↔", "VP deal view ↔", "Partner view ↔"

2. **Integration plan** — Prompt 7B Outcome section appended (light theme, VP/Partner scenarios, freshness N/A fix, README rewrite, verification results)

3. **HANDOFF.md** — Session 15's commit list and file count corrected; this entry added

### Current State

- **Branch:** `main`
- **Commits:** `df2c929` (Task 7B almost — contains Prompt 7B frontend polish + README rewrite)
- **Working tree:** 3 modified files uncommitted (this documentation pass only):
  - `CLAUDE.md` — uvicorn command + scenario reference
  - `docs/HANDOFF.md` — this entry
  - `docs/plans/2026-04-10-pipeline-integration-plan.md` — Prompt 7B outcome section
- **Tests:** 148 passed, 14 skipped, 0 failed
- **Evaluator:** precision@5=0.3000, recall=1.0000, violations=0%
- **Hostile review:** `clean` (Prompt 7A — no new review; Prompt 7B was frontend/docs only)

### Remaining Tasks (ordered)

1. **Commit this documentation batch** — `CLAUDE.md`, `docs/HANDOFF.md`, `docs/plans/2026-04-10-pipeline-integration-plan.md`

2. **Browser visual verification** — Open `frontend/index.html` with `python3 -m uvicorn src.main:app --reload` running. Confirm:
   - Light theme renders (cream background, white cards, warm amber accent)
   - "Single" and "Compare" scenario rows visible and labelled
   - "Analyst wall ↔" shows 7 blocked in full/rbac, 0 in naive
   - "VP deal view ↔" and "Partner view ↔" trigger compare mode with correct roles
   - Naive column freshness shows "freshness N/A" not 0.00
   - Evals tab renders 10 metric cards + 8-row per-query table

3. **Optional: Remove dead code** — `apply_freshness()` in `freshness.py` and `filter_by_role()` in `policies.py` are unreachable on the request path

### Blockers and Warnings

None blocking. The only pending item is manual browser verification (cannot be done from CLI).

### Suggested First Action

Commit the 3 documentation files, then open `frontend/index.html` in a browser with the server running.

---

## Session — 2026-04-12 (Session 17 / Browser Verification: Prompt 7B Demo-Ready)

### Summary

Browser verification pass using `webapp-testing` Playwright skill. **44 passed / 0 failed / 0 warnings.** Prompt 7B is complete and demo-ready. No code changes in this session.

**What was verified:**

- **Light theme:** body background confirmed `rgb(245, 241, 234)` — warm cream as intended
- **Page load:** QueryTrace brand, 3 mode buttons, empty state with "Permission-Aware Context Gateway" title and "Analyst wall ↔" hint
- **Scenario rows:** "SINGLE" and "COMPARE" rows both visible and labelled; all 3 scenario buttons present
- **Single mode:** 5 analyst docs, summary bar, relevance bars, Decision Trace expand/collapse, 13 chips, budget bar
- **Analyst wall ↔:** 7 `blocked in full` flags on NAIVE column; NAIVE blocked=0, FULL blocked=7; NAIVE freshness shows "N/A" (12 labels); 3 trace panels open by default
- **VP deal view ↔:** 3 columns, FULL blocked=2, compare banner shows VP role
- **Partner view ↔:** 3 columns, FULL blocked=0 (full access confirmed), partner role in banner
- **Mode switching:** Compare → Single: results visible, policy selector restored; Single → Evals: search section hidden
- **Evals tab:** 10 metric cards, Precision@5=0.3000, Recall=1.0000, Violations=0.0%, 8-row table, footer "Queries run: 8 · Failed: 0"
- **naive_top_k freshness N/A:** 12 N/A labels confirmed in single mode

### Current State

- **Branch:** `main`
- **Last commit:** `551972e` (Task 7B almost2 — CLAUDE.md + HANDOFF + plan docs)
- **Working tree:** modified `docs/HANDOFF.md`, `docs/plans/2026-04-10-pipeline-integration-plan.md` (this pass only)
- **Tests:** 148 passed, 14 skipped, 0 failed
- **Evaluator:** precision@5=0.3000, recall=1.0000, violations=0%
- **Browser verification:** COMPLETE — 44/44 Playwright checks
- **Hostile review:** `clean` (Prompt 7A; Prompt 7B was frontend/docs only)
- **Demo status:** READY

### Remaining Tasks (ordered)

1. **Commit this documentation batch** — `docs/HANDOFF.md`, `docs/plans/2026-04-10-pipeline-integration-plan.md`

2. **(Optional) Remove dead code** — `apply_freshness()` in `freshness.py` and `filter_by_role()` in `policies.py` are unreachable on the request path; safe to delete when convenient

3. **(Optional) Evaluator corpus re-read** — `run_evals()` reloads roles/metadata independently of `main.py`'s loaded copies; cosmetic, no correctness impact

### Blockers and Warnings

None. Project is demo-ready.

### Suggested First Action

Commit the 2 documentation files. No further work is required before submission.

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
