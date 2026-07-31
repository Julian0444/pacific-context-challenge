# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (runtime only)
pip install -r requirements.txt
# Dev dependencies (pytest, httpx, ruff) — required to run the test suite
pip install -r requirements-dev.txt

# Run the API server (from repo root)
python3 -m uvicorn src.main:app --reload
# API at http://localhost:8000, docs at http://localhost:8000/docs

# Rebuild the FAISS index after changing corpus documents (all workspaces / one)
python3 -m src.indexer
python3 -m src.indexer --workspace saas-internal

# Create a workspace from a directory of documents (Fase 3; .pdf/.txt/.md/.docx)
python3 -m src.workspace create my-kb --from-dir ~/docs --name "My KB"
python3 -m src.workspace list

# Run all tests (427 passed, 0 skipped)
python3 -m pytest tests/ -v

# Run a single test file or test
python3 -m pytest tests/test_policies.py -v
python3 -m pytest tests/test_main.py::test_query_returns_200 -v

# Lint
ruff check src/ tests/

# Eval harness — full_policy by default; --compare runs naive_top_k vs full_policy;
# --workspace picks the corpus (default pe-deal)
python3 -m src.evaluator
python3 -m src.evaluator --compare
python3 -m src.evaluator --workspace saas-internal --compare

# Ask-mode fidelity (Fase 4) — OPT-IN, spends tokens, needs ANTHROPIC_API_KEY.
# --ask measures citation validity over the 12-query benchmark and writes a
# dated snapshot to evals/results/; --ask-goldens regenerates the measured
# role-pair snapshots in corpora/<slug>/ask_goldens.json. CI runs neither.
python3 -m src.evaluator --ask
python3 -m src.evaluator --ask-goldens
```

Local note: always use `.venv/bin/python` on this machine (the system `python3` has a broken torch stack for this repo).

## Architecture

QueryTrace is a retrieval pipeline: natural-language query + user role (+ workspace) in, token-budgeted document context out.

### Workspaces (`src/workspaces.py`, Fase 2)

Corpora are **workspaces**: self-contained directories under `corpora/<slug>/` with `workspace.json` (manifest: name, description, doc_types, role_hints, scenarios, example_queries, search_placeholder, empty_state_description, blocked_disclosure), `documents/*.txt`, `metadata.json`, `roles.json`, `users.json`, and `evals.json`. Index artifacts live in `artifacts/<slug>/`.

`src/workspaces.py` is the central resolver: `get_workspace(slug|None)` (None → `default_workspace()`, env-overrideable via `QUERYTRACE_DEFAULT_WORKSPACE`, default `pe-deal`) returns a frozen `Workspace` dataclass with all paths + loaded `manifest`/`roles`/`metadata`/`users`, cached per slug under a lock. `list_workspaces()` scans `corpora/*/workspace.json`. **Slugs are user input that reaches filesystem paths**: `validate_slug()` (`^[a-z0-9-]{1,40}$`) runs before any path is built — malformed → `InvalidWorkspaceSlug` (API: 400), well-formed but missing → `WorkspaceNotFound` (API: 404). `invalidate_workspace_cache(slug)` drops the cache after ingest mutates a corpus.

Two shipped workspaces: `pe-deal` (Atlas Capital, 16 docs, analyst/vp/partner, personas julia/victoria/patricia) and `saas-internal` (Nimbus Analytics, 14 docs, employee/manager/exec, personas sofia/marcos/alex — hints demo-employee/demo-manager/demo-admin). Doc ids (`doc_NNN`) are per-workspace namespaces and collide across corpora by design; isolation is asserted on titles/content in tests.

**Bring-your-own-corpus CLI (`src/workspace.py`, Fase 3 Etapa D).** `python -m src.workspace create <slug> --from-dir DIR [--roles roles.json] [--name] [--description]` scans DIR recursively for supported files and creates a complete `corpora/<slug>/` (manifest with `doc_types: ["document"]`, roles — default viewer(1) < editor(2) < admin(3), empty `users.json`, metadata) by running each file through the same `prepare_ingest()`/`finalize_ingest()` as an HTTP upload (magic bytes, dedup-skip with warning, unreadable-skip with warning, incremental indexing). Per-doc defaults: `min_role` = lowest rank, date = mtime, title = humanized filename. If nothing is ingestable the skeleton is removed and the command exits non-zero. `python -m src.workspace list` prints all workspaces. `create_workspace()` is the testable core (`tests/test_workspace_cli.py` sandboxes `CORPORA_DIR`/`ARTIFACTS_ROOT` and fakes `_embed_texts`/`_get_model` — note `src.main` must be imported before patching `CORPORA_DIR` because `_BENCHMARK_COUNT` resolves the default workspace at import time).

### Pipeline (POST /query in `src/main.py`)

`main.py` is a minimal HTTP boundary: resolve workspace → validate role → `run_pipeline()` → map `PipelineResult` to `QueryResponse`.

```
run_pipeline(request, retriever, roles, metadata)   ← src/pipeline.py
  ↓
retrieve(query, top_k)          → List[ScoredDocument]      (CHUNK rows since Fase 5: hybrid FAISS cosine + BM25, fused via RRF; doc_id = parent doc, chunk_id = row)
  ↓
filter_permissions(docs, ...)   → PermissionResult           (permitted + blocked_by_permission; per chunk, min_role inherited from parent)
  ↓
score_freshness(docs, metadata) → FreshnessResult            (scored + demoted_as_stale; 0.5× penalty for superseded; keyed on parent doc_id)
  ↓
pack_budget(docs, budget, max_docs) → BudgetResult           (packed chunks + over_budget; max_docs = top_k caps UNIQUE PARENT DOCS — H4; token budget is the second limit)
  ↓
build_trace(...)                → DecisionTrace              (chunk-level accounting invariant + derived *_doc_count metrics)
  ↓
