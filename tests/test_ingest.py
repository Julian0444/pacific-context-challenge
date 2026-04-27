"""Tests for src.ingest and the POST /ingest endpoint."""

import io
import json

import pytest
from fastapi.testclient import TestClient

from src import ingest
from src.ingest import (
    IngestError,
    extract_text_from_pdf,
    generate_next_doc_id,
    ingest_document,
    sanitize_filename,
)


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

def test_sanitize_filename_basic():
    assert sanitize_filename("Hello World") == "hello_world"


def test_sanitize_filename_collapses_nonword():
    assert sanitize_filename("Q1 2024 — Meridian  Financials!!") == "q1_2024_meridian_financials"


def test_sanitize_filename_rejects_path_traversal():
    # Path separators and dots are all folded into underscores by the regex.
    result = sanitize_filename("../../etc/passwd")
    assert "/" not in result
    assert ".." not in result
    assert result == "etc_passwd"


def test_sanitize_filename_empty_fallback():
    assert sanitize_filename("") == "document"
    assert sanitize_filename("!!!") == "document"


def test_sanitize_filename_length_cap():
    long = "a" * 200
    assert len(sanitize_filename(long)) == 60


# ---------------------------------------------------------------------------
# generate_next_doc_id
# ---------------------------------------------------------------------------

def test_generate_next_doc_id_advances(tmp_path):
    mp = tmp_path / "metadata.json"
    mp.write_text(json.dumps({"documents": [
        {"id": "doc_001"}, {"id": "doc_007"}, {"id": "doc_002"},
    ]}))
    assert generate_next_doc_id(str(mp)) == "doc_008"


def test_generate_next_doc_id_empty_corpus(tmp_path):
    mp = tmp_path / "metadata.json"
    mp.write_text(json.dumps({"documents": []}))
    assert generate_next_doc_id(str(mp)) == "doc_001"


def test_generate_next_doc_id_ignores_malformed_ids(tmp_path):
    mp = tmp_path / "metadata.json"
    mp.write_text(json.dumps({"documents": [
        {"id": "doc_003"}, {"id": "custom"}, {"id": ""},
    ]}))
    assert generate_next_doc_id(str(mp)) == "doc_004"


# ---------------------------------------------------------------------------
# extract_text_from_pdf
# ---------------------------------------------------------------------------

def test_extract_text_empty_bytes():
    with pytest.raises(IngestError) as exc:
        extract_text_from_pdf(b"")
    assert exc.value.status_code == 400


def test_extract_text_unreadable_pdf():
    with pytest.raises(IngestError) as exc:
        extract_text_from_pdf(b"not a pdf at all")
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# ingest_document — validation (no disk writes)
# ---------------------------------------------------------------------------

def _stub_extract(_bytes):
    return "A" * 300


def _write_tmp_metadata(tmp_path):
    mp = tmp_path / "metadata.json"
    mp.write_text(json.dumps({"documents": [{"id": "doc_001"}]}))
    return mp


def test_ingest_oversize_file(tmp_path, monkeypatch):
    mp = _write_tmp_metadata(tmp_path)
    monkeypatch.setattr("src.ingest.extract_text_from_pdf", _stub_extract)
    huge = b"x" * (ingest.MAX_PDF_BYTES + 1)
    with pytest.raises(IngestError) as exc:
        ingest_document(
            pdf_bytes=huge, title="t", date="2024-01-01",
            min_role="analyst", doc_type="research_note", sensitivity="low",
            tags=[], metadata_path=str(mp), corpus_dir=str(tmp_path),
        )
    assert exc.value.status_code == 413


