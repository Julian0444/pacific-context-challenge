"""
tests/test_retriever.py — Tests for hybrid (RRF) retrieval.

Demonstrates that BM25 lexical signal materially changes ranking compared
to semantic-only retrieval, and that the retriever interface remains
compatible with RetrieverProtocol.
"""

import json
from pathlib import Path

import pytest
from src.retriever import retrieve, semantic_retrieve, _rrf_fuse, _normalize_scores
from src.protocols import RetrieverProtocol


# ---------------------------------------------------------------------------
# Protocol compatibility
# ---------------------------------------------------------------------------

class TestProtocol:
    def test_retrieve_satisfies_protocol(self):
        """retrieve() is callable as RetrieverProtocol."""
        assert isinstance(retrieve, RetrieverProtocol)

    def test_semantic_retrieve_satisfies_protocol(self):
        """semantic_retrieve() also satisfies RetrieverProtocol."""
        assert isinstance(semantic_retrieve, RetrieverProtocol)


# ---------------------------------------------------------------------------
# Result shape and basic properties
# ---------------------------------------------------------------------------

class TestResultShape:
    REQUIRED_KEYS = {
        "rank", "doc_id", "title", "file_name", "score", "type",
        "date", "min_role", "sensitivity", "superseded_by",
        "tags", "short_summary", "excerpt",
    }

    def test_retrieve_returns_list_of_dicts(self):
        results = retrieve("ARR growth", top_k=3)
        assert isinstance(results, list)
        assert len(results) == 3
        for r in results:
            assert isinstance(r, dict)

    def test_result_has_all_expected_keys(self):
        results = retrieve("financial model", top_k=1)
        assert len(results) >= 1
        assert self.REQUIRED_KEYS.issubset(results[0].keys())

    def test_scores_normalized_to_unit_interval(self):
        """Fused scores should be in [0, 1]."""
        results = retrieve("Meridian acquisition due diligence", top_k=8)
        for r in results:
            assert 0.0 <= r["score"] <= 1.0, f"score {r['score']} out of [0,1]"

    def test_top_result_has_score_one(self):
        """Min-max normalization means the top result gets score 1.0."""
        results = retrieve("Atlas Capital", top_k=5)
        assert results[0]["score"] == pytest.approx(1.0)

    def test_ranks_are_sequential(self):
        results = retrieve("revenue retention", top_k=4)
        for i, r in enumerate(results):
            assert r["rank"] == i + 1

    def test_top_k_clamped_to_corpus_size(self):
        results = retrieve("anything", top_k=999)
        metadata_path = Path(__file__).resolve().parents[1] / "corpus" / "metadata.json"
        with open(metadata_path) as f:
            corpus_size = len(json.load(f)["documents"])
        assert len(results) == corpus_size


# ---------------------------------------------------------------------------
# Hybrid vs semantic: BM25 materially changes ranking
# ---------------------------------------------------------------------------

class TestHybridVsSemantic:
    """Show that the lexical signal from BM25 changes the result ordering."""

    def test_exact_name_query_ranking_differs(self):
        """Query with an exact person name ('Rohan Mehta') — BM25 promotes
        docs that contain the literal string."""
        q = "Rohan Mehta CTO departure integration risk"
        hybrid = [r["doc_id"] for r in retrieve(q, top_k=8)]
        sem = [r["doc_id"] for r in semantic_retrieve(q, top_k=8)]
        assert hybrid != sem, "Hybrid and semantic should differ for exact-name query"

    def test_exact_figure_query_ranking_differs(self):
        """Query with exact financial figures — BM25 favours docs with
        the literal term '$38.1M'."""
        q = "Diana Park customer concentration 38.1M ARR"
        hybrid = [r["doc_id"] for r in retrieve(q, top_k=8)]
        sem = [r["doc_id"] for r in semantic_retrieve(q, top_k=8)]
        assert hybrid != sem, "Hybrid and semantic should differ for exact-figure query"

    def test_bm25_rescues_dd_memo_for_clearwater_risks(self):
        """The DD memo (doc_006) discusses 'Project Clearwater' risks in detail.
        Semantic search may not rank it highly for a name-heavy query, but
        BM25 should promote it because the exact terms match."""
        q = "Rohan Mehta CTO departure integration risk"
        hybrid = [r["doc_id"] for r in retrieve(q, top_k=5)]
        sem = [r["doc_id"] for r in semantic_retrieve(q, top_k=5)]

        # doc_006 (DD memo) should appear in hybrid top-5
        assert "doc_006" in hybrid, (
            f"Expected doc_006 in hybrid top-5, got {hybrid}"
        )
        # And it should rank higher in hybrid than semantic
        if "doc_006" in sem:
            hybrid_rank = hybrid.index("doc_006")
            sem_rank = sem.index("doc_006")
            assert hybrid_rank <= sem_rank, (
                f"doc_006 should rank at least as high in hybrid "
                f"(hybrid={hybrid_rank}, semantic={sem_rank})"
            )

    def test_bm25_promotes_customer_concentration_for_exact_terms(self):
        """doc_012 (customer concentration analysis) contains exact figures
        like '38.1M' and name 'Diana Park'. BM25 should keep it #1 or
        improve its position for an exact-term query."""
        q = "Diana Park customer concentration 38.1M ARR"
        hybrid = retrieve(q, top_k=3)
        # doc_012 should be the top result in hybrid
        assert hybrid[0]["doc_id"] == "doc_012"


