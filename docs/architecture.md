# QueryTrace — Architecture

QueryTrace is a retrieval pipeline with policy enforcement and full decision auditing: a natural-language query plus a user role goes in, a token-budgeted document context comes out, and every document that was retrieved is accounted for in a structured `decision_trace` — included, blocked by permissions, demoted as stale, or dropped by the token budget.

The stack is FastAPI + FAISS + BM25 + all-MiniLM-L6-v2 embeddings on ONNX Runtime (fastembed), with a static HTML/JS frontend served from the same process. All persistent state lives on local disk (`corpora/<slug>/`, `artifacts/<slug>/` — one bundle per workspace since Fase 2); there is no database, no network calls during a query, and no background workers.

## System overview

```
POST /query {query, role, top_k, policy_name}
        │
        ▼
src/main.py          thin HTTP boundary: validate role → run_pipeline() → QueryResponse
        │
        ▼
src/pipeline.py      orchestrator (no I/O, dependencies injected via Protocol)
        │
   1. retrieve            hybrid FAISS + BM25, RRF fusion        → List[ScoredDocument]
   2. filter_permissions  RBAC by role rank                      → permitted + blocked
   3. score_freshness     corpus-relative decay, 0.5× stale      → scored + demoted_as_stale
   4. pack_budget         greedy packing under token budget      → packed + dropped
   5. build_trace         audit trace + accounting invariant     → DecisionTrace
        │
        ▼
PipelineResult → QueryResponse {context[], total_tokens, decision_trace}
```

Roles and corpus metadata are loaded once at startup in `src/main.py`. The embedding model is a lazy-loaded per-process singleton in `src/embedder.py` (the only module that touches the inference runtime); BM25 objects are per-workspace singletons in `src/retriever.py`.

## Pipeline orchestration (`src/pipeline.py`)

Each stage in `src/stages/` is a standalone pure-compute function with typed inputs and a named result dataclass — no I/O, no side effects:

| Module | Function | Result type |
|---|---|---|
| `src/stages/permission_filter.py` | `filter_permissions(docs, user_ctx, roles)` | `PermissionResult` |
| `src/stages/freshness_scorer.py` | `score_freshness(docs, metadata, half_life_days)` | `FreshnessResult` |
| `src/stages/budget_packer.py` | `pack_budget(docs, token_budget, enforce_budget)` | `BudgetResult` |
| `src/stages/trace_builder.py` | `build_trace(...)` | `DecisionTrace` |

`run_pipeline()` wraps each stage call in a `StageOk` / `StageErr` result. `_unwrap()` converts any `StageErr` into a `PipelineError(stage, error)`, aborting on the first failure; `src/main.py` maps `PipelineError` to HTTP 500 with the failing stage named in the detail. Retrieval results are validated into Pydantic `ScoredDocument` models at the stage boundary, so malformed retriever output fails loudly inside the `retrieve` stage rather than deep in the pipeline.

A Pydantic type chain runs end-to-end (`src/models.py`): `ScoredDocument` → `FreshnessScoredDocument` → `BlockedDocument` / `StaleDocument` / `IncludedDocument` / `DroppedByBudget` → `DecisionTrace` → `QueryResponse`. Domain models are `frozen=True, extra="forbid"`; `ScoredDocument` uses `extra="ignore"` to absorb extra keys from the retriever. `QueryRequest` bounds its inputs: `query` is 1–2000 chars, `top_k` is 1–50.

## Chunking (`src/chunker.py`, Fase 5 Etapa B)

The retrieval unit is the **chunk**, not the document. `chunk_text()` splits on blank-line paragraphs and greedily merges them to ~350 tokens (tiktoken `cl100k_base` — the same encoding the budget packer counts with), with ~15% overlap between consecutive chunks; oversized paragraphs fall back to sentence splits, oversized sentences to hard token windows. Chunk ids are stable and human-readable (`doc_003#c01`); each chunk records char offsets into the original document. Every chunk row inherits the parent document's metadata (`min_role`, `date`, `superseded_by`, `tags`), so permission and freshness stages need no changes — they key on `doc_id`, which always names the parent document.

This resolves the two halves of the old truncation problem: the embedder used to see only the start of each document (the rest was semantically invisible — BM25 masked the loss because it reads full text), and the packed "context" was a fixed 500-char teaser. Now every part of a document has its own embedding row, and the packer packs full chunk text.

## Hybrid retrieval (`src/retriever.py`)

Two rankers score **every chunk row** on every query:

