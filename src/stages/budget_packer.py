"""
budget_packer.py — Pure compute stage: token-budget-aware context assembly.

Ranks CHUNKS by a 50/50 blend of similarity and freshness scores, then
greedily packs them under two independent limits (Fase 5 Etapa B, resolves
audit finding H4):

  1. `max_docs` — the request's top_k, redefined as the maximum number of
     UNIQUE PARENT DOCUMENTS in the final context. A chunk whose document
     is already in the context never opens a new document slot; a chunk
     from a new document is dropped once max_docs distinct documents are
     packed. None = uncapped (naive baseline).
  2. `token_budget` — the total token ceiling, as before.

Chunks cut by either limit are tracked as dropped_by_budget.

No I/O.  No side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

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
    max_docs: Optional[int] = None,
) -> BudgetResult:
    """Rank chunks by combined score and greedily pack under both limits.

    Args:
        docs:           Freshness-scored candidate chunks.
        token_budget:   Maximum tokens allowed in the assembled context.
        enforce_budget: If False, all chunks are packed regardless of budget
                        or max_docs (dangerous baseline mode).
        max_docs:       Maximum unique parent documents in the context
                        (the request's top_k — see module docstring / H4).
                        None = no document cap.

    Returns:
        BudgetResult with packed chunks, dropped chunks, total_tokens used,
        and budget_utilization ratio.
    """
    if not docs:
        return BudgetResult(packed=[], over_budget=[], total_tokens=0, budget_utilization=0.0)

    ranked = sorted(docs, key=_combined_score, reverse=True)

    packed: List[IncludedDocument] = []
    over_budget: List[DroppedByBudget] = []
    total_tokens = 0
    packed_doc_ids: set = set()

    for doc in ranked:
        text = doc.excerpt
        tk = _count_tokens(text)

        doc_cap_hit = (
            max_docs is not None
            and doc.doc_id not in packed_doc_ids
            and len(packed_doc_ids) >= max_docs
        )
        if enforce_budget and (doc_cap_hit or total_tokens + tk > token_budget):
            over_budget.append(
                DroppedByBudget(
                    doc_id=doc.doc_id,
                    token_count=tk,
                    score=doc.score,
                    freshness_score=doc.freshness_score,
                    title=doc.title,
                    chunk_id=doc.chunk_id,
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
                chunk_id=doc.chunk_id,
                chunk_index=doc.chunk_index,
                chunk_count=doc.chunk_count,
            )
        )
        total_tokens += tk
        packed_doc_ids.add(doc.doc_id)

    utilization = total_tokens / token_budget if token_budget > 0 else 0.0

    return BudgetResult(
        packed=packed,
        over_budget=over_budget,
        total_tokens=total_tokens,
        budget_utilization=round(utilization, 4),
    )
