"""Tests for src.ingest and the POST /ingest endpoint."""

import io
import json

import pytest
from fastapi.testclient import TestClient

from src import ingest
from src.ingest import (
    IngestError,
    check_magic_bytes,
    compute_content_hash,
    extract_text,
    extract_text_from_md,
    extract_text_from_pdf,
    extract_text_from_txt,
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

def _stub_extract(_bytes, _filename="upload.pdf"):
    return "A" * 300


def _write_tmp_metadata(tmp_path):
    mp = tmp_path / "metadata.json"
    mp.write_text(json.dumps({"documents": [{"id": "doc_001"}]}))
    return mp


def test_ingest_oversize_file(tmp_path, monkeypatch):
    mp = _write_tmp_metadata(tmp_path)
    monkeypatch.setattr("src.ingest.extract_text", _stub_extract)
    huge = b"x" * (ingest.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(IngestError) as exc:
        ingest_document(
            file_bytes=huge, title="t", date="2024-01-01",
            min_role="analyst", doc_type="research_note", sensitivity="low",
            tags=[], metadata_path=str(mp), corpus_dir=str(tmp_path),
        )
    assert exc.value.status_code == 413


def test_ingest_bad_date(tmp_path, monkeypatch):
    mp = _write_tmp_metadata(tmp_path)
    monkeypatch.setattr("src.ingest.extract_text", _stub_extract)
    with pytest.raises(IngestError) as exc:
        ingest_document(
            file_bytes=b"x", title="t", date="not-a-date",
            min_role="analyst", doc_type="research_note", sensitivity="low",
            tags=[], metadata_path=str(mp), corpus_dir=str(tmp_path),
        )
    assert exc.value.status_code == 400
    assert "YYYY-MM-DD" in str(exc.value)


def test_ingest_rejects_impossible_date(tmp_path, monkeypatch):
    """Regex-valid but non-calendar dates ('2024-99-99') must be rejected —
    otherwise they land in metadata.json and permanently 500 freshness scoring."""
    mp = _write_tmp_metadata(tmp_path)
    monkeypatch.setattr("src.ingest.extract_text", _stub_extract)
    with pytest.raises(IngestError) as exc:
        ingest_document(
            file_bytes=b"x", title="t", date="2024-99-99",
            min_role="analyst", doc_type="research_note", sensitivity="low",
            tags=[], metadata_path=str(mp), corpus_dir=str(tmp_path),
        )
    assert exc.value.status_code == 400
    assert "real calendar date" in str(exc.value)


def test_ingest_accepts_leap_day():
    ingest._validate_inputs(
        title="t",
        date="2024-02-29",
        min_role="analyst",
        doc_type="research_note",
        sensitivity="low",
    )


def test_ingest_bad_role(tmp_path, monkeypatch):
    mp = _write_tmp_metadata(tmp_path)
    monkeypatch.setattr("src.ingest.extract_text", _stub_extract)
    with pytest.raises(IngestError):
        ingest_document(
            file_bytes=b"x", title="t", date="2024-01-01",
            min_role="god", doc_type="research_note", sensitivity="low",
            tags=[], metadata_path=str(mp), corpus_dir=str(tmp_path),
        )


def test_ingest_bad_doc_type(tmp_path, monkeypatch):
    mp = _write_tmp_metadata(tmp_path)
    monkeypatch.setattr("src.ingest.extract_text", _stub_extract)
    with pytest.raises(IngestError):
        ingest_document(
            file_bytes=b"x", title="t", date="2024-01-01",
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
    monkeypatch.setattr("src.ingest.extract_text", _stub_extract)
    with pytest.raises(IngestError):
        ingest_document(
            file_bytes=b"x", title="t", date="2024-01-01",
            min_role="analyst", doc_type="research_note", sensitivity="ultra",
            tags=[], metadata_path=str(mp), corpus_dir=str(tmp_path),
        )


def test_ingest_empty_title(tmp_path, monkeypatch):
    mp = _write_tmp_metadata(tmp_path)
    monkeypatch.setattr("src.ingest.extract_text", _stub_extract)
    with pytest.raises(IngestError):
        ingest_document(
            file_bytes=b"x", title="   ", date="2024-01-01",
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

    def fake_add(workspace=None, entry=None, text=None, on_stage=None):
        calls["build"] += 1

    monkeypatch.setattr("src.ingest.extract_text", _stub_extract)
    monkeypatch.setattr("src.ingest.indexer.add_document", fake_add)

    entry = ingest_document(
        file_bytes=b"fake-pdf-bytes",
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

    monkeypatch.setattr("src.ingest.extract_text", _stub_extract)
    monkeypatch.setattr("src.ingest.indexer.add_document", lambda workspace=None, entry=None, text=None, on_stage=None: None)

    entry = ingest_document(
        file_bytes=b"x", title="Hello World", date="2024-05-01",
        min_role="analyst", doc_type="research_note", sensitivity="low",
        tags=[], metadata_path=str(mp), corpus_dir=str(docs_dir),
    )
    assert entry["file_name"] == "hello_world_doc_002.txt"


# ---------------------------------------------------------------------------
# /ingest endpoint — validation paths (via TestClient)
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """TestClient with an admin session — /ingest requires one since Fase P.

    Jobs run inline (Fase 3): a 202 response means the job already executed
    synchronously, so tests can fetch its terminal state without polling.
    """
    from src import auth, jobs
    from src.main import app

    auth.reset_rate_limiter()
    jobs.configure(run_inline=True)
    jobs.reset_jobs()
    c = TestClient(app)
    resp = c.post("/login", json={"username": "patricia", "password": "demo-admin"})
    assert resp.status_code == 200, resp.text
    yield c
    auth.reset_rate_limiter()
    jobs.configure(run_inline=False)
    jobs.reset_jobs()


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


def test_ingest_endpoint_is_not_a_coroutine():
    """/ingest must stay a plain `def`: as a coroutine its 5-10s synchronous
    reindex would run on the event loop and freeze every other endpoint.
    Plain functions are dispatched to FastAPI's threadpool."""
    import asyncio

    from src.main import ingest as ingest_endpoint

    assert not asyncio.iscoroutinefunction(ingest_endpoint)


def test_endpoint_rejects_unsupported_extension_415(client):
    resp = client.post(
        "/ingest",
        data=_form(),
        files={"file": ("malware.exe", io.BytesIO(b"MZ..."), "application/octet-stream")},
    )
    assert resp.status_code == 415
    assert ".pdf" in resp.json()["detail"]


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
    # Real %PDF- signature (passes the magic-bytes gate) but bytes pdfplumber
    # can't parse → 422.
    resp = client.post(
        "/ingest",
        data=_form(),
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\ngarbage-not-a-pdf"), "application/pdf")},
    )
    assert resp.status_code == 422


CANNED_ENTRY = {
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
    "content_hash": "h",
}


def test_endpoint_happy_path_with_patched_ingest(client, monkeypatch):
    """Patch prepare/finalize + cache invalidation to avoid disk/reindex side
    effects. Verifies the 202 + job flow end to end (jobs run inline in tests):
    POST → job_id, then the job endpoint reports done with the result payload,
    and the caches were cleared by the job.
    """
    from src import main as main_mod

    monkeypatch.setattr(main_mod, "prepare_ingest", lambda **kw: {"prepared": True})
    monkeypatch.setattr(
        main_mod, "finalize_ingest", lambda prepared, on_stage=None: CANNED_ENTRY
    )
    inval_calls = {"n": 0}
    monkeypatch.setattr(
        main_mod,
        "invalidate_caches",
        lambda workspace=None: inval_calls.__setitem__("n", inval_calls["n"] + 1),
    )

    # Prime the per-slug evals cache with a sentinel so we can confirm the
    # ingested workspace's entry is cleared (other slugs stay cached).
    main_mod._evals_cache["pe-deal"] = {"sentinel": True}
    main_mod._evals_cache["other-ws"] = {"sentinel": True}

    resp = client.post(
        "/ingest",
        data=_form(),
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")},
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["workspace"] == "pe-deal"
    assert body["job_id"]

    job = client.get(f"/ingest/jobs/{body['job_id']}")
    assert job.status_code == 200, job.text
    job_body = job.json()
    assert job_body["state"] == "done"
    assert job_body["error"] is None
    result = job_body["result"]
    assert result["status"] == "ok"
    assert result["doc_id"] == "doc_099"
    assert result["title"] == "Test Upload"
    assert result["tags"] == ["a", "b"]
    assert "total_documents" in result

    assert inval_calls["n"] == 1
    assert "pe-deal" not in main_mod._evals_cache
    assert "other-ws" in main_mod._evals_cache
    main_mod._evals_cache.pop("other-ws", None)


# ---------------------------------------------------------------------------
# Fase 3 Etapa A — multi-format extraction dispatcher
# ---------------------------------------------------------------------------

LONG_TEXT = "QueryTrace ingestion test content. " * 5  # > MIN_EXTRACTED_CHARS


def _docx_bytes(paragraphs):
    import docx

    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def test_extract_text_txt_utf8():
    text = extract_text(LONG_TEXT.encode("utf-8"), "notes.txt")
    assert text == LONG_TEXT.strip()


def test_extract_text_txt_latin1_fallback():
    raw = ("Ingesta de artículos con acentuación española. " * 3).encode("latin-1")
    text = extract_text_from_txt(raw)
    assert "acentuación" in text


def test_extract_text_md_strips_frontmatter():
    md = "---\ntitle: Secret Draft\nauthor: x\n---\n# Heading\n\n" + LONG_TEXT
    text = extract_text(md.encode("utf-8"), "draft.md")
    assert "title: Secret Draft" not in text
    assert text.startswith("# Heading")


def test_extract_text_md_without_frontmatter_untouched():
    md = "# Plain doc\n\n" + LONG_TEXT
    assert extract_text_from_md(md.encode("utf-8")) == md


def test_extract_text_docx_happy():
    payload = _docx_bytes(["First paragraph of the memo.", "", LONG_TEXT])
    text = extract_text(payload, "memo.docx")
    assert "First paragraph of the memo." in text
    assert LONG_TEXT.strip() in text


def test_extract_text_docx_corrupt_zip_422():
    # Valid ZIP signature (passes magic bytes) but not a real docx → 422.
    with pytest.raises(IngestError) as exc:
        extract_text(b"PK\x03\x04garbage-not-a-zip" + b"x" * 100, "memo.docx")
    assert exc.value.status_code == 422


def test_extract_text_unsupported_extension_415():
    with pytest.raises(IngestError) as exc:
        extract_text(b"anything at all", "payload.exe")
    assert exc.value.status_code == 415


def test_extract_text_no_extension_415():
    with pytest.raises(IngestError) as exc:
        extract_text(b"anything at all", "README")
    assert exc.value.status_code == 415


def test_extract_text_empty_bytes_400():
    with pytest.raises(IngestError) as exc:
        extract_text(b"", "notes.txt")
    assert exc.value.status_code == 400


def test_extract_text_too_short_422():
    with pytest.raises(IngestError) as exc:
        extract_text(b"tiny", "notes.txt")
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# Fase 3 Etapa A — magic bytes vs lying extensions
# ---------------------------------------------------------------------------

def test_magic_bytes_pdf_named_but_text_content_415():
    with pytest.raises(IngestError) as exc:
        extract_text(LONG_TEXT.encode("utf-8"), "fake.pdf")
    assert exc.value.status_code == 415


def test_magic_bytes_txt_named_but_pdf_content_415():
    with pytest.raises(IngestError) as exc:
        extract_text(b"%PDF-1.4\n" + LONG_TEXT.encode("utf-8"), "fake.txt")
    assert exc.value.status_code == 415


def test_magic_bytes_md_named_but_zip_content_415():
    with pytest.raises(IngestError) as exc:
        extract_text(b"PK\x03\x04" + LONG_TEXT.encode("utf-8"), "fake.md")
    assert exc.value.status_code == 415


def test_magic_bytes_txt_with_nul_bytes_415():
    with pytest.raises(IngestError) as exc:
        extract_text(b"binary\x00junk" + LONG_TEXT.encode("utf-8"), "fake.txt")
    assert exc.value.status_code == 415


def test_magic_bytes_docx_named_but_no_zip_signature_415():
    with pytest.raises(IngestError) as exc:
        extract_text(LONG_TEXT.encode("utf-8"), "fake.docx")
    assert exc.value.status_code == 415


def test_check_magic_bytes_accepts_matching_signatures():
    check_magic_bytes(b"%PDF-1.7 rest", ".pdf")
    check_magic_bytes(b"PK\x03\x04rest", ".docx")
    check_magic_bytes(b"plain text", ".txt")
    check_magic_bytes(b"# markdown", ".md")


# ---------------------------------------------------------------------------
# Fase 3 Etapa A — content-hash dedup (409)
# ---------------------------------------------------------------------------

def test_content_hash_normalizes_whitespace_and_case():
    a = compute_content_hash("Hello   World\n\nSecond line")
    b = compute_content_hash("hello world second LINE")
    c = compute_content_hash("hello world second line different")
    assert a == b
    assert a != c


def _ingest_txt(tmp_path, content, title):
    return ingest_document(
        file_bytes=content.encode("utf-8"),
        title=title,
        date="2024-05-01",
        min_role="analyst",
        doc_type="research_note",
        sensitivity="low",
        tags=[],
        metadata_path=str(tmp_path / "metadata.json"),
        corpus_dir=str(tmp_path / "documents"),
        filename="upload.txt",
    )


def test_ingest_duplicate_content_409(tmp_path, monkeypatch):
    (tmp_path / "documents").mkdir()
    (tmp_path / "metadata.json").write_text(json.dumps({"documents": []}))
    monkeypatch.setattr("src.ingest.indexer.add_document", lambda workspace=None, entry=None, text=None, on_stage=None: None)

    first = _ingest_txt(tmp_path, LONG_TEXT, "Original Doc")
    assert first["content_hash"] == compute_content_hash(LONG_TEXT)

    # Same content, different title / layout → still a duplicate.
    with pytest.raises(IngestError) as exc:
        _ingest_txt(tmp_path, "  " + LONG_TEXT.replace(". ", ".\n\n") + "  ", "Renamed Copy")
    assert exc.value.status_code == 409
    assert first["id"] in str(exc.value)

    # Only one document landed in metadata.
    reloaded = json.loads((tmp_path / "metadata.json").read_text())
    assert len(reloaded["documents"]) == 1


def test_ingest_different_content_not_deduped(tmp_path, monkeypatch):
    (tmp_path / "documents").mkdir()
    (tmp_path / "metadata.json").write_text(json.dumps({"documents": []}))
    monkeypatch.setattr("src.ingest.indexer.add_document", lambda workspace=None, entry=None, text=None, on_stage=None: None)

    _ingest_txt(tmp_path, LONG_TEXT, "Doc A")
    _ingest_txt(tmp_path, LONG_TEXT + " extra tail content", "Doc B")
    reloaded = json.loads((tmp_path / "metadata.json").read_text())
    assert len(reloaded["documents"]) == 2


def test_pre_fase3_entries_without_hash_never_match(tmp_path, monkeypatch):
    (tmp_path / "documents").mkdir()
    # A legacy entry with no content_hash key must not collide with anything.
    (tmp_path / "metadata.json").write_text(json.dumps({"documents": [{"id": "doc_001"}]}))
    monkeypatch.setattr("src.ingest.indexer.add_document", lambda workspace=None, entry=None, text=None, on_stage=None: None)

    entry = _ingest_txt(tmp_path, LONG_TEXT, "New Doc")
    assert entry["id"] == "doc_002"


# ---------------------------------------------------------------------------
# Fase 3 Etapa A — endpoint: size caps, formats, 409 mapping
# ---------------------------------------------------------------------------

def test_endpoint_content_length_oversize_413(client):
    # An 11 MB body is rejected by the Content-Length gate before the file is read.
    big = b"x" * (11 * 1024 * 1024)
    resp = client.post(
        "/ingest",
        data=_form(),
        files={"file": ("big.txt", io.BytesIO(big), "text/plain")},
    )
    assert resp.status_code == 413


def test_endpoint_streamed_oversize_413(client, monkeypatch):
    """With the Content-Length gate loosened, the chunked read loop still caps
    the file at MAX_UPLOAD_BYTES (second belt for chunked/lying encodings)."""
    from src import main as main_mod

    monkeypatch.setattr(main_mod, "_MULTIPART_OVERHEAD_BYTES", 100 * 1024 * 1024)
    big = b"x" * (11 * 1024 * 1024)
    resp = client.post(
        "/ingest",
        data=_form(),
        files={"file": ("big.txt", io.BytesIO(big), "text/plain")},
    )
    assert resp.status_code == 413


def test_endpoint_accepts_txt_with_patched_ingest(client, monkeypatch):
    from src import main as main_mod

    captured = {}

    def fake_prepare(**kw):
        captured.update(kw)
        return {"prepared": True}

    monkeypatch.setattr(main_mod, "prepare_ingest", fake_prepare)
    monkeypatch.setattr(
        main_mod, "finalize_ingest",
        lambda prepared, on_stage=None: dict(CANNED_ENTRY, id="doc_100"),
    )
    monkeypatch.setattr(main_mod, "invalidate_caches", lambda workspace=None: None)

    resp = client.post(
        "/ingest",
        data=_form(title="Note"),
        files={"file": ("note.txt", io.BytesIO(LONG_TEXT.encode()), "text/plain")},
    )
    assert resp.status_code == 202, resp.text
    job = client.get(f"/ingest/jobs/{resp.json()['job_id']}").json()
    assert job["state"] == "done"
    assert job["result"]["doc_id"] == "doc_100"
    # The handler forwards the original filename so extraction dispatches on it.
    assert captured["filename"] == "note.txt"
    assert captured["file_bytes"] == LONG_TEXT.encode()


def test_endpoint_lying_extension_maps_to_415(client):
    # Text bytes named .pdf: passes the extension gate, fails magic bytes → 415.
    resp = client.post(
        "/ingest",
        data=_form(),
        files={"file": ("fake.pdf", io.BytesIO(LONG_TEXT.encode()), "application/pdf")},
    )
    assert resp.status_code == 415


def test_endpoint_duplicate_maps_to_409(client, monkeypatch):
    """The dedup check runs in the synchronous half — the uploader gets the
    409 on the request itself, not buried in a failed job."""
    from src import main as main_mod
    from src.ingest import IngestError as IE

    def raise_dup(**kw):
        raise IE("Duplicate content: identical to existing document doc_003.", status_code=409)

    monkeypatch.setattr(main_mod, "prepare_ingest", raise_dup)
    resp = client.post(
        "/ingest",
        data=_form(),
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4 body"), "application/pdf")},
    )
    assert resp.status_code == 409
    assert "doc_003" in resp.json()["detail"]
