"""
context_assembler.py — Takes ranked retrieved chunks and assembles a final context
list for the LLM, respecting a token budget and ordering by combined relevance + freshness.
"""

import tiktoken

ENCODING = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(ENCODING.encode(text))


def _combined_score(chunk: dict) -> float:
    """Combine semantic similarity and freshness into a single ranking score."""
    sim = chunk.get("score", 0.0)
    fresh = chunk.get("freshness_score", 0.0)
    return 0.5 * sim + 0.5 * fresh


def assemble(chunks: list, token_budget: int = 2048) -> tuple:
    """Rank chunks by combined score, then greedily pack within the token budget.

    Returns:
        (context_list, total_token_count) where context_list contains the
        DocumentChunk-shaped dicts that fit within budget, ordered by rank.
    """
    if not chunks:
        return [], 0

    ranked = sorted(chunks, key=_combined_score, reverse=True)

    context = []
    total_tokens = 0

    for chunk in ranked:
        text = chunk.get("content", chunk.get("excerpt", ""))
        chunk_tokens = _count_tokens(text)

        if total_tokens + chunk_tokens > token_budget:
            continue

        context.append({
            "doc_id": chunk["doc_id"],
            "content": text,
            "score": chunk.get("score", 0.0),
            "freshness_score": chunk.get("freshness_score"),
            "tags": chunk.get("tags", []),
        })
        total_tokens += chunk_tokens

    return context, total_tokens