PipelineResult → QueryResponse  (context list of chunks, total_tokens, decision_trace)
```

The retrieval unit is the **chunk** (Fase 5 Etapa B): `src/chunker.py` produces ~350-token paragraph-aware chunks with ~15% overlap, ids `doc_NNN#cNN`, char offsets, and full parent-metadata inheritance. `top_k` = max unique documents in the final context (naive baseline stays uncapped). The pipeline over-retrieves by 6× (`retrieve_k = top_k * 6`) to cover permission attrition + chunk inflation (~2 chunks/doc). Trace accounting (`blocked + included + dropped == retrieved`) counts chunks; `TraceMetrics` adds `included/blocked/stale/dropped_doc_count` (unique parent docs) and the UI/evaluator/session-audit present doc-level numbers.

Roles and metadata are resolved **per request** from the workspace resolver (no module-level corpus state in `main.py`); the retriever is bound to the workspace via `functools.partial(retrieve, workspace=ws.slug)`, so `pipeline.py` and the stages are workspace-agnostic. The embedding model (ONNX via fastembed) is lazy-loaded as a corpus-independent singleton in `src/embedder.py` — the single seam to the inference runtime; indexer and retriever call `embedder.embed()` and never import the runtime directly.

### Stage-based structure (`src/stages/`)

Each stage is a standalone pure-compute function with typed inputs and a named result dataclass. No I/O, no side effects.

| Module | Function | Result type |
|--------|----------|-------------|
| `permission_filter.py` | `filter_permissions(docs, user_ctx, roles)` | `PermissionResult` |
| `freshness_scorer.py` | `score_freshness(docs, metadata, half_life_days)` | `FreshnessResult` |
| `budget_packer.py` | `pack_budget(docs, token_budget, enforce_budget, max_docs)` | `BudgetResult` |
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

Key types: `ScoredDocument`, `FreshnessScoredDocument`, `BlockedDocument`, `StaleDocument`, `DroppedByBudget`, `IncludedDocument`, `DecisionTrace`, `TraceMetrics`, `PipelineResult`, `QueryRequest`, `QueryResponse`, `CompareRequest`, `CompareResponse`, `IngestResponse`, `Citation`, `AskUsage`, `AskResponse` (Fase 4). Domain models are `frozen=True + extra="forbid"`. `ScoredDocument` uses `extra="ignore"` to absorb extra keys the retriever returns.

`IncludedDocument` and `DocumentChunk` carry additional metadata (all `Optional[str] = None`): `title`, `doc_type`, `date`, `superseded_by`. These flow through the full chain: retriever `_build_results()` → `ScoredDocument.doc_type` → `FreshnessScoredDocument.doc_type` → `IncludedDocument` → `DocumentChunk` → API `context[]`. The frontend receives all four fields on every response item.

Chunk identity (Fase 5 Etapa B) travels the same chain as optional fields: `chunk_id`, `chunk_index`, `chunk_count` on `ScoredDocument`/`FreshnessScoredDocument`/`IncludedDocument`/`DocumentChunk`; `BlockedDocument`/`StaleDocument`/`DroppedByBudget` carry `chunk_id`. `TraceMetrics` adds optional `included/blocked/stale/dropped_doc_count` (unique parent docs). All default to `None`, so pre-chunking payloads stay valid.

`BlockedDocument` also carries `title: Optional[str] = None` and `doc_type: Optional[str] = None`, populated by `permission_filter.py` from `doc.title` / `doc.doc_type`. These power the blocked-documents section in the Single mode frontend.

### Retrieval (`src/retriever.py`)

Hybrid retrieval combining FAISS semantic search and BM25 lexical search via Reciprocal Rank Fusion (RRF). Both rankers score the full corpus; RRF fuses the two 1-based rank dicts: `score(d) = 1/(60 + rank_sem) + 1/(60 + rank_bm25)`. Fused scores are min-max normalized to [0, 1]. `retrieve(query, top_k, workspace=None)` is the default (hybrid); `semantic_retrieve()` is provided for comparison. Both satisfy `RetrieverProtocol` (callers bind the workspace with `partial`).

Per-workspace caches: `_bm25` is a `dict[slug, BM25Okapi]`; the embeddings model stays a global singleton (corpus-independent). `invalidate_caches(workspace=None)` drops one slug's BM25 entry (or all). FAISS is re-read from disk on every `retrieve()` call.

The pipeline over-retrieves by 6× (`retrieve_k = policy.top_k * 6`) to compensate for downstream permission attrition and chunk inflation (~2 chunks/doc) before the budget packer clamps the final set.

### Indexing (`src/indexer.py`)

Chunks each document via `src/chunker.py` (~350-token paragraph-aware chunks, ~15% overlap, sentence/token-window fallbacks for oversized units) and embeds every chunk with `all-MiniLM-L6-v2` (ONNX via `src/embedder.py`), building a FAISS `IndexFlatIP` (cosine similarity via L2-normalized vectors). Also tokenizes chunk text for BM25 (stopword-filtered). **One row per chunk**: payload `id` = chunk id (`doc_NNN#cNN`), `doc_id` = parent, plus `chunk_index`/`chunk_count`/`char_start`/`char_end` and the chunk's full text as `excerpt` (the packable content — the old 500-char teaser is gone). All functions take a `workspace` ref (slug, `Workspace`, or None → default). Persists three artifacts per workspace:
- `artifacts/<slug>/querytrace.index` — FAISS index (384-dim vectors)
- `artifacts/<slug>/index_documents.json` — ordered document payloads matching FAISS row order
- `artifacts/<slug>/bm25_corpus.json` — tokenized corpus for BM25 (same row order)

All three must exist for a workspace before it can serve queries. If missing, run `python3 -m src.indexer --workspace <slug>` (no flag = rebuild every workspace).

### Corpus & access control

- Per workspace: `corpora/<slug>/metadata.json` — each doc has `min_role` and `superseded_by` (doc id or null for stale pairs); `corpora/<slug>/roles.json` — three roles with `access_rank`.
- Access rule: user's `access_rank` >= document's `min_role` rank (rank comparison is generic; role names are workspace-defined).
- `pe-deal`: analyst (1) < vp (2) < partner (3); stale pairs doc_002→doc_003 (research notes), doc_007→doc_008 (financial models), doc_014→doc_010 (IC draft defer → final approval memo).
- `saas-internal`: employee (1) < manager (2) < exec (3); stale pairs doc_003→doc_004 (on-call runbook v1→v2), doc_007→doc_008 (comp bands 2023→2024), doc_013→doc_014 (roadmap draft→final).

