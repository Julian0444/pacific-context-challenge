# QueryTrace — Backend Analysis

**Date:** 2026-04-18
**Scope:** Backend-only (`src/`, pipeline, tests). Read-only audit, no code changes.
**Branch:** `codex/must-a-idea1-2`

**Fresh `pytest` status at time of audit:** `171 passed, 1 failed, 14 skipped`. The failing test is `tests/test_retriever.py::TestResultShape::test_top_k_clamped_to_corpus_size` — hard-codes `len(results) == 12` but the corpus is now 13 docs (see CR-1).

Working tree also has uncommitted drift (`corpus/documents/agenda.txt` untracked, `corpus/metadata.json` + `artifacts/*` modified) from an ingest that was not reverted.

---

## 1. Backend execution summary

QueryTrace is a read-mostly retrieval service. Two hot paths:

- **Query path** (`POST /query`, `POST /compare`, `GET /evals`): user text + role → hybrid retrieval (FAISS + BM25, RRF-fused) → RBAC filter → corpus-relative freshness scoring → token-budgeted greedy pack → audit trace. Pure compute after the retriever step.
- **Mutation path** (`POST /ingest`): multipart PDF → pdfplumber text → atomic-ish metadata append under a `threading.Lock` → synchronous FAISS+BM25 rebuild → in-process cache invalidation.

All persistent state lives on local disk (`corpus/`, `artifacts/`). No database, no network calls during a query, no background workers. The SBERT model, FAISS index, and BM25 object are lazy-loaded singletons per process (`src/retriever.py:42-58`). Roles and metadata are loaded once at app startup (`src/main.py:44-47`) but `_metadata` is a mutable dict so ingest can update it in-place.

A Pydantic type chain runs end-to-end: `ScoredDocument` (retriever output, `extra="ignore"`) → `FreshnessScoredDocument` → `IncludedDocument` / `BlockedDocument` / `StaleDocument` / `DroppedByBudget` → `DecisionTrace` → `QueryResponse.DocumentChunk`. Domain models are `frozen=True, extra="forbid"`; API boundary models are looser.

## 2. Pipeline walkthrough

Entry: `src/main.py:65 query()` → validates role → calls `run_pipeline()` (`src/pipeline.py:126`) → maps result to `QueryResponse`.

Inside `run_pipeline` (`src/pipeline.py:149-195`):

1. **Policy resolve** — `resolve_policy(name, top_k)` (`src/policies.py:36`) looks up `POLICY_PRESETS` and overrides `top_k` via `model_copy`. Raises `ValueError` on unknown name — main.py:76 converts that to HTTP 400.
2. **User context** — `roles[request.role]["access_rank"]` + role name → frozen `UserContext`.
3. **Retrieve** — `_retrieve_stage` calls the injected retriever with `retrieve_k = policy.top_k * 3`. The retriever (`src/retriever.py:177`) reads FAISS + BM25 from disk on every call, computes 1-based rank dicts, fuses with `RRF_score(d) = 1/(60+r_sem) + 1/(60+r_bm25)`, min-max normalises to [0, 1], sorts, clamps to `top_k`, and builds dicts with all corpus metadata fields. Results are validated into `ScoredDocument`; extra keys are silently dropped (`extra="ignore"`).
4. **Permission filter** — `src/stages/permission_filter.py:26`. Two branches: missing `doc.min_role` in roles → `BlockedDocument(reason="unknown_min_role")`; rank compare → permitted or `BlockedDocument(reason="insufficient_role")`. Skipped entirely when `policy.skip_permission_filter=True` (naive_top_k).
5. **Freshness** — `src/stages/freshness_scorer.py:30`. Builds `meta_by_id` from full metadata each call. Reference date = `max(all_dates)`. For each permitted doc: looks up metadata, exponential decay (`compute_freshness` in `src/freshness.py:18`), multiplies by `0.5` if superseded. Missing metadata → `freshness=0.0`, `is_stale=False`, but `superseded_by` is preserved from the ScoredDocument (inconsistent; finding MA-6). Produces `FreshnessScoredDocument` list + `StaleDocument` entries. Skipped → all freshness=0.0, all not stale.
6. **Budget packer** — `src/stages/budget_packer.py:44`. Sorts by `0.5*score + 0.5*freshness_score`, iterates, tokenises `doc.excerpt` with cl100k_base, greedily packs. Over-budget docs → `DroppedByBudget`. Returns `BudgetResult(packed, over_budget, total_tokens, budget_utilization)`. `enforce_budget=False` packs everything.
7. **Trace builder** — `src/stages/trace_builder.py:24`. Asserts `blocked+included+dropped == retrieved_count` (raises `ValueError` on mismatch — see finding MA-7). Computes avg_score, avg_freshness_score, assembles full `DecisionTrace`.

`_unwrap` (`src/pipeline.py:60`) converts each `StageErr` to `PipelineError(stage, error)`, which main.py:78 maps to HTTP 500. Any non-stage exception from `run_pipeline` bubbles as-is.

## 3. Module map

| Module | Role | Key I/O |
|---|---|---|
| `src/main.py` | FastAPI boundary. `/query`, `/compare`, `/evals`, `/ingest`, `/health`. Static mount at `/app` (EOF, line 260). | Loads `roles.json` + `metadata.json` at import. `/evals` caches module-global `_evals_cache`. |
| `src/pipeline.py` | Orchestrator. Wraps each stage in `StageOk/StageErr`, aborts on first error. Builds `UserContext`, resolves policy, threads TTFT timer. | No I/O. |
| `src/models.py` | Pydantic contract models. `frozen=True, extra="forbid"` on domain types; API types use `extra="forbid"` on request/response but `DocumentChunk` has none declared (MI-4). | — |
| `src/policies.py` | `POLICY_PRESETS` dict + `resolve_policy(name, top_k)`. Also `load_roles()` + dead `filter_by_role()`. | Reads roles.json. |
| `src/retriever.py` | Hybrid retrieval. `retrieve()` (default), `semantic_retrieve()` (comparison). Lazy singletons `_model`, `_bm25`; `invalidate_caches()` resets `_bm25`. | Reads FAISS + `index_documents.json` + `bm25_corpus.json` on every `retrieve()` call. FAISS not cached in-process. |
| `src/indexer.py` | Full rebuild: load docs, embed with MiniLM-L6-v2, write `querytrace.index` + `index_documents.json` + `bm25_corpus.json`. `tokenize_for_bm25()` used by both indexer and retriever. | Writes three artifacts to `artifacts/`. |
| `src/ingest.py` | PDF → text → metadata append → reindex. `_INGEST_LOCK` threading.Lock, validation, filename sanitiser, doc_id generator. | Writes `corpus/documents/<file>.txt`, mutates `corpus/metadata.json`, invokes `indexer.build_and_save()`. |
| `src/evaluator.py` | 8-query harness, precision@k + recall + permission_violation_rate. Uses `run_pipeline()` so metrics reflect the assembled context. | Reads `evals/test_queries.json`. |
| `src/stages/*.py` | Four pure-compute stages. No I/O, no globals. Each returns a named dataclass result. | — |
| `src/protocols.py` | `RetrieverProtocol`, `RoleStoreProtocol`, `MetadataStoreProtocol` for DI. | — |
| `src/freshness.py` | Pure helpers. `compute_freshness()` used by freshness stage. `apply_freshness()` is dead. | — |
| `src/context_assembler.py` | Dead code — pre-stage-refactor packer. Only referenced by `tests/test_context_assembler.py`. | — |

## 4. State, caching, and runtime behavior

- **Process-local singletons**: `_model` (SBERT), `_bm25` (BM25Okapi). `_model` never invalidated — corpus-independent. `_bm25` invalidated only by `invalidate_caches()` post-ingest.
- **Per-request disk reads**: `retrieve()` calls `load_persisted_index()` every time — reads FAISS and the payload JSON on every query. BM25 corpus only on cold-cache.
- **Module-global mutable state in main.py**: `_metadata` dict + `_evals_cache` optional. Ingest mutates both. Not thread-safe across uvicorn workers.
- **Lock scope**: `_INGEST_LOCK` serialises metadata+reindex inside one process. Multi-worker uvicorn breaks it (MA-2). `invalidate_caches()` runs *outside* the lock from `main.py:234`; between the lock release and the cache invalidation, a concurrent `/query` can run against new FAISS but stale `_bm25`.
- **Evals cache**: module-level `Optional[dict]`. Populated on first `/evals` call. Cleared by ingest. On exception during `run_evals`, cache stays None and next call retries fully.
- **Static frontend**: mounted at `/app` via `StaticFiles(html=True)`. Any future route starting with `/app/...` will be shadowed.
- **CORS**: `allow_origins=["*"]`, all methods, all headers. Justified in CLAUDE.md for `file://` dev; production tradeoff (MA-3).
- **Ingest gate**: `ALLOW_INGEST` env read per-request. No other auth on `/ingest` even when enabled (CR-2).

