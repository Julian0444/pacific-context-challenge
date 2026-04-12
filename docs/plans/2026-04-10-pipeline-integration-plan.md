# Pipeline Integration Plan — 2026-04-10
# Updated after Prompt 4 (Session 10) — 2026-04-11

## Executive Summary

Sessions 7–8 introduced contract models, protocols, the pipeline orchestrator, and wired `main.py`. Session 9 (Prompt 3) delivered `src/stages/` (P3-1), hardened the `DecisionTrace` model, and refactored `pipeline.py` to delegate to typed stages. Session 10 (Prompt 4) replaced the semantic-only retriever with hybrid retrieval (FAISS + BM25 via RRF), added `tests/test_retriever.py`, and tuned `pipeline.py` to over-retrieve by 3× to compensate for permission attrition. P0, P1, P2-1, P2-2, P3-1, P3-3, and the out-of-scope P4 (hybrid retrieval) are complete. **P2-3 is the sole remaining planned item.** P3-2 will be resolved as a side-effect of P2-3.

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
| P2-3 | Wire evaluator.py | ⏳ **Pending — Prompt 5 target** |
| P3-1 | src/stages/ typed functions | ✅ Done |
| P3-2 | freshness.py mutation refactor | 🔶 Partial — resolves automatically when P2-3 lands |
| P3-3 | CLAUDE.md cleanup | ✅ Done |
| P4-1 | Hybrid retrieval (FAISS + BM25 via RRF) | ✅ Done |

## Prompt 5 Scope (tests + evaluator + hardening)

Everything remaining collapses to one work item:

**P2-3: Wire `evaluator.py` to `run_pipeline()`**
- Replace `retrieve → filter_by_role → apply_freshness → assemble` inline pipeline in `run_evals()` with `run_pipeline(request, retriever, roles, metadata)`
- Adapt `per_query` metrics extraction to use `PipelineResult.trace` fields (`trace.included`, `trace.blocked_by_permission`, `trace.metrics`)
- Update `tests/test_evaluator.py` assertions to match the wired interface (assembled_ids sourced from `IncludedDocument` objects, not raw dicts)
- Run `python3 -m src.evaluator` and confirm precision@k ≥ 0.33, recall = 1.0, permission_violation_rate = 0%
- P3-2 closes as a side-effect: `apply_freshness()` will no longer be called anywhere on the request path

**Acceptance criteria:**
1. `python3 -m pytest tests/ -q` → all 137+ tests pass
2. `python3 -m pytest tests/test_evaluator.py -v` → all 17+ tests pass
3. `python3 -m src.evaluator` → produces output with `permission_violation_rate: 0%`, `avg_recall: 1.0000`

## Recommended Prompt 5 Starting Point

```
# In evaluator.py run_evals():
from src.pipeline import run_pipeline
from src.models import QueryRequest

for q in queries:
    request = QueryRequest(query=q["query"], role=q["role"], top_k=top_k)
    result = run_pipeline(request, retrieve, roles, metadata)
    # assembled_ids = [doc.doc_id for doc in result.context]
    # freshness values from result.trace.included[i].freshness_score
```
