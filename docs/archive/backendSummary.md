# QueryTrace — Backend Analysis

**Date:** 2026-04-18
**Scope:** Backend only (`src/`, pipeline, tests). Read-only audit, no code changes.
**Branch:** `codex/must-a-idea1-2`

**Freshly-run `pytest` status:** `171 passed, 1 failed, 14 skipped`. The failing test was `tests/test_retriever.py::TestResultShape::test_top_k_clamped_to_corpus_size` — at the time of the audit it hardcoded `len(results) == 12` but the corpus had drifted to 13 documents (see CR-1).

The working tree also had uncommitted drift (`corpus/documents/agenda.txt` untracked, `corpus/metadata.json` + `artifacts/*` modified) from an ingest that was never reverted.

**Update 2026-04-22 (UI-A):** the corpus contamination was removed. `agenda.txt` / `doc_013` no longer exists, artifacts were rebuilt to 12 vectors, and the test had been previously refactored to read `corpus_size` dynamically from `metadata.json`. Current `pytest` status: `172 passed, 14 skipped, 0 failed`. CR-1 below is historical.

**Update 2026-04-25 (UI-E):** the demo corpus was intentionally expanded to 16 redacted documents (`doc_013`–`doc_016` are now legal diligence, IC draft, public valuation article, and CTO memo). Artifacts were rebuilt to 16 vectors and the evaluator now runs 12 corpus-grounded queries. The `agenda.txt` contamination from UI-A remains resolved; the new `doc_013` is redacted content, not the old Agenda probe.

---

## Visual index of the analysis

```
┌─────────────────────────────────────────────────────────────────────┐
│                       THIS DOCUMENT                                 │
├─────────────────────────────────────────────────────────────────────┤
│  1. Executive summary of the backend                                │
│  2. Pipeline walkthrough (with flow diagram)                        │
│  3. Module-by-module map (with dependency graph)                    │
│  4. State, caching, and runtime (with concurrency diagram)          │
│  5. API contracts (with request/response schemas)                   │
│  6. Findings by severity (with visual distribution)                 │
│  7. Open questions                                                  │
│  8. Final verdict                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Executive summary of the backend

QueryTrace is a mostly read-only retrieval service. Two critical paths:

- **Query path** (`POST /query`, `POST /compare`, `GET /evals`): user text + role → hybrid retrieval (FAISS + BM25 fused with RRF) → RBAC filter → corpus-relative freshness scoring → greedy token-budget packing → audit trace. Pure compute after the retriever step.
- **Mutation path** (`POST /ingest`): multipart PDF → text via pdfplumber → near-atomic metadata append under a `threading.Lock` → synchronous FAISS+BM25 rebuild → in-process cache invalidation.

All persistent state lives on local disk (`corpus/`, `artifacts/`). No database, no network calls during a query, no background workers. The SBERT model, FAISS index, and BM25 object are lazy-loaded per-process singletons (`src/retriever.py:42-58`). Roles and metadata are loaded once at startup (`src/main.py:44-47`) but `_metadata` is a mutable dict so ingest can update it in place.

A Pydantic type chain runs end-to-end:

```
  ┌──────────────────┐   extra="ignore"     ┌────────────────────────┐
  │ retriever dict   │ ───────────────────▶│   ScoredDocument       │
  │ (FAISS + BM25)   │                      │ frozen, ignore extras  │
  └──────────────────┘                      └───────────┬────────────┘
                                                        │
                                                        ▼
                                         ┌──────────────────────────────┐
                                         │ FreshnessScoredDocument      │
                                         │ + freshness_score, is_stale  │
                                         └──────────────┬───────────────┘
                                                        │
                                                        ▼
               ┌─────────────────────┬─────────────────┴──────────┬───────────────────┐
               ▼                     ▼                            ▼                   ▼
      ┌────────────────┐  ┌─────────────────┐          ┌──────────────────┐  ┌────────────────┐
      │ BlockedDocument│  │ StaleDocument   │          │ IncludedDocument │  │ DroppedByBudget│
      │ (filter)       │  │ (freshness)     │          │ (budget packer)  │  │ (budget packer)│
      └───────┬────────┘  └────────┬────────┘          └────────┬─────────┘  └────────┬───────┘
              │                    │                            │                     │
              └────────────────────┴──────────┬─────────────────┴─────────────────────┘
                                              ▼
                                    ┌──────────────────────┐
                                    │   DecisionTrace      │
                                    │ + TraceMetrics       │
                                    └──────────┬───────────┘
                                               │
                                               ▼
                                    ┌──────────────────────┐
                                    │   QueryResponse      │
                                    │  (DocumentChunk[])   │
                                    └──────────────────────┘
