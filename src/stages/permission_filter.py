"""
permission_filter.py — Pure compute stage: role-based access control.

Compares the requesting user's access_rank against each document's min_role
rank.  Documents the user cannot see are separated into a blocked list with
explicit reasons and structured fields.

No I/O.  No side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.models import BlockedDocument, ScoredDocument, UserContext
from src.protocols import RoleStoreProtocol


@dataclass(frozen=True)
class PermissionResult:
    permitted: List[ScoredDocument]
    blocked: List[BlockedDocument]


def filter_permissions(
    docs: List[ScoredDocument],
    user_ctx: UserContext,
    roles: RoleStoreProtocol,
) -> PermissionResult:
    """Partition documents into permitted and blocked based on role rank.

    Args:
        docs:     Scored candidates from the retriever.
        user_ctx: The requesting user's role and access_rank.
        roles:    Role store mapping role names to metadata with access_rank.

    Returns:
        PermissionResult with permitted and blocked lists.
    """
    permitted: List[ScoredDocument] = []
    blocked: List[BlockedDocument] = []

    for doc in docs:
        try:
            doc_role_meta = roles[doc.min_role]
        except KeyError:
            # Unknown min_role — block this doc rather than aborting the pipeline
            blocked.append(
                BlockedDocument(
                    doc_id=doc.doc_id,
                    reason="unknown_min_role",
                    required_role=doc.min_role,
                    user_role=user_ctx.role,
                )
            )
            continue

        doc_rank = doc_role_meta["access_rank"]

        if doc_rank <= user_ctx.access_rank:
            permitted.append(doc)
        else:
            blocked.append(
                BlockedDocument(
                    doc_id=doc.doc_id,
                    reason="insufficient_role",
                    required_role=doc.min_role,
                    user_role=user_ctx.role,
                )
            )

    return PermissionResult(permitted=permitted, blocked=blocked)
