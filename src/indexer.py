"""
indexer.py — Loads documents from corpora/<slug>/documents/, chunks them
(~350-token paragraph-aware chunks, src/chunker.py), embeds each chunk with
all-MiniLM-L6-v2 (ONNX via src/embedder.py), builds a FAISS index for semantic
retrieval, and builds a tokenized BM25 corpus for lexical retrieval.
One FAISS/BM25 row per CHUNK since Fase 5 Etapa B.

Artifacts are written per workspace to artifacts/<slug>/:
  - querytrace.index      (FAISS index file)
  - index_documents.json  (ordered doc payloads matching FAISS row order)
  - bm25_corpus.json      (tokenized document texts for BM25, same row order)

CLI:
  python -m src.indexer                      # rebuild every workspace
  python -m src.indexer --workspace pe-deal  # rebuild one workspace
"""

import argparse
import json
import os
import re
from typing import Optional, Union

import numpy as np
import faiss

from src.embedder import MODEL_NAME  # noqa: F401  (re-exported; retriever imports it here)
from src.workspaces import Workspace, get_workspace, list_workspaces

# Functions below accept a workspace slug, an already-resolved Workspace,
# or None (→ the default workspace).
WorkspaceRef = Optional[Union[str, Workspace]]


def _resolve(workspace: WorkspaceRef = None) -> Workspace:
    """Accept a slug, a Workspace, or None (default workspace) and resolve it."""
    if isinstance(workspace, Workspace):
        return workspace
    return get_workspace(workspace)


def _atomic_write_json(path: str, obj, **dump_kwargs) -> None:
    """Write JSON via a same-directory .tmp file + os.replace.

    Readers (retriever reloads artifacts per request) never observe a
    half-written file, and a crash mid-write leaves the previous version
    intact instead of a truncated file.
    """
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(obj, f, **dump_kwargs)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_documents(workspace: WorkspaceRef = None) -> list[dict]:
    """Load a workspace's documents and merge with its metadata.

    Returns a list of dicts, each with keys:
        id, file_name, title, type, date, min_role, sensitivity,
        superseded_by, tags, short_summary, content
    """
    ws = _resolve(workspace)
    docs = []
    for entry in ws.metadata["documents"]:
        file_path = os.path.join(ws.documents_dir, entry["file_name"])
        if not os.path.exists(file_path):
            raise FileNotFoundError(
                f"Metadata references '{entry['file_name']}' but file not found at {file_path}"
            )
        with open(file_path, "r") as f:
            content = f.read()
        docs.append({**entry, "content": content})

    return docs


def _embed_texts(texts: list, show_progress_bar: bool = False) -> np.ndarray:
    """Embed texts via the shared embedder singleton (L2-normalized, float32).

    Thin wrapper around src.embedder.embed — kept as a module-level seam so
    tests can fake embeddings without loading the ONNX model.
    `show_progress_bar` is accepted for signature compatibility (fastembed
    has no progress bar; corpora are small enough not to need one).
    """
    from src import embedder

    return embedder.embed(texts)


def _chunk_payloads(doc: dict) -> list[dict]:
    """Chunk one document into per-chunk payload rows (Fase 5 Etapa B).

    Each row inherits the parent document's metadata (min_role, date,
    superseded_by, tags, ...) and carries the chunk's full text as the
    packable content. `id` is the unique row key (the chunk id); `doc_id`
    is the parent document — every downstream stage keys permissions,
    freshness and evals on `doc_id`.
    """
    from src.chunker import chunk_text

    rows = []
    chunks = chunk_text(doc["id"], doc["content"])
    for chunk in chunks:
        payload = {k: v for k, v in doc.items() if k != "content"}
        payload["id"] = chunk.chunk_id
        payload["doc_id"] = chunk.doc_id
        payload["chunk_index"] = chunk.chunk_index
        payload["chunk_count"] = len(chunks)
        payload["char_start"] = chunk.char_start
        payload["char_end"] = chunk.char_end
        # Full chunk text — this is what the budget packer packs and the
        # Ask prompt embeds (replaces the old 500-char display excerpt).
        payload["excerpt"] = chunk.text
        rows.append(payload)
    return rows


