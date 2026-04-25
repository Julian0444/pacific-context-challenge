"""
budget_packer.py — Pure compute stage: token-budget-aware context assembly.

Ranks documents by a 50/50 blend of similarity and freshness scores, then
greedily packs them into the token budget.  Documents that don't fit are
tracked as dropped_by_budget.

No I/O.  No side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import tiktoken

from src.models import DroppedByBudget, FreshnessScoredDocument, IncludedDocument

# --- Constants ---
SIMILARITY_WEIGHT = 0.5
FRESHNESS_WEIGHT = 0.5
DEFAULT_TOKEN_BUDGET = 2048

_ENCODING = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def _combined_score(doc: FreshnessScoredDocument) -> float:
    return SIMILARITY_WEIGHT * doc.score + FRESHNESS_WEIGHT * doc.freshness_score


@dataclass(frozen=True)
class BudgetResult:
    packed: List[IncludedDocument]
    over_budget: List[DroppedByBudget]
    total_tokens: int
    budget_utilization: float


def pack_budget(
    docs: List[FreshnessScoredDocument],
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    enforce_budget: bool = True,
) -> BudgetResult:
    """Rank by combined score and greedily pack within the token budget.

    Args:
        docs:           Freshness-scored candidates.
        token_budget:   Maximum tokens allowed in the assembled context.
        enforce_budget: If False, all docs are packed regardless of budget
                        (dangerous baseline mode).

    Returns:
        BudgetResult with packed documents, over-budget documents,
        total_tokens used, and budget_utilization ratio.
    """
    if not docs:
        return BudgetResult(packed=[], over_budget=[], total_tokens=0, budget_utilization=0.0)

    ranked = sorted(docs, key=_combined_score, reverse=True)

    packed: List[IncludedDocument] = []
    over_budget: List[DroppedByBudget] = []
    total_tokens = 0

    for doc in ranked:
        text = doc.excerpt
        tk = _count_tokens(text)

        if enforce_budget and total_tokens + tk > token_budget:
            over_budget.append(
                DroppedByBudget(
                    doc_id=doc.doc_id,
                    token_count=tk,
                    score=doc.score,
                    freshness_score=doc.freshness_score,
                )
            )
            continue

        packed.append(
            IncludedDocument(
                doc_id=doc.doc_id,
                content=text,
                score=doc.score,
                freshness_score=doc.freshness_score,
                tags=doc.tags,
                token_count=tk,
                title=doc.title,
                doc_type=doc.doc_type,
                date=doc.date,
                superseded_by=doc.superseded_by,
            )
        )
        total_tokens += tk

    utilization = total_tokens / token_budget if token_budget > 0 else 0.0

    return BudgetResult(
        packed=packed,
        over_budget=over_budget,
        total_tokens=total_tokens,
        budget_utilization=round(utilization, 4),
    )