# ---------------------------------------------------------------------------
# RRF fusion logic (unit tests with synthetic data)
# ---------------------------------------------------------------------------

class TestRRFFusion:
    def test_rrf_symmetric_for_same_ranking(self):
        """If both retrievers agree, the fused ranking preserves the order."""
        sem = {"a": 1, "b": 2, "c": 3}
        bm25 = {"a": 1, "b": 2, "c": 3}
        fused = _rrf_fuse(sem, bm25, 3)
        ranked = sorted(fused, key=lambda k: fused[k], reverse=True)
        assert ranked == ["a", "b", "c"]

    def test_rrf_present_in_both_beats_one_only(self):
        """A doc present in both rankings (even at low rank) should beat a
        doc present in only one ranking (at high rank), because the missing
        ranking gets the worst-case default rank."""
        sem = {"a": 1}
        bm25 = {"b": 2}
        # a: 1/(60+1) + 1/(60+3)=default  →  1/61 + 1/63 ≈ 0.0322
        # b: 1/(60+3)=default + 1/(60+2)   →  1/63 + 1/62 ≈ 0.0320
        # But a doc in BOTH at modest ranks beats one in only one:
        both = {"a": 1, "b": 2}
        bm25_both = {"a": 2, "b": 1}
        fused = _rrf_fuse(both, bm25_both, 5)
        # c only appears in semantic at rank 3, missing from bm25 → rank 6
        sem_partial = {"a": 1, "b": 2, "c": 3}
        bm25_partial = {"a": 2, "b": 1}
        fused2 = _rrf_fuse(sem_partial, bm25_partial, 5)
        # a and b appear in both → c (only in sem) should be lowest
        ranked = sorted(fused2, key=lambda k: fused2[k], reverse=True)
        assert ranked[-1] == "c"

    def test_rrf_symmetric_swap(self):
        """Swapping ranks between the two systems produces equal RRF scores."""
        sem = {"a": 1, "b": 3}
        bm25 = {"a": 3, "b": 1}
        fused = _rrf_fuse(sem, bm25, 3)
        assert fused["a"] == pytest.approx(fused["b"])

    def test_rrf_deterministic(self):
        """Same inputs produce identical outputs."""
        sem = {"x": 1, "y": 3, "z": 2}
        bm25 = {"x": 2, "y": 1, "z": 3}
        r1 = _rrf_fuse(sem, bm25, 3)
        r2 = _rrf_fuse(sem, bm25, 3)
        assert r1 == r2

    def test_rrf_missing_doc_gets_worst_rank(self):
        """A doc in one ranking but not the other gets default worst rank."""
        sem = {"a": 1}
        bm25 = {"a": 1, "b": 1}
        fused = _rrf_fuse(sem, bm25, 2)
        # b is missing from semantic → gets rank 3 (n_total + 1)
        # a: 1/(60+1) + 1/(60+1) = 2/61
        # b: 1/(60+3) + 1/(60+1) = 1/63 + 1/61
        assert fused["a"] > fused["b"]

    def test_normalize_scores_maps_to_unit_interval(self):
        raw = {"a": 0.05, "b": 0.03, "c": 0.01}
        normed = _normalize_scores(raw)
        assert normed["a"] == pytest.approx(1.0)
        assert normed["c"] == pytest.approx(0.0)
        assert 0.0 < normed["b"] < 1.0

    def test_normalize_scores_handles_equal_scores(self):
        raw = {"a": 0.03, "b": 0.03}
        normed = _normalize_scores(raw)
        assert normed["a"] == pytest.approx(1.0)
        assert normed["b"] == pytest.approx(1.0)

    def test_normalize_scores_empty(self):
        assert _normalize_scores({}) == {}
