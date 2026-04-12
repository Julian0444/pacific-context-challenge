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

**Current test state:** 142 passed, 14 skipped, 0 failed
**Current eval metrics:** precision@5=0.3000, recall=1.0000, permission_violation_rate=0%
**Hostile review verdict:** `clean` (two consecutive clean passes — Pass 2 and Pass 3)
