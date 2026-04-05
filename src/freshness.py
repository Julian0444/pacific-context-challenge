"""
freshness.py — Scores documents by recency using their date metadata field.
Fresher documents receive higher scores. Stale documents (superseded_by != null)
are demoted but not removed.
"""

import math
from datetime import datetime

STALE_PENALTY = 0.5  # multiplicative penalty for superseded docs


def compute_freshness(date_str: str, half_life_days: float = 30.0) -> float:
    """Compute a freshness score in [0, 1] using exponential decay.

    Args:
        date_str: ISO 8601 date string (YYYY-MM-DD).
        half_life_days: Number of days for the score to decay by half.

    Returns:
        A float in [0, 1] where 1.0 means today.
    """
    doc_date = datetime.strptime(date_str, "%Y-%m-%d")
    age_days = max((datetime.now() - doc_date).days, 0)
    return math.exp(-math.log(2) * age_days / half_life_days)


def apply_freshness(chunks: list, metadata: dict, half_life_days: float = 30.0) -> list:
    """Attach freshness_score to each chunk based on corpus metadata.

    Stale documents (superseded_by != null) receive an additional penalty.
    Chunks are returned in their original order.
    """
    meta_by_id = {doc["id"]: doc for doc in metadata["documents"]}

    for chunk in chunks:
        doc_meta = meta_by_id.get(chunk["doc_id"])
        if doc_meta is None:
            chunk["freshness_score"] = 0.0
            continue

        score = compute_freshness(doc_meta["date"], half_life_days)

        if doc_meta.get("superseded_by"):
            score *= STALE_PENALTY

        chunk["freshness_score"] = score

    return chunks