```

Domain models are `frozen=True, extra="forbid"`; API boundary models are more lenient.

## 2. Pipeline walkthrough

**Entry:** `src/main.py:65 query()` → validate role → call `run_pipeline()` (`src/pipeline.py:126`) → map result to `QueryResponse`.

### Pipeline flow diagram

```
                         ┌──────────────────┐
                         │  POST /query     │
                         │  {query, role,   │
                         │   top_k, policy} │
                         └────────┬─────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │  main.py: query()         │
                    │  validate role → 400 if   │
                    │  unknown                  │
                    └──────────────┬───────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │  run_pipeline()           │
                    │  pipeline.py:126          │
                    └──────────────┬───────────┘
                                   │
                  resolve_policy(name, top_k)
                                   │
                                   ▼
          ┌────────────────────────────────────────────┐
          │ Stage 1: retrieve(query, top_k * 3)         │
          │   FAISS cosine  ─┐                          │
          │                  ├── RRF fusion ── norm ──▶ │
          │   BM25 lexical  ─┘                          │
          │                                             │
          │   Output: List[ScoredDocument]              │
          └──────────────────┬──────────────────────────┘
                             │
                             ▼
          ┌────────────────────────────────────────────┐
          │ Stage 2: filter_permissions()               │
          │   access_rank(user) >= rank(doc.min_role)?  │
          └───────┬────────────────────────┬────────────┘
                  │                        │
                  ▼                        ▼
           ┌─────────────┐         ┌─────────────────┐
           │ permitted   │         │ blocked[]       │
           │ (continues) │         │ (to the trace)  │
           └──────┬──────┘         └────────┬────────┘
                  │                         │
                  ▼                         │
          ┌────────────────────────────────────────────┐
          │ Stage 3: score_freshness()                  │
          │   exp_decay(age, half_life)                 │
          │   × 0.5 if superseded_by != null            │
          └──────────────────┬──────────────────────────┘
                             │ List[FreshnessScoredDocument]
                             │ + List[StaleDocument]
                             ▼
          ┌────────────────────────────────────────────┐
          │ Stage 4: pack_budget()                      │
          │   rank by 0.5*sim + 0.5*fresh               │
          │   greedy: if total+tk > budget → drop       │
          └───────┬────────────────────────┬────────────┘
                  │                        │
                  ▼                        ▼
           ┌─────────────┐         ┌─────────────────┐
           │ packed[]    │         │ over_budget[]   │
           │ (context)   │         │ (to the trace)  │
           └──────┬──────┘         └────────┬────────┘
                  │                         │
                  └────────────┬────────────┘
                               ▼
          ┌────────────────────────────────────────────┐
          │ Stage 5: build_trace()                      │
          │   INVARIANT:                                │
          │   blocked + included + dropped == retrieved │
          │   ⚠ raise ValueError if mismatch (MA-7)    │
          └──────────────────┬──────────────────────────┘
                             │ PipelineResult
                             ▼
                   ┌──────────────────────┐
                   │  QueryResponse       │
                   │  → HTTP 200 JSON     │
                   └──────────────────────┘