### Evaluation harness (`src/evaluator.py`)

Fully implemented and wired to `run_pipeline()`. `run_evals(queries, k, top_k, policy_name, workspace)` runs a workspace's 12 corpus-grounded test queries through the production pipeline and computes precision@k, recall, permission_violation_rate, avg_context_docs, avg_freshness_score, plus trace-level metrics (avg_blocked_count, avg_stale_count, avg_dropped_count, avg_budget_utilization). CLI: `python3 -m src.evaluator` (flags: `--k`, `--top-k`, `--compare`, `--workspace`, `--evals`). `--compare` runs `naive_top_k` and `full_policy` side by side and asserts full_policy has zero violations (used as a CI smoke on the default workspace). Measured baselines (post-chunking): pe-deal naive 50% violation rate → full 0% (P@5 0.2667→0.3000); saas-internal naive 58% → full 0% (P@5 0.2667→0.2500); recall 1.0 everywhere. Context items are chunks — `assembled_ids` dedupes to unique parent docs (first-seen order) before P@k/recall, and the per-query blocked/stale/dropped counts use the `*_doc_count` trace metrics. The `--token-budget` flag was removed — budget is policy-owned.

### Compare endpoint (POST /compare in `src/main.py`)

Runs the same query through multiple policy presets side-by-side. Calls `run_pipeline()` for each requested policy — no business logic duplication. Request accepts `query`, `role`, `top_k`, `policies` (default: all three presets), and optional `workspace`. Returns `CompareResponse` with `results: Dict[str, QueryResponse]` keyed by policy name.

### Ask endpoint (POST /ask in `src/main.py`, logic in `src/ask.py` — Fase 4)

Grounded answers over the governed context. Request body is identical to `/query` (`QueryRequest`); the packed context goes to a Claude model and the answer returns with mechanically validated `[doc_id]` citations. **Feature flag:** the mode exists only when `ANTHROPIC_API_KEY` is set — `/health` exposes `ask_enabled` and removing the var is the kill-switch (403 with a clear message).

Gate order in the handler: feature flag (403) → session/workspace/role (same Fase P/2 semantics as `/query`: server-derived role, forced `full_policy` for non-admins, workspace binding 403) → **cache** (hit → served with `cached: true`, zero tokens, no rate-limit charge) → **rate limit** (per-IP via `X-Forwarded-For` + global window → 429) → `run_pipeline()` → `build_prompt()` → model call (provider failures → 502, stack-free).

`src/ask.py` is pure-compute except `call_model()` (the single network touchpoint; tests monkeypatch `_get_client`):
- `build_prompt(query, included_docs)` — system mandates context-only answers with `[doc_id]` citations; user embeds exactly the packed context as `<doc id= title= date= type=>` blocks — sibling chunks of one document are grouped into a single `<doc>` block (chunk order, `[...]` separators) so citations stay doc-level and no id repeats. Blocked docs can never reach it (tested at unit and API level).
- `extract_citations(answer, included_ids)` — regex `\[(doc_\d+)\]`, deduped in order; `valid` iff the id was in the prompt context. `grounded_doc_count` = distinct valid.
- Cache keyed `(workspace, normalized query, role, policy, top_k)`, TTL `ASK_CACHE_TTL_SECONDS` (default 3600s), bounded at 256 entries. **Stores the unredacted response; `_redact_trace_for_viewer` is applied per viewer at serve time** (a guest and julia can share one entry and see different traces).
- Rate limiter mirrors the login limiter: `ASK_MAX_PER_MINUTE` (default 6/IP) + `ASK_MAX_PER_MINUTE_GLOBAL` (default 30) over a 60s window. `reset_ask_state()` clears cache + windows (tests).
- `trim_to_context_cap()` — defensive second belt (`ASK_MAX_CONTEXT_TOKENS`, default 4096) on top of the packer's 2048 budget; never trims in practice.
- Env knobs: `ASK_MODEL` (default `claude-haiku-4-5`), `ASK_MAX_TOKENS` (600), `ASK_TEMPERATURE` (0.2; `none` omits the param for models that reject it), `ASK_TIMEOUT_SECONDS` (30, max_retries=1).

`AskResponse` (in `src/models.py`, with `Citation` and `AskUsage`): `{query, answer, citations: [{doc_id, valid}], grounded_doc_count, model, usage: {input_tokens, output_tokens}, cached, context, total_tokens, decision_trace}` — the trace always travels with the answer. `/ask` is available to guests and all sessions (it is the product payoff, not an admin tool); it does not write session-audit entries (audit documents `/query` only).

Evaluator integration (`src/evaluator.py`): `run_ask_evals()` measures **citation_validity_rate**, **groundedness_rate**, **expected_cited_rate** over a workspace's benchmark via the exact `/ask` code path; CLI `--ask` writes `evals/results/ask-YYYY-MM-DD-<slug>.json`. `run_ask_goldens()` / `--ask-goldens` fills `corpora/<slug>/ask_goldens.json` (3 pe-deal role-pair cases; `snapshots: null` until a keyed run generates measured answers). Both flags hard-fail without `ANTHROPIC_API_KEY`; tests inject a fake `call` — CI needs no key and no network.

### Workspace endpoints (GET /workspaces, GET /workspaces/{slug}/meta in `src/main.py`)

`GET /workspaces` → `{workspaces: [{slug, name, description, doc_count}], default}`. `GET /workspaces/{slug}/meta` → everything the frontend renders for one workspace: `roles` (name, access_rank, description, manifest `hint`, **computed `docs_visible`** from metadata — nothing hardcoded), `total_docs`, `doc_types`, `scenarios`, `example_queries`, `search_placeholder`, `empty_state_description`, and `personas` (same cards as `/personas`, no hashes). Malformed slug → 400; unknown → 404.

### Evals endpoint (GET /evals in `src/main.py`)

Returns cached evaluator results as structured JSON, **per workspace** (`/evals?workspace=<slug>`, default workspace when omitted). On first call per slug: loads `corpora/<slug>/evals.json`, runs `run_evals(queries, k=5, top_k=8, workspace=slug)`, and stores the result in the module-level `_evals_cache: Dict[slug, dict]`. Subsequent calls return the cached dict. Response shape: `{ "per_query": [...], "aggregate": {...} }`. The route is a thin dispatch — all metric logic lives in `src/evaluator.py`.

