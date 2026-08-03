"""
embedder.py — minimal embedding interface for the whole pipeline (Fase 5 Etapa A).

Single entry point: embed(texts) -> np.ndarray of L2-normalized float32
vectors, shape (len(texts), EMBEDDING_DIM). Everything else in the codebase
(indexer, retriever) goes through this module and never imports the inference
runtime directly, so the runtime can be swapped without touching callers.

Current implementation: fastembed (ONNX Runtime) running the fp32 ONNX export
of all-MiniLM-L6-v2 (source repo: qdrant/all-MiniLM-L6-v2-onnx, model.onnx —
fastembed's default variant for this model id, verified fp32 not int8).
Replaces the previous sentence-transformers/torch stack (~500 MB of deps)
with ~50 MB of onnxruntime.

Runtime note: the ONNX tokenizer truncates at 512 tokens vs 256 under
sentence-transformers, so on documents longer than 256 tokens the vectors
are not bit-identical to the torch ones (the ONNX model sees *more* of the
document). Retrieval quality is gated by the eval harness, not by vector
equality — see plansToPortfolio/fase-5-retrieval-depth.md Etapa A.
"""

import os
from pathlib import Path
from typing import Any, Sequence

import numpy as np

# Full model id as fastembed knows it. The short "all-MiniLM-L6-v2" alias used
# by sentence-transformers is not a registered fastembed id.
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# Lazy singleton — the model is corpus-independent and loads once per process.
_model: Any = None


def _cache_dir() -> str:
    """Persistent model cache location.

    fastembed's default is <tempdir>/fastembed_cache, which macOS (and most
    hosts) periodically purge — leaving a half-deleted snapshot that fails
    with ONNXRuntimeError NO_SUCHFILE instead of re-downloading. Cache under
    the user's home instead; FASTEMBED_CACHE_PATH still wins when set.
    """
    path = os.environ.get("FASTEMBED_CACHE_PATH") or str(
        Path.home() / ".cache" / "querytrace" / "fastembed"
    )
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def _get_model() -> Any:
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding(MODEL_NAME, cache_dir=_cache_dir())
    return _model


def embed(texts: Sequence[str]) -> np.ndarray:
    """Embed texts into L2-normalized float32 vectors.

    Contract (relied on by indexer and retriever):
      - shape (len(texts), EMBEDDING_DIM), dtype float32
      - every row has unit L2 norm (FAISS IndexFlatIP == cosine similarity)
      - deterministic for identical input
      - empty input -> shape (0, EMBEDDING_DIM)
    """
    if not texts:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    vectors = np.array(list(_get_model().embed(list(texts))), dtype=np.float32)
    # fastembed already normalizes for this model; re-normalize defensively so
    # the contract holds even if the upstream default changes.
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms
