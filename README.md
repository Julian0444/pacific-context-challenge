# QueryTrace

A lightweight context-aware document retrieval system built with FastAPI and semantic search.

QueryTrace ingests a document corpus, indexes it with sentence embeddings, and serves relevant context to a language model — with role-based access policies and freshness scoring.

---

## Project Structure

```
.
├── corpus/               # Raw documents + metadata
│   ├── documents/        # Source documents (txt, md, etc.)
│   ├── metadata.json     # Per-document metadata
│   └── roles.json        # Role definitions and access tags
├── src/                  # Core application logic
│   ├── main.py           # FastAPI app and route definitions
│   ├── models.py         # Pydantic request/response models
│   ├── indexer.py        # Document loading and FAISS index builder
│   ├── retriever.py      # Semantic search over the index
│   ├── context_assembler.py  # Rank, trim, and assemble retrieved chunks
│   ├── policies.py       # Role-based access filtering
│   ├── freshness.py      # Recency scoring for documents
│   └── evaluator.py      # Eval runner against test queries
├── evals/
│   └── test_queries.json # Evaluation queries with expected results
├── frontend/             # Minimal web UI
│   ├── index.html
│   ├── app.js
│   └── styles.css
└── requirements.txt
```

---

## TODO

- [ ] Populate `corpus/documents/` with sample documents
- [ ] Implement `indexer.py` — load docs, embed, build FAISS index
- [ ] Implement `retriever.py` — semantic search over the index
- [ ] Implement `context_assembler.py` — rank, trim, and assemble retrieved chunks
- [ ] Implement `policies.py` — role-based access filtering
- [ ] Implement `freshness.py` — score documents by recency
- [ ] Implement `evaluator.py` — run evals against `test_queries.json`
- [ ] Wire everything together in `main.py` (FastAPI routes)
- [ ] Build out the frontend in `app.js`
- [ ] Write unit tests

---

## Quickstart

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload
```
