# Pipeline Integration Plan — 2026-04-10
# Updated after Prompt 2 (Session 8) — 2026-04-11

## Executive Summary

Session 7 introduced 13 Pydantic contract models (`src/models.py`) and 3 Protocol interfaces (`src/protocols.py`). Session 8 (Prompt 2) delivered the full pipeline orchestrator and wired `main.py`. P0 and P1 items are complete. P2-1 and P2-2 are complete. P2-3 and all P3 items remain.

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

#### P3-1: Create src/stages/ with typed stage functions — **PENDING**
Individual modules where each function accepts/returns Pydantic models instead of dicts. Blocked on P3-2.

#### P3-2: Refactor freshness.py to return new dicts instead of mutating in-place — **PENDING**
Required before P3-1. Current pipeline works around mutation via model_dump/re-validate at boundaries.

#### P3-3: Clean up CLAUDE.md — **PENDING**
Still contains stale claims: "evaluator.py — not yet implemented", "evals/test_queries.json — placeholder entries", and appended webapp-testing instructions.

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
| P3-1 | src/stages/ typed functions | ⏳ Pending |
| P3-2 | freshness.py mutation refactor | ⏳ Pending |
| P3-3 | CLAUDE.md cleanup | ⏳ Pending |

## Recommended Next Steps

```
P2-3 → P3-3 → P3-2 → P3-1
```

P2-3 first (eliminates the last duplicate pipeline). P3-3 is a 5-minute doc fix. P3-2 unblocks P3-1.