def build_index(docs: list[dict]) -> tuple[faiss.IndexFlatIP, list[dict]]:
    """Chunk + embed documents and build a FAISS inner-product index.

    One index row per CHUNK (not per document) since Fase 5 Etapa B.
    Uses cosine similarity (vectors are L2-normalized before indexing).

    Returns:
        (faiss_index, payloads) where payloads[i] corresponds to index row i.
    """
    payloads = []
    for doc in docs:
        payloads.extend(_chunk_payloads(doc))

    embeddings = _embed_texts([p["excerpt"] for p in payloads], show_progress_bar=True)

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    return index, payloads


def save_index(
    index: faiss.IndexFlatIP,
    payloads: list[dict],
    workspace: WorkspaceRef = None,
) -> None:
    """Persist the FAISS index and document payloads to artifacts/<slug>/.

    Both writes are atomic (tmp + os.replace). Payloads are written before
    the FAISS index so a concurrent reader never sees a new index paired
    with missing payloads; the residual window (new payloads + old index)
    lasts one os.replace and is documented as a known limitation of the
    single-file-pair layout.
    """
    ws = _resolve(workspace)
    os.makedirs(ws.artifacts_dir, exist_ok=True)
    _atomic_write_json(ws.index_docs_path, payloads, indent=2)
    tmp_index = f"{ws.index_path}.tmp"
    try:
        faiss.write_index(index, tmp_index)
        os.replace(tmp_index, ws.index_path)
    except BaseException:
        if os.path.exists(tmp_index):
            os.remove(tmp_index)
        raise
    print(f"Saved FAISS index ({index.ntotal} vectors) → {ws.index_path}")
    print(f"Saved document payloads → {ws.index_docs_path}")


def load_persisted_index(
    workspace: WorkspaceRef = None,
) -> tuple[faiss.IndexFlatIP, list[dict]]:
    """Load a workspace's previously built index and payloads from disk."""
    ws = _resolve(workspace)
    if not os.path.exists(ws.index_path):
        raise FileNotFoundError(
            f"No index found at {ws.index_path}. "
            f"Run `python -m src.indexer --workspace {ws.slug}` to build it."
        )
    index = faiss.read_index(ws.index_path)
    with open(ws.index_docs_path, "r") as f:
        payloads = json.load(f)
    return index, payloads


# ---------------------------------------------------------------------------
# BM25 corpus
# ---------------------------------------------------------------------------

_BM25_STOPWORDS = frozenset(
    "a an and are as at be but by do did does for from had has have he her "
    "his how i if in into is it its just me my no nor not of on or our out "
    "own s she so some such t than that the their them then there these they "
    "this those through to too under up very was we were what when where "
    "which while who whom why will with would you your".split()
)


def tokenize_for_bm25(text: str) -> list[str]:
    """Tokenize text for BM25: lowercase, stopword-filtered, min length 2.

    Stopword removal prevents corpus-common function words from dominating
    BM25 scoring in small corpora where IDF is noisy.
    """
    return [
        t
        for t in re.findall(r"[a-zA-Z0-9]+", text.lower())
        if len(t) >= 2 and t not in _BM25_STOPWORDS
    ]


def build_bm25_corpus(payloads: list[dict]) -> list[list[str]]:
    """Tokenize chunk texts for BM25. Same row order as the FAISS payloads."""
    return [tokenize_for_bm25(p["excerpt"]) for p in payloads]


def save_bm25_corpus(tokenized: list[list[str]], workspace: WorkspaceRef = None) -> None:
    """Persist the tokenized corpus for BM25 retrieval (atomic write)."""
    ws = _resolve(workspace)
    os.makedirs(ws.artifacts_dir, exist_ok=True)
    _atomic_write_json(ws.bm25_path, tokenized)
    print(f"Saved BM25 corpus ({len(tokenized)} documents) → {ws.bm25_path}")