- **Semantic** — FAISS `IndexFlatIP` over L2-normalized `all-MiniLM-L6-v2` embeddings (cosine similarity via inner product), computed by `src/embedder.py` (ONNX Runtime via fastembed — the single seam to the inference runtime).
- **Lexical** — `BM25Okapi` over stopword-filtered chunk tokens (shared tokenizer in `src/indexer.py`).

The two 1-based rank lists are fused with Reciprocal Rank Fusion:

```
RRF_score(c) = 1/(60 + rank_semantic(c)) + 1/(60 + rank_bm25(c))
```

`k = 60` is the standard constant from Cormack, Clarke & Buettcher (SIGIR 2009). Chunks missing from one ranking receive worst-case rank `n_total + 1`. Fused scores are min-max normalized to [0, 1], sorted, and clamped to `top_k` rows (which is itself clamped to corpus row count).

The pipeline **over-retrieves by 6×** (`retrieve_k = policy.top_k * 6`) to compensate for downstream permission attrition *and* chunk inflation (~2 rows per document; `top_k` caps unique documents, see below) — an analyst-level query can lose most of its candidate chunks to RBAC, and the budget packer still bounds the final context regardless of how many candidates enter. `semantic_retrieve()` (FAISS-only) is kept alongside `retrieve()` for ablation comparison; both satisfy `RetrieverProtocol` (`src/protocols.py`), which is how the pipeline stays retriever-agnostic.

## Policy presets (`src/policies.py`)

| Name | Permission filter | Freshness | Budget |
|---|---|---|---|
| `naive_top_k` | off | off | off (dangerous baseline) |
| `permission_aware` | on | off | on |
| `full_policy` | on | on | on |
| `default` | on | on | on (alias for `full_policy`) |

`resolve_policy(name, top_k)` looks up the preset and applies the request's `top_k` override via `model_copy`; an unknown name raises `ValueError`, mapped to HTTP 400. `PolicyConfig` defaults: `token_budget=2048`, `top_k=5`, `half_life_days=365`. Skipped stages are short-circuited in `src/pipeline.py` (e.g. skipped freshness yields `freshness_score=0.0` for all docs), so every policy still produces a complete, invariant-checked trace.

## DecisionTrace and the accounting invariant

Every `/query` response carries a `decision_trace` (`src/models.py`):

- `user_context` — role and access_rank
- `policy_config` — the resolved preset and its flags
- `included` — documents packed into context
- `blocked_by_permission` — documents the role cannot access (with `required_role` / `user_role`)
- `demoted_as_stale` — superseded documents (still included, with a 0.5× freshness penalty)
- `dropped_by_budget` — documents that scored well but exceeded the token budget
- `metrics` — counts plus `avg_score`, `avg_freshness_score`, `budget_utilization`
- `total_tokens` and `ttft_proxy_ms` (pipeline wall-clock in ms)

`src/stages/trace_builder.py` enforces the accounting invariant — every retrieved CHUNK must land in exactly one terminal bucket:

```
blocked + included + dropped == retrieved      (all counts are chunks)
```

(Stale chunks are demoted, not removed, so they count inside `included`.) A violation raises `TraceAccountingError`, a `RuntimeError` subclass — deliberately **not** a `ValueError`, because the HTTP boundary maps `ValueError` to 400 (bad request) and an internal accounting bug must surface as a 500.

Because users reason about documents rather than chunks, `TraceMetrics` carries both views: the chunk-level `*_count` fields (which the invariant is checked against) and derived `*_doc_count` fields (unique parent documents per bucket). The UI, the session audit, and the evaluator all present doc-level numbers; trace entry lists remain per-chunk (each entry carries `chunk_id`) so the audit stays exact.

**`top_k` semantics (H4, resolved):** `top_k` is the maximum number of **unique parent documents** in the final context; the token budget is the second, independent limit. The budget packer enforces both — a chunk of an already-packed document never opens a new document slot, and a chunk from a new document is dropped once `top_k` distinct documents are packed. The naive baseline (`skip_budget`) is uncapped by design.

## Corpus and access control

- `corpora/<slug>/metadata.json` — per-doc `min_role`, `date`, `superseded_by` (doc id or null), `sensitivity`, `tags` (pe-deal: 16 docs; saas-internal: 14).
- `corpora/<slug>/roles.json` — three roles with `access_rank` (pe-deal: analyst (1) < vp (2) < partner (3); saas-internal: employee (1) < manager (2) < exec (3)).
- Access rule: user's `access_rank` >= the rank of the document's `min_role`. A document whose `min_role` is unknown to the role store is blocked (reason `unknown_min_role`) rather than aborting the pipeline.
- Three superseded pairs exercise stale demotion: `doc_002 → doc_003` (research notes), `doc_007 → doc_008` (financial models), `doc_014 → doc_010` (IC draft → final approval memo).

