"""
retriever.py — Hybrid retrieval: semantic (FAISS) + lexical (BM25) with
Reciprocal Rank Fusion (RRF).

Both retrievers rank the full corpus, then RRF merges the two rankings into
a single fused score per document.  The fused scores are min-max normalized
to [0, 1] for downstream compatibility.

Fusion method
-------------
RRF is deterministic, requires no score-distribution normalization, and is
well-suited for combining rankings from different scoring systems.

    RRF_score(d) = 1/(k + rank_semantic(d)) + 1/(k + rank_bm25(d))

k = 60 is the standard constant from Cormack, Clarke & Buettcher (2009).

Reference:
    "Reciprocal Rank Fusion outperforms Condorcet and individual
     Rank Learning Methods" — SIGIR 2009
"""

from typing import Dict, Optional

import numpy as np
from rank_bm25 import BM25Okapi

from src import embedder
from src.indexer import (
    load_persisted_index,
    load_bm25_corpus,
    tokenize_for_bm25,
)
from src.workspaces import get_workspace

# RRF constant — higher k dampens rank differences.
RRF_K = 60

# ---------------------------------------------------------------------------
# Lazy-loaded caches (expensive objects loaded once per process)
# ---------------------------------------------------------------------------

# The embeddings model lives in src.embedder (corpus-independent singleton).
# BM25 depends on the workspace's tokenized corpus → one instance per slug.
_bm25: Dict[str, BM25Okapi] = {}


def _get_bm25(workspace_slug: str) -> BM25Okapi:
    bm25 = _bm25.get(workspace_slug)
    if bm25 is None:
        corpus = load_bm25_corpus(workspace_slug)
        bm25 = BM25Okapi(corpus)
        _bm25[workspace_slug] = bm25
    return bm25


def invalidate_caches(workspace: Optional[str] = None) -> None:
    """Reset in-process caches that depend on a workspace's persisted corpus.

    Call after a workspace's corpus is rebuilt (see src.ingest). Resets only
    the BM25 entry for that slug (all slugs when None); FAISS is re-read from
    disk on every retrieve() call, and the embeddings model is
    corpus-independent and can be kept cached.
    """
    if workspace is None:
        _bm25.clear()
    else:
        _bm25.pop(workspace, None)


# ---------------------------------------------------------------------------
# Internal ranking functions
# ---------------------------------------------------------------------------

def _semantic_ranks(
    query: str,
    index,
    payloads: list[dict],
) -> dict[str, int]:
    """Return {doc_id: 1-based rank} from FAISS cosine similarity."""
    query_vec = embedder.embed([query])

    n = index.ntotal
    scores, indices = index.search(query_vec, n)

    ranks: dict[str, int] = {}
    for rank_0, (idx, _score) in enumerate(zip(indices[0], scores[0])):
        if idx == -1:
            continue
        ranks[payloads[idx]["id"]] = rank_0 + 1
    return ranks


def _bm25_ranks(
    query: str,
    payloads: list[dict],
    workspace_slug: str,
) -> dict[str, int]:
    """Return {doc_id: 1-based rank} from BM25 lexical scoring."""
    bm25 = _get_bm25(workspace_slug)
    tokens = tokenize_for_bm25(query)
    scores = bm25.get_scores(tokens)

    # argsort descending — ties broken by index order (stable)
    ranked_indices = np.argsort(-scores, kind="stable")
    ranks: dict[str, int] = {}
    for rank_0, idx in enumerate(ranked_indices):
        ranks[payloads[idx]["id"]] = rank_0 + 1
    return ranks


def _rrf_fuse(
    semantic: dict[str, int],
    bm25: dict[str, int],
    n_total: int,
) -> dict[str, float]:
    """Combine two rank dicts via Reciprocal Rank Fusion.

    Documents missing from a ranking receive rank = n_total + 1 (worst-case).
    """
    all_docs = set(semantic) | set(bm25)
    default_rank = n_total + 1
    fused: dict[str, float] = {}
    for doc_id in all_docs:
        sem_r = semantic.get(doc_id, default_rank)
        bm25_r = bm25.get(doc_id, default_rank)
        fused[doc_id] = 1.0 / (RRF_K + sem_r) + 1.0 / (RRF_K + bm25_r)
    return fused


def _normalize_scores(fused: dict[str, float]) -> dict[str, float]:
    """Min-max normalize fused RRF scores to [0, 1]."""
    if not fused:
        return fused
    vals = list(fused.values())
    lo, hi = min(vals), max(vals)
    span = hi - lo
    if span == 0:
        return {k: 1.0 for k in fused}
    return {k: (v - lo) / span for k, v in fused.items()}


