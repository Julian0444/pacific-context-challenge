# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the API server (from repo root)
python3 -m uvicorn src.main:app --reload
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

Key types: `ScoredDocument`, `FreshnessScoredDocument`, `BlockedDocument`, `StaleDocument`, `DroppedByBudget`, `IncludedDocument`, `DecisionTrace`, `TraceMetrics`, `PipelineResult`, `QueryRequest`, `QueryResponse`, `CompareRequest`, `CompareResponse`, `IngestResponse`. Domain models are `frozen=True + extra="forbid"`. `ScoredDocument` uses `extra="ignore"` to absorb extra keys the retriever returns.

`IncludedDocument` and `DocumentChunk` carry additional metadata (all `Optional[str] = None`): `title`, `doc_type`, `date`, `superseded_by`. These flow through the full chain: retriever `_build_results()` → `ScoredDocument.doc_type` → `FreshnessScoredDocument.doc_type` → `IncludedDocument` → `DocumentChunk` → API `context[]`. The frontend receives all four fields on every response item.

`BlockedDocument` also carries `title: Optional[str] = None` and `doc_type: Optional[str] = None`, populated by `permission_filter.py` from `doc.title` / `doc.doc_type`. These power the blocked-documents section in the Single mode frontend.

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

### Ingestion endpoint (POST /ingest in `src/main.py`)

Multipart endpoint for uploading a PDF + metadata at runtime. The HTTP handler in `main.py` is a thin adapter; all logic lives in `src/ingest.py`.

Form fields: `file` (PDF, ≤10 MB), `title`, `date` (YYYY-MM-DD), `min_role` (analyst/vp/partner), `doc_type` (one of 10 corpus values), `sensitivity` (low/medium/high/confidential), `tags` (comma-separated). `src/ingest.py` validates inputs, extracts text with `pdfplumber`, writes `corpus/documents/<sanitized_title>.txt` (no PDF is persisted), appends to `corpus/metadata.json`, and triggers `indexer.build_and_save()` for a full FAISS + BM25 rebuild. A module-level `threading.Lock` serializes the metadata write + reindex. After a successful ingest the endpoint mutates `main._metadata["documents"]` in place, calls `retriever.invalidate_caches()` (resets the in-process `_bm25` singleton; FAISS is re-read from disk on every request), and sets `_evals_cache = None`.

Error codes: 415 (non-PDF content-type), 400 (empty title / bad date / bad enum), 413 (>10 MB), 422 (unreadable PDF / <50 chars of extractable text). The happy-path response is `IngestResponse` (`src/models.py`) containing `doc_id`, `title`, `file_name`, `type`, `date`, `min_role`, `sensitivity`, `tags`, and `total_documents`.

Demo-scope caveats: no RBAC on `/ingest` (anyone can upload), no delete/edit path, reindex is synchronous (~5–10s), and writes go straight to repo paths — uploads will vanish on ephemeral hosting filesystems.

### Frontend

Static HTML/CSS/JS in `frontend/` — no build step. Open `frontend/index.html` directly in a browser with the server running.