## 5. API / backend contract summary

- `GET /health` → `{status: "ok", ingest_enabled: bool}`.
- `POST /query` → `{query, context: List[DocumentChunk], total_tokens, decision_trace?}`. `DocumentChunk` carries `doc_id, content, score, freshness_score?, tags, title?, doc_type?, date?, superseded_by?`. Decision trace includes `user_context, policy_config, included, blocked_by_permission, demoted_as_stale, dropped_by_budget, total_tokens, ttft_proxy_ms, metrics`.
- `POST /compare` → `{query, role, results: Dict[policy_name, QueryResponse]}`. Empty policies list → 400; any unknown policy → 400.
- `GET /evals` → `{per_query: [...], aggregate: {...}}`. Cached after first call.
- `POST /ingest` (multipart) → `IngestResponse` with `doc_id, title, file_name, type, date, min_role, sensitivity, tags, total_documents`. Status codes: 403 (disabled), 415 (non-PDF), 400 (validation), 413 (>10MB), 422 (unreadable/<50 chars), 500 (layout error).
- Invariants: `retrieved_count == blocked_count + included_count + dropped_count` enforced in `trace_builder`; `result.trace.included == result.context` verified by test.

## 6. Backend findings (hostile-reviewer mindset)

### CRITICAL

**CR-1 — Working-tree drift from an actual ingest is currently breaking a test**
- `corpus/metadata.json` + `artifacts/*` modified; `corpus/documents/agenda.txt` untracked.
- `tests/test_retriever.py:67-69` hard-codes `assert len(results) == 12  # corpus has 12 docs`, but metadata + FAISS now contain 13 entries (IDs `doc_001…doc_013`).
- Why it matters: (a) the test is brittle — any real ingest breaks it; (b) CI-green claims from earlier session (172/14/0) are only true against a specific, undocumented artifact state; (c) this is exactly the ephemeral-filesystem caveat from CLAUDE.md manifesting as source-tree drift, not just runtime drift. The ingest demo mutates committed files with no "demo sandbox" isolation.
- Fix: parameterise the test from `load_documents()` / metadata.json instead of hardcoding. Separately, decide whether `corpus/` should be repo-tracked truth or runtime-mutable state — right now it is both, and the conflict is unresolved.

**CR-2 — No auth on `/ingest` when enabled**
- `src/main.py:177-253`. The only gate is the `ALLOW_INGEST` env var.
- On any Render deploy with `ALLOW_INGEST != "false"`, any caller on the public internet can write arbitrary documents into the corpus, trigger a ~5–10s reindex, and change what future `/query` calls return (including responses to other users). No API key, no rate limit, no origin check, and CORS is `*` so browser-based write floods are possible.
- Why it matters: even if the deploy is demo-only, "demo" + "public URL" + "mutation endpoint" is a classic stepping-stone for prompt-injection / corpus-poisoning into the downstream LLM context. Ingest is also CPU/IO-heavy: trivial denial-of-service vector (upload N 10 MB PDFs serially).
- Fix: require a shared secret header when `ALLOW_INGEST=true`, rate-limit per IP, or keep ingest disabled on any internet-facing deploy and allow it only via CLI.

### MAJOR

**MA-1 — Silent divergence between FAISS index, payload JSON, and BM25 corpus**
- `src/retriever.py:192-202` loads three artifacts (`querytrace.index`, `index_documents.json`, `bm25_corpus.json`) with no cross-consistency check. All three are built in one `indexer.build_and_save()` pass, but nothing stops partial writes, hand-edits, or version skew.
- `_bm25_ranks` at `src/retriever.py:107-110` correlates BM25 argsort row indices with `payloads[idx]["id"]`. If `bm25_corpus.json` was built from a different doc order than `index_documents.json`, BM25 ranks are assigned to the wrong doc IDs with zero visible error.
- Why it matters: silent wrong-answer bug class. Hardest to detect because tests may pass (ranks are still "some ranking") while prod returns nonsense.
- Fix: write a manifest (fingerprint of metadata + row count) alongside artifacts; validate on load. Or collapse the three files into a single `.npz`/pickle.

