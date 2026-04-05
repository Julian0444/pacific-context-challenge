"""
retriever.py — Semantic search over the FAISS index built by indexer.py.

Accepts a natural-language query, embeds it with the same model used for indexing,
and returns the top-k most relevant documents with similarity scores.
"""

import numpy as np
from sentence_transformers import SentenceTransformer

from src.indexer import MODEL_NAME, load_persisted_index

# Lazy-loaded singleton so the model is only loaded once per process
_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def retrieve(query: str, top_k: int = 8) -> list[dict]:
    """Run a semantic search against the persisted FAISS index.

    Args:
        query: Natural-language search string.
        top_k: Number of results to return (default 8).

    Returns:
        A list of dicts, ranked by descending similarity, each containing:
            doc_id, title, file_name, score, type, date, min_role,
            tags, short_summary, superseded_by, sensitivity, excerpt
    """
    index, payloads = load_persisted_index()

    # Clamp top_k to corpus size
    top_k = min(top_k, index.ntotal)

    model = _get_model()
    query_vec = model.encode([query], normalize_embeddings=True)
    query_vec = np.array(query_vec, dtype=np.float32)

    scores, indices = index.search(query_vec, top_k)

    results = []
    for rank, (idx, score) in enumerate(zip(indices[0], scores[0])):
        if idx == -1:
            continue
        payload = payloads[idx]
        results.append({
            "rank": rank + 1,
            "doc_id": payload["id"],
            "title": payload["title"],
            "file_name": payload["file_name"],
            "score": float(score),
            "type": payload["type"],
            "date": payload["date"],
            "min_role": payload["min_role"],
            "sensitivity": payload["sensitivity"],
            "superseded_by": payload["superseded_by"],
            "tags": payload["tags"],
            "short_summary": payload["short_summary"],
            "excerpt": payload["excerpt"],
        })

    return results


def print_results(results: list[dict]) -> None:
    """Pretty-print retrieval results to stdout."""
    for r in results:
        stale = " [STALE]" if r["superseded_by"] else ""
        print(f"  #{r['rank']}  {r['doc_id']}  score={r['score']:.4f}  "
              f"role>={r['min_role']}{stale}")
        print(f"       {r['title']}")
        print(f"       {r['short_summary'][:120]}")
        print()


if __name__ == "__main__":
    sample_queries = [
        "What is Meridian's ARR growth rate and revenue projection?",
        "What are the customer concentration risks for Meridian?",
        "What are the proposed deal terms for the Meridian acquisition?",
    ]

    for q in sample_queries:
        print(f"{'='*80}")
        print(f"QUERY: {q}")
        print(f"{'='*80}")
        results = retrieve(q, top_k=8)
        print_results(results)
