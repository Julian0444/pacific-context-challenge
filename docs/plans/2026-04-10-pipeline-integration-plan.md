# Pipeline Integration Plan — 2026-04-10
# Updated after Prompt 3 (Session 9) — 2026-04-11

## Executive Summary

Sessions 7–8 introduced contract models, protocols, the pipeline orchestrator, and wired `main.py`. Session 9 (Prompt 3) delivered `src/stages/` (P3-1), hardened the `DecisionTrace` model, and refactored `pipeline.py` to delegate to typed stages. P0, P1, P2-1, P2-2, and P3-1 are complete. P2-3, P3-2 (partial), and P3-3 remain.

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

#### P2-3: Wire evaluator.py to pipeline.py — **PENDING**
`evaluator.py:run_evals()` still contains its own inline retrieve → filter → freshness → assemble pipeline. Replace with calls to `run_pipeline()`. Extract metrics from `PipelineResult.trace`.
- Risk: `evaluator.py` calls `filter_by_role(chunks, role, roles)` with 3 args — do not change this signature
- Acceptance: all 17 `test_evaluator.py` tests pass; CLI `python3 -m src.evaluator` produces identical output

---

### P3 — Deferred improvements

#### ~~P3-1: Create src/stages/ with typed stage functions~~ — DONE
`src/stages/` created with four typed pure-compute stage modules:
- `permission_filter.py` — `filter_permissions() → PermissionResult`
- `freshness_scorer.py` — `score_freshness() → FreshnessResult` (calls `compute_freshness()` directly, no mutation)
- `budget_packer.py` — `pack_budget() → BudgetResult` (tracks `over_budget` as `DroppedByBudget`)
- `trace_builder.py` — `build_trace() → DecisionTrace`
`pipeline.py` refactored to delegate to these stages. Stage results are named frozen dataclasses, not raw tuples.

#### P3-2: Refactor freshness.py to return new dicts instead of mutating in-place — **PARTIAL**
`freshness_scorer.py` in stages calls `compute_freshness()` directly and constructs new typed objects — no mutation. The mutation path in `freshness.py:apply_freshness()` still exists but is no longer on the critical request path. `evaluator.py` still calls `apply_freshness()` via its own inline pipeline. Fully eliminating the mutation API requires wiring evaluator to `run_pipeline()` first (P2-3).

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
| P2-3 | Wire evaluator.py | ⏳ Pending |
| P3-1 | src/stages/ typed functions | ✅ Done |
| P3-2 | freshness.py mutation refactor | 🔶 Partial (stages bypass mutation; evaluator still uses apply_freshness) |
| P3-3 | CLAUDE.md cleanup | ✅ Done |

## Recommended Next Steps

```
P2-3 → (P3-2 fully eliminated once evaluator is wired)
```

P2-3 is the only remaining planned item. Wiring `evaluator.py` to `run_pipeline()` eliminates the last duplicate inline pipeline and will also complete P3-2 (the mutation path in `apply_freshness()` will no longer be called anywhere on the request path).