### Session audit endpoint (GET /session-audit in `src/main.py`)

In-memory log of every successful `/query` call since the process started. Resets on restart — no disk persistence. Response shape: `{ "session_started_at": "...", "benchmark_count": 12, "entries": [...] }`. Each entry has `id` (q013, q014, ...), `created_at` (UTC), `user` (username or null), `workspace` (slug, Fase 2), `query`, `role`, `policy_name`, `precision_at_5` (always null — no expected_doc_ids for live queries), `recall` (always null), `metrics` (included_count, total_tokens, avg_score, avg_freshness_score, blocked_count, stale_count, dropped_count, budget_utilization — counts are DOC-level since Fase 5: sourced from the `*_doc_count` trace metrics), and `doc_ids` (included, blocked, stale, dropped arrays — unique parent doc ids in first-seen order). ID numbering: `q{benchmark_count + live_index:03d}` where `benchmark_count` is derived from the **default** workspace's `evals.json` at startup (currently 12); the id counter is global across workspaces. `/compare` and `/evals` do not log entries. Audit state is module-level (`_session_audit` list + `threading.Lock`), matching the `_evals_cache` pattern. Demo caveat: globally shared across all visitors in a single process; the log itself is one stream — entries are tagged by workspace rather than partitioned.

### Ingestion endpoint (POST /ingest in `src/main.py`)

Multipart endpoint for uploading a document + metadata at runtime. The HTTP handler in `main.py` is a thin adapter; all logic lives in `src/ingest.py`.

Form fields: `file` (.pdf/.txt/.md/.docx, ≤10 MB), `title`, `date` (YYYY-MM-DD), `min_role`, `doc_type`, `sensitivity` (low/medium/high/confidential), `tags` (comma-separated), and optional `workspace` (empty → default). **`min_role` and `doc_type` validate against the target workspace's vocabularies** (roles.json keys and the manifest's `doc_types`) — the old hardcoded frozensets are gone; `VALID_SENSITIVITY` stays global.

Fase 3 Etapa A hardening, in gate order in the handler: `Content-Length` over the cap → 413 before the file is read (64 KB multipart overhead allowance); unsupported extension → 415; the file is read in 1 MB chunks with a hard stop at `MAX_UPLOAD_BYTES` (10 MB, alias `MAX_PDF_BYTES` kept) → 413. Then `src/ingest.py`: `extract_text(file_bytes, filename)` dispatches on extension after a **magic-bytes check** (`%PDF-` in the first 1 KB for .pdf, ZIP `PK\x03\x04` signature for .docx, no NUL bytes / no binary signature for .txt/.md) → 415 on a lying extension; extraction via pdfplumber (.pdf), UTF-8→latin-1 decode (.txt), YAML-frontmatter-stripped text (.md), python-docx (.docx). Extracted text is hashed (`compute_content_hash`: sha256 over whitespace-collapsed, lowercased text) and compared against the workspace's `content_hash` entries → **409** naming the existing doc_id on duplicates (pre-Fase-3 entries have no hash and never match). New entries carry `content_hash`.

**Fase 3 Etapa B — async jobs.** Ingest is split in two halves in `src/ingest.py`: `prepare_ingest()` (synchronous — validation, extraction, hash, early dedup; everything that should fail the request itself) and `finalize_ingest(prepared, on_stage=None)` (heavy — under the module lock: authoritative dedup re-check, write `corpora/<slug>/documents/<sanitized_title>.txt`, append to `metadata.json` with `content_hash`, invalidate the workspace resolver cache, then index incrementally via `indexer.add_document(slug, entry, text, on_stage=...)`).

**Fase 3 Etapa C — incremental indexing.** `indexer.add_document(workspace, entry, text, on_stage=None)` chunks and embeds ONLY the new document (via `_embed_texts` → `src.embedder.embed`, the shared ONNX singleton), appends its chunk rows to the loaded FAISS index, appends the chunk payloads and BM25 token rows, and rewrites the three artifacts atomically (index last). Falls back to a full `build_and_save()` when artifacts are missing or drifted (`index.ntotal != len(payloads) != len(bm25)`); edits/deletes remain full-rebuild (IndexFlatIP has no cheap remove; `IndexIDMap` is the upgrade path). Measured (warm model, M-series): 16 docs full 0.04 s vs add 0.009 s; 160 docs full 0.22 s vs add 0.010 s (~21×, add is flat). `build_and_save(workspace, on_stage=None)` also accepts the stage callback. `ingest_document()` remains as the synchronous composition of both (tests / future CLI). On success the endpoint returns **202 `IngestAccepted{job_id, state, workspace}`** and `finalize_ingest` runs on the single-worker executor in `src/jobs.py` (`ThreadPoolExecutor(max_workers=1)` — serializes reindexes; tests use `jobs.configure(run_inline=True)` + `jobs.reset_jobs()`). Job states: `queued → extracting → embedding → indexing → done | failed` (`embedding`/`indexing` flipped by `build_and_save`'s `on_stage` callback); the `JobStore` retains the newest 50 jobs (older → 404). **Rollback:** if the job fails after writing the .txt/metadata entry, both are removed — no orphans. On `done`, the job itself invalidates `retriever.invalidate_caches(slug)`, pops `_evals_cache[slug]`, and stores an `IngestResponse`-shaped `result`. `GET /ingest/jobs/{job_id}` / `GET /ingest/jobs` (newest first, session's workspace only) require an admin session (401 guest / 403 non-admin / 403 cross-workspace / 404 unknown-or-expired) and the `ALLOW_INGEST` flag. Trade-off (documented in `src/jobs.py` + README Known Limitations): threads in-process for a single-instance demo; upgrade path is an external broker behind the same JobStore interface.