def load_bm25_corpus(workspace: WorkspaceRef = None) -> list[list[str]]:
    """Load a workspace's persisted tokenized corpus for BM25."""
    ws = _resolve(workspace)
    if not os.path.exists(ws.bm25_path):
        raise FileNotFoundError(
            f"No BM25 corpus at {ws.bm25_path}. "
            f"Run `python -m src.indexer --workspace {ws.slug}` to build it."
        )
    with open(ws.bm25_path) as f:
        return json.load(f)


def build_and_save(workspace: WorkspaceRef = None, on_stage=None) -> None:
    """Full pipeline for one workspace: load docs → embed → build FAISS + BM25 → save.

    `on_stage`, when given, is called with 'embedding' before the model runs
    and 'indexing' before artifacts are written — the ingest job store uses
    it to report real progress states.
    """
    ws = _resolve(workspace)
    print(f"[{ws.slug}] Loading documents from {ws.documents_dir}...")
    docs = load_documents(ws)
    print(f"[{ws.slug}] Loaded {len(docs)} documents.")

    # BM25 + payloads are written before the FAISS index (see save_index)
    # so the index — the artifact the retriever reads first — lands last.
    if on_stage is not None:
        on_stage("embedding")
    print(f"[{ws.slug}] Chunking + embedding with {MODEL_NAME}...")
    index, payloads = build_index(docs)

    print(f"[{ws.slug}] Building BM25 corpus ({len(payloads)} chunks)...")
    tokenized = build_bm25_corpus(payloads)

    if on_stage is not None:
        on_stage("indexing")
    save_bm25_corpus(tokenized, ws)
    save_index(index, payloads, ws)

    print(f"[{ws.slug}] Done.")


def add_document(
    workspace: WorkspaceRef, entry: dict, text: str, on_stage=None
) -> None:
    """Incrementally add ONE document to a workspace's artifacts — O(1) in
    corpus size instead of the O(N) full rebuild (Fase 3 Etapa C).

    Embeds only the new document, appends to the loaded FAISS index, appends
    the payload and the BM25 token row (existing rows are unchanged by a new
    document, so appending is equivalent to re-tokenizing the corpus), and
    rewrites the three artifacts atomically (index last, as in save_index).

    Falls back to a defensive full build_and_save() when artifacts are
    missing or drift is detected (row counts disagree). Edits/deletions
    remain full-rebuild territory: IndexFlatIP has no cheap remove without an
    IDMap (IndexIDMap is the upgrade path).
    """
    ws = _resolve(workspace)
    try:
        index, payloads = load_persisted_index(ws)
        tokenized = load_bm25_corpus(ws)
    except FileNotFoundError:
        print(f"[{ws.slug}] Artifacts missing — falling back to a full rebuild.")
        build_and_save(ws, on_stage=on_stage)
        return
    if index.ntotal != len(payloads) or len(tokenized) != len(payloads):
        print(
            f"[{ws.slug}] Artifact drift detected "
            f"(index={index.ntotal}, payloads={len(payloads)}, bm25={len(tokenized)}) "
            f"— falling back to a full rebuild."
        )
        build_and_save(ws, on_stage=on_stage)
        return

    if on_stage is not None:
        on_stage("embedding")
    new_rows = _chunk_payloads({**entry, "content": text})
    index.add(_embed_texts([r["excerpt"] for r in new_rows]))

    payloads.extend(new_rows)
    tokenized.extend(tokenize_for_bm25(r["excerpt"]) for r in new_rows)

    if on_stage is not None:
        on_stage("indexing")
    save_bm25_corpus(tokenized, ws)
    save_index(index, payloads, ws)
    print(
        f"[{ws.slug}] Incrementally indexed {entry.get('id')} "
        f"({len(new_rows)} chunks, {index.ntotal} rows)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build QueryTrace index artifacts")
    parser.add_argument(
        "--workspace",
        default=None,
        help="Workspace slug to index (default: all workspaces under corpora/)",
    )
    args = parser.parse_args()

    if args.workspace is not None:
        build_and_save(args.workspace)
        return

    workspaces = list_workspaces()
    if not workspaces:
        raise SystemExit("No workspaces found under corpora/ — nothing to index.")
    for summary in workspaces:
        build_and_save(summary["slug"])


if __name__ == "__main__":
    main()
