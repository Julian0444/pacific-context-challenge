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
retrieve(query, top_k)          → List[ScoredDocument]      (hybrid: FAISS cosine + BM25 lexical, fused via RRF; validated into typed models)
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

Key types: `ScoredDocument`, `FreshnessScoredDocument`, `BlockedDocument`, `StaleDocument`, `DroppedByBudget`, `IncludedDocument`, `DecisionTrace`, `TraceMetrics`, `PipelineResult`, `QueryRequest`, `QueryResponse`, `CompareRequest`, `CompareResponse`. Domain models are `frozen=True + extra="forbid"`. `ScoredDocument` uses `extra="ignore"` to absorb extra keys the retriever returns.

### Retrieval (`src/retriever.py`)

Hybrid retrieval combining FAISS semantic search and BM25 lexical search via Reciprocal Rank Fusion (RRF). Both rankers score the full corpus; RRF fuses the two 1-based rank dicts: `score(d) = 1/(60 + rank_sem) + 1/(60 + rank_bm25)`. Fused scores are min-max normalized to [0, 1]. `retrieve()` is the default (hybrid). `semantic_retrieve()` is provided for comparison. Both satisfy `RetrieverProtocol`.

The pipeline over-retrieves by 3× (`retrieve_k = policy.top_k * 3`) to compensate for downstream permission attrition before the budget packer clamps the final set.

### Indexing (`src/indexer.py`)

Embeds full document text with `all-MiniLM-L6-v2`, builds a FAISS `IndexFlatIP` (cosine similarity via L2-normalized vectors). Also tokenizes document text for BM25 (stopword-filtered). Persists three artifacts:
- `artifacts/querytrace.index` — FAISS index (384-dim vectors)
- `artifacts/index_documents.json` — ordered document payloads matching FAISS row order
- `artifacts/bm25_corpus.json` — tokenized corpus for BM25 (same row order)

All three must exist before the server starts. If missing, run `python3 -m src.indexer`.

### Corpus & access control

- `corpus/metadata.json` — each doc has `min_role` (analyst/vp/partner) and `superseded_by` (doc id or null for stale pairs)
- `corpus/roles.json` — three roles with `access_rank`: analyst (1) < vp (2) < partner (3)
- Access rule: user's `access_rank` >= document's `min_role` rank
- Two stale/superseded pairs: doc_002→doc_003 (research notes), doc_007→doc_008 (financial models)

### Evaluation harness (`src/evaluator.py`)

Fully implemented and wired to `run_pipeline()`. `run_evals()` runs 8 corpus-grounded test queries through the production pipeline and computes precision@k, recall, permission_violation_rate, avg_context_docs, avg_freshness_score, plus trace-level metrics (avg_blocked_count, avg_stale_count, avg_dropped_count, avg_budget_utilization). CLI: `python3 -m src.evaluator` (flags: `--k`, `--top-k`). The `--token-budget` flag was removed — budget is policy-owned. Current metrics: precision@5=0.3000, recall=1.0000, permission_violation_rate=0%.

### Compare endpoint (POST /compare in `src/main.py`)

Runs the same query through multiple policy presets side-by-side. Calls `run_pipeline()` for each requested policy — no business logic duplication. Request accepts `query`, `role`, `top_k`, and `policies` (default: all three presets). Returns `CompareResponse` with `results: Dict[str, QueryResponse]` keyed by policy name.

### Evals endpoint (GET /evals in `src/main.py`)

Returns cached evaluator results as structured JSON. On first call: loads `evals/test_queries.json`, runs `run_evals(queries, k=5, top_k=8)` through the production pipeline, and stores the result in a module-level cache. Subsequent calls return the cached dict (~1.6ms). Response shape: `{ "per_query": [...], "aggregate": {...} }`. The route is a thin dispatch — all metric logic lives in `src/evaluator.py`.

### Frontend

Static HTML/CSS/JS in `frontend/` — no build step. Open `frontend/index.html` directly in a browser with the server running.

Three modes controlled by a header toggle:
- **Single mode** — calls `POST /query` with a selected policy (naive/rbac/full). Renders result cards with relevance + freshness bars, tags, and a collapsible Decision Trace panel showing included/blocked/stale/dropped chips and budget utilization.
- **Compare mode** — calls `POST /compare`. Renders three side-by-side policy columns (NAIVE/RBAC/FULL) with severity-colored headers, stats strips (included/tokens/blocked/stale/dropped/ttft), compact doc cards, and expanded Decision Trace panels. Docs in the naive column that are blocked in `full_policy` are flagged with `blocked in full` annotations.
- **Evals mode** — calls `GET /evals` (lazy on first tab switch). Renders 10 aggregate metric cards (precision@5, recall, permission_violation_rate, avg_context_docs, avg_total_tokens, avg_freshness_score, avg_blocked_count, avg_stale_count, avg_dropped_count, avg_budget_utilization) and an 8-row per-query breakdown table.

"Sarah as Analyst ↔" scenario button switches to compare mode, sets analyst role and ARR query, and auto-submits — directly demonstrates permission filtering across policies.

## Environment note

Developed on Python 3.9.6 with LibreSSL 2.8.3. `tf-keras` may be needed for `sentence-transformers` compatibility on this Python version.