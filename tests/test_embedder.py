"""Contract tests for src/embedder.py (Fase 5 Etapa A).

The embedder is the single seam between the pipeline and the inference
runtime; these tests pin the contract every caller relies on (shape, dtype,
unit norm, determinism). They load the real ONNX model once per session —
same footprint as the retriever integration tests.
"""

import numpy as np
import pytest

from src import embedder


@pytest.fixture(scope="module")
def vectors():
    return embedder.embed(["alpha beta gamma", "the quarterly revenue grew 40%"])


def test_shape_and_dtype(vectors):
    assert vectors.shape == (2, embedder.EMBEDDING_DIM)
    assert vectors.dtype == np.float32


def test_rows_are_unit_norm(vectors):
    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3)


def test_deterministic_for_identical_input(vectors):
    again = embedder.embed(["alpha beta gamma", "the quarterly revenue grew 40%"])
    assert np.allclose(vectors, again, atol=1e-6)


def test_different_texts_get_different_vectors(vectors):
    assert not np.allclose(vectors[0], vectors[1], atol=1e-3)


def test_empty_input_returns_empty_matrix():
    out = embedder.embed([])
    assert out.shape == (0, embedder.EMBEDDING_DIM)
    assert out.dtype == np.float32


def test_cache_dir_defaults_outside_tempdir(monkeypatch, tmp_path):
    """The model cache must survive OS temp purges (macOS wipes /var/folders,
    leaving a half-deleted snapshot that fails with NO_SUCHFILE)."""
    import tempfile

    monkeypatch.delenv("FASTEMBED_CACHE_PATH", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    path = embedder._cache_dir()
    assert not path.startswith(tempfile.gettempdir())
    assert path == str(tmp_path / ".cache" / "querytrace" / "fastembed")


def test_cache_dir_env_override_wins(monkeypatch, tmp_path):
    override = tmp_path / "custom-cache"
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(override))
    assert embedder._cache_dir() == str(override)
    assert override.is_dir()  # created eagerly so fastembed never falls back