def _build_results(
    ranked_ids: list[tuple[str, float]],
    payloads: list[dict],
) -> list[dict]:
    """Convert (row_id, score) pairs into the standard result dict format.

    Rows are chunks (Fase 5 Etapa B): `doc_id` is the parent document id
    (what permissions, freshness, evals and citations key on) and `chunk_id`
    identifies the specific chunk. The .get fallbacks keep pre-chunking
    artifacts (one row per doc, id == doc_id) readable.
    """
    by_id = {p["id"]: p for p in payloads}
    results = []
    for rank_0, (row_id, score) in enumerate(ranked_ids):
        p = by_id[row_id]
        results.append({
            "rank": rank_0 + 1,
            "doc_id": p.get("doc_id", p["id"]),
            "chunk_id": p["id"],
            "chunk_index": p.get("chunk_index", 0),
            "chunk_count": p.get("chunk_count", 1),
            "title": p["title"],
            "file_name": p["file_name"],
            "score": float(score),
            "type": p["type"],
            "doc_type": p.get("type"),
            "date": p["date"],
            "min_role": p["min_role"],
            "sensitivity": p["sensitivity"],
            "superseded_by": p["superseded_by"],
            "tags": p["tags"],
            "short_summary": p["short_summary"],
            "excerpt": p["excerpt"],
        })
    return results


# ---------------------------------------------------------------------------
# Public API — both satisfy RetrieverProtocol
# ---------------------------------------------------------------------------

def retrieve(query: str, top_k: int = 8, workspace: Optional[str] = None) -> list[dict]:
    """Hybrid retrieval: semantic + BM25 fused with Reciprocal Rank Fusion.

    Both FAISS and BM25 rank all corpus documents, then RRF merges the two
    rankings.  Fused scores are min-max normalized to [0, 1].

    Args:
        query:     Natural-language search string.
        top_k:     Number of results to return (default 8).
        workspace: Workspace slug (default: the default workspace).

    Returns:
        A list of dicts ranked by fused score, each containing:
            doc_id, title, file_name, score, type, date, min_role,
            tags, short_summary, superseded_by, sensitivity, excerpt
    """
    ws = get_workspace(workspace)
    index, payloads = load_persisted_index(ws)
    n_total = index.ntotal
    top_k = min(top_k, n_total)

    sem = _semantic_ranks(query, index, payloads)
    bm25 = _bm25_ranks(query, payloads, ws.slug)
    fused = _rrf_fuse(sem, bm25, n_total)
    normed = _normalize_scores(fused)

    ranked = sorted(normed.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return _build_results(ranked, payloads)


def semantic_retrieve(query: str, top_k: int = 8, workspace: Optional[str] = None) -> list[dict]:
    """Semantic-only retrieval (FAISS cosine similarity).

    Provided for comparison and backward-compatibility testing.
    Same return shape as retrieve().
    """
    index, payloads = load_persisted_index(get_workspace(workspace))
    n_total = index.ntotal
    top_k = min(top_k, n_total)

    query_vec = embedder.embed([query])

    scores, indices = index.search(query_vec, top_k)

    results = []
    for rank_0, (idx, score) in enumerate(zip(indices[0], scores[0])):
        if idx == -1:
            continue
        p = payloads[idx]
        results.append({
            "rank": rank_0 + 1,
            "doc_id": p.get("doc_id", p["id"]),
            "chunk_id": p["id"],
            "chunk_index": p.get("chunk_index", 0),
            "chunk_count": p.get("chunk_count", 1),
            "title": p["title"],
            "file_name": p["file_name"],
            "score": float(score),
            "type": p["type"],
            "date": p["date"],
            "min_role": p["min_role"],
            "sensitivity": p["sensitivity"],
            "superseded_by": p["superseded_by"],
            "tags": p["tags"],
            "short_summary": p["short_summary"],
            "excerpt": p["excerpt"],
        })
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
        "Rohan Mehta CTO departure integration risk",
    ]

    for q in sample_queries:
        print(f"{'='*80}")
        print(f"QUERY: {q}")
        print(f"{'='*80}")

        print("\n--- Hybrid (RRF) ---")
        results = retrieve(q, top_k=5)
        print_results(results)

        print("--- Semantic only ---")
        sem_results = semantic_retrieve(q, top_k=5)
        print_results(sem_results)
