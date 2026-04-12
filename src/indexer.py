"""
indexer.py — Loads documents from corpus/documents/, generates sentence embeddings
with all-MiniLM-L6-v2, builds a FAISS index for semantic retrieval, and builds
a tokenized BM25 corpus for lexical retrieval.

Artifacts written to artifacts/:
  - querytrace.index      (FAISS index file)
  - index_documents.json  (ordered doc payloads matching FAISS row order)
  - bm25_corpus.json      (tokenized document texts for BM25, same row order)
"""

import json
import os
import re
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "corpus", "documents")
METADATA_PATH = os.path.join(os.path.dirname(__file__), "..", "corpus", "metadata.json")
ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "..", "artifacts")
INDEX_PATH = os.path.join(ARTIFACTS_DIR, "querytrace.index")
DOCS_PATH = os.path.join(ARTIFACTS_DIR, "index_documents.json")
BM25_PATH = os.path.join(ARTIFACTS_DIR, "bm25_corpus.json")

MODEL_NAME = "all-MiniLM-L6-v2"


def load_documents() -> list[dict]:
    """Load all corpus documents and merge with metadata.

    Returns a list of dicts, each with keys:
        id, file_name, title, type, date, min_role, sensitivity,
        superseded_by, tags, short_summary, content
    """
    with open(METADATA_PATH, "r") as f:
        metadata = json.load(f)

    docs = []
    for entry in metadata["documents"]:
        file_path = os.path.join(CORPUS_DIR, entry["file_name"])
        if not os.path.exists(file_path):
            raise FileNotFoundError(
                f"Metadata references '{entry['file_name']}' but file not found at {file_path}"
            )
        with open(file_path, "r") as f:
            content = f.read()
        docs.append({**entry, "content": content})

    return docs


def build_index(docs: list[dict]) -> tuple[faiss.IndexFlatIP, list[dict]]:
    """Embed documents and build a FAISS inner-product index.

    Uses cosine similarity (vectors are L2-normalized before indexing).

    Returns:
        (faiss_index, payloads) where payloads[i] corresponds to index row i.
    """
    model = SentenceTransformer(MODEL_NAME)
    texts = [doc["content"] for doc in docs]
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    embeddings = np.array(embeddings, dtype=np.float32)

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    # payload = everything except the full content (kept lightweight)
    payloads = []
    for doc in docs:
        payload = {k: v for k, v in doc.items() if k != "content"}
        # store a short excerpt for display purposes
        payload["excerpt"] = doc["content"][:500]
        payloads.append(payload)

    return index, payloads


def save_index(index: faiss.IndexFlatIP, payloads: list[dict]) -> None:
    """Persist the FAISS index and document payloads to artifacts/."""
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    faiss.write_index(index, INDEX_PATH)
    with open(DOCS_PATH, "w") as f:
        json.dump(payloads, f, indent=2)
    print(f"Saved FAISS index ({index.ntotal} vectors) → {INDEX_PATH}")
    print(f"Saved document payloads → {DOCS_PATH}")


def load_persisted_index() -> tuple[faiss.IndexFlatIP, list[dict]]:
    """Load a previously built index and its payloads from disk."""
    if not os.path.exists(INDEX_PATH):
        raise FileNotFoundError(
            f"No index found at {INDEX_PATH}. Run `python -m src.indexer` to build it."
        )
    index = faiss.read_index(INDEX_PATH)
    with open(DOCS_PATH, "r") as f:
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


def build_bm25_corpus(docs: list[dict]) -> list[list[str]]:
    """Tokenize full document texts for BM25. Same row order as FAISS."""
    return [tokenize_for_bm25(doc["content"]) for doc in docs]


def save_bm25_corpus(tokenized: list[list[str]]) -> None:
    """Persist the tokenized corpus for BM25 retrieval."""
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    with open(BM25_PATH, "w") as f:
        json.dump(tokenized, f)
    print(f"Saved BM25 corpus ({len(tokenized)} documents) → {BM25_PATH}")


def load_bm25_corpus() -> list[list[str]]:
    """Load the persisted tokenized corpus for BM25."""
    if not os.path.exists(BM25_PATH):
        raise FileNotFoundError(
            f"No BM25 corpus at {BM25_PATH}. Run `python -m src.indexer` to build it."
        )
    with open(BM25_PATH) as f:
        return json.load(f)


def build_and_save() -> None:
    """Full pipeline: load docs → embed → build FAISS + BM25 → save to disk."""
    print(f"Loading documents from {CORPUS_DIR}...")
    docs = load_documents()
    print(f"Loaded {len(docs)} documents.")

    print(f"Embedding with {MODEL_NAME}...")
    index, payloads = build_index(docs)
    save_index(index, payloads)

    print("Building BM25 corpus...")
    tokenized = build_bm25_corpus(docs)
    save_bm25_corpus(tokenized)

    print("Done.")


if __name__ == "__main__":
    build_and_save()
