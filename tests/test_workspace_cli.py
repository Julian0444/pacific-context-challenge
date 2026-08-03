"""Tests for the bring-your-own-corpus CLI (src/workspace.py, Fase 3 Etapa D)."""

import io
import json

import numpy as np
import pytest

# Imported at module scope on purpose: src.main computes _BENCHMARK_COUNT at
# import time from the real default workspace — importing it inside a test
# that monkeypatches CORPORA_DIR would break test-order independence.
import src.main  # noqa: F401
from src import workspaces
from src.workspace import DEFAULT_ROLES, create_workspace, humanize_title
from src.workspaces import invalidate_workspace_cache

LONG_TEXT = (
    "Quarterly revenue grew steadily while churn cohorts improved and the "
    "infrastructure migration stayed on budget across every region. " * 3
)


def _fake_embed(texts, show_progress_bar=False):
    out = []
    for t in texts:
        rowsum = float(len(t) % 7 + 1)
        out.append([rowsum, 1.0, 0.5, 0.25])
    arr = np.array(out, dtype=np.float32)
    return arr / np.linalg.norm(arr, axis=1, keepdims=True)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Isolated corpora/ + artifacts/ roots, fake embeddings, source docs dir."""
    corpora = tmp_path / "corpora"
    artifacts = tmp_path / "artifacts"
    corpora.mkdir()
    artifacts.mkdir()
    monkeypatch.setattr(workspaces, "CORPORA_DIR", str(corpora))
    monkeypatch.setattr(workspaces, "ARTIFACTS_ROOT", str(artifacts))
    monkeypatch.setattr("src.indexer._embed_texts", _fake_embed)
    # Query-path embeddings (retriever calls src.embedder.embed for the query)
    monkeypatch.setattr("src.embedder.embed", _fake_embed)
    invalidate_workspace_cache()

    src_dir = tmp_path / "mydocs"
    src_dir.mkdir()
    yield {"corpora": corpora, "artifacts": artifacts, "src": src_dir}
    invalidate_workspace_cache()
    from src.retriever import invalidate_caches

    invalidate_caches()


def _docx_bytes(paragraphs):
    import docx

    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def _seed_mixed_docs(src_dir):
    (src_dir / "board_notes_q1.txt").write_text("Board notes for Q1. " + LONG_TEXT)
    (src_dir / "roadmap-2024.md").write_text(
        "---\ntitle: internal\n---\n# Roadmap 2024\n\nPlatform milestones. " + LONG_TEXT
    )
    (src_dir / "hiring plan.docx").write_bytes(
        _docx_bytes(["Hiring plan for the platform org.", LONG_TEXT])
    )


def test_humanize_title():
    assert humanize_title("q1_2024-board_notes.md") == "Q1 2024 Board Notes"
    assert humanize_title("plan.docx") == "Plan"


def test_create_end_to_end_with_mixed_formats(sandbox):
    _seed_mixed_docs(sandbox["src"])

    summary = create_workspace("my-kb", from_dir=str(sandbox["src"]), name="My KB")

    assert summary["slug"] == "my-kb"
    assert len(summary["ingested"]) == 3
    assert summary["skipped"] == []
    assert summary["roles"] == ["viewer", "editor", "admin"]
    assert summary["min_role"] == "viewer"

    root = sandbox["corpora"] / "my-kb"
    for required in ("workspace.json", "metadata.json", "roles.json", "users.json"):
        assert (root / required).exists()
    metadata = json.loads((root / "metadata.json").read_text())
    assert len(metadata["documents"]) == 3
    entry = metadata["documents"][0]
    assert entry["min_role"] == "viewer"
    assert entry["type"] == "document"
    assert entry["content_hash"]
    # date defaulted from mtime — a real calendar date
    assert len(entry["date"]) == 10

    # Artifacts exist and are row-consistent.
    art = sandbox["artifacts"] / "my-kb"
    payloads = json.loads((art / "index_documents.json").read_text())
    bm25 = json.loads((art / "bm25_corpus.json").read_text())
    assert len(payloads) == len(bm25) == 3
    assert (art / "querytrace.index").exists()

    # The resolver serves it and it appears in list_workspaces().
    slugs = [w["slug"] for w in workspaces.list_workspaces()]
    assert "my-kb" in slugs


def test_created_workspace_answers_query_with_default_roles(sandbox):
    from fastapi.testclient import TestClient

    from src.main import app  # module already imported at top; just bind app

    _seed_mixed_docs(sandbox["src"])
    create_workspace("my-kb", from_dir=str(sandbox["src"]))

    client = TestClient(app)
    resp = client.post(
        "/query",
        json={"query": "hiring plan roadmap", "role": "viewer", "workspace": "my-kb"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["context"], "expected documents in context"
    assert body["decision_trace"]["user_context"]["role"] == "viewer"

    # A role from another workspace does not exist here.
    bad = client.post(
        "/query",
        json={"query": "x", "role": "partner", "workspace": "my-kb"},
    )
    assert bad.status_code == 400


def test_create_skips_duplicate_content(sandbox):
    (sandbox["src"] / "original.txt").write_text(LONG_TEXT)
    (sandbox["src"] / "copy_of_original.txt").write_text("  " + LONG_TEXT + "\n\n")

    summary = create_workspace("my-kb", from_dir=str(sandbox["src"]))
    assert len(summary["ingested"]) == 1
    assert len(summary["skipped"]) == 1
    assert summary["skipped"][0]["reason"] == "duplicate"


def test_create_skips_unreadable_file_with_warning(sandbox):
    (sandbox["src"] / "good.txt").write_text(LONG_TEXT)
    # ZIP signature but not a real docx → per-file 422, skipped, run continues.
    (sandbox["src"] / "broken.docx").write_bytes(b"PK\x03\x04not-really-a-docx" + b"x" * 60)

    summary = create_workspace("my-kb", from_dir=str(sandbox["src"]))
    assert [d["file"] for d in summary["ingested"]] == ["good.txt"]
    assert len(summary["skipped"]) == 1
    assert "broken.docx" in summary["skipped"][0]["file"]


def test_create_empty_dir_errors(sandbox):
    with pytest.raises(SystemExit, match="No supported documents"):
        create_workspace("my-kb", from_dir=str(sandbox["src"]))


def test_create_duplicate_slug_errors(sandbox):
    _seed_mixed_docs(sandbox["src"])
    create_workspace("my-kb", from_dir=str(sandbox["src"]))
    with pytest.raises(SystemExit, match="already exists"):
        create_workspace("my-kb", from_dir=str(sandbox["src"]))


def test_create_invalid_slug_errors(sandbox):
    _seed_mixed_docs(sandbox["src"])
    with pytest.raises(SystemExit):
        create_workspace("My KB!", from_dir=str(sandbox["src"]))
    assert not (sandbox["corpora"] / "My KB!").exists()


def test_create_nothing_ingestable_removes_skeleton(sandbox):
    (sandbox["src"] / "broken.docx").write_bytes(b"PK\x03\x04garbage" + b"x" * 60)
    with pytest.raises(SystemExit, match="workspace not created"):
        create_workspace("my-kb", from_dir=str(sandbox["src"]))
    assert not (sandbox["corpora"] / "my-kb").exists()


def test_create_with_custom_roles_file(sandbox, tmp_path):
    _seed_mixed_docs(sandbox["src"])
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({
        "roles": {
            "staff": {"access_rank": 1, "description": "Base"},
            "lead": {"access_rank": 2, "description": "Leads"},
        }
    }))
    summary = create_workspace(
        "my-kb", from_dir=str(sandbox["src"]), roles_path=str(roles_file)
    )
    assert summary["roles"] == ["staff", "lead"]
    assert summary["min_role"] == "staff"
    roles = json.loads((sandbox["corpora"] / "my-kb" / "roles.json").read_text())["roles"]
    assert roles["staff"]["name"] == "staff"


def test_default_roles_are_ranked():
    ranks = [r["access_rank"] for r in DEFAULT_ROLES.values()]
    assert sorted(ranks) == [1, 2, 3]
