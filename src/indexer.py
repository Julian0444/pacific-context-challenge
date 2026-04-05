"""
indexer.py — Loads documents from corpus/documents/, generates sentence embeddings
with all-MiniLM-L6-v2, and builds a FAISS index for semantic retrieval.

Artifacts written to artifacts/:
  - querytrace.index   (FAISS index file)
  - index_documents.json  (ordered doc payloads matching FAISS row order)
"""

import json
import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "corpus", "documents")
METADATA_PATH = os.path.join(os.path.dirname(__file__), "..", "corpus", "metadata.json")
ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "..", "artifacts")
INDEX_PATH = os.path.join(ARTIFACTS_DIR, "querytrace.index")
DOCS_PATH = os.path.join(ARTIFACTS_DIR, "index_documents.json")

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


def build_and_save() -> None:
    """Full pipeline: load docs → embed → build index → save to disk."""
    print(f"Loading documents from {CORPUS_DIR}...")
    docs = load_documents()
    print(f"Loaded {len(docs)} documents.")

    print(f"Embedding with {MODEL_NAME}...")
    index, payloads = build_index(docs)

    save_index(index, payloads)
    print("Done.")


if __name__ == "__main__":
    build_and_save()