Error codes (all on the POST itself, synchronous): 415 (unsupported extension / magic-bytes mismatch), 400 (empty title / bad date / bad enum / empty file), 409 (duplicate content, detail names the existing doc_id), 413 (>10 MB, by Content-Length or streamed read), 422 (unreadable file / <50 chars of extractable text). Failures inside the job surface as `state: "failed"` + `error: {status_code, detail}` on the job endpoint. The content-type header is ignored (spoofable and inconsistent across browsers for .md/.docx) — the extension + magic bytes are the contract. Frontend: `uploadDocument()` posts, then polls the job every 1 s rendering four progress dots with human labels; submit stays disabled until the job is terminal.

Demo-scope caveats: no delete/edit path, the reindex is still a full rebuild (~5–10s, now off-request on the job worker), jobs are in-memory (die with the process), and writes go straight to repo paths — uploads will vanish on ephemeral hosting filesystems. (Upload requires an admin session whose workspace matches the target — see Fase P/Fase 2 below.)

### Session auth & product mode (Fase P; workspace-bound since Fase 2)

Demo personas live **per workspace** in `corpora/<slug>/users.json` (pe-deal: julia/analyst, victoria/vp, patricia/partner+admin; saas-internal: sofia/employee, marcos/manager, alex/exec+admin; passwords deliberately public via `password_hint`, published in the README). `src/auth.py` implements stateless signed-cookie sessions (HMAC-SHA256, payload `{username, name, role, is_admin, workspace, exp}`, cookie `qt_session`, TTL 12h, secret from `QUERYTRACE_SECRET_KEY` with a loudly-warned dev default) plus an in-process login rate limiter (10/min per IP → 429).

Endpoints: `POST /login` (body `{username, password, workspace?}` → identity JSON incl. `workspace` + cookie; credentials verify against that workspace's users), `GET /me` (identity incl. workspace, or 401), `POST /logout`, `GET /personas?workspace=` (public login-screen cards incl. `docs_visible`/`password_hint`).

Session semantics in `main.py`:
- **Workspace binding** (`_resolve_request_workspace`): a session belongs to exactly ONE workspace (the one it logged into). A request naming a different workspace → **403** — never a silent role remap across corpora. Requests without `workspace` use the session's workspace; guests use the requested slug or the default. Pre-Fase-2 cookies (no `workspace` in payload) resolve to the default workspace.
- **Server-derived role** (`_apply_session_to_request`): with a session, `/query` takes the role from the cookie; an explicit conflicting body `role` → 400. Non-admin sessions also force `policy_name=full_policy` (explicit conflicting policy → 400). Guests (no cookie) keep the lab behavior — role from body, any policy, any workspace.
- **Trace redaction** (`_redact_trace_for_viewer`): non-admin sessions get `blocked_by_permission=[]` plus `blocked_summary={count, required_roles}` (model `BlockedSummary`); enforced at the API edge so curl reveals nothing the UI hides. Knob: the workspace manifest's `blocked_disclosure` (`count|titles`, default count); the `BLOCKED_DISCLOSURE` env var, when set, overrides the manifest (ops escape hatch). Admin and guest get the full trace.
- **Capabilities**: `/compare`, `/evals`, `/session-audit` return 403 for non-admin sessions (lab/admin tools). `/ingest` requires an admin session (401 guest / 403 non-admin) whose workspace matches the target, on top of the `ALLOW_INGEST` kill-switch. Audit entries carry `user` (username or null); non-admin viewers of `/session-audit` see `user: null` (anonymous).

Frontend: login screen (`#login-screen`, persona cards from the workspace meta, workspace name + switcher row, "Explore the Lab without signing in →" sets `sessionStorage.qt_guest`), session chip in header (identity + role · workspace + Sign out), `body.product-mode` hides role/policy selectors and lab modes for non-admins, admin keeps everything (role radios lock to the session role in Query mode, unlock in Side-by-side), and redacted responses render a withheld strip ("🔒 N documents withheld · requires vp+") with a "Why?" `<details>` popover. Upload button is hidden unless admin session + ingest enabled.

### Frontend

Static HTML/CSS/JS in `frontend/` — no build step. Open `frontend/index.html` directly in a browser with the server running.

**Lacre components (Fase 6 Etapas C–G) — where this section's older phrasing disagrees, this paragraph wins.** Result cards are **folios**: 3px double top rule, Fraunces `--fs-lg` title, `EXHIBIT NN` label (`.card-folio`, replaces the `#N` rank and the `::before` accent bar), `REF: doc_NNN` meta badges; the stale badge is now a rotated `.stamp.stamp-superseded` + readable reason, and blocked mini-cards carry an absolute `.stamp-blocked` (stamp system: double ring, feTurbulence ink mask, `--stamp-blend/--stamp-alpha` per theme — multiply on paper / screen on carbon; variants blocked/superseded/approved/overbudget; `.stamp-flat` is the unrotated, unmasked ledger variant). The Single summary bar is a **memo letterhead** (`.memo-field` hairline table: Prepared for · Policy · Documents · Tokens (·% of budget) · Blocked · Stale; export button says "Download filing"; class `.summary-bar` retained for the UI-B stale gate). The Single trace panel is retitled **Decision Record** and renders `buildDecisionRecordHTML()` — one ledger row per doc per action (Document · Ref · Action mark · Basis, inline, no tooltip-only data); Compare keeps the compact chips via `buildTraceChipsHTML()` (`compact=true`). Redacted product sessions get one count-only Blocked row ("N withheld… titles withheld server-side"). `StaleDocument`/`DroppedByBudget` now carry optional `title` (populated by the freshness/budget stages) so stale/dropped rows show titles. The header has a `#classification-line` ("Private & Confidential · <manifest name>") and `.brand-mark` is the circular lacre QT seal (the only brand red, D6.1); `#theme-toggle` sits beside it. The Single empty state is a **memo cover** (`.empty-kicker` + `.empty-display` Fraunces 2.2rem with the measured 50%→0% claim); the login screen is a **letter** (`.login-box` sheet, pitch H1, business-card personas with `ROLE · CLEARANCE I-III` from ROLE_RANKS, `#guest-link` as the primary ink CTA, disclaimer demoted to small print). Compare columns carry **verdict stamps** (naive: `LEAKED N DOCS` where N = full's `blocked_doc_count`, only when >0; full: `CLEAN`) and compare-cards are mini-folios with `REF:` badges. Metrics mode replaced the 10-card grid with a **CERTIFIED plaque** (`buildCertifiedPlaqueHTML` — approved stamp ONLY at exactly 0% violations, warning plaque otherwise) + a 9-row hairline financial statement (`.metrics-table`, Fraunces figures at two decimals) + inline budget fill bars (`budgetCellHTML`, animated via `animateBars()` double-rAF like all fill bars; static under reduced-motion). Assets: `favicon.svg` and `og-card.png` use the lacre seal identity; the README demo GIF and screenshots live in `docs/media/`.

