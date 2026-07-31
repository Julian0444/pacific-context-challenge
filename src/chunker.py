"""
chunker.py — Paragraph-aware document chunking (Fase 5 Etapa B).

Why: the embedding model reads at most ~512 tokens per input, so embedding
whole documents silently ignores everything past the start. Chunking gives
every part of a document its own FAISS/BM25 row, and the budget packer packs
real chunk content instead of a fixed 500-char teaser.

Algorithm: split on blank-line paragraph boundaries, then greedily merge
consecutive paragraphs until the next one would push the chunk past
TARGET_TOKENS. Oversized paragraphs fall back to sentence splits, and
oversized sentences to hard token windows. Consecutive chunks overlap by
~OVERLAP_RATIO of TARGET_TOKENS (the tail paragraphs of one chunk re-open
the next) so no idea is cut mid-thought at a boundary.

Chunk ids are stable and human-readable: "<doc_id>#c<NN>" (doc_003#c01).
Char offsets refer to the original document text; because of the overlap,
chunk N+1's char_start may be lower than chunk N's char_end.

Token counting uses the same tiktoken encoding as the budget packer, so a
chunk's size here is exactly what it will cost to pack downstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

import tiktoken

TARGET_TOKENS = 350
OVERLAP_RATIO = 0.15

_ENCODING = tiktoken.get_encoding("cl100k_base")

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    chunk_id: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int
    token_count: int


def _count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def _split_units(text: str) -> List[Tuple[int, int, str]]:
    """Split text into (start, end, unit) tuples no larger than TARGET_TOKENS.

    Units are paragraphs; paragraphs over the target are re-split into
    sentences; sentences over the target are hard-split by token windows
    (cl100k round-trips losslessly, so offsets stay exact).
    """
    units: List[Tuple[int, int, str]] = []

    pos = 0
    paragraphs: List[Tuple[int, int]] = []
    for m in _PARAGRAPH_BREAK.finditer(text):
        paragraphs.append((pos, m.start()))
        pos = m.end()
    paragraphs.append((pos, len(text)))

    for p_start, p_end in paragraphs:
        para = text[p_start:p_end]
        if not para.strip():
            continue
        if _count_tokens(para) <= TARGET_TOKENS:
            units.append((p_start, p_end, para))
            continue

        # Paragraph too big → sentences
        s_pos = 0
        sentences: List[Tuple[int, int]] = []
        for m in _SENTENCE_BREAK.finditer(para):
            sentences.append((s_pos, m.start()))
            s_pos = m.end()
        sentences.append((s_pos, len(para)))

        for s_start, s_end in sentences:
            sent = para[s_start:s_end]
            if not sent.strip():
                continue
            if _count_tokens(sent) <= TARGET_TOKENS:
                units.append((p_start + s_start, p_start + s_end, sent))
                continue

            # Sentence too big → hard token windows
            tokens = _ENCODING.encode(sent)
            offset = 0
            for w in range(0, len(tokens), TARGET_TOKENS):
                piece = _ENCODING.decode(tokens[w : w + TARGET_TOKENS])
                units.append((
                    p_start + s_start + offset,
                    p_start + s_start + offset + len(piece),
                    piece,
                ))
                offset += len(piece)

    return units


def chunk_text(doc_id: str, text: str) -> List[Chunk]:
    """Chunk a document into overlapping ~TARGET_TOKENS pieces.

    Every document yields at least one chunk (a short document is exactly
    one chunk covering the whole text). Chunk ids are "<doc_id>#c<NN>",
    numbered from 01 in document order.
    """
    stripped = text.strip()
    if not stripped:
        return []

    units = _split_units(text)
    if not units:
        return []

    overlap_budget = int(TARGET_TOKENS * OVERLAP_RATIO)

    groups: List[List[Tuple[int, int, str]]] = []
    current: List[Tuple[int, int, str]] = []
    current_tokens = 0

    for unit in units:
        unit_tokens = _count_tokens(unit[2])
        if current and current_tokens + unit_tokens > TARGET_TOKENS:
            groups.append(current)
            # Overlap: seed the next chunk with the tail units of this one,
            # newest first, up to the overlap token budget.
            tail: List[Tuple[int, int, str]] = []
            tail_tokens = 0
            for prev in reversed(current):
                pt = _count_tokens(prev[2])
                if tail_tokens + pt > overlap_budget:
                    break
                tail.insert(0, prev)
                tail_tokens += pt
            current = list(tail)
            current_tokens = tail_tokens
        current.append(unit)
        current_tokens += unit_tokens
    if current:
        groups.append(current)

    # A trailing group made only of overlap units duplicates content already
    # emitted — drop it (can happen when the last unit fits into the overlap).
    if len(groups) > 1 and set(groups[-1]) <= set(groups[-2]):
        groups.pop()

    chunks: List[Chunk] = []
    for i, group in enumerate(groups):
        start = group[0][0]
        end = group[-1][1]
        body = text[start:end]
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}#c{i + 1:02d}",
                chunk_index=i,
                text=body,
                char_start=start,
                char_end=end,
                token_count=_count_tokens(body),
            )
        )
    return chunks
