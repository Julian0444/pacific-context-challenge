# Handoff — QueryTrace

## Session Summary

Three tasks were completed to bootstrap the QueryTrace project, a context-aware document retrieval system for a Pacific internship assignment:

1. **Repo scaffolding** — Created the full project structure at the repo root (not nested). All `src/` Python modules were created as stubs with docstrings and `raise NotImplementedError`. Frontend files (`index.html`, `app.js`, `styles.css`) were created with working markup and JS that calls `POST /query`. `CLAUDE.md` was written to orient future sessions.

2. **Financial corpus** — Built a 12-document fictional corpus about Atlas Capital Partners evaluating the acquisition of Meridian Technologies ("Project Clearwater"). Documents span public filings, research notes, deal memos, financial models, internal emails, board materials, and an LP update. Two explicit stale/superseded pairs were created (Q3→Q4 research note, financial model v1→v2). Three semantically similar pairs ensure the retriever surfaces competing candidates. `corpus/metadata.json` tracks all document metadata including `superseded_by` links. `corpus/roles.json` defines three roles: analyst (rank 1) < vp (rank 2) < partner (rank 3).

3. **Indexing and retrieval** — Implemented `src/indexer.py` and `src/retriever.py`. The indexer loads documents, embeds them with `all-MiniLM-L6-v2`, and builds a FAISS `IndexFlatIP` index (cosine similarity via normalized vectors). Artifacts are persisted to `artifacts/`. The retriever loads the persisted index and returns top-k results (default 8) with full metadata. Smoke-tested with three queries — stale and current documents both surface as candidates, confirming the retriever does not pre-filter and leaves that decision to the context assembler.

## Current State

- **Branch:** `main` (single commit: `6e55da7 Initial commit`)
- **All work is uncommitted.** Every file created in Tasks 1–3 is untracked or modified.
- **Modified files:** `README.md` (replaced stub with full project README)
- **Untracked:** everything else — `CLAUDE.md`, `corpus/`, `src/`, `evals/`, `frontend/`, `artifacts/`, `requirements.txt`, `docs/`
- **Tests:** none written yet, no test runner configured
- **FAISS index:** built and persisted in `artifacts/` (12 vectors, 384 dimensions)
- **Dependencies installed locally:** `sentence-transformers`, `faiss-cpu`, `tf-keras` (needed for Python 3.9 compatibility)

## Remaining Tasks (ordered)

1. **Implement `src/policies.py`** — Role-based access filtering. Use `min_role` from `corpus/metadata.json` compared against `access_rank` from `corpus/roles.json`. A document is accessible if the requesting role's `access_rank` >= the document's `min_role` rank. Filter retriever results accordingly.

2. **Implement `src/freshness.py`** — Exponential decay scoring using the `date` field in metadata. Documents with `superseded_by != null` should be demoted (not removed). Attach a `freshness_score` to each retrieval candidate.

3. **Implement `src/context_assembler.py`** — Take filtered, freshness-scored candidates and assemble a final context pack. Use `tiktoken` for token counting against a budget (default 2048 tokens). This is where stale documents get dropped in favor of their newer replacements when both are present.

4. **Wire `src/main.py`** — Connect the `POST /query` endpoint to the full pipeline: `retrieve → filter_by_role → apply_freshness → assemble`. Update `src/models.py` if the response schema needs adjustment (e.g., the current `QueryRequest` defaults role to `"viewer"` but the corpus uses `analyst`/`vp`/`partner`).

5. **Implement `src/evaluator.py`** — Load test queries from `evals/test_queries.json`, run them through the pipeline, compute precision@k. The current test queries file has placeholder entries with empty `expected_doc_ids` — these need to be filled in with real expected results.

6. **Build out the frontend** — `frontend/app.js` already calls `POST /query` and renders results. Will need adjustments once the response shape is finalized. The role dropdown currently includes "viewer" which doesn't exist in the corpus roles.

7. **Commit all work** — Nothing has been committed since the initial commit. All task work should be staged and committed.

## Blockers and Warnings

- **Python 3.9 environment:** The system Python is 3.9.6 with LibreSSL 2.8.3. `tf-keras` was installed to work around a Keras 3 incompatibility in `transformers`. This is fragile — if dependencies are upgraded, this may break again.
- **`src/models.py` role default mismatch:** `QueryRequest.role` defaults to `"viewer"` but the corpus only defines `analyst`, `vp`, `partner`. This will cause a runtime error or silent policy failure when the pipeline is wired up. Fix the default to `"analyst"`.
- **`evals/test_queries.json` is placeholder:** The two test queries have empty `expected_doc_ids` and one uses role `"viewer"`. These need real expected results before the evaluator is useful.
- **`artifacts/` gitignore:** The FAISS index and payloads are binary/generated files. Decide whether to commit them for convenience or add to `.gitignore` and require `python3 -m src.indexer` after clone.

## Suggested First Action

Fix the role default in `src/models.py` (change `"viewer"` to `"analyst"`), then implement `src/policies.py` — it's the smallest module and unblocks the full pipeline wiring.