```

### Stage-by-stage detail

Inside `run_pipeline` (`src/pipeline.py:149-195`):

1. **Policy resolution** — `resolve_policy(name, top_k)` (`src/policies.py:36`) looks up `POLICY_PRESETS` and overrides `top_k` via `model_copy`. Raises `ValueError` if the name is unknown — main.py:76 converts it to HTTP 400.
2. **User context** — `roles[request.role]["access_rank"]` + role name → frozen `UserContext`.
3. **Retrieve** — `_retrieve_stage` calls the injected retriever with `retrieve_k = policy.top_k * 3`. The retriever (`src/retriever.py:177`) reads FAISS + BM25 from disk on every call, computes 1-based rank dicts, fuses with `RRF_score(d) = 1/(60+r_sem) + 1/(60+r_bm25)`, min-max normalizes to [0, 1], sorts, clamps to `top_k`, and builds dicts with all corpus metadata fields. Results are validated into `ScoredDocument`; extra keys are silently discarded (`extra="ignore"`).
4. **Permission filter** — `src/stages/permission_filter.py:26`. Two branches: `doc.min_role` unknown in roles → `BlockedDocument(reason="unknown_min_role")`; rank comparison → permitted or `BlockedDocument(reason="insufficient_role")`. Skipped entirely when `policy.skip_permission_filter=True` (naive_top_k).
5. **Freshness** — `src/stages/freshness_scorer.py:30`. Builds `meta_by_id` from all metadata on every call. Reference date = `max(all_dates)`. For each permitted doc: look up metadata, exponential decay (`compute_freshness` in `src/freshness.py:18`), multiply by `0.5` if superseded. Missing metadata → `freshness=0.0`, `is_stale=False`, but `superseded_by` is preserved from the ScoredDocument (inconsistent; finding MA-6). Produces `FreshnessScoredDocument` list + `StaleDocument` entries. If skipped → all freshness=0.0, none stale.
6. **Budget packer** — `src/stages/budget_packer.py:44`. Sorts by `0.5*score + 0.5*freshness_score`, iterates, tokenizes `doc.excerpt` with cl100k_base, packs greedily. Over-budget docs → `DroppedByBudget`. Returns `BudgetResult(packed, over_budget, total_tokens, budget_utilization)`. `enforce_budget=False` packs everything.
7. **Trace builder** — `src/stages/trace_builder.py:24`. Asserts `blocked+included+dropped == retrieved_count` (raises `ValueError` on mismatch — see finding MA-7). Computes avg_score, avg_freshness_score, assembles the full `DecisionTrace`.

`_unwrap` (`src/pipeline.py:60`) converts each `StageErr` to `PipelineError(stage, error)`, which main.py:78 maps to HTTP 500. Any non-stage exception from `run_pipeline` bubbles up as-is.

## 3. Module map

### Dependency graph

```
                          ┌──────────────┐
                          │   main.py    │  ← FastAPI, endpoints
                          │  (FastAPI)   │     /query /compare /evals
                          └──┬───────┬───┘     /ingest /health /app
                             │       │
                ┌────────────┤       ├────────────────┐
                │            │       │                │
                ▼            ▼       ▼                ▼
         ┌────────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐
         │ pipeline.py │ │ingest.py│ │evaluator │ │ models.py    │
         │ (orchestr.) │ │ (writes │ │.py       │ │ (Pydantic)   │
         │            │ │ corpus) │ │ (metrics)│ │              │
         └──┬─────┬───┘ └────┬────┘ └────┬─────┘ └──────────────┘
            │     │          │            │
            ▼     └──────────┼─────────┐  │
      ┌──────────┐           │         │  │
      │stages/   │           ▼         │  │
      │(4 stages)│      ┌──────────┐  │  │
      │          │      │indexer.py│  │  │
      │ permission│      │ (rebuild)│  │  │
      │ freshness │      └────┬─────┘  │  │
      │ budget    │           │        │  │
      │ trace     │           ▼        ▼  ▼
      └─────┬─────┘     ┌─────────────────────┐
            │           │    retriever.py      │
            ▼           │ (FAISS + BM25 + RRF) │
      ┌──────────┐      └──────────┬──────────┘
      │protocols │                 │
      │.py (DI)  │                 ▼
      └──────────┘           ┌──────────────┐
                             │  artifacts/  │
                             │ .index .json │
                             └──────────────┘
```

### Module-by-module table

| Module | Role | Key I/O |
|---|---|---|
| `src/main.py` | FastAPI boundary. `/query`, `/compare`, `/evals`, `/ingest`, `/health`. Static mount at `/app` (EOF, line 260). | Loads `roles.json` + `metadata.json` at import. `/evals` caches module-global `_evals_cache`. |
| `src/pipeline.py` | Orchestrator. Wraps each stage in `StageOk/StageErr`, aborts on first error. Builds `UserContext`, resolves policy, measures TTFT. | No I/O. |
| `src/models.py` | Pydantic contract models. `frozen=True, extra="forbid"` on domain types; API types use `extra="forbid"` on request/response but `DocumentChunk` declares none (MI-4). | — |
| `src/policies.py` | `POLICY_PRESETS` dict + `resolve_policy(name, top_k)`. Also `load_roles()` and the dead `filter_by_role()`. | Reads roles.json. |
| `src/retriever.py` | Hybrid retrieval. `retrieve()` (default), `semantic_retrieve()` (comparison). Lazy singletons `_model`, `_bm25`; `invalidate_caches()` resets `_bm25`. | Reads FAISS + `index_documents.json` + `bm25_corpus.json` on every `retrieve()` call. FAISS is not cached in-process. |
| `src/indexer.py` | Full rebuild: loads docs, embeds with MiniLM-L6-v2, writes `querytrace.index` + `index_documents.json` + `bm25_corpus.json`. `tokenize_for_bm25()` used by both indexer and retriever. | Writes three artifacts to `artifacts/`. |
| `src/ingest.py` | PDF → text → append metadata → reindex. `_INGEST_LOCK` threading.Lock, validation, filename sanitizer, doc_id generator. | Writes `corpus/documents/<file>.txt`, mutates `corpus/metadata.json`, invokes `indexer.build_and_save()`. |
| `src/evaluator.py` | 12-query harness, precision@k + recall + permission_violation_rate. Uses `run_pipeline()` so metrics reflect assembled context. | Reads `evals/test_queries.json`. |
| `src/stages/*.py` | Four pure-compute stages. No I/O, no globals. Each returns a named dataclass. | — |
| `src/protocols.py` | `RetrieverProtocol`, `RoleStoreProtocol`, `MetadataStoreProtocol` for dependency injection. | — |
| `src/freshness.py` | Pure helpers. `compute_freshness()` used by the freshness stage. `apply_freshness()` is dead. | — |
| `src/context_assembler.py` | Dead code — pre-refactor packer. Only referenced by `tests/test_context_assembler.py`. | — |

## 4. State, caching, and runtime behavior

### Ingest concurrency diagram (MA-2)

```
Thread A (upload PDF 1)         Thread B (upload PDF 2)      Thread C (query)
    │                                 │                            │
    │  extract_text                   │  extract_text              │
    │  (NO lock, ~5s)                 │  (NO lock, ~5s)            │
    │                                 │                            │
    ├──▶ acquire _INGEST_LOCK ▓▓▓▓   │                            │
    │   (B waits)                     │                            │
    │                                 │                            │
    │   write metadata.json           │                            ├─▶ retrieve()
    │   build_and_save() 5-10s        │                            │   │
    │     ├─ FAISS.write (not atomic) │                            │   ├─ FAISS.read
    │     │                           │                            │   │   ⚠ may read
    │     │                           │                            │   │   half-written
    │     │                           │                            │   │   file → 500
    │     ├─ index_documents.json     │                            │   │
    │     └─ bm25_corpus.json         │                            │   ├─ BM25 singleton
    │                                 │                            │   │   ⚠ still old
    │   release lock ───────────────▶│                            │   │
    │                                 ├──▶ acquire lock ▓▓▓▓▓     │   │
    │                                 │                            │   │
    │   ◀── (here main.py calls       │                            │   │
    │       invalidate_caches())       │                            │   │
    │                                 │                            │   │
    │   RACE WINDOW: main.py released the lock, but hasn't yet
    │   called invalidate_caches() → C gets new FAISS +
    │   old BM25 and returns incoherent ranking.
    │
    ▼
```

### Key state points

- **Process-local singletons**: `_model` (SBERT), `_bm25` (BM25Okapi). `_model` is never invalidated — it's corpus-independent. `_bm25` is only invalidated via `invalidate_caches()` post-ingest.
- **Per-request disk reads**: `retrieve()` calls `load_persisted_index()` every time — reads FAISS and the payload JSON on every query. The BM25 corpus is only read on cold-cache.
- **Module-global mutable state in main.py**: `_metadata` dict + optional `_evals_cache`. Ingest mutates both. Not thread-safe across uvicorn workers.
- **Lock scope**: `_INGEST_LOCK` serializes metadata+reindex within one process. A multi-worker uvicorn breaks this (MA-2). `invalidate_caches()` runs *outside* the lock from `main.py:234`; between lock release and invalidation, a concurrent `/query` can race against new FAISS but old `_bm25`.
- **Evals cache**: module-level `Optional[dict]`. Populated on first `/evals` call. Cleared by ingest. If `run_evals` fails, the cache stays None and the next call retries in full.
- **Static frontend**: mounted at `/app` via `StaticFiles(html=True)`. Any future route starting with `/app/...` will be shadowed.
- **CORS**: `allow_origins=["*"]`, all methods, all headers. Justified in CLAUDE.md for `file://` dev; production tradeoff (MA-3).
- **Ingest gate**: env `ALLOW_INGEST` read per-request. No other auth on `/ingest` even when enabled (CR-2).

## 5. API contracts summary

### Endpoint schemas

```
┌───────────────────────────────────────────────────────────────────┐
│  GET /health                                                      │
│  ─────────────                                                    │
│  ← { "status": "ok", "ingest_enabled": bool }                     │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  POST /query                                                      │
│  ─────────────                                                    │
│  → { "query": str, "role": "analyst|vp|partner",                  │
│      "top_k": int=5, "policy_name": str="default" }               │
│                                                                   │
│  ← { "query": str,                                                │
│      "context": [ DocumentChunk... ],                             │
│      "total_tokens": int,                                         │
│      "decision_trace": DecisionTrace | null }                     │
│                                                                   │
│  DocumentChunk:                                                   │
│    { doc_id, content, score, freshness_score?, tags,              │
│      title?, doc_type?, date?, superseded_by? }                   │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  POST /compare                                                    │
│  ─────────────                                                    │
│  → { "query", "role", "top_k",                                    │
│      "policies": ["naive_top_k","permission_aware","full_policy"]}│
│                                                                   │
│  ← { "query", "role",                                             │
│      "results": { <policy_name>: QueryResponse, ... } }           │
│                                                                   │
│  400 if policies=[] or unknown policy.                            │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  GET /evals                                                       │
│  ──────────                                                       │
│  ← { "per_query": [...], "aggregate": {...} }                     │
│                                                                   │
│  Cached after the first call.                                     │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  POST /ingest  (multipart/form-data)                              │
│  ─────────────                                                    │
│  → file=PDF, title, date=YYYY-MM-DD, min_role, doc_type,          │
│    sensitivity, tags="a,b,c"                                      │
│                                                                   │
│  ← IngestResponse {                                               │
│      status, doc_id, title, file_name, type, date, min_role,      │
│      sensitivity, tags, total_documents }                         │
│                                                                   │
│  Error codes:                                                     │
│   403 → ingest disabled (ALLOW_INGEST=false)                      │
│   415 → not a PDF                                                 │
│   400 → validation (empty title, bad date, invalid enum)          │
│   413 → >10 MB                                                    │
│   422 → unreadable PDF or <50 chars of extractable text           │
│   500 → corpus layout error                                       │
└───────────────────────────────────────────────────────────────────┘
```

### DecisionTrace structure

```
DecisionTrace
├── user_context: UserContext
│     ├── role: str
│     └── access_rank: int
├── policy_config: PolicyConfig
│     ├── name, token_budget, top_k, half_life_days
│     └── skip_permission_filter, skip_freshness, skip_budget
├── included: List[IncludedDocument]
├── blocked_by_permission: List[BlockedDocument]
├── demoted_as_stale: List[StaleDocument]
├── dropped_by_budget: List[DroppedByBudget]
├── total_tokens: int
├── ttft_proxy_ms: float
└── metrics: TraceMetrics
      ├── retrieved_count
      ├── blocked_count, stale_count, dropped_count, included_count
      ├── total_tokens, budget_utilization
      └── avg_score, avg_freshness_score
```

### Invariants

- `retrieved_count == blocked_count + included_count + dropped_count` — enforced in `trace_builder`.
- `result.trace.included == result.context` — verified by test.

## 6. Backend findings (hostile reviewer mode)

### Severity distribution

```
  CRITICAL  ██                           2
  MAJOR     ███████                      7
  MINOR     █████████                    9
  NIT       █████                        5
            ─────────────────────────
            0    5    10   15
```

### Suggested closure order

```
   ┌────────────┐    ┌────────────┐    ┌────────────┐
   │   CR-1     │──▶ │   CR-2     │──▶ │   MA-2     │
   │ tree drift │    │ auth ingest│    │ proc lock  │
   └────────────┘    └────────────┘    └────────────┘
                                              │
   ┌────────────┐    ┌────────────┐    ┌──────▼─────┐
   │   MA-7     │◀── │   MA-3     │◀── │   MA-1     │
   │ trace 400  │    │ CORS *     │    │ artifacts  │
   └────────────┘    └────────────┘    └────────────┘
          │
          ▼
   (MINOR + NIT can wait)
```

---

### CRITICAL

**CR-1 — [RESOLVED 2026-04-22] Working-tree drift from a real ingest was breaking a test**
- *Original symptom:* `corpus/metadata.json` + `artifacts/*` modified; `corpus/documents/agenda.txt` untracked.
- *Original symptom:* `tests/test_retriever.py:67-69` hardcoded `assert len(results) == 12  # corpus has 12 docs`, but metadata + FAISS had 13 entries (IDs `doc_001…doc_013`).
- Why it mattered: (a) the test was brittle — any real ingest broke it; (b) "CI is green" claims were only true against a specific artifact state; (c) the ingest demo mutates committed files without any "demo sandbox" isolation.
- *Fix applied (UI-A):* `agenda.txt` removed, metadata trimmed to 12 docs, artifacts rebuilt. The test had already been previously refactored to read `corpus_size` from `metadata.json`, so the dynamic fix is already in place. The ephemeral-vs-tracked tension around `corpus/` remains unresolved at the design level.

**CR-2 — No auth on `/ingest` when enabled**
- `src/main.py:177-253`. The only gate is the `ALLOW_INGEST` env var.
- On any Render deploy with `ALLOW_INGEST != "false"`, any caller on the public internet can write arbitrary documents to the corpus, trigger a ~5–10s reindex, and change what future `/query` calls return (including responses to other users). No API key, no rate limit, no origin check, and with CORS `*` so browser-based write floods are possible.
- Why it matters: even if the deploy is demo-only, "demo" + "public URL" + "mutation endpoint" is a classic stepping stone for prompt-injection / corpus poisoning in the downstream LLM context. Ingest is also CPU/IO-heavy: trivial denial-of-service vector (upload N 10 MB PDFs in series).

### Visual summary of stages affected by each MAJOR finding

```
   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ retrieve │──▶│ permiss. │──▶│ freshness│──▶│ budget   │──▶│ trace    │
   └────┬─────┘   └──────────┘   └────┬─────┘   └──────────┘   └────┬─────┘
        │                             │                              │
        ├─ MA-1 (artifacts drift)     ├─ MA-6 (superseded_by quirk)  ├─ MA-7 (ValueError→400)
        ├─ MA-4 (top_k×3 in naive)    │
        └─ MA-5 (semantic w/o doc_type)
```

### MAJOR

**MA-1 — Silent divergence between FAISS index, payload JSON, and BM25 corpus**
- `src/retriever.py:192-202` loads three artifacts (`querytrace.index`, `index_documents.json`, `bm25_corpus.json`) with no cross-consistency check. All three are built in a single `indexer.build_and_save()` pass, but nothing prevents partial writes, hand-edits, or mismatched versions.
- `_bm25_ranks` at `src/retriever.py:107-110` correlates BM25 argsort row indices with `payloads[idx]["id"]`. If `bm25_corpus.json` was built with a different order than `index_documents.json`, BM25 ranks are assigned to the wrong doc IDs with no visible error.
- Why it matters: "silently incorrect answer" bug class. Very hard to detect because tests can pass (the ranks are still "some ranking") while prod returns garbage.
- Fix: write a manifest (metadata fingerprint + row count) alongside the artifacts; validate on load. Or consolidate all three files into a single `.npz`/pickle.

**MA-2 — Ingest lock is in-process; reindex is synchronous and non-atomic**
- `src/ingest.py:45, 177-207`. `_INGEST_LOCK = threading.Lock()` serializes only within one Python process. A multi-worker uvicorn deploy (common in production FastAPI) has one lock per worker → concurrent writes to `metadata.json` race.
- `indexer.build_and_save()` writes three files sequentially (`src/indexer.py:152-166`) without temp-file + rename atomicity. A `/query` calling `load_persisted_index()` mid-write can see a half-written `querytrace.index` → `faiss.read_index` fails → 500.
- `main.py:234` calls `invalidate_caches()` *after* releasing the ingest lock. During the few microseconds between lock release and cache reset, `/query` can hit new FAISS + old BM25 singleton and produce a ranking from misaligned payloads.
- Fix: use a file lock, write to `.tmp` and `os.replace()`, and invalidate caches inside the lock.

**MA-3 — `CORSMiddleware(allow_origins=["*"])` in production**
- `src/main.py:33-38`. The rationale (dev convenience for `file://`) doesn't apply when the frontend is mounted same-origin at `/app/`.
- With `*` + `allow_methods=["*"]`, every endpoint — including `/ingest` when enabled — is callable from any origin by any browser. Combined with CR-2, a cross-site script kiddie can submit an ingest form pointing at your host from `evil.example.com`.
- Fix: when `ALLOW_INGEST=false`, still restrict to known origins or the deploy's own host. Document the dev/prod separation instead of conflating them.

**MA-4 — `naive_top_k` returns 3× the `top_k` the user requested**
- `src/pipeline.py:161`: `retrieve_k = policy.top_k * 3` regardless of policy. For `naive_top_k` (skips permission, skips freshness, skips budget), there's no attrition to compensate for — the multiplier was introduced for the permission-aware case.
- A caller requesting `top_k=5, policy_name="naive_top_k"` gets **15** docs in context. Tests pass because `test_naive_top_k_dangerous_baseline` only asserts `included_count == retrieved_count`, not that included_count equals the requested top_k.
- Why it matters: the "No Filters" column in Compare mode looks artificially inflated vs. "Full Pipeline" — the "naive is dangerous" narrative comes partly from the multiplier, not from the missing filters. Evals are unaffected (the evaluator always uses the `default` policy), but eyeball comparisons mislead viewers.
- Fix: multiply only when `not policy.skip_permission_filter`, or document that `top_k` is a retrieval-stage knob, not a final-context knob.

**MA-5 — `semantic_retrieve()` omits `doc_type` from its result dicts**
- `src/retriever.py:205-241`. The production hybrid `_build_results` includes `"doc_type": p.get("type")` (line 161), but `semantic_retrieve` does not. Anyone switching retrievers for ablation (which `semantic_retrieve` documents supporting, line 207) sees `doc_type=None` flowing through the entire pipeline to the frontend.
- `ScoredDocument.model_config = ConfigDict(frozen=True, extra="ignore")` hides this — no validation error, just nulls.
- Fix: share the result dict builder between `retrieve` and `semantic_retrieve`.

**MA-6 — The freshness stage produces inconsistent state when metadata lookup fails**
- `src/stages/freshness_scorer.py:56-60`. When `doc_meta is None`, `freshness_score=0.0`, `is_stale=False`, but `superseded_by = doc.superseded_by` is forwarded from the retriever. A `FreshnessScoredDocument` with `superseded_by="doc_XXX"` and `is_stale=False` flows downstream — contradictory.
- At the same time no `StaleDocument` row is added for that doc, so the trace undercounts `stale_count`. The UI "⚠ Superseded by …" badge (driven by `superseded_by`) still renders on the card, but the trace narrative would say "0 stale."
- Why it matters: the divergence between retriever (authoritative for `superseded_by` at ingest time) and metadata (authoritative for everything else) can happen every time the two fall out of sync (see MA-1).
- Fix: treat missing metadata as an error and block the doc, or trust metadata only (clear `superseded_by` as well).

**MA-7 — `build_trace`'s invariant check raises `ValueError`, which main.py maps to HTTP 400**
- `src/stages/trace_builder.py:55-60` raises `ValueError("Document accounting mismatch: ...")` when the invariant is violated.
- `run_pipeline` does NOT wrap `build_trace` in a stage wrapper (`src/pipeline.py:178-189` — it's called directly, without `_unwrap`). So a mismatch bubbles up as a `ValueError`.
- `src/main.py:76-77` catches `ValueError` as HTTP 400 "Bad Request" and sends the invariant message to the client. A real server invariant violation should be 500, and the internal message should not leak.
- Fix: wrap `build_trace` like the other stages, or catch trace `ValueError` separately and raise 500.

### MINOR

**MI-1 — Dead code paths with accidental-use risk**
- `src/policies.py:65-79` `filter_by_role()` — untyped, operates on "chunks" dicts, duplicates what `permission_filter.py` does on `ScoredDocument`. Public surface (no `_` prefix).
- `src/freshness.py:44-70` `apply_freshness()` — same story, writes mutable state to dicts.
- `src/context_assembler.py` — entire file is dead (only test_context_assembler.py imports it).
- Fix: delete or mark as deprecated.

**MI-2 — Non-uniform tie-breaking between FAISS and BM25 rankings**
- `src/retriever.py:107` uses `np.argsort(-scores, kind="stable")`, FAISS returns in descending score order. For corpora with ties (unlikely in this small corpus), the fusion may favor one retriever's tie-breaking rule. OK for prod, worth noting.

**MI-3 — `_normalize_scores` collapses all-equal scores to 1.0**
- `src/retriever.py:140-141`. A caller comparing top-1 vs top-N can't distinguish "one doc clearly better" from "no signal at all." Unlikely in practice but worth a comment.

**MI-4 — `DocumentChunk` has no `model_config`, implicitly allowing extras**
- `src/models.py:220-231`. All other API models use `extra="forbid"`. Asymmetric strictness: extra fields in the response never fail validation, so typos go undetected in tests.
- Fix: add `model_config = ConfigDict(extra="forbid")`.

**MI-5 — `score_freshness` rebuilds `meta_by_id` and `reference_date` on every call**
- `src/stages/freshness_scorer.py:46-48`. For the small demo corpus this is fine (µs), but the pipeline recomputes this per-request even though `_metadata` was loaded once at startup and only mutates on ingest. A lazy cache keyed on metadata revision would be slightly cleaner — not a performance issue today.

**MI-6 — `/evals` never retries a failed load**
- `src/main.py:167-174`. If `run_evals` throws (corrupt metadata, missing queries), the exception propagates, `_evals_cache` stays None, and the next call re-throws. The cache is write-through-on-success-only. Not a bug, but it means a transient failure during evals warmup keeps the endpoint broken until the exception stops.

**MI-7 — `ingest_document` extracts text before acquiring the lock**
- `src/ingest.py:175` calls `extract_text_from_pdf()` outside `_INGEST_LOCK` (line 177). OK for perf (pdfplumber is slow), but it means two concurrent uploads each spend 5–10s extracting, then serialize on the lock for reindex. Worst case: two workers racing to compute `generate_next_doc_id()` after extraction — the first wins, the second re-reads metadata under lock and gets `doc_(N+1)`. OK today, but worth noting.

**MI-8 — `compute_freshness` clamps negative ages to 0**
- `src/freshness.py:40` `age_days = max((ref - doc_date).days, 0)`. A doc dated after the reference gets score=1.0 (max freshness). The pipeline always uses `max(all_dates)` as reference so it's safe — until someone passes a static reference and ingests a future-dated doc.

**MI-9 — FastAPI `version="0.2.0"`**
- `src/main.py:31`. Hasn't been bumped through MUST-A to NICE-B. Purely cosmetic for OpenAPI / `/docs`.

### NIT

**NI-1 — `semantic_retrieve()` result dict key order doesn't match `_build_results`**
- `src/retriever.py:226-240` omits `doc_type`, has different key order than `_build_results`. Cosmetic but a diff hotspot.

**NI-2 — `_BM25_STOPWORDS` is defined inline as a frozenset built from `.split()`**
- `src/indexer.py:107-113`. Easy to extend, but hardcoded and not duplicated anywhere — if a future query flow wants to share tokenization, it'll have to import from indexer (which pulls in FAISS/SBERT). Separating the tokenizer into its own module would decouple retrieval from indexing.

**NI-3 — Naming inconsistency around "type" vs "doc_type"**
- Metadata uses `"type"` (ingest.py:192, indexer output). The retriever exposes both `type` AND `doc_type` (line 160-161) by calling `.get("type")`. Downstream models use `doc_type`. Two names for the same field is brittle.

**NI-4 — `PipelineError.__init__` pre-formats the stage but main.py re-formats it**
- `src/pipeline.py:57` and `src/main.py:81` both embed the stage name in the 500 detail. Harmless; minor duplication.

**NI-5 — `_ingest_enabled()` env parsing accepts "true"/"True"/"1"/etc. but only documents "false"/"0"**
- `src/main.py:56`. `"not in {"false", "0"}"` means "TRUE", "yes", "", "anything" enables ingest. The permissive default is intentional per CLAUDE.md but the asymmetric semantics (off-only-on-exact-match) is surprising for ops.

---

## 7. Open questions / assumptions

1. **Is committed `corpus/` intended to be mutable at runtime?** CLAUDE.md acknowledges the ephemeral-fs caveat but doesn't prescribe what happens with source-tree mutations on a dev machine (see CR-1). If `corpus/` is canonical, `/ingest` shouldn't touch it; if it's a working sandbox, it shouldn't be committed.
2. **Are multi-worker uvicorn deploys supported?** The Procfile (`uvicorn ... --host 0.0.0.0 --port $PORT`) doesn't set `--workers`, so Render's default (1 worker) applies. If that ever changes, MA-2 activates.
3. **What is the contract between `ScoredDocument` (extra="ignore") and the retriever?** The `extra="ignore"` is convenient for adapter flexibility but means regressions in the retriever's fields (missing `doc_type`) are undetectable without explicit tests.
4. **Is `_metadata` read mid-mutation at `main.py:237-238`?** `_metadata["documents"] = fresh["documents"]` is an atomic pointer swap under CPython (GIL), so readers see either old or new — but the `_metadata` dict identity is preserved, meaning any code that took a reference to `_metadata["documents"]` before ingest now has a stale list. No such code exists today; worth noting.
5. **Is the lack of `extra="forbid"` on `DocumentChunk` deliberate for frontend compatibility?** The docstring says "Preserved for frontend compatibility" — perhaps old clients were adding extras. If so, it deserves a comment.

## 8. Final verdict

**The pipeline core is solid.** The stage-based structure, typed dataclass results, Protocol-based DI, the trace-builder invariant check, and the 172-test harness give the retrieval path real defensive depth. RBAC is enforced at the right point, freshness is corpus-relative, budget is authoritative. Happy-path correctness is tight.

**Weaknesses cluster around the ingest/reindex path and artifact hygiene.** Three intertwined issues: (CR-1) source-tree drift from the ingest demo that broke a test and was never reverted; (CR-2) unauthenticated mutation on a publicly deployed endpoint; (MA-2) in-process lock + non-atomic reindex that doesn't survive multi-worker deploys or mid-write reads. These aren't theoretical — they materialize the moment the app is deployed with `ALLOW_INGEST=true` or with more than one worker.

**Secondary fragility: silent signal degradation.** `extra="ignore"` on ScoredDocument, the uniform 3× top_k multiplier across policies, `semantic_retrieve` dropping `doc_type`, and the freshness/`superseded_by` mismatch in MA-6 all produce wrong-but-plausible output instead of errors. These are the hardest bugs to catch in a read-only pipeline.

Tests are **exhaustive for the happy path and the policy-preset matrix**, **thin on artifact drift and concurrency scenarios**, and **contain at least one stale assumption** (CR-1) that was actively breaking. The evaluator is well-integrated and reliable as long as artifacts and metadata stay in sync.

Net: the query path is production-grade for the demo's scope; the ingest path is a demo feature that shipped with production endpoints. Closing CR-1, CR-2, MA-1, MA-2, MA-3, and MA-7 would bring the entire backend up to the same bar as the retrieval core.

---

## Appendix: Timeline of a typical request

```
 t=0 ms  ┃ client sends POST /query
         ┃
 t=~1    ┃ FastAPI parses JSON, validates QueryRequest
         ┃
 t=~1    ┃ main.py validates role (400 if unknown)
         ┃
 t=~1    ┃ run_pipeline() → resolve_policy
         ┃
 t=~1    ┃ ┌─────────────────────────────────┐
         ┃ │ _retrieve_stage                 │
 t=~50   ┃ │   SBERT.encode(query) ~20ms     │
         ┃ │   faiss.read_index() ~5ms       │
         ┃ │   faiss.search() ~2ms           │
         ┃ │   BM25.get_scores() ~1ms        │
         ┃ │   RRF fuse + normalize ~1ms     │
         ┃ └─────────────────────────────────┘
         ┃
 t=~51   ┃ filter_permissions (µs)
         ┃
 t=~52   ┃ score_freshness (µs — rebuilds meta_by_id)
         ┃
 t=~55   ┃ pack_budget (~3ms — tiktoken encoding)
         ┃
 t=~55   ┃ build_trace (µs)
         ┃
 t=~56   ┃ main.py maps to QueryResponse
         ┃
 t=~57   ┃ FastAPI serializes to JSON, responds 200

         (ttft_proxy_ms ~= 50-60ms is what you'll see in trace.ttft_proxy_ms
          after SBERT model warmup)
```
