"""
freshness.py — Scores documents by recency relative to the corpus timeline.

Uses corpus-relative dating: age is measured from the newest document in the
corpus, not from the current calendar date. This keeps freshness scores
meaningful regardless of when the eval runs.

Stale documents (superseded_by != null) are demoted with a multiplicative
penalty but remain eligible for retrieval.
"""

import math
from datetime import datetime

STALE_PENALTY = 0.5  # multiplicative penalty for superseded docs


def compute_freshness(
    date_str: str,
    half_life_days: float = 365.0,
    reference_date: str = None,
) -> float:
    """Compute a freshness score in [0, 1] using exponential decay.

    Args:
        date_str: ISO 8601 date string (YYYY-MM-DD) for the document.
        half_life_days: Number of days for the score to decay by half.
        reference_date: The "now" reference point (YYYY-MM-DD). If None,
            uses today. In practice, apply_freshness passes the newest
            corpus date so scores are time-independent.

    Returns:
        A float in [0, 1] where 1.0 means same date as reference.
    """
    doc_date = datetime.strptime(date_str, "%Y-%m-%d")
    if reference_date is not None:
        ref = datetime.strptime(reference_date, "%Y-%m-%d")
    else:
        ref = datetime.now()
    age_days = max((ref - doc_date).days, 0)
    return math.exp(-math.log(2) * age_days / half_life_days)


def apply_freshness(chunks: list, metadata: dict, half_life_days: float = 365.0) -> list:
    """Attach freshness_score to each chunk based on corpus metadata.

    Recency is computed relative to the newest document in the corpus,
    so scores remain meaningful regardless of the current calendar date.
    Stale documents (superseded_by != null) receive an additional penalty.
    """
    meta_by_id = {doc["id"]: doc for doc in metadata["documents"]}

    # Use the newest document date as the reference point
    all_dates = [doc["date"] for doc in metadata["documents"]]
    reference_date = max(all_dates)

    for chunk in chunks:
        doc_meta = meta_by_id.get(chunk["doc_id"])
        if doc_meta is None:
            chunk["freshness_score"] = 0.0
            continue

        score = compute_freshness(doc_meta["date"], half_life_days, reference_date)

        if doc_meta.get("superseded_by"):
            score *= STALE_PENALTY

        chunk["freshness_score"] = score

    return chunks
