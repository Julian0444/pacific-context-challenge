"""Tests for src.indexer helpers (atomic artifact writes, incremental add)."""

import json
import os

import numpy as np
import pytest

from src.indexer import _atomic_write_json, add_document
from src.workspaces import Workspace


def test_atomic_write_json_writes_valid_file(tmp_path):
    path = tmp_path / "out.json"
    _atomic_write_json(str(path), {"a": 1, "b": [1, 2]}, indent=2)
    assert json.loads(path.read_text()) == {"a": 1, "b": [1, 2]}


def test_atomic_write_json_replaces_existing(tmp_path):
    path = tmp_path / "out.json"
    path.write_text(json.dumps({"old": True}))
    _atomic_write_json(str(path), {"new": True})
    assert json.loads(path.read_text()) == {"new": True}


def test_atomic_write_json_failure_keeps_original_and_no_tmp(tmp_path):
    """On serialization failure the final file is untouched and no .tmp orphan
    is left behind."""
    path = tmp_path / "out.json"
    path.write_text(json.dumps({"original": True}))

    with pytest.raises(TypeError):
        _atomic_write_json(str(path), {"bad": object()})

    assert json.loads(path.read_text()) == {"original": True}
    assert not os.path.exists(str(path) + ".tmp")
    assert os.listdir(tmp_path) == ["out.json"]


def test_atomic_write_json_no_tmp_after_success(tmp_path):
    path = tmp_path / "out.json"
    _atomic_write_json(str(path), [1, 2, 3])
    assert os.listdir(tmp_path) == ["out.json"]


# ---------------------------------------------------------------------------
# add_document — incremental O(1) indexing (Fase 3 Etapa C)
# ---------------------------------------------------------------------------

def _fake_embed(texts, show_progress_bar=False):
    """Deterministic tiny embeddings — no model load in tests."""
    out = []
    for t in texts:
        rowsum = float(len(t) % 7 + 1)
        out.append([rowsum, 1.0, 0.5, 0.25])
    arr = np.array(out, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / norms


def _tmp_workspace(tmp_path, docs):
    """Materialize a minimal on-disk workspace + a Workspace ref for it."""
    documents_dir = tmp_path / "documents"
    artifacts_dir = tmp_path / "artifacts"
    documents_dir.mkdir(exist_ok=True)
    artifacts_dir.mkdir(exist_ok=True)
    entries = []
    for i, (title, content) in enumerate(docs, start=1):
        file_name = f"doc_{i:03d}.txt"
        (documents_dir / file_name).write_text(content)
        entries.append({
            "id": f"doc_{i:03d}", "file_name": file_name, "title": title,
            "type": "research_note", "date": "2024-01-01", "min_role": "analyst",
            "sensitivity": "low", "superseded_by": None, "tags": [],
            "short_summary": content[:50],
        })
    metadata = {"documents": entries}
    (tmp_path / "metadata.json").write_text(json.dumps(metadata))
    return Workspace(
        slug="tmp-ws", root=str(tmp_path), documents_dir=str(documents_dir),
        metadata_path=str(tmp_path / "metadata.json"), roles_path="",
        users_path="", evals_path="", artifacts_dir=str(artifacts_dir),
        index_path=str(artifacts_dir / "querytrace.index"),
        index_docs_path=str(artifacts_dir / "index_documents.json"),
        bm25_path=str(artifacts_dir / "bm25_corpus.json"),
        manifest={}, roles={}, metadata=metadata, users={},
    )


NEW_ENTRY = {
    "id": "doc_003", "file_name": "new_doc.txt", "title": "New Doc",
    "type": "research_note", "date": "2024-06-01", "min_role": "analyst",
    "sensitivity": "low", "superseded_by": None, "tags": ["new"],
    "short_summary": "fresh", "content_hash": "abc123",
}


def test_add_document_keeps_artifacts_consistent(tmp_path, monkeypatch):
    import faiss

    from src import indexer

    monkeypatch.setattr(indexer, "_embed_texts", _fake_embed)
    ws = _tmp_workspace(tmp_path, [("A", "alpha content one"), ("B", "beta content two")])
    indexer.build_and_save(ws)

    text = "gamma content three — the incrementally added document body"
    add_document(ws, NEW_ENTRY, text)

    index = faiss.read_index(ws.index_path)
    payloads = json.loads(open(ws.index_docs_path).read())
    bm25 = json.loads(open(ws.bm25_path).read())
    # Short docs → one chunk each; rows are chunks with doc_id = parent
    assert index.ntotal == len(payloads) == len(bm25) == 3
    assert payloads[-1]["id"] == "doc_003#c01"
    assert payloads[-1]["doc_id"] == "doc_003"
    assert payloads[-1]["excerpt"].startswith("gamma content")
    assert payloads[-1]["content_hash"] == "abc123"
    assert "content" not in payloads[-1]
    assert "gamma" in bm25[-1]


def test_add_document_falls_back_when_artifacts_missing(tmp_path, monkeypatch):
    from src import indexer

    ws = _tmp_workspace(tmp_path, [("A", "alpha content one")])
    calls = {"rebuild": 0}
    monkeypatch.setattr(
        indexer, "build_and_save",
        lambda workspace=None, on_stage=None: calls.__setitem__("rebuild", 1),
    )
    add_document(ws, NEW_ENTRY, "text")  # no artifacts on disk yet
    assert calls["rebuild"] == 1


def test_add_document_falls_back_on_drift(tmp_path, monkeypatch):
    from src import indexer

    monkeypatch.setattr(indexer, "_embed_texts", _fake_embed)
    ws = _tmp_workspace(tmp_path, [("A", "alpha content one"), ("B", "beta content two")])
    indexer.build_and_save(ws)

    # Corrupt: drop one payload so len(payloads) != index.ntotal.
    payloads = json.loads(open(ws.index_docs_path).read())
    _atomic_write_json(ws.index_docs_path, payloads[:1])

    calls = {"rebuild": 0}
    monkeypatch.setattr(
        indexer, "build_and_save",
        lambda workspace=None, on_stage=None: calls.__setitem__("rebuild", 1),
    )
    add_document(ws, NEW_ENTRY, "text")
    assert calls["rebuild"] == 1


def test_add_document_reports_stages(tmp_path, monkeypatch):
    from src import indexer

    monkeypatch.setattr(indexer, "_embed_texts", _fake_embed)
    ws = _tmp_workspace(tmp_path, [("A", "alpha content one")])
    indexer.build_and_save(ws)

    stages = []
    add_document(ws, NEW_ENTRY, "some new text body", on_stage=stages.append)
    assert stages == ["embedding", "indexing"]
