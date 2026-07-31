"""Chunking integration tests (Fase 5 Etapa B).

Covers the plan's required assertions: metadata inheritance from parent
docs, top_k as a unique-document cap (H4), the chunk-level trace accounting
invariant, and doc-level dedup in the evaluator's assembled ids.
"""

from functools import partial

from src.indexer import _chunk_payloads
from src.models import FreshnessScoredDocument, QueryRequest
from src.pipeline import run_pipeline
from src.retriever import retrieve
from src.stages.budget_packer import pack_budget
from src.workspaces import get_workspace


# ---------------------------------------------------------------------------
# Metadata inheritance
# ---------------------------------------------------------------------------

LONG_CONTENT = "\n\n".join(
    f"Paragraph {i}. " + ("Revenue grew and churn improved across regions. " * 12)
    for i in range(12)
)

DOC = {
    "id": "doc_042",
    "file_name": "x.txt",
    "title": "Long Doc",
    "type": "board_memo",
    "date": "2024-03-01",
    "min_role": "vp",
    "sensitivity": "high",
    "superseded_by": "doc_043",
    "tags": ["a", "b"],
    "short_summary": "s",
    "content": LONG_CONTENT,
}


class TestChunkPayloadInheritance:
    def test_every_chunk_inherits_parent_metadata(self):
        rows = _chunk_payloads(DOC)
        assert len(rows) > 1, "fixture doc must produce multiple chunks"
        for row in rows:
            assert row["doc_id"] == "doc_042"
            assert row["min_role"] == "vp"
            assert row["date"] == "2024-03-01"
            assert row["superseded_by"] == "doc_043"
            assert row["tags"] == ["a", "b"]
            assert "content" not in row

    def test_chunk_rows_have_identity_and_text(self):
        rows = _chunk_payloads(DOC)
        assert [r["id"] for r in rows] == [
            f"doc_042#c{i + 1:02d}" for i in range(len(rows))
        ]
        assert all(r["chunk_count"] == len(rows) for r in rows)
        assert all(r["excerpt"].strip() for r in rows)


# ---------------------------------------------------------------------------
# top_k = unique-document cap (H4)
# ---------------------------------------------------------------------------

def _chunk(doc_id, chunk_index, score, tokens=10):
    return FreshnessScoredDocument(
        doc_id=doc_id,
        score=score,
        excerpt="word " * tokens,
        min_role="analyst",
        freshness_score=score,
        chunk_id=f"{doc_id}#c{chunk_index + 1:02d}",
        chunk_index=chunk_index,
        chunk_count=9,
    )


class TestTopKDocCap:
    def test_max_docs_caps_unique_documents_not_chunks(self):
        docs = [
            _chunk("doc_001", 0, 0.9),
            _chunk("doc_001", 1, 0.8),
            _chunk("doc_002", 0, 0.7),
            _chunk("doc_003", 0, 0.6),
        ]
        result = pack_budget(docs, token_budget=10_000, max_docs=2)
        packed_docs = {d.doc_id for d in result.packed}
        assert packed_docs == {"doc_001", "doc_002"}
        # both doc_001 chunks fit — the cap counts documents, not chunks
        assert len(result.packed) == 3
        assert [d.doc_id for d in result.over_budget] == ["doc_003"]

    def test_chunk_of_already_packed_doc_passes_after_cap(self):
        docs = [
            _chunk("doc_001", 0, 0.9),
            _chunk("doc_002", 0, 0.8),
            _chunk("doc_001", 1, 0.7),  # cap reached, but doc_001 already in
        ]
        result = pack_budget(docs, token_budget=10_000, max_docs=2)
        assert len(result.packed) == 3
        assert result.over_budget == []

    def test_no_cap_when_max_docs_none(self):
        docs = [_chunk(f"doc_{i:03d}", 0, 0.5) for i in range(8)]
        result = pack_budget(docs, token_budget=10_000, max_docs=None)
        assert len(result.packed) == 8

    def test_cap_not_enforced_in_naive_mode(self):
        docs = [_chunk(f"doc_{i:03d}", 0, 0.5) for i in range(8)]
        result = pack_budget(docs, token_budget=1, enforce_budget=False, max_docs=2)
        assert len(result.packed) == 8