def test_ingest_bad_date(tmp_path, monkeypatch):
    mp = _write_tmp_metadata(tmp_path)
    monkeypatch.setattr("src.ingest.extract_text_from_pdf", _stub_extract)
    with pytest.raises(IngestError) as exc:
        ingest_document(
            pdf_bytes=b"x", title="t", date="not-a-date",
            min_role="analyst", doc_type="research_note", sensitivity="low",
            tags=[], metadata_path=str(mp), corpus_dir=str(tmp_path),
        )
    assert exc.value.status_code == 400
    assert "YYYY-MM-DD" in str(exc.value)


def test_ingest_bad_role(tmp_path, monkeypatch):
    mp = _write_tmp_metadata(tmp_path)
    monkeypatch.setattr("src.ingest.extract_text_from_pdf", _stub_extract)
    with pytest.raises(IngestError):
        ingest_document(
            pdf_bytes=b"x", title="t", date="2024-01-01",
            min_role="god", doc_type="research_note", sensitivity="low",
            tags=[], metadata_path=str(mp), corpus_dir=str(tmp_path),
        )


def test_ingest_bad_doc_type(tmp_path, monkeypatch):
    mp = _write_tmp_metadata(tmp_path)
    monkeypatch.setattr("src.ingest.extract_text_from_pdf", _stub_extract)
    with pytest.raises(IngestError):
        ingest_document(
            pdf_bytes=b"x", title="t", date="2024-01-01",
            min_role="analyst", doc_type="whatever", sensitivity="low",
            tags=[], metadata_path=str(mp), corpus_dir=str(tmp_path),
        )


@pytest.mark.parametrize("doc_type", ["internal_memo", "legal_memo", "news_article"])
def test_ingest_accepts_current_demo_doc_types(doc_type):
    ingest._validate_inputs(
        title="t",
        date="2024-01-01",
        min_role="analyst",
        doc_type=doc_type,
        sensitivity="low",
    )


def test_ingest_bad_sensitivity(tmp_path, monkeypatch):
    mp = _write_tmp_metadata(tmp_path)
    monkeypatch.setattr("src.ingest.extract_text_from_pdf", _stub_extract)
    with pytest.raises(IngestError):
        ingest_document(
            pdf_bytes=b"x", title="t", date="2024-01-01",
            min_role="analyst", doc_type="research_note", sensitivity="ultra",
            tags=[], metadata_path=str(mp), corpus_dir=str(tmp_path),
        )


def test_ingest_empty_title(tmp_path, monkeypatch):
    mp = _write_tmp_metadata(tmp_path)
    monkeypatch.setattr("src.ingest.extract_text_from_pdf", _stub_extract)
    with pytest.raises(IngestError):
        ingest_document(
            pdf_bytes=b"x", title="   ", date="2024-01-01",
            min_role="analyst", doc_type="research_note", sensitivity="low",
            tags=[], metadata_path=str(mp), corpus_dir=str(tmp_path),
        )


# ---------------------------------------------------------------------------
# ingest_document — happy path (tmp dirs + stubbed extract + stubbed reindex)
# ---------------------------------------------------------------------------

def test_ingest_document_happy_path(tmp_path, monkeypatch):
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()
    mp = tmp_path / "metadata.json"
    mp.write_text(json.dumps({"documents": [{"id": "doc_001"}]}))

    calls = {"build": 0}

    def fake_build():
        calls["build"] += 1

    monkeypatch.setattr("src.ingest.extract_text_from_pdf", _stub_extract)
    monkeypatch.setattr("src.ingest.indexer.build_and_save", fake_build)

    entry = ingest_document(
        pdf_bytes=b"fake-pdf-bytes",
        title="Hello World",
        date="2024-05-01",
        min_role="analyst",
        doc_type="research_note",
        sensitivity="low",
        tags=["a", "b", "  ", "c"],
        metadata_path=str(mp),
        corpus_dir=str(docs_dir),
    )

    assert entry["id"] == "doc_002"
    assert entry["file_name"] == "hello_world.txt"
    assert entry["title"] == "Hello World"
    assert entry["tags"] == ["a", "b", "c"]
    assert entry["short_summary"].startswith("A")
    assert calls["build"] == 1

    written = docs_dir / "hello_world.txt"
    assert written.exists()
    assert written.read_text().startswith("A")

    reloaded = json.loads(mp.read_text())
    ids = [d["id"] for d in reloaded["documents"]]
    assert ids == ["doc_001", "doc_002"]


def test_ingest_document_duplicate_filename_suffix(tmp_path, monkeypatch):
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()
    (docs_dir / "hello_world.txt").write_text("existing")
    mp = tmp_path / "metadata.json"
    mp.write_text(json.dumps({"documents": [{"id": "doc_001"}]}))

    monkeypatch.setattr("src.ingest.extract_text_from_pdf", _stub_extract)
    monkeypatch.setattr("src.ingest.indexer.build_and_save", lambda: None)

    entry = ingest_document(
        pdf_bytes=b"x", title="Hello World", date="2024-05-01",
        min_role="analyst", doc_type="research_note", sensitivity="low",
        tags=[], metadata_path=str(mp), corpus_dir=str(docs_dir),
    )
    assert entry["file_name"] == "hello_world_doc_002.txt"


# ---------------------------------------------------------------------------
# /ingest endpoint — validation paths (via TestClient)
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from src.main import app
    return TestClient(app)


def _form(**overrides):
    base = {
        "title": "Test Upload",
        "date": "2024-05-01",
        "min_role": "analyst",
        "doc_type": "research_note",
        "sensitivity": "low",
        "tags": "a,b",
    }
    base.update(overrides)
    return base


def test_endpoint_rejects_non_pdf_415(client):
    resp = client.post(
        "/ingest",
        data=_form(),
        files={"file": ("note.txt", io.BytesIO(b"plain text"), "text/plain")},
    )
    assert resp.status_code == 415


def test_endpoint_rejects_bad_role_400(client):
    resp = client.post(
        "/ingest",
        data=_form(min_role="god"),
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-"), "application/pdf")},
    )
    assert resp.status_code == 400


def test_endpoint_rejects_bad_date_400(client):
    resp = client.post(
        "/ingest",
        data=_form(date="05/01/2024"),
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-"), "application/pdf")},
    )
    assert resp.status_code == 400


def test_endpoint_rejects_unreadable_pdf_422(client):
    # Valid content-type but bytes that pdfplumber can't parse → 422
    resp = client.post(
        "/ingest",
        data=_form(),
        files={"file": ("x.pdf", io.BytesIO(b"garbage-not-a-pdf"), "application/pdf")},
    )
    assert resp.status_code == 422


def test_endpoint_happy_path_with_patched_ingest(client, monkeypatch):
    """Patch ingest_document + cache invalidation to avoid disk/reindex side effects.

    Verifies FastAPI wiring, response model shape, and that caches are cleared.
    """
    from src import main as main_mod

    canned_entry = {
        "id": "doc_099",
        "file_name": "test_upload.txt",
        "title": "Test Upload",
        "type": "research_note",
        "date": "2024-05-01",
        "min_role": "analyst",
        "sensitivity": "low",
        "superseded_by": None,
        "tags": ["a", "b"],
        "short_summary": "canned",
    }

    # Stub out the heavy work
    monkeypatch.setattr(main_mod, "ingest_document", lambda **kw: canned_entry)
    inval_calls = {"n": 0}
    monkeypatch.setattr(main_mod, "invalidate_caches", lambda: inval_calls.__setitem__("n", inval_calls["n"] + 1))

    # Prime the evals cache with a sentinel so we can confirm it's cleared
    main_mod._evals_cache = {"sentinel": True}

    resp = client.post(
        "/ingest",
        data=_form(),
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["doc_id"] == "doc_099"
    assert body["title"] == "Test Upload"
    assert body["tags"] == ["a", "b"]
    assert "total_documents" in body
    assert inval_calls["n"] == 1
    assert main_mod._evals_cache is None