**Lacre design foundation (Fase 6 Etapa B).** All color decisions live in three token blocks in `styles.css` — `:root` (light "cotton paper"), the `@media (prefers-color-scheme: dark)` block, and `:root[data-theme="dark"]` (dark "reading room") — zero color literals are allowed outside them (gate enforced with a brace-aware grep). `--accent` is **ink** (D6.1: sealing-wax red `--lacre` is reserved for the brand seal and danger stamps); base hues `--lacre/--verde/--ocre/--azul` map to naive+blocked / full+included / rbac+stale / dropped+budget+freshness. Typography: Fraunces (display, only ≥1.15rem), Source Serif 4 (body), IBM Plex Mono (machine voice) — every `font-size` uses one of the 8 scale tokens `--fs-2xs…--fs-3xl` (0.7–2.2rem, hard floor 0.7rem); radii tokens are 2/4/8px. Grain + warm radial atmosphere ship as `--grain`/`--atmosphere` data-URIs on `body` and `.login-screen` only (never over controls). Theme selection: a boot script in `index.html` `<head>` applies `localStorage.qt_theme` to `<html data-theme>` pre-paint; the `#theme-toggle` button in the header flips and persists it; the attribute beats the media query in both directions. All contrast pairs are ≥4.5:1 calculated in both themes (dark lacre/verde were lifted above the original plan values to pass AA).

**Workspace layer (Fase 2).** Everything corpus-specific renders from `GET /workspaces` + `GET /workspaces/{slug}/meta` at bootstrap: role radios (with `ROLE_DESCRIPTIONS`/`ROLE_RANKS` rebuilt per workspace — "Sees N of M docs" uses the computed `docs_visible`), onboarding scenario cards (Single dual-action + Compare compact), example shortcut rows, search placeholder, empty-state description, login personas, and the Upload form's min_role/doc_type selects. A workspace picker sits in the header and on the login screen; switching persists the slug to `sessionStorage.qt_workspace` and `location.reload()`s for a clean re-bootstrap (if a session is bound to another workspace it signs out first and lands on the new workspace's login screen). Workspace resolution order at bootstrap: session binding > stored picker choice > server default. `.example-btn` clicks are handled by a delegated document-level listener (`handleExampleClick`) because scenario buttons re-render per workspace. All API calls (`/query`, `/compare`, `/evals`, `/login`, `/ingest`) carry the current workspace. If `/workspaces` or `/meta` is unreachable, a minimal `FALLBACK_META` keeps the form usable so submit can show the "Backend unavailable" error card.

