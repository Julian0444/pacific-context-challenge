# Pipeline Integration Plan — 2026-04-10
# Updated after Prompt 5 (Session 11) — 2026-04-12

## Executive Summary

Sessions 7–8 introduced contract models, protocols, the pipeline orchestrator, and wired `main.py`. Session 9 (Prompt 3) delivered `src/stages/` (P3-1), hardened the `DecisionTrace` model, and refactored `pipeline.py` to delegate to typed stages. Session 10 (Prompt 4) replaced the semantic-only retriever with hybrid retrieval (FAISS + BM25 via RRF), added `tests/test_retriever.py`, and tuned `pipeline.py` to over-retrieve by 3× to compensate for permission attrition. Session 11 (Prompt 5) wired `evaluator.py` to `run_pipeline()` (P2-3), removed the dead `token_budget` evaluator interface, added trace-level metrics to evaluator output, hardened tests, and marked legacy dict-plumbing tests as deprecated. P3-2 closed as a side-effect. **All planned items are complete.** Remaining work is a test hardening MINOR fix and frontend trace display.

---

## Tasks

### P0 — Blocking ✅ COMPLETE

#### ~~P0-1: Fix MetadataStoreProtocol shape mismatch~~ — DONE
Updated `MetadataStoreProtocol` to match actual raw metadata shape (`metadata["documents"]` → list). Fixed docstring and `__getitem__` semantics.

#### ~~P0-2: Fix RoleStoreProtocol.keys() return type annotation~~ — DONE
Changed return type from `List[str]` to `Iterable[str]`, compatible with `dict.keys()`.

---

### P1 — Quick wins ✅ COMPLETE

#### ~~P1-1: Add per-document token_count to assembler output~~ — DONE
`assemble()` now includes `token_count` in each output dict. `IncludedDocument` construction in the pipeline uses it directly.

#### ~~P1-2: Integration test proving ScoredDocument parses real retriever output~~ — DONE
`tests/test_pipeline.py::test_default_policy_returns_pipeline_result` exercises the full retrieve → `ScoredDocument.model_validate` boundary with real data.

---

### P2 — Core pipeline.py build

#### ~~P2-1: Create src/pipeline.py~~ — DONE
Five-stage orchestrator: retrieve → permission_filter → freshness_scorer → budget_packer → trace_builder.
- Each stage returns `StageOk | StageErr`; `_unwrap()` raises `PipelineError` on failure
- `run_pipeline(request, retriever, roles, metadata) → PipelineResult`
- `DecisionTrace` populated with blocked, stale, included, and metrics on every run
- 18 integration tests in `tests/test_pipeline.py`
- Policy presets added to `src/policies.py`: `naive_top_k` (retrieval only, no RBAC, no freshness, no budget), `permission_aware` (RBAC, no freshness), `full_policy`, `default`
- `PolicyConfig` extended with `skip_permission_filter`, `skip_freshness`, `skip_budget`

#### ~~P2-2: Wire main.py to pipeline.py~~ — DONE
`main.py` is now a minimal HTTP boundary: validate role → `run_pipeline()` → map response. `decision_trace` is populated in every `/query` response. All 6 `test_main.py` tests pass.

#### ~~P2-3: Wire evaluator.py to pipeline.py~~ — DONE
`evaluator.py:run_evals()` now calls `run_pipeline(QueryRequest(...), retrieve, roles, metadata)`. Inline pipeline (`filter_by_role`, `apply_freshness`, `assemble`) removed entirely. Assembled doc IDs and freshness scores come from `PipelineResult.trace.included` (typed `IncludedDocument` objects). Dead `token_budget` parameter and `--token-budget` CLI flag removed. Trace-level metrics (blocked_count, stale_count, dropped_count, budget_utilization) added to per-query and aggregate output. `tests/test_evaluator.py` grew from 17 → 22 tests. `tests/test_pipeline.py` grew from 18 → 28 tests. Legacy dict-plumbing tests (filter_by_role, apply_freshness, assemble) marked skipped (14 total across 3 files). Current eval metrics: precision@5=0.3000, recall=1.0000, permission_violation_rate=0%.

---

### P4 — Out-of-scope additions (completed in Prompt 4)