Four modes controlled by a header toggle:
- **Single mode** — calls `POST /query` with a selected policy (No Filters / Permissions Only / Full Pipeline). Before any query runs, the results area renders a guided empty state (`#empty-state`) with three `.onboard-card` scenarios ("Permission Wall" / "Stale Detection" / "Full Access") in a responsive 3-column grid (collapses to 1 column ≤720px). Each card carries `data-query` / `data-role` / `data-mode="compare"` and reuses the `.example-btn` click handler, so clicking a card switches to Compare mode and runs the scenario in one step. The empty state is removed on the first query (does not restore for the session). Result cards show: document title as heading (fallback to `doc_id`), a metadata line with `doc_id` badge + formatted doc type + date, a 200-char excerpt with "Show more ▾ / Hide ▴" expand/collapse (expands to the full ~500-char indexer excerpt, not the source document), relevance + freshness bars, tags, and a stale/superseded badge ("⚠ Superseded by … — freshness penalized 0.5×") on demoted docs. Below the result cards, a collapsible blocked-documents section (🔒 N documents blocked by permissions) shows one mini-card per blocked doc with title, doc_id badge, doc type, and a human-readable reason ("Requires X role — you are Y"). The section is hidden when no documents are blocked. A collapsible Decision Trace panel below that opens with a natural-language summary paragraph (`.trace-summary`) translating included/blocked/stale/dropped counts into prose — e.g., "5 documents were included (571 tokens, 28% of budget). 7 documents were blocked — your role (analyst) cannot access vp-level materials." — followed by the existing technical chips and a metrics strip. `title=` tooltips on the Budget label, avg score, avg freshness, and ttft spans explain each metric. A role description paragraph (`#role-description`) sits under the role chips and updates on every role change (including programmatic sets from `.example-btn` / onboard-card clicks) via `ROLE_DESCRIPTIONS` + `updateRoleDescription()` in `app.js`. A policy description updates below the selector chips; selecting "No Filters" shows an amber warning banner.
- **Compare mode** — calls `POST /compare`. Renders three side-by-side policy columns (No Filters / Permissions Only / Full Pipeline) with severity-colored headers, stats strips (included/tokens/blocked/stale/dropped/ttft), compact doc cards (title heading, `doc_id` badge + type + date metadata, 120-char snippet, mini score/freshness bars, compact "⚠ Superseded" badge on stale docs), and expanded Decision Trace panels. Each column's trace panel opens with a compact variant of the narrative summary (`.trace-summary-compact`: tighter padding/type, stale details collapsed to a count, zero-dropped sentence omitted). Docs in the No Filters column that are blocked in `full_policy` are flagged with `blocked in full` annotations.
- **Evals mode** — calls `GET /evals` (lazy on first tab switch). Renders an executive-summary narrative banner (`.evals-narrative`) above the cards with three sentences: a permission-violations line (celebratory when rate=0, warning otherwise), a recall line (100% or fallback), and a budget-utilization tier line (`efficient <60%`, `moderate 60–80%`, `heavy >80%`). Then 10 aggregate metric cards (precision@5, recall, permission_violation_rate, avg_context_docs, avg_total_tokens, avg_freshness_score, avg_blocked_count, avg_stale_count, avg_dropped_count, avg_budget_utilization), each with a one-line `.metric-card-hint` micro-explanation. Below, an 8-row per-query breakdown table whose Query cell shows a `.evals-qid` id pill plus the query text truncated to 50 chars (full text via `title=`).
- **Admin mode** — hides the query form/results and shows an ingest form (file, title, date, min_role, doc_type, sensitivity, tags). `uploadDocument()` POSTs `FormData` to `/ingest`; the submit button disables and shows a spinner during the call, then renders a success status with the returned `doc_id` and the new corpus count, or an error status with the server message. All user-origin strings go through `escapeHTML`. A demo-only advisory in the panel notes that uploads persist to `corpus/` and `artifacts/` and will be lost on ephemeral hosting filesystems.

Policy labels in the UI are human-readable ("No Filters", "Permissions Only", "Full Pipeline") while the backend API names remain unchanged (`naive_top_k`, `permission_aware`, `full_policy`). `POLICY_META` in `app.js` maps between them. Both `naive_top_k` and `permission_aware` have `skipFreshness: true` — freshness displays as "N/A" since the backend skips freshness scoring for those policies.

Three one-click compare scenarios in the UI: "Analyst wall ↔" (analyst, ARR query — 7 docs blocked), "VP deal view ↔" (vp, financial model query), "Partner view ↔" (partner, IC memo query). Each auto-switches to Compare mode and submits.

## Environment note

Developed on Python 3.9.6 with LibreSSL 2.8.3. `tf-keras` may be needed for `sentence-transformers` compatibility on this Python version.

Ingestion adds two runtime deps in `requirements.txt`: `pdfplumber` (PDF text extraction) and `python-multipart` (FastAPI `File`/`Form` parsing). Both are pulled in by `pip install -r requirements.txt`.