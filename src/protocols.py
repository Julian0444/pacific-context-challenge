"""
protocols.py — typing.Protocol definitions for external dependencies.

These protocols decouple pipeline stages from concrete implementations,
making each stage independently testable without importing heavy modules
(sentence-transformers, FAISS, etc.).

Usage in pipeline stages:
    from src.protocols import RetrieverProtocol, RoleStoreProtocol
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Protocol, runtime_checkable


@runtime_checkable
class RetrieverProtocol(Protocol):
    """Anything that takes a query + top_k and returns a list of document dicts.

    The current concrete implementation is ``src.retriever.retrieve``.
    A stub or BM25 variant can satisfy this protocol without subclassing.

    Return shape (each dict):
        doc_id, score, excerpt, min_role, tags, date, superseded_by,
        title, short_summary, sensitivity, rank, file_name, type
    """

    def __call__(self, query: str, top_k: int) -> List[Dict]: ...


@runtime_checkable
class RoleStoreProtocol(Protocol):
    """A mapping of role-name → role metadata dict (must include ``access_rank``)."""

    def __getitem__(self, role: str) -> Dict: ...

    def __contains__(self, role: object) -> bool: ...

    def keys(self) -> Iterable[str]: ...


@runtime_checkable
class MetadataStoreProtocol(Protocol):
    """Raw corpus metadata loaded from metadata.json.

    Must support ``metadata["documents"]`` → list of doc dicts.
    Each doc dict has at least: id, date, superseded_by.
    This matches the shape that ``stages.freshness_scorer.score_freshness`` expects.
    """

    def __getitem__(self, key: str) -> Any: ...

    def __contains__(self, key: object) -> bool: ...