Four modes controlled by a header toggle (visible labels: Query / Side-by-side / Metrics / Upload; `data-mode` keys: single / compare / evals / admin):
- **Query mode** (`single`) — calls `POST /query` with a selected policy (No Filters / Permissions Only / Full Pipeline). Before any query runs, the results area renders a guided empty state (`#empty-state`) with three `.onboard-card` scenarios ("Permission Wall" / "Financial model access" / "Stale Detection") in a responsive 3-column grid (collapses to 1 column ≤720px). **UI-C restructure**: each `.onboard-card` is a non-interactive `<div>` wrapper (no `cursor:pointer`, no hover-lift on the card body) containing title + hint plus an `.onboard-actions` row with two `.example-btn` children — `.onboard-primary` carries `data-mode="single"` (runs the scenario in Single with `full_policy`, stays in Single), `.onboard-secondary` carries `data-mode="compare"` and reads "Open in Compare →" (explicitly switches to Compare and runs the comparison). The existing `.example-btn` click handler dispatches on `data-mode` and covers both buttons with no branching. Clicking the card body outside the two buttons does nothing — mode transitions are always explicit. The empty state is removed on the first query (does not restore for the session). Result cards are **grouped per parent document** (Fase 5 Etapa B: `groupContextByDoc()` merges sibling chunks — best-scoring chunk visible, one card per doc, no duplicates). Cards show: document title as heading (fallback to `doc_id`), a metadata line with `doc_id` badge + formatted doc type + date + a `.card-sections-badge` ("matched N of M sections") when the doc is multi-chunk, a 200-char excerpt with "Show more ▾ / Hide ▴" expand/collapse (expands to ALL matched chunks joined with `[…]` separators), relevance + freshness bars, tags, and a stale/superseded badge ("⚠ Superseded by … — freshness penalized 0.5×") on demoted docs. Trace chips, blocked mini-cards, the narrative summary, and the summary-bar counts are all deduped to parent docs via `groupTraceEntries()` / `docCount()` (chunk ids listed in chip tooltips, "·N chunks" suffix on multi-chunk included chips). Below the result cards, a collapsible blocked-documents section (🔒 N documents blocked by permissions) shows one mini-card per blocked doc with title, doc_id badge, doc type, and a human-readable reason ("Requires X role — you are Y"). The section is hidden when no documents are blocked. A collapsible Decision Trace panel below that opens with a natural-language summary paragraph (`.trace-summary`) translating included/blocked/stale/dropped counts into prose — e.g., "6 documents were included (675 tokens, 33% of budget). 10 documents were blocked — your role (analyst) cannot access vp- and partner-level materials." — followed by the existing technical chips and a metrics strip. `title=` tooltips on the Budget label, avg score, avg freshness, and ttft spans explain each metric. A role description paragraph (`#role-description`) sits under the role chips and updates on every role change (including programmatic sets from `.example-btn` / onboard-card clicks) via `ROLE_DESCRIPTIONS` + `updateRoleDescription()` in `app.js`. A policy description updates below the selector tabs; selecting "No Filters" shows an amber warning banner. **Single example buttons (`.example-btn[data-mode="single"]`) are deterministic presets**: the click handler forces `policy=full_policy`, toggles the matching policy radio, and re-runs `updatePolicyDescription("full_policy")` so the `#policy-warning` clears if the user previously had "No Filters" selected. The manual form `submit` path still honors whichever policy radio the user has chosen. **Ask AI (Fase 4)**: a `#ask-btn` (✦ Ask AI) sits next to Run, hidden unless `/health` reports `ask_enabled` AND the mode is Single (`updateAskButtonVisibility()`, re-evaluated on every `switchMode`). `runAsk()` posts the same body as `/query` to `/ask` (same session rules: omit role with a session, omit policy for non-admins), renders the normal result view via `renderSingleResult(data, role, policy)` (AskResponse is a superset of QueryResponse), then prepends an `.ask-panel`: answer text with `[doc_id]` citations rendered as chips — valid ones are buttons that scroll to and highlight the matching `.result-card[data-doc-id]` (`.card-highlight` pulse, reduced-motion safe), invalid ones are red/struck-through with a tooltip — plus a grounding badge ("Grounded in N docs · M blocked docs never reached the model") and a mono usage note (model · tokens in/out · "served from cache" when `cached`). Errors (403 disabled / 429 rate limit / 502 provider) surface through the standard error card with the server's detail message. The `.ask-panel` participates in the stale-results fade. **Stale-results banner (UI-B)**: when the role or policy radio diverges from the `(role, policy)` pair that produced the rendered result, a `#stale-results-banner` (`role="status"` / `aria-live="polite"`) is inserted at the top of `#results-section` and the section gains a `results-stale` class that fades the summary bar, result cards, blocked section, and trace panel to 60% opacity. The banner reads "Controls changed — press **Run** to refresh these results." and is cleared on Run, on Single preset click, on mode switch out of Single, and when radios are toggled back to match the last-rendered values. On mode switch into Single, `evaluateSingleStale()` re-runs so a round trip (Single → Compare → Single) with a diverged role radio still surfaces the banner. The gate for all banner logic is the presence of `.summary-bar` inside `#results-section` — empty state, skeleton, error state, and "no results" views never trigger it. `_lastRenderedRole` / `_lastRenderedPolicy` are module-level in `app.js` and updated only on successful non-empty renders.
- **Side-by-side mode** (`compare`) — calls `POST /compare`. Renders three side-by-side policy columns (No Filters / Permissions Only / Full Pipeline) with severity-colored headers, stats strips (included/tokens/blocked/stale/dropped/ttft), compact doc cards (title heading, `doc_id` badge + type + date metadata, 120-char snippet, mini score/freshness bars, compact "⚠ Superseded" badge on stale docs), and expanded Decision Trace panels. Each column's trace panel opens with a compact variant of the narrative summary (`.trace-summary-compact`: tighter padding/type, stale details collapsed to a count, zero-dropped sentence omitted). Docs in the No Filters column that are blocked in `full_policy` are flagged with `blocked in full` annotations. **Compare onboarding empty state (UI-C)**: before any `/compare` runs, `#compare-empty-state` (first child of `#compare-section`) renders three single-click preview cards mirroring the Single empty-state layout — Permission Wall (analyst · ARR), Financial model access (vp · financial models), Stale Detection (partner · IC + LP) — each using `.onboard-card.onboard-card-compact` as a `<button>` with `data-mode="compare"` and a qualitative hint ("Naive surfaces 16 · RBAC + Full block 10"). The `.compare-banner` is `hidden` on initial load; `setLoadingCompare(true)` removes `#compare-empty-state`, reveals the banner, and injects the skeleton. Once removed, the Compare empty state does not reappear for the session.
- **Metrics mode** (`evals`) — calls `GET /evals` (lazy on first tab switch). Renders an executive-summary narrative banner (`.evals-narrative`) above the cards with three sentences: a permission-violations line (celebratory when rate=0, warning otherwise), a recall line (100% or fallback), and a budget-utilization tier line (`efficient <60%`, `moderate 60–80%`, `heavy >80%`). Then 10 aggregate metric cards (precision@5, recall, permission_violation_rate, avg_context_docs, avg_total_tokens, avg_freshness_score, avg_blocked_count, avg_stale_count, avg_dropped_count, avg_budget_utilization), each with a one-line `.metric-card-hint` micro-explanation. Below, a 12-row per-query breakdown table whose Query cell shows a `.evals-qid` id pill plus the query text truncated to 50 chars (full text via `title=`).
- **Upload mode** (`admin`) — hides the query form/results and shows an ingest form (file, title, date, min_role, doc_type, sensitivity, tags; the min_role/doc_type options come from the workspace meta). `uploadDocument()` POSTs `FormData` to `/ingest` with the current workspace set on the form data; the submit button disables and shows a spinner during the call, then renders a success status with the returned `doc_id` and the new corpus count, or an error status with the server message. All user-origin strings go through `escapeHTML`. A demo-only advisory in the panel notes that uploads persist to `corpora/<workspace>/` and `artifacts/<workspace>/` and will be lost on ephemeral hosting filesystems.

The policy selector uses a tab-style layout (`.policy-tab`) instead of chips. Each tab shows a human-readable label ("No Filters", "Permissions Only", "Full Pipeline") plus a mono sub-label listing the active pipeline stages (e.g., "Retrieval + RBAC + Freshness + Budget"). The active tab has a 2px bottom border in the policy's severity color; inactive tabs show hover feedback via `--accent-subtle`. Backend API names remain unchanged (`naive_top_k`, `permission_aware`, `full_policy`). `POLICY_META` in `app.js` maps between them. Both `naive_top_k` and `permission_aware` have `skipFreshness: true` — freshness displays as "N/A" since the backend skips freshness scoring for those policies.

Scenario entry points (post UI-D3; manifest-driven since Fase 2). Each workspace's three base stories live in its `workspace.json` `scenarios` array (pe-deal: Permission Wall / Financial model access / Stale Detection; saas-internal: Permission Wall / Stale Runbook / Roadmap Drift) and render as dual-action cards in the Single empty state (primary `Run in Single` + secondary `Open in Compare →`) and as single-click preview cards in the Compare empty state. The shortcut rows under the search bar come from the manifest's `example_queries` (grouped by `mode`): pe-deal keeps `Diligence risks` (vp) + `IC recommendation` (partner) in the Single row and `Stale detection →` (partner) in the Compare row; saas-internal has `Outage postmortem` (employee) + `Hiring plan` (manager) + `Salary bands →` (employee). Total scenario entry points visible on initial Single open: 6 per workspace (3 empty-state cards + 2 Single row + 1 Compare row). Tooltips are phenomenon-framed (describe what appears in the result), not role-framed. Scenario hints carry measured numbers (e.g., saas permission wall: "8 documents blocked").