#### ~~P4-1: Hybrid retrieval (FAISS + BM25 via RRF)~~ — DONE
`src/retriever.py` rewritten to fuse semantic ranks (FAISS cosine similarity) with lexical ranks (BM25 Okapi) using Reciprocal Rank Fusion (k=60). Fused scores are min-max normalized to [0, 1].
- `src/indexer.py` extended with `tokenize_for_bm25`, `build_bm25_corpus`, `save_bm25_corpus`, `load_bm25_corpus`
- `artifacts/bm25_corpus.json` generated and committed
- `rank_bm25` added to `requirements.txt`
- `tests/test_retriever.py` added: 20 tests covering protocol compatibility, result shape, hybrid-vs-semantic ranking difference, RRF unit tests, and score normalization
- Initial evaluator regression after switching to hybrid: ranking order changed, causing precision@k to drop for some queries. Fixed by adding `retrieve_k = policy.top_k * 3` in `pipeline.py` to over-retrieve and compensate for downstream permission attrition.
- Final test count after Prompt 4: **137 passing** (`python3 -m pytest tests/ -q`)

---

### P3 — Deferred improvements

#### ~~P3-1: Create src/stages/ with typed stage functions~~ — DONE
`src/stages/` created with four typed pure-compute stage modules:
- `permission_filter.py` — `filter_permissions() → PermissionResult`
- `freshness_scorer.py` — `score_freshness() → FreshnessResult` (calls `compute_freshness()` directly, no mutation)
- `budget_packer.py` — `pack_budget() → BudgetResult` (tracks `over_budget` as `DroppedByBudget`)
- `trace_builder.py` — `build_trace() → DecisionTrace`
`pipeline.py` refactored to delegate to these stages. Stage results are named frozen dataclasses, not raw tuples.

#### ~~P3-2: Refactor freshness.py to return new dicts instead of mutating in-place~~ — CLOSED (side-effect of P2-3)
`freshness_scorer.py` in stages calls `compute_freshness()` directly and constructs new typed objects — no mutation. `apply_freshness()` in `freshness.py` is no longer called anywhere on the request path (evaluator now uses `run_pipeline()`). The mutation API remains in the codebase as dead code; it can be removed when convenient but poses no correctness risk.

#### ~~P3-3: Clean up CLAUDE.md~~ — DONE
Removed stale claims ("evaluator.py not implemented", "evals/test_queries.json has placeholders", leaked task prompt). CLAUDE.md now reflects the pipeline orchestrator, stage-based structure, policy presets, and `DecisionTrace` behavior.

---

## Status Summary

| Priority | Item | Status |
|----------|------|--------|
| P0-1 | MetadataStoreProtocol fix | ✅ Done |
| P0-2 | RoleStoreProtocol.keys() fix | ✅ Done |
| P1-1 | Assembler token_count | ✅ Done |
| P1-2 | ScoredDocument integration test | ✅ Done |
| P2-1 | src/pipeline.py | ✅ Done |
| P2-2 | Wire main.py | ✅ Done |
| P2-3 | Wire evaluator.py | ✅ Done |
| P3-1 | src/stages/ typed functions | ✅ Done |
| P3-2 | freshness.py mutation refactor | ✅ Closed (side-effect of P2-3) |
| P3-3 | CLAUDE.md cleanup | ✅ Done |
| P4-1 | Hybrid retrieval (FAISS + BM25 via RRF) | ✅ Done |

## Prompt 5 Outcome (completed 2026-04-12)

All planned items are now complete. The only open items are post-plan hardening and frontend work:

**Completed in Prompt 5:**
- P2-3: `evaluator.py` wired to `run_pipeline()` — inline pipeline removed
- Dead `token_budget` evaluator interface removed
- Trace-level metrics added to evaluator output and tests
- `tests/test_evaluator.py`: 17 → 22 tests
- `tests/test_pipeline.py`: 18 → 28 tests
- 14 legacy dict-plumbing tests marked skipped (filter_by_role, apply_freshness, assemble)
- P3-2 closed as side-effect
- Two passes of hostile review; verdict `risks_noted`