Freshness (`src/freshness.py` + `src/stages/freshness_scorer.py`) is **corpus-relative**: exponential decay with a 365-day half-life measured against the newest document date in the corpus, not the wall clock, so scores are stable regardless of when the eval runs. Superseded documents get a multiplicative 0.5× penalty and a `StaleDocument` trace entry (per chunk, inherited from the parent's metadata). The budget packer (`src/stages/budget_packer.py`) then ranks chunks by `0.5 × relevance + 0.5 × freshness` and greedily packs full chunk text, counting tokens with tiktoken `cl100k_base`, until the token budget or the `top_k` unique-document cap is exhausted.

## Indexing and artifacts (`src/indexer.py`)

`python3 -m src.indexer` chunks each document (`src/chunker.py`), embeds every chunk with `all-MiniLM-L6-v2` (384-dim vectors, ONNX via `src/embedder.py`) and persists three artifacts, all of which must exist before the server starts. **One row per chunk** — `id` is the chunk id, `doc_id` the parent document:

- `artifacts/<slug>/querytrace.index` — FAISS `IndexFlatIP`
- `artifacts/<slug>/index_documents.json` — ordered chunk payloads matching FAISS row order (inherited doc metadata + the chunk's full text as `excerpt`)
- `artifacts/<slug>/bm25_corpus.json` — tokenized chunk corpus for BM25, same row order

All writes are **atomic**: JSON goes through a same-directory `.tmp` file + `os.replace`, and the FAISS index uses the same tmp + replace pattern. Since the retriever re-reads artifacts per request, a reader never observes a half-written file, and a crash mid-write leaves the previous version intact. Write order is BM25 corpus → payloads → FAISS index, so the index — the artifact the retriever reads first — lands last.

## Ingestion (`src/ingest.py`, `POST /ingest`)

The HTTP handler in `src/main.py` is a thin adapter; all logic lives in `src/ingest.py`:

The synchronous half (fails the request itself, `prepare_ingest()`):

1. Cheap request-level gates in the handler — `Content-Length` over the cap → 413 before the file is read; the file is then read in 1 MB chunks with a hard stop at 10 MB (a 2 GB body is never buffered whole); unsupported extension → 415. Supported formats: `.pdf`, `.txt`, `.md`, `.docx`.
2. Validate inputs — size (413 over 10 MB, second belt), title, real calendar date, `min_role` / `doc_type` / `sensitivity` enums (400).
3. `extract_text(file_bytes, filename)` dispatches on the extension after a **magic-bytes check** (`%PDF-` for PDF, ZIP `PK` signature for .docx, no-binary-content for .txt/.md — a lying extension is a 415, not a parser crash): pdfplumber for PDF, UTF-8/latin-1 decode for .txt, frontmatter-stripped text for .md, python-docx for .docx. Unreadable content or under 50 extractable chars → 422.
4. The extracted text is content-hashed (sha256 over whitespace-collapsed, lowercased text). If the hash already exists in the workspace's metadata → **409** naming the existing doc_id (idempotent re-uploads).

On success the request returns **202 + `job_id`** and the heavy half (`finalize_ingest()`) runs on a single-worker `ThreadPoolExecutor` (`src/jobs.py`) that serializes reindexes:

5. Under the module `threading.Lock`: authoritative dedup re-check, next `doc_NNN` id, write the extracted text to `corpora/<slug>/documents/<sanitized_title>.txt` (the original file is never persisted), atomically append to that workspace's `metadata.json` (including `content_hash`), and index **incrementally** via `indexer.add_document(slug, entry, text, on_stage=...)` — only the new document is embedded and appended to the loaded FAISS index; the payload and the BM25 token row are appended and all three artifacts rewritten atomically (index last). O(1) per document instead of O(N): measured with a warm model, at 160 docs a full rebuild takes ~0.22 s vs ~0.010 s for the incremental add (~21×), and the add stays flat as the corpus grows. `add_document` falls back to a defensive `build_and_save()` when artifacts are missing or drifted (row counts disagree); edits/deletions remain full-rebuild territory (`IndexFlatIP` has no cheap remove without an `IndexIDMap` — the noted upgrade path). The `on_stage` callback flips the job through `embedding` → `indexing`. If anything fails after the .txt/metadata landed, **both are rolled back** (no orphans) and the job ends `failed` with a typed `{status_code, detail}` error.
6. On success the job resets the in-process BM25 cache (`retriever.invalidate_caches(slug)`), clears the `/evals` cache entry, and stores the `IngestResponse` payload as its `result`.

`GET /ingest/jobs/{job_id}` (and `GET /ingest/jobs`, newest first) report `queued → extracting → embedding → indexing → done | failed`; both require an admin session bound to the job's workspace. The job store retains the newest 50 jobs; older ids → 404. Why threads and not Celery: single-instance demo — zero infrastructure, serialized reindexes, real progress; jobs die with the process and cannot span instances, and the upgrade path is an external broker behind the same `JobStore` interface.

The handler is a plain `def` (not `async def`) on purpose: FastAPI dispatches sync handlers to its threadpool, so the event loop stays responsive during the up-to-~1s synchronous extraction. The `ALLOW_INGEST` env flag gates the endpoint and the job endpoints (403 when disabled); ingest is on unless the value is exactly `"false"` or `"0"` (case-insensitive), and read-only public deploys set `ALLOW_INGEST=false`. Known demo-scope limits: the lock and job queue are per-process (single-worker deploys only), and writes go to repo paths that vanish on ephemeral hosting filesystems.

**Bring-your-own-corpus CLI** (`src/workspace.py`): `python -m src.workspace create <slug> --from-dir DIR` builds a complete workspace from a directory of documents by running every file through the same `prepare_ingest()`/`finalize_ingest()` pipeline (magic bytes, dedup skip, incremental indexing), with defaults: roles viewer/editor/admin (override via `--roles`), `min_role` = lowest rank, date = file mtime, `doc_type` = "document", title = humanized filename. `python -m src.workspace list` enumerates workspaces.

## Evaluation harness (`src/evaluator.py`)

`run_evals()` executes 12 corpus-grounded test queries per workspace (`corpora/<slug>/evals.json`) through the **production** `run_pipeline()` — metrics reflect the final assembled context, not raw retrieval. Per query and in aggregate it computes:

- **precision@k** — with k clamped to the actual result size, so short contexts (caused by role filtering or the token budget) are not penalized for documents the system could not have returned;
- **recall** — fraction of expected docs found anywhere in the assembled context;
- **permission_violation_rate** — fraction of queries whose context contains any forbidden doc id;
- context-size, token, freshness, and trace-level aggregates (blocked/stale/dropped counts, budget utilization).

CLI: `python3 -m src.evaluator` (flags `--k`, `--top-k`, `--evals`). `--compare` runs `naive_top_k` and `full_policy` side by side, prints a comparison table, and asserts the full pipeline is violation-free (CI smoke check). The token budget is policy-owned, not an eval knob.

Measured results on the 12-query benchmark: precision@5 = 0.3333 — the theoretical ceiling given expected-set sizes, reached by all 12 queries — recall = 1.0, permission violations 0% under `full_policy` vs 50% under `naive_top_k`, and ~71% average budget utilization. The test suite is 391 passed, 0 skipped.

Ask-mode fidelity (opt-in, spends tokens): `--ask` runs the benchmark through the `/ask` code path and measures citation validity / groundedness / expected-cited rates, writing a dated snapshot to `evals/results/`; `--ask-goldens` regenerates the measured role-pair snapshots in `corpora/<slug>/ask_goldens.json`. Both require `ANTHROPIC_API_KEY`; CI runs neither (the Ask surface is tested against a mocked client).

## Ask mode (`src/ask.py`, `POST /ask`)

The one place the assembled context is actually *used*: `/ask` accepts the same body as `/query`, runs the same `run_pipeline()`, and hands the packed documents to a Claude model (`ASK_MODEL`, default Haiku) as `<doc id= title= date= type=>` blocks under a context-only system prompt. Because the prompt is built exclusively from `PipelineResult.context`, a document blocked by RBAC **cannot** reach the model — asserted by tests at both the prompt-builder and API level.

Citations are validated mechanically: every `[doc_id]` in the answer is checked against the ids that were in the prompt (`valid` flag per citation, `grounded_doc_count` aggregate) — no LLM judge. The response carries the full `decision_trace`, so what the model saw and what it never saw are part of the same auditable contract as `/query` (including per-viewer redaction for non-admin sessions).

Public-demo guardrails, all in-process: a TTL answer cache keyed `(workspace, normalized query, role, policy, top_k)` (repeat demos are free and marked `cached: true`), per-IP + global rate limits (429), a defensive prompt-size cap on top of the budget packer, and stack-free 502s for provider failures. The whole mode is feature-flagged by `ANTHROPIC_API_KEY` — unset, `/ask` returns 403 and the UI hides the button.

## API surface (`src/main.py`)

| Endpoint | Purpose |
|---|---|
| `POST /query` | Run one query through a named policy preset; returns context + `decision_trace`. |
| `POST /ask` | Grounded answer over the governed context with validated `[doc_id]` citations (see Ask mode above); 403 when no model key is configured. |
| `POST /compare` | Same query through multiple presets (default: all three); one `QueryResponse` per policy. Reuses `run_pipeline()` — no logic duplication. |
| `GET /evals` | Cached evaluator results (`{per_query, aggregate}`); computed on first call, cache cleared by ingest. |
| `GET /session-audit` | In-memory log of live `/query` calls since process start (ids `q013+`, continuing after the 12 benchmark queries); resets on restart. |
| `POST /ingest` | Multipart document upload (.pdf/.txt/.md/.docx) + metadata; magic-bytes verified, content-hash deduped (409); → 202 + job_id; gated by `ALLOW_INGEST`. |
| `GET /ingest/jobs/{job_id}` | Ingest job progress (queued → extracting → embedding → indexing → done\|failed); admin session, own workspace only. |
| `GET /ingest/jobs` | Ingest jobs for the session's workspace, newest first; admin session. |
| `GET /health` | `{"status": "ok", "ingest_enabled": <bool>, "ask_enabled": <bool>, "default_workspace": <slug>}` — the frontend uses the flags to hide Upload / Ask AI when disabled. |

The static frontend (`frontend/`, no build step) is mounted last at `/app/` via `StaticFiles(html=True)`; `/` redirects there. Served same-origin, the frontend needs no CORS in production; the permissive CORS middleware exists to keep the `file://` dev flow working. `/app` responses carry `Cache-Control: no-store` so long-lived browser tabs pick up new deploys.

Error mapping at the boundary: unknown role or policy → 400, stage failure (`PipelineError`) → 500 with the failing stage named, invariant violation (`TraceAccountingError`) → 500. Request validation (query length, `top_k` bounds, `extra="forbid"` on request models) is handled by Pydantic before any handler code runs.

## Running locally

```bash
pip install -r requirements.txt
python3 -m src.indexer                          # build artifacts (only after corpus changes)
python3 -m uvicorn src.main:app --reload        # API at :8000, frontend at /app/, docs at /docs
python3 -m pytest tests/ -v                     # full suite
python3 -m src.evaluator --compare              # naive vs full policy benchmark
```

## Limitations & trade-offs

Deliberate scope cuts for a demo-sized system — each one is either accepted or scheduled on the roadmap:

- **Demo-grade auth** — `/ingest` requires an admin session and roles are server-derived from a signed (HMAC-SHA256) cookie, but there is no registration, password reset, or SSO; demo credentials are deliberately public. The declared upgrade path is OIDC (Okta/IdP groups mapped to roles). `ALLOW_INGEST=false` remains as an environment kill-switch on top of the session check (defense in depth). Set `QUERYTRACE_SECRET_KEY` in any real deployment — the dev fallback logs a loud warning.
- **In-process job queue (threads, not Celery)** — `POST /ingest` returns 202 immediately and the reindex runs on a single-worker `ThreadPoolExecutor` that serializes uploads. That is the deliberate choice for a single-instance demo: zero infrastructure, real progress states, and the request never blocks. The explicit trade-off: jobs die with the process (no persistence or retries) and the queue cannot span multiple instances — the upgrade path when either matters is an external broker (Celery/RQ/SQS) behind the same `JobStore` interface. Failed jobs roll back their document and metadata entry, so no orphans survive.
- **Single-process state** — the evals cache and session audit log are in-memory and per-process; running multiple workers would give each worker its own view.
- **Chunking granularity** — documents are indexed as ~350-token chunks (resolving the old embed-only-the-start truncation), but chunk boundaries are paragraph-greedy, not semantic; a cross-encoder reranker over fused chunks is the declared next step on the roadmap (Fase 5 Etapa C, unbuilt).
- **Open CORS** — `allow_origins=["*"]` is kept so the `file://` dev flow works; same-origin serving makes it unused in production.
- **Ephemeral disk on free-tier hosts** — if deployed (e.g. Render free tier), uploaded documents and rebuilt artifacts vanish on the next deploy or restart unless a persistent disk is attached; the committed two-workspace corpora (16 + 14 docs) are the durable baseline.
- **Prompt injection via ingested documents (Ask mode)** — a malicious uploaded document could contain "ignore your instructions" text. Mitigation is real but partial: documents enter the prompt inside tagged `<doc>` blocks and the system prompt mandates context-only answers with citations; the mechanical citation validator flags fabricated sources. A dedicated injection-hardening pass is out of demo scope.
- **In-process Ask guardrails** — the Ask answer cache and rate-limit windows are per-process (like the evals cache and audit log); multiple workers would each keep their own.
