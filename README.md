# QueryTrace — Context Policy Lab

A **permission-aware context gateway** built as a policy lab. Given a natural-language query and a user role, QueryTrace retrieves relevant documents from a private equity corpus, applies role-based access control, penalises stale documents, enforces a token budget, and returns both the assembled context and a full decision audit trace.

**Corpus:** 12 documents from the fictional Atlas Capital / Meridian Technologies deal ("Project Clearwater") — spanning public filings, research notes, deal memos, financial models, board materials, and LP updates. Three role levels (analyst < VP < partner) enforced via `min_role` per document.

---

## Demo: the fastest path to understanding the system

### 1. Start the server

```bash
pip install -r requirements.txt
python3 -m uvicorn src.main:app --reload
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

### 2. Open the frontend

Open `frontend/index.html` in a browser (no build step required). The server must be running.

### 3. Run the key scenarios

The **Compare** tab shows all three policies side by side:

| Scenario | How to trigger | What it demonstrates |
|---|---|---|
| **Permission Wall** | Single empty state → card "Permission Wall" → `Open in Compare →` | Analyst is blocked from 7 VP/partner docs that naive retrieval surfaces. Full policy shows 7 blocked, naive shows 0. |
| **Financial model access** | Single empty state → card "Financial model access" → `Open in Compare →` | VP sees deal memos and financial models blocked from analyst. Stale doc_007 (financial model v1) is demoted by full policy. |
| **Stale Detection** (renamed from "Partner view") | Compare row shortcut `Stale detection →`, or Single empty state → card "Stale Detection" → `Open in Compare →` | Partner has full corpus access. No permission blocks in any policy. Full pipeline demotes 2 superseded docs 0.5× (doc_002, doc_007). |
| **Evals dashboard** | Click "Evals" tab | Live pipeline metrics: precision@5, recall, permission violation rate, trace counts across 8 test queries. |

---

## Architecture

```
POST /query   → run_pipeline() → QueryResponse  (single-policy)
POST /compare → run_pipeline() × 3 policies     (side-by-side)
GET  /evals   → run_evals() (cached after first call)
```

### Pipeline stages (`src/stages/`)

```
retrieve(query, top_k × 3)          → hybrid FAISS + BM25 via RRF
  ↓
filter_permissions(docs, role)       → permitted + blocked_by_permission
  ↓
score_freshness(docs, metadata)      → scored + demoted_as_stale (0.5× penalty)
  ↓
pack_budget(docs, token_budget)      → packed + dropped_by_budget
  ↓
build_trace(...)                     → DecisionTrace (full audit with metrics)
```

Over-retrieval: the pipeline fetches `top_k × 3` candidates to compensate for permission attrition before the budget packer clamps the final set.

### Policy presets (`src/policies.py`)

| Name | Permission filter | Freshness | Budget |
|---|---|---|---|
| `naive_top_k` | off | off | off |
| `permission_aware` | on | off | on |
| `full_policy` | on | on | on |
| `default` | on | on | on |

### Corpus & access control

```
analyst  (rank 1) — public filings, research notes, press releases
vp       (rank 2) — deal memos, financial models, internal email
partner  (rank 3) — IC memos, LP updates, board materials
```

Two superseded document pairs:
- `doc_002` → `doc_003` (research note Q3 → Q4 revision)
- `doc_007` → `doc_008` (financial model v1 → v2)

Superseded docs receive a 0.5× freshness penalty and appear in `demoted_as_stale` on the trace.

### DecisionTrace

Every `/query` and `/compare` response includes a `decision_trace` with:

- `included` — documents packed into context (with score, token count)
- `blocked_by_permission` — documents the role cannot access (with required role)
- `demoted_as_stale` — superseded documents (with penalty and superseding doc)
- `dropped_by_budget` — documents that scored well but exceeded the token budget
- `metrics` — counts, avg_score, avg_freshness_score, budget_utilization
- `ttft_proxy_ms` — wall-clock time of the pipeline

---

## All endpoints

```bash
# Single policy query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "ARR growth rate", "role": "analyst", "top_k": 8, "policy_name": "full_policy"}'

# Side-by-side policy comparison
curl -X POST http://localhost:8000/compare \
  -H "Content-Type: application/json" \
  -d '{"query": "ARR growth rate", "role": "analyst", "top_k": 8}'

# Evaluation dashboard (cached after first call ~5–10s)
curl http://localhost:8000/evals

# Health check
curl http://localhost:8000/health
```

---

## Running tests and evaluator

```bash
# Full test suite (172 passed, 14 skipped — skipped are deprecated legacy tests)
python3 -m pytest tests/ -v

# Evaluator — runs 8 corpus-grounded queries through the production pipeline
python3 -m src.evaluator
# Flags: --k 5 --top-k 8

# Current eval metrics:
#   Avg Precision@5: 0.3000
#   Avg Recall:      1.0000
#   Permission violations: 0%
#   Avg blocked: 3.38 · avg stale: 1.62 · avg budget util: 53%
```

---

## Regenerating artifacts

The FAISS index and BM25 corpus are pre-built and committed to `artifacts/`. If you change any documents in `corpus/documents/` or `corpus/metadata.json`, rebuild:

```bash
python3 -m src.indexer
# Produces:
#   artifacts/querytrace.index   — FAISS IndexFlatIP (384-dim, 12 vectors)
#   artifacts/index_documents.json
#   artifacts/bm25_corpus.json
```

---

## Project structure

```
src/
  main.py           # FastAPI app — /query, /compare, /evals, /health
  pipeline.py       # Orchestrator: StageOk/StageErr abort-on-failure
  stages/
    permission_filter.py   # filter_permissions() → PermissionResult
    freshness_scorer.py    # score_freshness()    → FreshnessResult
    budget_packer.py       # pack_budget()        → BudgetResult
    trace_builder.py       # build_trace()        → DecisionTrace
  retriever.py      # Hybrid FAISS + BM25 via RRF
  indexer.py        # Embeds docs, builds FAISS + BM25 artifacts
  policies.py       # Policy presets + resolve_policy()
  models.py         # Pydantic contract models (frozen + extra=forbid)
  protocols.py      # RetrieverProtocol, RoleStoreProtocol, MetadataStoreProtocol
  evaluator.py      # run_evals() — wired to run_pipeline()
corpus/
  documents/        # 12 .txt source documents
  metadata.json     # Per-doc: min_role, superseded_by, tags, dates
  roles.json        # analyst / vp / partner with access_rank
artifacts/          # Pre-built FAISS index + BM25 corpus (committed)
evals/
  test_queries.json # 8 corpus-grounded queries with expected doc IDs
frontend/
  index.html        # Static UI — open directly in browser
  app.js            # Single / Compare / Evals modes
  styles.css
tests/              # 172 passing, 14 skipped
  test_pipeline.py  test_stages.py  test_retriever.py
  test_models.py    test_evaluator.py  test_main.py  ...
```

---

## Environment note

Developed on Python 3.9.6 / macOS with LibreSSL 2.8.3. `tf-keras` may be needed for `sentence-transformers` compatibility on this Python version:

```bash
pip install tf-keras
```