**MA-2 — Ingest lock is in-process only; reindex is synchronous and non-atomic**
- `src/ingest.py:45, 177-207`. `_INGEST_LOCK = threading.Lock()` serialises only within one Python process. A multi-worker uvicorn deploy (common for FastAPI production) has one lock per worker → concurrent writes to `metadata.json` race.
- `indexer.build_and_save()` writes three files sequentially (`src/indexer.py:152-166`) with no temp-file-and-rename atomicity. A `/query` that calls `load_persisted_index()` mid-write can see a half-written `querytrace.index` → `faiss.read_index` failure → 500.
- `main.py:234` calls `invalidate_caches()` *after* releasing the ingest lock. For the few microseconds between lock release and cache reset, `/query` can hit new FAISS + stale BM25 singleton and produce a ranked answer from misaligned payloads.
- Fix: use a file lock, write to `.tmp` files and `os.replace()`, and invalidate caches inside the lock.

**MA-3 — `CORSMiddleware(allow_origins=["*"])` in production**
- `src/main.py:33-38`. Rationale (dev convenience for `file://`) does not apply when the frontend is mounted same-origin at `/app/`.
- With `*` + `allow_methods=["*"]`, every endpoint — including `/ingest` when enabled — is callable from any origin by any browser. Combined with CR-2 above, cross-site script kiddie can submit an ingest form targeting your host from `evil.example.com`.
- Fix: when `ALLOW_INGEST=false`, still restrict to known origins or the deploy's own host. Document the dev/prod split instead of conflating them.

**MA-4 — `naive_top_k` returns 3× the user's requested `top_k`**
- `src/pipeline.py:161`: `retrieve_k = policy.top_k * 3` regardless of policy. For `naive_top_k` (skip permission filter, skip freshness, skip budget), there is no attrition to compensate for — the multiplier was introduced for the permission-aware case.
- A caller asking for `top_k=5, policy_name="naive_top_k"` gets **15** docs in context. Tests pass because `test_naive_top_k_dangerous_baseline` only asserts `included_count == retrieved_count`, not that included_count equals the requested top_k.
- Why it matters: the "No Filters" column in Compare mode looks artificially inflated vs. "Full Pipeline" — the narrative that "naive is dangerous" is partly driven by the multiplier, not the missing filters. Evals are unaffected (the evaluator always uses `default` policy), but eyeballed compare results mislead viewers.
- Fix: either multiply only when `not policy.skip_permission_filter`, or document that `top_k` is a retrieval-stage knob, not a final-context knob.

**MA-5 — `semantic_retrieve()` omits `doc_type` from its result dicts**
- `src/retriever.py:205-241`. The production hybrid `_build_results` includes `"doc_type": p.get("type")` (line 161), but `semantic_retrieve` does not. Anyone swapping retrievers for ablation (the very thing `semantic_retrieve` is documented to support, line 207) sees `doc_type=None` flow through the whole pipeline into the frontend.
- `ScoredDocument.model_config = ConfigDict(frozen=True, extra="ignore")` hides this — no validation error, just nulls.
- Fix: share the result-dict builder between `retrieve` and `semantic_retrieve`.

**MA-6 — Freshness stage produces inconsistent state when metadata lookup fails**
- `src/stages/freshness_scorer.py:56-60`. When `doc_meta is None`, `freshness_score=0.0`, `is_stale=False`, but `superseded_by = doc.superseded_by` is still forwarded from the retriever. A `FreshnessScoredDocument` with `superseded_by="doc_XXX"` and `is_stale=False` flows downstream — contradictory.
- Simultaneously no `StaleDocument` row is added for that doc, so the trace undercounts `stale_count`. The UI's "⚠ Superseded by …" badge (driven by `superseded_by`) would still render on the card, but the trace narrative would say "0 stale."
- Why it matters: divergence between retriever (authoritative for `superseded_by` at ingest time) and metadata (authoritative for everything else) can happen whenever the two get out of sync (see MA-1).
- Fix: treat missing metadata as an error and block the doc, or trust metadata only (clear `superseded_by` too).