**Remaining (outside original plan scope):**
1. ~~Fix hostile review MINOR~~ — **DONE (Prompt 6 follow-up)**: added `assert result.trace.policy_config.skip_budget is False` to `test_permission_aware_enforces_budget`
2. ~~Hostile review Pass 3 → achieve `clean` verdict~~ — **DONE (Prompt 6 Pass 3)**: two consecutive clean passes achieved; verdict `clean`
3. ~~Frontend: surface `decision_trace` fields (blocked, stale, dropped, budget_utilization) in the UI~~ — **DONE (Prompt 6)**: Decision Trace panel renders all four categories with colored chips and budget utilization bar
4. ~~Frontend: comparison view for `naive_top_k` vs `full_policy`~~ — **DONE (Prompt 6)**: 3-column compare mode (naive/rbac/full) with `POST /compare` endpoint, policy severity color coding, cross-policy highlights
5. ~~Demo readiness: trace fields visible in browser~~ — **DONE (Prompt 6)**: Full pipeline story demonstrable; "Sarah as Analyst" scenario button triggers compare mode directly

**Prompt 6 Pass 3 hardening (compare endpoint):**
- Empty-policies guard added to `POST /compare`: `if not request.policies: raise HTTPException(400, ...)`
- `test_compare_returns_all_three_policies` strengthened: uses analyst role + restricted query; asserts `decision_trace is not None`; asserts `naive_top_k.blocked_count == 0` and `full_policy.blocked_count > 0`
- `test_compare_empty_policies_returns_400` added
- `tests/test_main.py`: 9 → 11 tests

**Current test state after Prompt 6:** 142 passed, 14 skipped, 0 failed
**Current eval metrics:** precision@5=0.3000, recall=1.0000, permission_violation_rate=0%
**Hostile review verdict (Prompt 6):** `clean` (two consecutive clean passes — Pass 2 and Pass 3)

---

## Prompt 7A Outcome (completed 2026-04-12)

All original plan items remain complete. Prompt 7A added evaluator HTTP exposure and frontend Evals dashboard — both outside the original plan scope.

**Completed in Prompt 7A:**
- `GET /evals` endpoint added to `src/main.py` — calls `run_evals()` via existing evaluator; module-level cache (`_evals_cache`) for ~1.6ms warm responses vs. ~5–10s cold. Additive: no changes to `/query` or `/compare`.
- 6 new tests in `tests/test_main.py` (11 → 17): status, aggregate keys, 8-query count, no violations (with error-record guard), per-query key shape (`precision_at_5` contract), caching identity
- Frontend third mode "Evals": lazy-fetches `GET /evals` on first tab switch; 10 aggregate metric cards + 8-row per-query breakdown table; structured JSON consumed directly (no CLI text parsing)
- Hostile review: Pass 1 found 2 MINOR (misleading test assertion on error records; per-query key untested) + 1 MINOR noted (evaluator re-reads corpus files) + 2 NIT. Both MINORs fixed. Pass 2 clean. Verdict: `clean`

**Current test state after Prompt 7A:** 148 passed, 14 skipped, 0 failed
**Current eval metrics:** precision@5=0.3000, recall=1.0000, permission_violation_rate=0% (unchanged)
**Hostile review verdict (Prompt 7A):** `clean`

**Uncommitted files (as of end of Prompt 7A):**
- `src/main.py`, `tests/test_main.py`, `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`

**Remaining post-plan items:**
1. Commit Prompt 7A batch
2. Browser visual verification of Evals tab (not yet performed — only curl + JS syntax check done)
3. Prompt 7B display-quality fixes: `naive_top_k` freshness shows `0.0` (misleading); `POLICY_META` unknown-policy badge fallback; duplicate CSS `@media` block

---

## Prompt 7B Outcome (completed 2026-04-12)

All original plan items remain complete. Prompt 7B was a polish and demo-readiness pass — no backend changes.

**Completed in Prompt 7B:**

