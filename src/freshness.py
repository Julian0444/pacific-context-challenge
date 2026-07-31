"""
freshness.py — Scores documents by recency relative to the corpus timeline.

Uses corpus-relative dating: age is measured from the newest document in the
corpus, not from the current calendar date. This keeps freshness scores
meaningful regardless of when the eval runs.

Stale-document demotion lives in stages/freshness_scorer.py, which calls
compute_freshness() and applies the superseded penalty.
"""

import math
from datetime import datetime


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
            uses today. In practice, the stages layer passes the newest
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