Export + micro-interactions (NICE-A):
- **Export JSON** — an `.export-btn` (`⤓ Export JSON`) sits right-aligned inside Single mode's `.summary-bar` (filename `querytrace_<role>_<policy>.json`) and inside `#compare-banner` (filename `querytrace_compare_<role>.json`). The button downloads the verbatim `/query` or `/compare` response via a Blob + `URL.createObjectURL` → `a.click()` → `URL.revokeObjectURL` (paired in `setTimeout(0)`, verified non-leaking under repeated clicks). `renderCompare()` removes any prior `.export-btn` in the banner before appending, so re-renders never stack duplicates.
- **Motion polish** — mode-switch fade (`.mode-enter` → `@keyframes mode-fade` 200ms ease-out, added in `switchMode()` and removed on `animationend`); result cards use `@keyframes result-card-in` (translateY 8px → 0) and get a translateY(-1px) hover lift; `.metric-card` gets a translateY(-2px) hover lift; `.btn-spinner` pulses opacity 1↔0.7 on top of its rotate; `.trace-body` open/close uses a `max-height` + padding transition instead of `display: none↔block`. All motion reuses the `--dur: 180ms` / `--ease: cubic-bezier(0.22,1,0.36,1)` tokens. A `@media (prefers-reduced-motion: reduce)` block disables the new animations and hover transforms while preserving functional behavior.

## Environment note

Developed on Python 3.9.6 with LibreSSL 2.8.3. Embeddings run on ONNX Runtime via `fastembed` (Fase 5 Etapa A) — torch/sentence-transformers are gone from the dependency tree. `onnxruntime` 1.19.x is the last release with py3.9 wheels; py3.11 (CI/Render) resolves a newer one. The model cache lives under `~/.cache/querytrace/fastembed` (`FASTEMBED_CACHE_PATH` overrides) — fastembed's default tempdir cache gets purged by macOS, leaving a half-deleted snapshot that fails with `ONNXRuntimeError NO_SUCHFILE` instead of re-downloading (`src/embedder.py:_cache_dir`).

Ingestion adds two runtime deps in `requirements.txt`: `pdfplumber` (PDF text extraction) and `python-multipart` (FastAPI `File`/`Form` parsing). Both are pulled in by `pip install -r requirements.txt`.

## Deploy (read-only, Render-first)

The app is packaged as a single service: FastAPI JSON API + the static `frontend/` mounted at `/app/` via `StaticFiles(directory="frontend", html=True)` (resolved from `__file__` so CWD does not matter). The deployed demo URL is `https://<render-host>/app/` — a trailing slash is required; `/app` without it 307-redirects to `/app/` (Starlette default).

**Render web service:**
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn src.main:app --host 0.0.0.0 --port $PORT` (also in `Procfile` for buildpack-based flows).
- Environment variables:
  - `ALLOW_INGEST=false` — disables `POST /ingest` (returns 403). Required for read-only deploys so the public Admin form cannot mutate the corpus.
  - `QUERYTRACE_SECRET_KEY` — session-cookie signing secret (Fase P); the dev fallback logs a loud warning.
  - `ANTHROPIC_API_KEY` — optional (Fase 4): enables `POST /ask` + the Ask AI button. Unset = the mode disappears; that's the kill-switch. The key is set in the hosting dashboard only — never in the repo. Optional `ASK_*` knobs documented in the Ask endpoint section.
  - `PORT` — provided automatically by Render; do not hard-code.
- Python version: Render picks up `python-3.11.x` by default; either accept the auto-detection or pin with a `.python-version` file if a mismatch arises on build.
- Artifacts are committed per workspace (`artifacts/<slug>/{querytrace.index, index_documents.json, bm25_corpus.json}`) so the container boots without running the indexer. `.gitignore` only excludes `artifacts/*.faiss|*.pkl|*.npy`, which do not match these filenames.

**`ALLOW_INGEST` semantics.** Read per-request by `_ingest_enabled()` in `src/main.py`. Default is enabled — the flag is off only when the env var is exactly `"false"` or `"0"` (case-insensitive). Tests therefore do not need to set the flag. The frontend probes `GET /health` on load; when `ingest_enabled === false`, the Upload mode button and `#admin-section` are hidden; when `ask_enabled === false`, the Ask AI button stays hidden. `GET /health` response shape: `{"status": "ok", "ingest_enabled": <bool>, "ask_enabled": <bool>, "default_workspace": <slug>}`.

**`API_BASE` behavior (in `frontend/app.js`).** When the page is opened on `localhost` / `127.0.0.1` / `file://`, `API_BASE` is `http://localhost:8000` (cross-origin, CORS-permitted). On any other host, `API_BASE` is `""` — fetches become same-origin relative URLs (e.g., `/query`), so `https://host/app/` calls `https://host/query`. CORS is permissive (`allow_origins=["*"]`) purely to keep the `file://` dev flow working.

**Ephemeral-filesystem caveat (inherited from MUST-D).** With `ALLOW_INGEST` unset, `/ingest` writes to `corpora/<slug>/documents/*.txt`, `corpora/<slug>/metadata.json`, and `artifacts/<slug>/*`. On Render's default ephemeral disks these writes survive only until the next deploy/restart. For a persistent Upload-mode demo, attach a Render Disk mounted at the repo root or keep `ALLOW_INGEST=false` and rely on the committed two-workspace baseline (16 + 14 docs).

**Non-target hosts.** Railway works from the same `Procfile` unchanged. Fly.io needs a Dockerfile (out of scope).

**Local quickstart mirrors production.**

```bash
python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000
# Frontend: http://localhost:8000/app/
# API:       http://localhost:8000/{query,compare,evals,health}
```