**MA-7 — `build_trace`'s invariant check raises `ValueError`, which main.py maps to HTTP 400**
- `src/stages/trace_builder.py:55-60` raises `ValueError("Document accounting mismatch: ...")` on invariant violation.
- `run_pipeline` does NOT wrap `build_trace` in a stage wrapper (`src/pipeline.py:178-189` — called directly, no `_unwrap`). So a mismatch bubbles as `ValueError`.
- `src/main.py:76-77` catches `ValueError` as HTTP 400 "Bad Request" and sends the invariant message to the client. A true server-side invariant violation should be 500, and the internal message shouldn't leak.
- Fix: wrap `build_trace` like the other stages, or catch `ValueError` from trace separately and raise 500.

### MINOR

**MI-1 — Dead code paths risk accidental use**
- `src/policies.py:65-79` `filter_by_role()` — untyped, operates on dict "chunks", duplicates what `permission_filter.py` does on `ScoredDocument`. Public surface (no `_` prefix).
- `src/freshness.py:44-70` `apply_freshness()` — same story, writes mutable state into chunk dicts.
- `src/context_assembler.py` — entire file is dead (only test_context_assembler.py imports it).
- Fix: delete or mark with deprecation.

**MI-2 — Non-uniform tie-breaking between FAISS and BM25 rankings**
- `src/retriever.py:107` uses `np.argsort(-scores, kind="stable")`, FAISS returns by descending score. For corpora with ties (unlikely in a 13-doc corpus), the fusion can favour one retriever's tie-breaking rule. Fine for prod, worth noting.

**MI-3 — `_normalize_scores` collapses all-equal fused scores to all-1.0**
- `src/retriever.py:140-141`. A caller comparing top-1 against top-N can't distinguish "one clearly-best doc" from "no signal at all." Unlikely in practice but worth a comment.

**MI-4 — `DocumentChunk` has no `model_config`, implicitly allowing extras**
- `src/models.py:220-231`. All other API models are `extra="forbid"`. Asymmetric strictness: extra fields in response never fail validation, so typos go unnoticed in tests.
- Fix: add `model_config = ConfigDict(extra="forbid")`.

**MI-5 — `score_freshness` rebuilds `meta_by_id` and `reference_date` on every call**
- `src/stages/freshness_scorer.py:46-48`. For 13 docs this is fine (µs), but the pipeline recomputes these per request even though `_metadata` is loaded once at startup and mutated only by ingest. A lazy cache keyed by metadata revision would be slightly cleaner — not a performance issue today.

**MI-6 — `/evals` never retries a failed load**
- `src/main.py:167-174`. If `run_evals` raises (metadata corrupted, queries missing), exception propagates, `_evals_cache` stays None, and the next call re-raises. The cache is write-through-on-success only. Not a bug, but means a transient failure during eval warmup keeps the endpoint broken until the exception stops.

**MI-7 — `ingest_document` extracts text before acquiring the lock**
- `src/ingest.py:175` calls `extract_text_from_pdf()` outside `_INGEST_LOCK` (line 177). OK for perf (pdfplumber is slow), but means two concurrent uploads each spend 5–10s extracting, then serialise on the lock for the reindex. Worst case: two workers racing to compute `generate_next_doc_id()` after extraction — first wins, second reads metadata again under lock and gets `doc_(N+1)`. Fine today, but worth noting.

**MI-8 — `compute_freshness` clamps negative ages to 0**
- `src/freshness.py:40` `age_days = max((ref - doc_date).days, 0)`. A doc dated after the reference gets score=1.0 (max freshness). Pipeline always uses `max(all_dates)` as reference so this is safe — until someone passes a static reference and ingests a future-dated doc.

**MI-9 — FastAPI `version="0.2.0"`**
- `src/main.py:31`. Hasn't been bumped across MUST-A through NICE-B. Purely cosmetic for OpenAPI / `/docs`.

### NIT

**NI-1 — `semantic_retrieve()` result dict order does not match `_build_results`**
- `src/retriever.py:226-240` omits `doc_type`, has a different key order than `_build_results`. Cosmetic but a diff hotspot.

