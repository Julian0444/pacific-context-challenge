"""Tests for context_assembler.py — token-budgeted context assembly.

LEGACY: assemble() is no longer on the request path.  Budget packing is now
handled by src/stages/budget_packer.py (pack_budget), which is tested in
tests/test_stages.py::TestBudgetPacker.  These tests are retained as
documentation of the old dict-based API but are skipped to avoid misleading
confidence in dead code.
"""

import pytest
from src.context_assembler import assemble

pytestmark = pytest.mark.skip(
    reason="legacy: assemble() replaced by stages/budget_packer.py on all request paths"
)


def _make_chunk(doc_id, content="Short content.", score=0.9, freshness_score=0.8, tags=None):
    return {
        "doc_id": doc_id,
        "content": content,
        "score": score,
        "freshness_score": freshness_score,
        "tags": tags or [],
    }


def test_assemble_returns_list_and_token_count():
    chunks = [_make_chunk("d1")]
    context, total_tokens = assemble(chunks, token_budget=2048)
    assert isinstance(context, list)
    assert isinstance(total_tokens, int)
    assert total_tokens > 0


def test_assemble_respects_token_budget():
    # Create chunks with long content that will exceed a small budget
    long_text = "word " * 500  # ~500 tokens
    chunks = [
        _make_chunk("d1", content=long_text, score=0.95, freshness_score=0.9),
        _make_chunk("d2", content=long_text, score=0.90, freshness_score=0.8),
        _make_chunk("d3", content=long_text, score=0.85, freshness_score=0.7),
    ]
    context, total_tokens = assemble(chunks, token_budget=600)
    assert total_tokens <= 600
    # Should include at most 1 chunk with 600 budget (each ~500 tokens)
    assert len(context) <= 2


def test_assemble_ranks_by_combined_score():
    chunks = [
        _make_chunk("low", score=0.5, freshness_score=0.5),
        _make_chunk("high", score=0.95, freshness_score=0.95),
    ]
    context, _ = assemble(chunks, token_budget=2048)
    # Higher combined score should come first
    assert context[0]["doc_id"] == "high"


def test_assemble_empty_chunks():
    context, total_tokens = assemble([], token_budget=2048)
    assert context == []
    assert total_tokens == 0


def test_assemble_prefers_fresh_over_stale():
    chunks = [
        _make_chunk("stale", score=0.92, freshness_score=0.3),
        _make_chunk("fresh", score=0.90, freshness_score=0.9),
    ]
    context, _ = assemble(chunks, token_budget=2048)
    # fresh should rank higher due to better combined score
    assert context[0]["doc_id"] == "fresh"