# ---------------------------------------------------------------------------
# Pipeline-level: trace accounting + doc counts with the real corpus
# ---------------------------------------------------------------------------

def _run(role="analyst", policy="full_policy", top_k=5):
    ws = get_workspace("pe-deal")
    request = QueryRequest(
        query="What is the IC recommendation for the Meridian acquisition?",
        role=role,
        top_k=top_k,
        policy_name=policy,
    )
    retriever = partial(retrieve, workspace=ws.slug)
    return run_pipeline(request, retriever, ws.roles, ws.metadata)


class TestChunkTraceInvariant:
    def test_accounting_counts_chunks(self):
        result = _run()
        m = result.trace.metrics
        # retrieved = 3 × top_k chunk rows (corpus permitting)
        assert m.blocked_count + m.included_count + m.dropped_count == m.retrieved_count
        assert m.included_count == len(result.trace.included)

    def test_doc_counts_are_derived_and_bounded(self):
        result = _run()
        m = result.trace.metrics
        assert m.included_doc_count == len({d.doc_id for d in result.trace.included})
        assert m.included_doc_count <= m.included_count
        assert m.blocked_doc_count <= m.blocked_count

    def test_top_k_bounds_unique_docs_in_context(self):
        result = _run(role="partner", top_k=3)
        unique_docs = {d.doc_id for d in result.context}
        assert len(unique_docs) <= 3

    def test_included_chunks_carry_chunk_identity(self):
        result = _run(role="partner")
        for item in result.context:
            assert item.chunk_id and item.chunk_id.startswith(item.doc_id + "#c")


# ---------------------------------------------------------------------------
# Deep-content retrieval — the point of chunking
# ---------------------------------------------------------------------------

class TestDeepContentRetrieval:
    """Queries targeting the END of long documents. Pre-chunking, this text
    was beyond the embedder's truncation window and semantically invisible
    (only BM25 could see it). With per-chunk rows the tail is retrievable.

    Honest note (also in the README): a third probe — doc_010's closing
    'APPROVE for final negotiation' — still loses to its near-duplicate
    draft memo doc_014 at doc rank ~7; chunking does not resolve
    near-duplicate confusion, the stale-pair demotion does.
    """

    def test_tail_only_covenant_language_found(self):
        q = ("revenue concentration covenant in the deal terms, "
             "no single customer above 25% of ARR")
        docs = list(dict.fromkeys(r["doc_id"] for r in retrieve(q, top_k=10)))
        assert docs.index("doc_012") <= 2

    def test_tail_only_media_contact_found(self):
        q = "who is the media contact for Meridian press inquiries"
        docs = list(dict.fromkeys(r["doc_id"] for r in retrieve(q, top_k=10)))
        assert docs.index("doc_004") <= 2
        # and it is a LATE chunk that matches, not the document head
        rows = [r for r in retrieve(q, top_k=10) if r["doc_id"] == "doc_004"]
        assert any(r["chunk_index"] > 0 for r in rows)


# ---------------------------------------------------------------------------
# Evaluator dedups chunks to parent docs
# ---------------------------------------------------------------------------

class TestEvaluatorDedup:
    def test_assembled_ids_are_unique_parent_docs(self):
        from src.evaluator import load_test_queries, run_evals

        ws = get_workspace("pe-deal")
        queries = load_test_queries(ws.evals_path)[:3]
        report = run_evals(queries, k=5, top_k=8, workspace="pe-deal")
        for row in report["per_query"]:
            ids = row["assembled_ids"]
            assert len(ids) == len(set(ids)), f"duplicate doc in {row['id']}: {ids}"
            assert all("#" not in did for did in ids), "chunk ids leaked into evals"
