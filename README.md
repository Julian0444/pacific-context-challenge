# QueryTrace — Context Policy Lab

> When an LLM asks for context, *what gets in — and what gets left out — is a policy decision.* QueryTrace makes every one of those decisions visible.

QueryTrace is a retrieval pipeline that assembles token-budgeted document context for LLM prompts and exposes a full audit trace of every filtering, ranking, and packing decision along the way. It combines hybrid search (FAISS semantic + BM25 lexical, fused via Reciprocal Rank Fusion), role-based access control, corpus-relative freshness scoring with stale-document penalties, and greedy token-budget packing — then lets you compare what happens when you turn each of those controls on and off.

The corpus is a 16-document private equity deal scenario (Atlas Capital acquiring Meridian Technologies at $340M) spanning public filings, research notes, deal memos, financial models, IC memos, legal diligence, and LP updates — with three access tiers (analyst, VP, partner) and three superseded document pairs that test how the pipeline handles outdated information.

**[Try it live](https://context-policy-lab.onrender.com/app/)** — no setup required.

---

## What you'll see

### Three scenarios that show why retrieval policy matters

| Scenario | What to try | What it reveals |
|---|---|---|
| **Permission Wall** | Query "ARR growth rate" as an **analyst** | The analyst sees 6 documents. Switch to Compare mode: the naive pipeline (no filters) surfaces all 16 — including 10 VP/partner-only docs the analyst should never see. |
| **Financial Model Access** | Query "financial model revenue projections" as a **VP** | The VP gains access to deal memos and financial models blocked from analysts. The full pipeline demotes the superseded financial model v1 (`doc_007` → `doc_008`). |
| **Stale Detection** | Query "IC memo and LP quarterly update" as a **partner** | The partner has full corpus access — no permission blocks in any policy. But the full pipeline still demotes 3 superseded documents with a 0.5x freshness penalty, pushing current versions higher. |

The frontend's **Compare mode** runs the same query through all three policies side by side, so you can see exactly which documents appear, disappear, or get reranked as controls are toggled.

### Decision Trace

Every response includes a `decision_trace` that accounts for every retrieved document:

- **Included** — documents packed into context, with similarity score, freshness score, and token count
- **Blocked by permission** — documents the role cannot access, with the required role and reason
- **Demoted as stale** — superseded documents that received a 0.5x freshness penalty
- **Dropped by budget** — documents that scored well but didn't fit the token budget
- **Metrics** — aggregate counts, average scores, budget utilization, and wall-clock pipeline time

The invariant `blocked + included + dropped == retrieved` is enforced at runtime — every candidate is accounted for.

---

## Pipeline

```
query + role
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  retrieve(query, top_k × 3)                              │
│  FAISS cosine + BM25 lexical → Reciprocal Rank Fusion    │
│  min-max normalize to [0, 1]                             │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  filter_permissions(docs, role)                          │
│  user access_rank >= doc min_role rank?                   │
│  → permitted[]  +  blocked_by_permission[]               │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  score_freshness(docs, metadata)                         │
│  exponential decay (half-life) × 0.5 if superseded       │
│  → scored[]  +  demoted_as_stale[]                       │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  pack_budget(docs, token_budget)                         │
│  rank by 0.5×similarity + 0.5×freshness                  │
│  greedy pack with tiktoken counting                      │
│  → packed[]  +  dropped_by_budget[]                      │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  build_trace(...)                                        │
│  assert blocked + included + dropped == retrieved        │
│  → DecisionTrace with full metrics                       │
└─────────────────────────────────────────────────────────┘
```

The pipeline over-retrieves by 3x (`top_k × 3` candidates) to compensate for permission attrition before the budget packer clamps the final set. Each stage is a pure function with typed inputs and a named result dataclass — no I/O, no side effects, no shared state.

### Policy presets

| Preset | Permission filter | Freshness scoring | Token budget | Purpose |
|---|---|---|---|---|
| `naive_top_k` | off | off | off | Dangerous baseline — shows what uncontrolled retrieval looks like |
| `permission_aware` | **on** | off | **on** | RBAC + budget, ignores staleness |
| `full_policy` | **on** | **on** | **on** | Production: all controls active |

---

## Corpus

16 documents from a fictional PE acquisition (Atlas Capital / Meridian Technologies — "Project Clearwater"):

```
analyst  (rank 1)  — public filings, research notes, press releases, news, sector overview
VP       (rank 2)  — deal memos, financial models, internal email, internal memos
partner  (rank 3)  — IC memos, LP updates, board materials, legal diligence
```

Three superseded document pairs test how the pipeline handles outdated information:

| Superseded | Replaced by | What changed |
|---|---|---|
| `doc_002` Research Notes Q3 | `doc_003` Research Notes Q4 | Quarterly revision |
| `doc_007` Financial Model v1 ($480M) | `doc_008` Financial Model v2 ($340M) | Valuation revised down |
| `doc_014` IC Draft (defer) | `doc_010` IC Final (approve) | Recommendation reversed |

---

## Evaluation

A 12-query harness runs through the production pipeline and measures:

| Metric | Value | What it means |
|---|---|---|
| Avg Precision@5 | 0.33 | Top-5 hit rate across diverse query types |
| Avg Recall | 1.00 | Every expected document is retrieved somewhere in the ranked list |
| Permission violations | 0% | No role ever sees a document above its clearance |
| Avg budget utilization | 71% | Token budget is used efficiently without overpacking |
| Avg blocked | 4.17 | Average docs filtered by RBAC per query |
| Avg stale demoted | 2.08 | Average superseded docs penalized per query |

Test queries cover: revenue growth, stale document handling, permission walls, customer concentration, model revisions, board access, integration risks, LP reporting, legal diligence, governance changes, valuation contradictions, and leadership continuity.

---

## Frontend

Four modes, no build step:

- **Query** — single-policy query with role and policy selector. Result cards show document title, metadata, relevance + freshness bars, stale badges, and a blocked-documents section. Collapsible Decision Trace panel with a natural-language summary.
- **Compare** — same query through all three policies side by side. Shows which documents appear, disappear, or get reranked as controls change.
- **Metrics** — benchmark results (precision, recall, permission safety) + live session audit log of every query since server start.
- **Upload** — PDF ingestion with metadata (title, date, role, doc type, sensitivity, tags). Triggers a full FAISS + BM25 rebuild. Disabled on the public deploy.

Onboarding cards on first load guide you through the three key scenarios with one click.

---

## API

```
POST /query          →  single-policy retrieval + decision trace
POST /compare        →  same query through multiple policies side-by-side
GET  /evals          →  12-query benchmark results (cached after first call)
GET  /session-audit  →  in-memory log of every /query call since startup
POST /ingest         →  PDF upload + corpus rebuild (disabled on public deploy)
GET  /health         →  status + feature flags
```

Interactive API docs at [`/docs`](https://context-policy-lab.onrender.com/docs).

---

## Running locally

```bash
pip install -r requirements.txt
python3 -m uvicorn src.main:app --reload
# App:  http://localhost:8000/app/
# API:  http://localhost:8000/docs
```

FAISS index and BM25 corpus are pre-built and committed — no indexing step needed. To rebuild after changing documents:

```bash
python3 -m src.indexer
```

Tests:

```bash
python3 -m pytest tests/ -v    # 175 passing, 14 skipped (deprecated)
python3 -m src.evaluator       # 12-query eval harness
```

---

## Project structure

```
src/
  main.py              FastAPI app — endpoints + static mount at /app
  pipeline.py          Stage orchestrator (StageOk/StageErr, abort-on-failure)
  stages/
    permission_filter.py   RBAC filter → PermissionResult
    freshness_scorer.py    Exponential decay + stale penalty → FreshnessResult
    budget_packer.py       Greedy token packing → BudgetResult
    trace_builder.py       Audit trace assembly → DecisionTrace
  retriever.py         Hybrid FAISS + BM25 via Reciprocal Rank Fusion
  indexer.py           Builds FAISS index + BM25 corpus from documents
  models.py            Pydantic models (frozen, extra=forbid)
  policies.py          Three policy presets + resolver
  protocols.py         DI interfaces (RetrieverProtocol, RoleStoreProtocol)
  evaluator.py         12-query evaluation harness
  ingest.py            PDF upload → text extraction → corpus rebuild
corpus/
  documents/           16 source documents (.txt)
  metadata.json        Per-doc: min_role, superseded_by, tags, dates
  roles.json           analyst / vp / partner with access_rank
artifacts/             Pre-built FAISS index + BM25 corpus (committed)
evals/
  test_queries.json    12 corpus-grounded queries with expected doc IDs
frontend/
  index.html           Static UI (no build step)
  app.js               Query / Compare / Metrics / Upload modes
  styles.css
tests/                 175 passing, 14 skipped
```

---

## Tech stack

- **Backend:** Python, FastAPI, Pydantic v2
- **Retrieval:** FAISS (semantic), BM25 (lexical), sentence-transformers (all-MiniLM-L6-v2)
- **Tokenization:** tiktoken (cl100k_base) for budget packing
- **Frontend:** Vanilla HTML/CSS/JS (no framework, no build step)
- **Ingestion:** pdfplumber for PDF text extraction
- **Deploy:** Render (single service, static frontend mounted at `/app/`)
