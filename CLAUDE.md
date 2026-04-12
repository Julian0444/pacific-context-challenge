# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the API server (from repo root)
uvicorn src.main:app --reload
# API at http://localhost:8000, docs at http://localhost:8000/docs

# Rebuild the FAISS index after changing corpus documents
python3 -m src.indexer

# Run all tests
python3 -m pytest tests/ -v

# Run a single test file or test
python3 -m pytest tests/test_policies.py -v
python3 -m pytest tests/test_main.py::test_query_returns_200 -v
```

## Architecture

QueryTrace is a retrieval pipeline: natural-language query + user role in, token-budgeted document context out.

### Pipeline (POST /query in `src/main.py`)

`main.py` is a minimal HTTP boundary: validate role → `run_pipeline()` → map `PipelineResult` to `QueryResponse`.

```
run_pipeline(request, retriever, roles, metadata)   ← src/pipeline.py
  ↓
retrieve(query, top_k)          → List[ScoredDocument]      (raw FAISS hits validated into typed models)
  ↓
filter_permissions(docs, ...)   → PermissionResult           (permitted + blocked_by_permission)
  ↓
score_freshness(docs, metadata) → FreshnessResult            (scored + demoted_as_stale; 0.5× penalty for superseded)
  ↓
pack_budget(docs, budget)       → BudgetResult               (packed + over_budget + budget_utilization)
  ↓
build_trace(...)                → DecisionTrace              (full audit trace with metrics + ttft_proxy_ms)
  ↓
PipelineResult → QueryResponse  (context list, total_tokens, decision_trace)
```

Roles and metadata are loaded once at startup in `main.py`. The sentence-transformers model is lazy-loaded as a singleton in `retriever.py`.

### Stage-based structure (`src/stages/`)

Each stage is a standalone pure-compute function with typed inputs and a named result dataclass. No I/O, no side effects.

| Module | Function | Result type |
|--------|----------|-------------|
| `permission_filter.py` | `filter_permissions(docs, user_ctx, roles)` | `PermissionResult` |
| `freshness_scorer.py` | `score_freshness(docs, metadata, half_life_days)` | `FreshnessResult` |
| `budget_packer.py` | `pack_budget(docs, token_budget, enforce_budget)` | `BudgetResult` |
| `trace_builder.py` | `build_trace(...)` | `DecisionTrace` |

`pipeline.py` wraps each call in `StageOk`/`StageErr` and aborts on first failure via `PipelineError`.

### Policy presets (`src/policies.py`)

| Name | Permission filter | Freshness | Budget |
|------|-------------------|-----------|--------|
| `naive_top_k` | off | off | off (dangerous baseline) |
| `permission_aware` | on | off | on |
| `full_policy` | on | on | on |
| `default` | on | on | on (alias for full_policy) |

`resolve_policy(name, top_k)` looks up a preset and applies the request's `top_k` override.

### DecisionTrace

Every `/query` response includes `decision_trace` with:
- `user_context` — role and access_rank
- `policy_config` — which preset was used and its flags
- `included` — documents packed into context
- `blocked_by_permission` — documents the role cannot access
- `demoted_as_stale` — superseded documents (included with 0.5× freshness penalty)
- `dropped_by_budget` — documents that scored well but exceeded the token budget
- `metrics` — counts, `avg_score`, `avg_freshness_score`, `budget_utilization`
- `total_tokens` and `ttft_proxy_ms`

### Contract models (`src/models.py`)

Key types: `ScoredDocument`, `FreshnessScoredDocument`, `BlockedDocument`, `StaleDocument`, `DroppedByBudget`, `IncludedDocument`, `DecisionTrace`, `TraceMetrics`, `PipelineResult`, `QueryRequest`, `QueryResponse`. Domain models are `frozen=True + extra="forbid"`. `ScoredDocument` uses `extra="ignore"` to absorb extra keys the retriever returns.

### Indexing (`src/indexer.py`)

Embeds full document text with `all-MiniLM-L6-v2`, builds a FAISS `IndexFlatIP` (cosine similarity via L2-normalized vectors). Persists to `artifacts/querytrace.index` + `artifacts/index_documents.json`. The index must exist before the server starts — if missing, run `python3 -m src.indexer`.

### Corpus & access control

- `corpus/metadata.json` — each doc has `min_role` (analyst/vp/partner) and `superseded_by` (doc id or null for stale pairs)
- `corpus/roles.json` — three roles with `access_rank`: analyst (1) < vp (2) < partner (3)
- Access rule: user's `access_rank` >= document's `min_role` rank
- Two stale/superseded pairs: doc_002→doc_003 (research notes), doc_007→doc_008 (financial models)

### Evaluation harness (`src/evaluator.py`)

Fully implemented. `run_evals()` runs 8 corpus-grounded test queries through the pipeline and computes precision@k, recall, permission_violation_rate, avg_context_docs, avg_freshness_score. CLI: `python3 -m src.evaluator`. Currently uses its own inline pipeline (not yet wired to `run_pipeline()`).

### Frontend

Static HTML/JS in `frontend/`. `app.js` calls `POST /query` at `http://localhost:8000`. Open `frontend/index.html` directly in a browser (no build step). Displays doc_id, relevance score, freshness score, tags, and total_tokens per result.

## Environment note

Developed on Python 3.9.6 with LibreSSL 2.8.3. `tf-keras` may be needed for `sentence-transformers` compatibility on this Python version.