"""Tests for src/chunker.py (Fase 5 Etapa B)."""

import tiktoken

from src.chunker import TARGET_TOKENS, chunk_text

_ENC = tiktoken.get_encoding("cl100k_base")


def _tokens(text):
    return len(_ENC.encode(text))


PARA = (
    "Quarterly revenue grew forty percent year over year while churn cohorts "
    "improved and the infrastructure migration stayed on budget across every "
    "region the company operates in today."
)


def make_doc(n_paragraphs):
    return "\n\n".join(f"Paragraph {i}. {PARA}" for i in range(n_paragraphs))


class TestShortDocuments:
    def test_short_doc_is_single_chunk(self):
        text = make_doc(2)
        chunks = chunk_text("doc_001", text)
        assert len(chunks) == 1
        c = chunks[0]
        assert c.chunk_id == "doc_001#c01"
        assert c.chunk_index == 0
        assert c.text == text
        assert (c.char_start, c.char_end) == (0, len(text))

    def test_empty_and_whitespace_docs_yield_no_chunks(self):
        assert chunk_text("doc_001", "") == []
        assert chunk_text("doc_001", "   \n\n  ") == []


class TestLongDocuments:
    def test_long_doc_splits_into_multiple_chunks(self):
        chunks = chunk_text("doc_002", make_doc(40))
        assert len(chunks) > 1

    def test_every_chunk_within_target(self):
        for c in chunk_text("doc_002", make_doc(40)):
            # target + overlap seed is the worst case for a merged chunk
            assert c.token_count <= TARGET_TOKENS + int(TARGET_TOKENS * 0.15) + 5

    def test_ids_are_stable_and_ordered(self):
        chunks = chunk_text("doc_002", make_doc(40))
        assert [c.chunk_id for c in chunks] == [
            f"doc_002#c{i + 1:02d}" for i in range(len(chunks))
        ]
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_chunking_is_deterministic(self):
        text = make_doc(40)
        assert chunk_text("doc_002", text) == chunk_text("doc_002", text)

    def test_offsets_point_into_original_text(self):
        text = make_doc(40)
        for c in chunk_text("doc_002", text):
            assert text[c.char_start : c.char_end] == c.text

    def test_consecutive_chunks_overlap(self):
        text = make_doc(40)
        chunks = chunk_text("doc_002", text)
        for prev, nxt in zip(chunks, chunks[1:]):
            # the next chunk starts before the previous one ends (~15% overlap)
            assert nxt.char_start < prev.char_end

    def test_full_coverage_no_gaps(self):
        text = make_doc(40)
        chunks = chunk_text("doc_002", text)
        covered_end = chunks[0].char_end
        for c in chunks[1:]:
            assert c.char_start <= covered_end  # no gap
            covered_end = max(covered_end, c.char_end)
        assert chunks[0].char_start == 0
        assert covered_end == len(text)


class TestDegenerateInputs:
    def test_giant_single_paragraph_falls_back_to_sentences(self):
        text = " ".join(PARA for _ in range(30))  # one paragraph, ~900 tokens
        chunks = chunk_text("doc_003", text)
        assert len(chunks) > 1
        for c in chunks:
            assert text[c.char_start : c.char_end] == c.text

    def test_giant_single_sentence_hard_splits(self):
        text = "word " * 3000  # no sentence breaks, ~3000 tokens
        chunks = chunk_text("doc_004", text)
        assert len(chunks) > 1
        for c in chunks:
            assert c.token_count <= TARGET_TOKENS + int(TARGET_TOKENS * 0.15) + 5

    def test_real_corpus_doc_chunks_cleanly(self):
        import glob

        path = sorted(glob.glob("corpora/pe-deal/documents/*.txt"))[0]
        text = open(path).read()
        chunks = chunk_text("doc_001", text)
        assert chunks, "real doc must yield at least one chunk"
        for c in chunks:
            assert text[c.char_start : c.char_end] == c.text