- **Light theme migration** (`frontend/styles.css` full rewrite): warm parchment palette (`--bg-page: #f5f1ea`, `--bg-card: #ffffff`, amber `#8b6914`), shadow system added, duplicate `@media` blocks merged (4 → 2)
- **VP and Partner compare scenarios** added to `frontend/index.html`: "VP deal view ↔" and "Partner view ↔" alongside the existing "Analyst wall ↔" (renamed from "Sarah as Analyst ↔"). Two-row scenario layout ("Single" / "Compare") with role-dot indicators
- **`naive_top_k` freshness N/A fix** (`frontend/app.js`): freshness score now renders as "N/A — skipped by policy" instead of misleading `0.00` in both single and compare card views. `skipFreshness: true` added to POLICY_META
- **POLICY_META fallback badge fix**: unknown policy variant changed from `"full"` (green) to `"unknown"` (neutral grey `col-badge-unknown`)
- **README complete rewrite**: old TODO-list stub replaced with demo table, pipeline diagram, policy preset matrix, corpus access control docs, curl examples, evaluator metrics, artifact regeneration instructions
- **CLAUDE.md**: fixed `uvicorn` command to `python3 -m uvicorn`; updated frontend scenario reference
- **Verification pass**: `python3 -m pytest -q` → 148 passed, 14 skipped, 0 failed; `python3 -m src.evaluator` → precision@5=0.3000, recall=1.0000, violations=0%; JS syntax clean; all 3 endpoints verified via curl

**Current test state after Prompt 7B:** 148 passed, 14 skipped, 0 failed
**Current eval metrics:** precision@5=0.3000, recall=1.0000, permission_violation_rate=0% (unchanged)
**Hostile review verdict:** `clean` (from Prompt 7A — no new review; Prompt 7B changes are frontend/docs only)

**All Prompt 7B files committed across two commits:**
- `df2c929 Task 7B almost` — frontend polish + README
- `551972e Task 7B almost2` — CLAUDE.md + HANDOFF.md + this plan

**Browser verification (completed 2026-04-12):** `webapp-testing` Playwright run — 44 passed / 0 failed / 0 warnings. Confirmed: light theme `rgb(245,241,234)`, Single/Compare/Evals modes, Analyst wall (7 blocked), VP deal view (2 blocked), Partner view (0 blocked), NAIVE freshness N/A, Evals P@5=0.3000/Recall=1.0000/Violations=0%.

**Prompt 7B status: COMPLETE and demo-ready.**

**Remaining optional items (non-blocking):**
1. ~~Manual browser verification~~ — **DONE** (44/44 Playwright checks pass)
2. Remove dead code — `apply_freshness()` and `filter_by_role()` are unreachable on the request path
3. `run_evals()` corpus re-read — reloads roles/metadata independently of `main.py`'s loaded copies; cosmetic, no correctness impact

---

## Prompt 8 Outcome (completed 2026-04-13)

Final hardening / submission-readiness pass. No architecture changes. Four targeted fixes applied.

**Completed in Prompt 8:**

- **Bug fix — `/query` invalid policy returned 500** (`src/main.py`): Added `except ValueError` guard matching the one already present in `/compare`. Invalid `policy_name` now returns `400` with a clear error message. Test added: `test_query_invalid_policy_returns_400`.
- **XSS fix — trace chip `title` attributes** (`frontend/app.js`): `required_role` and `superseded_by` values in blocked/stale chip `title` attributes were unescaped; wrapped in `escapeHTML()`.
- **Stale docstring fix** (`src/protocols.py`): `MetadataStoreProtocol` docstring referenced dead `freshness.apply_freshness`; updated to `stages.freshness_scorer.score_freshness`.
- **Stale comment fix** (`src/freshness.py`): `compute_freshness()` docstring referenced dead `apply_freshness`; updated to "the stages layer".
- **Browser verification (65 Playwright checks):** 0 UI failures. All demo flows confirmed: light theme, Single mode (full + naive), Compare mode (Analyst wall / VP / Partner scenarios), Evals dashboard, mode switching, 0 JS console errors.

**Current test state after Prompt 8:** 149 passed, 14 skipped, 0 failed
**Current eval metrics:** precision@5=0.3000, recall=1.0000, permission_violation_rate=0% (unchanged)
**Hostile review verdict:** `clean` (no new review — Prompt 8 changes are bug fixes only)

**Modified files (uncommitted at end of session):**
- `frontend/app.js`, `src/main.py`, `src/protocols.py`, `src/freshness.py`, `tests/test_main.py`

**Prompt 8 status: COMPLETE. Project is submission-ready.**
