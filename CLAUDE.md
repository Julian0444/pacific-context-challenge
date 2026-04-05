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

```
retrieve(query, top_k)        → raw semantic hits from FAISS (dicts with doc_id, score, excerpt, min_role, etc.)
  ↓
filter_by_role(chunks, role)  → drops docs where role's access_rank < doc's min_role rank
  ↓
apply_freshness(chunks, meta) → attaches freshness_score; superseded docs get 0.5× penalty (demoted, not removed)
  ↓
assemble(chunks, budget)      → sorts by 50/50 similarity+freshness, greedily packs within tiktoken token budget (default 2048)
  ↓
QueryResponse                 → list of DocumentChunk + total_tokens
```

Roles and metadata are loaded once at module level in `main.py`. The sentence-transformers model is lazy-loaded as a singleton in `retriever.py`.

### Data flow between modules

The retriever returns plain dicts (not Pydantic models). These dicts flow through `policies` and `freshness` as-is — each module reads/writes specific keys (`min_role`, `freshness_score`). Only `main.py` converts to `DocumentChunk` at the end. The assembler reads `content` falling back to `excerpt`.

### Indexing (`src/indexer.py`)

Embeds full document text with `all-MiniLM-L6-v2`, builds a FAISS `IndexFlatIP` (cosine similarity via L2-normalized vectors). Persists to `artifacts/querytrace.index` + `artifacts/index_documents.json`. The index must exist before the server starts — if missing, run `python3 -m src.indexer`.

### Corpus & access control

- `corpus/metadata.json` — each doc has `min_role` (analyst/vp/partner) and `superseded_by` (doc id or null for stale pairs)
- `corpus/roles.json` — three roles with `access_rank`: analyst (1) < vp (2) < partner (3)
- Access rule: user's `access_rank` >= document's `min_role` rank
- Two stale/superseded pairs: doc_002→doc_003 (research notes), doc_007→doc_008 (financial models)

### Stubs remaining

- `src/evaluator.py` — not yet implemented (all methods raise `NotImplementedError`)
- `evals/test_queries.json` — placeholder entries with empty `expected_doc_ids`

### Frontend

Static HTML/JS in `frontend/`. `app.js` calls `POST /query` at `http://localhost:8000`. Open `frontend/index.html` directly in a browser (no build step).

## Environment note

Developed on Python 3.9.6 with LibreSSL 2.8.3. `tf-keras` may be needed for `sentence-transformers` compatibility on this Python version.