**NI-2 — `_BM25_STOPWORDS` is defined inline as a frozen set built from `.split()`**
- `src/indexer.py:107-113`. Easily extended, but hardcoded and duplicated nowhere else — if a future query flow wants to share tokenization, it'll need to import from indexer (which pulls in FAISS/SBERT). Splitting the tokenizer into its own module would decouple retrieval from indexing.

**NI-3 — Naming inconsistency around "type" vs "doc_type"**
- Metadata uses `"type"` (ingest.py:192, indexer output). Retriever exposes both `type` AND `doc_type` (line 160-161) by calling `.get("type")`. Downstream models use `doc_type`. Two names for the same field is fragile.

**NI-4 — `PipelineError.__init__` message pre-formats the stage but main.py re-formats it**
- `src/pipeline.py:57` and `src/main.py:81` both embed the stage name in the 500 detail. Harmless; a minor duplication.

**NI-5 — `_ingest_enabled()` env parsing accepts "true"/"True"/"1"/etc. but documents only "false"/"0"**
- `src/main.py:56`. `"not in {"false", "0"}"` means "TRUE", "yes", "", "anything" all enable ingest. The permissive default is intentional per CLAUDE.md but the asymmetric semantic (off-only-on-exact-match) is surprising for ops.

---

## 7. Open questions / assumptions

1. **Is the committed `corpus/` intended to be mutable at runtime?** CLAUDE.md acknowledges the ephemeral-fs caveat but does not prescribe what happens to source-tree mutations on a dev machine (see CR-1). If `corpus/` is canonical, `/ingest` shouldn't touch it; if it's a working sandbox, it shouldn't be checked in.
2. **Are multi-worker uvicorn deploys supported?** The Procfile (`uvicorn ... --host 0.0.0.0 --port $PORT`) doesn't set `--workers`, so Render defaults apply (1 worker). If that ever changes, MA-2 becomes active.
3. **What's the contract between `ScoredDocument` (extra="ignore") and the retriever?** The `extra="ignore"` is convenient for adapter flexibility but means regressions in retriever fields (missing `doc_type`) are undetectable without explicit tests.
4. **Is `_metadata` mutation in `main.py:237-238` ever read mid-mutation?** `_metadata["documents"] = fresh["documents"]` is an atomic pointer swap in CPython (GIL), so readers see either old or new — but `_metadata` dict identity is preserved, meaning any code that took a reference to `_metadata["documents"]` before ingest now holds a stale list. No such code exists today; worth a note.
5. **Is `DocumentChunk`'s lack of `extra="forbid"` deliberate for frontend compatibility?** The docstring says "Preserved for frontend compatibility" — maybe old clients added extras. If so, that deserves a comment.

## 8. Final verdict

**Pipeline core is solid.** The stage-based structure, typed dataclass results, Protocol-based DI, trace-builder invariant check, and 172-test harness give the retrieval path real defensive depth. RBAC is enforced at the right point, freshness is corpus-relative, budget is authoritative. Happy-path correctness is tight.

**Weaknesses cluster around the ingest/reindex path and artifact hygiene.** Three interlocking issues: (CR-1) source-tree drift from the demo ingest that broke a test and was never reverted; (CR-2) unauthenticated mutation on a public-deploy-ready endpoint; (MA-2) in-process lock + non-atomic reindex that doesn't survive multi-worker deploys or mid-write reads. These are not theoretical — they materialise the moment the app is deployed with `ALLOW_INGEST=true` or with more than one worker.

**Secondary fragility: silent degradation of signal.** `extra="ignore"` on ScoredDocument, the 3× top_k multiplier applied uniformly across policies, `semantic_retrieve` dropping `doc_type`, and the freshness/`superseded_by` mismatch in MA-6 all produce wrong-but-plausible output rather than errors. These are the hardest bugs to catch in a read-only pipeline.

Tests are **thorough for the happy path and policy-preset matrix**, **thin on artifact-drift and concurrency scenarios**, and **contain at least one stale assumption** (CR-1) that currently breaks. The evaluator is well-integrated and trustworthy as long as artifacts and metadata are in sync.

Net: the query path is production-grade for the demo's scope; the ingest path is a demo feature that was shipped with production endpoints. Closing CR-1, CR-2, MA-1, MA-2, MA-3, and MA-7 would bring the whole backend to the same bar as the retrieval core.
