"""
freshness_scorer.py — Pure compute stage: corpus-relative freshness scoring.

Scores each document by recency relative to the newest document in the corpus.
Superseded documents receive a multiplicative penalty and are tracked as stale.

No I/O.  No side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.freshness import compute_freshness
from src.models import FreshnessScoredDocument, ScoredDocument, StaleDocument
from src.protocols import MetadataStoreProtocol

# --- Constants ---
STALE_PENALTY = 0.5
DEFAULT_HALF_LIFE_DAYS = 365


@dataclass(frozen=True)
class FreshnessResult:
    scored: List[FreshnessScoredDocument]
    stale: List[StaleDocument]


def score_freshness(
    docs: List[ScoredDocument],
    metadata: MetadataStoreProtocol,
    half_life_days: int = DEFAULT_HALF_LIFE_DAYS,
) -> FreshnessResult:
    """Score documents by corpus-relative recency and flag stale entries.

    Args:
        docs:           Permitted candidates after role filtering.
        metadata:       Raw corpus metadata (dict with "documents" key).
        half_life_days: Exponential decay half-life for freshness scoring.

    Returns:
        FreshnessResult with scored documents and a list of stale entries
        (including superseded_by when applicable).
    """
    meta_by_id = {doc["id"]: doc for doc in metadata["documents"]}
    all_dates = [doc["date"] for doc in metadata["documents"]]
    reference_date = max(all_dates)

    scored: List[FreshnessScoredDocument] = []
    stale: List[StaleDocument] = []

    for doc in docs:
        doc_meta = meta_by_id.get(doc.doc_id)

        if doc_meta is None:
            freshness_score = 0.0
            is_stale = False
            superseded_by = doc.superseded_by
        else:
            freshness_score = compute_freshness(
                doc_meta["date"], half_life_days, reference_date,
            )
            superseded_by = doc_meta.get("superseded_by") or doc.superseded_by
            is_stale = bool(superseded_by)

            if is_stale:
                freshness_score *= STALE_PENALTY

        fd = FreshnessScoredDocument(
            doc_id=doc.doc_id,
            score=doc.score,
            excerpt=doc.excerpt,
            min_role=doc.min_role,
            tags=doc.tags,
            date=doc.date,
            superseded_by=superseded_by,
            title=doc.title,
            short_summary=doc.short_summary,
            sensitivity=doc.sensitivity,
            doc_type=doc.doc_type,
            freshness_score=freshness_score,
            is_stale=is_stale,
        )
        scored.append(fd)

        if is_stale:
            stale.append(
                StaleDocument(
                    doc_id=doc.doc_id,
                    superseded_by=superseded_by,
                    freshness_score=freshness_score,
                    penalty_applied=STALE_PENALTY,
                )
            )

    return FreshnessResult(scored=scored, stale=stale)
