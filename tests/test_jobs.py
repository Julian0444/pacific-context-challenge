"""Tests for src.jobs and the async /ingest job flow (Fase 3 Etapa B)."""

import io
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from src import jobs
from src.ingest import IngestError, finalize_ingest, ingest_document
from src.jobs import JobStore

LONG_TEXT = "QueryTrace job test content for the async ingest flow. " * 4


@pytest.fixture(autouse=True)
def _clean_jobs():
    jobs.reset_jobs()
    yield
    jobs.reset_jobs()
    jobs.configure(run_inline=False)


# ---------------------------------------------------------------------------
# JobStore
# ---------------------------------------------------------------------------

def test_jobstore_create_and_get():
    store = JobStore()
    job = store.create("pe-deal")
    assert job["state"] == "queued"
    assert job["workspace"] == "pe-deal"
    assert job["error"] is None and job["result"] is None
    fetched = store.get(job["id"])
    assert fetched["id"] == job["id"]
    # get() returns a copy — callers cannot mutate the store through it.
    fetched["state"] = "tampered"
    assert store.get(job["id"])["state"] == "queued"


def test_jobstore_update_states_and_terminal_payloads():
    store = JobStore()
    job = store.create("pe-deal")
    before = store.get(job["id"])["updated_at"]
    store.update(job["id"], state="embedding")
    assert store.get(job["id"])["state"] == "embedding"
    assert store.get(job["id"])["updated_at"] >= before
    store.update(job["id"], state="failed", error={"status_code": 500, "detail": "boom"})
    fetched = store.get(job["id"])
    assert fetched["state"] == "failed"
    assert fetched["error"]["detail"] == "boom"


def test_jobstore_rejects_unknown_state():
    store = JobStore()
    job = store.create("pe-deal")
    with pytest.raises(ValueError):
        store.update(job["id"], state="exploding")


def test_jobstore_update_expired_job_is_noop():
    store = JobStore(max_jobs=1)
    old = store.create("pe-deal")
    store.create("pe-deal")  # evicts `old`
    store.update(old["id"], state="done")  # must not raise
    assert store.get(old["id"]) is None


def test_jobstore_retention_evicts_oldest():
    store = JobStore(max_jobs=2)
    first = store.create("pe-deal")
    second = store.create("pe-deal")
    third = store.create("pe-deal")
    assert store.get(first["id"]) is None
    assert store.get(second["id"]) is not None
    assert store.get(third["id"]) is not None


def test_jobstore_list_newest_first_and_workspace_filter():
    store = JobStore()
    a = store.create("pe-deal")
    b = store.create("saas-internal")
    c = store.create("pe-deal")
    assert [j["id"] for j in store.list()] == [c["id"], b["id"], a["id"]]
    assert [j["id"] for j in store.list(workspace="pe-deal")] == [c["id"], a["id"]]


# ---------------------------------------------------------------------------
# Single-worker executor — serialization
# ---------------------------------------------------------------------------

def test_single_worker_serializes_submissions():
    """Two submitted jobs never overlap: the second starts after the first
    ends (max_workers=1 is the serialization mechanism)."""
    jobs.configure(run_inline=False)
    order = []
    done = threading.Event()

    def first():
        order.append("first-start")
        time.sleep(0.15)
        order.append("first-end")

    def second():
        order.append("second-start")
        done.set()

    jobs.submit(first)
    jobs.submit(second)
    assert done.wait(timeout=5)
    assert order == ["first-start", "first-end", "second-start"]


def test_inline_mode_runs_synchronously():
    jobs.configure(run_inline=True)
    ran = []
    jobs.submit(lambda: ran.append(True))
    assert ran == [True]


# ---------------------------------------------------------------------------
# finalize_ingest — stage callbacks + rollback
# ---------------------------------------------------------------------------

def _prepared(tmp_path, text=LONG_TEXT, title="Job Doc"):
    return {
        "workspace_slug": "pe-deal",
        "metadata_path": str(tmp_path / "metadata.json"),
        "corpus_dir": str(tmp_path / "documents"),
        "text": text,
        "content_hash": "hash-" + title,
        "title": title,
        "date": "2024-05-01",
        "min_role": "analyst",
        "doc_type": "research_note",
        "sensitivity": "low",
        "tags": [],
        "superseded_by": None,
    }


def test_finalize_reports_stages_in_order(tmp_path, monkeypatch):
    (tmp_path / "documents").mkdir()
    (tmp_path / "metadata.json").write_text(json.dumps({"documents": []}))

    def fake_add(workspace=None, entry=None, text=None, on_stage=None):
        on_stage("embedding")
        on_stage("indexing")

    monkeypatch.setattr("src.ingest.indexer.add_document", fake_add)
    stages = []
    entry = finalize_ingest(_prepared(tmp_path), on_stage=stages.append)
    assert stages == ["embedding", "indexing"]
    assert entry["id"] == "doc_001"


def test_finalize_rollback_on_reindex_failure(tmp_path, monkeypatch):
    """A job that fails after writing the .txt and the metadata entry must
    clean both up — no orphan document survives a failed ingest."""
    (tmp_path / "documents").mkdir()
    (tmp_path / "metadata.json").write_text(
        json.dumps({"documents": [{"id": "doc_001"}]})
    )

    def exploding_add(workspace=None, entry=None, text=None, on_stage=None):
        raise RuntimeError("model exploded mid-reindex")

    monkeypatch.setattr("src.ingest.indexer.add_document", exploding_add)

    with pytest.raises(RuntimeError):
        finalize_ingest(_prepared(tmp_path))

    # No orphan .txt file...
    assert list((tmp_path / "documents").iterdir()) == []
    # ...and the metadata entry was removed again.
    reloaded = json.loads((tmp_path / "metadata.json").read_text())
    assert [d["id"] for d in reloaded["documents"]] == ["doc_001"]


def test_finalize_duplicate_race_raises_409(tmp_path, monkeypatch):
    """prepare passed, but an identical doc landed before the job's turn —
    the authoritative under-lock re-check still 409s."""
    (tmp_path / "documents").mkdir()
    monkeypatch.setattr(
        "src.ingest.indexer.add_document", lambda workspace=None, entry=None, text=None, on_stage=None: None
    )
    (tmp_path / "metadata.json").write_text(json.dumps({"documents": []}))

    ingest_document(
        file_bytes=LONG_TEXT.encode(), title="First", date="2024-05-01",
        min_role="analyst", doc_type="research_note", sensitivity="low",
        tags=[], metadata_path=str(tmp_path / "metadata.json"),
        corpus_dir=str(tmp_path / "documents"), filename="a.txt",
    )
    from src.ingest import compute_content_hash

    prepared = _prepared(tmp_path)
    prepared["content_hash"] = compute_content_hash(LONG_TEXT)
    with pytest.raises(IngestError) as exc:
        finalize_ingest(prepared)
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# /ingest job endpoints — auth, flow, failure surface
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_client():
    from src import auth
    from src.main import app

    auth.reset_rate_limiter()
    jobs.configure(run_inline=True)
    c = TestClient(app)
    resp = c.post("/login", json={"username": "patricia", "password": "demo-admin"})
    assert resp.status_code == 200, resp.text
    yield c
    auth.reset_rate_limiter()


def _form(**overrides):
    base = {
        "title": "Job Upload",
        "date": "2024-05-01",
        "min_role": "analyst",
        "doc_type": "research_note",
        "sensitivity": "low",
        "tags": "",
    }
    base.update(overrides)
    return base


def _post_upload(client):
    return client.post(
        "/ingest",
        data=_form(),
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")},
    )


def test_failed_job_surfaces_typed_error(admin_client, monkeypatch):
    from src import main as main_mod

    monkeypatch.setattr(main_mod, "prepare_ingest", lambda **kw: {"prepared": True})

    def exploding_finalize(prepared, on_stage=None):
        raise RuntimeError("reindex died")

    monkeypatch.setattr(main_mod, "finalize_ingest", exploding_finalize)

    resp = _post_upload(admin_client)
    assert resp.status_code == 202
    job = admin_client.get(f"/ingest/jobs/{resp.json()['job_id']}").json()
    assert job["state"] == "failed"
    assert job["error"]["status_code"] == 500
    assert "reindex died" in job["error"]["detail"]
    assert job["result"] is None


def test_failed_job_keeps_ingest_error_status(admin_client, monkeypatch):
    from src import main as main_mod

    monkeypatch.setattr(main_mod, "prepare_ingest", lambda **kw: {"prepared": True})

    def dup_finalize(prepared, on_stage=None):
        raise IngestError("Duplicate content: identical to doc_002.", status_code=409)

    monkeypatch.setattr(main_mod, "finalize_ingest", dup_finalize)

    resp = _post_upload(admin_client)
    job = admin_client.get(f"/ingest/jobs/{resp.json()['job_id']}").json()
    assert job["state"] == "failed"
    assert job["error"]["status_code"] == 409


def test_jobs_index_lists_own_workspace_newest_first(admin_client, monkeypatch):
    from src import main as main_mod

    monkeypatch.setattr(main_mod, "prepare_ingest", lambda **kw: {"prepared": True})
    monkeypatch.setattr(
        main_mod, "finalize_ingest",
        lambda prepared, on_stage=None: {
            "id": "doc_900", "file_name": "f.txt", "title": "t",
            "type": "research_note", "date": "2024-05-01", "min_role": "analyst",
            "sensitivity": "low", "superseded_by": None, "tags": [],
            "short_summary": "s", "content_hash": "h",
        },
    )
    monkeypatch.setattr(main_mod, "invalidate_caches", lambda workspace=None: None)

    first = _post_upload(admin_client).json()["job_id"]
    second = _post_upload(admin_client).json()["job_id"]
    # A job from another workspace must not appear in this session's list.
    jobs.get_store().create("saas-internal")

    listing = admin_client.get("/ingest/jobs")
    assert listing.status_code == 200
    ids = [j["id"] for j in listing.json()]
    assert ids == [second, first]


def test_job_fetch_unknown_id_404(admin_client):
    resp = admin_client.get("/ingest/jobs/deadbeef0000")
    assert resp.status_code == 404


def test_job_fetch_cross_workspace_403(admin_client):
    foreign = jobs.get_store().create("saas-internal")
    resp = admin_client.get(f"/ingest/jobs/{foreign['id']}")
    assert resp.status_code == 403


def test_job_endpoints_require_session_401():
    from src import auth
    from src.main import app

    auth.reset_rate_limiter()
    c = TestClient(app)
    assert c.get("/ingest/jobs").status_code == 401
    assert c.get("/ingest/jobs/abc123abc123").status_code == 401


def test_job_endpoints_require_admin_403():
    from src import auth
    from src.main import app

    auth.reset_rate_limiter()
    c = TestClient(app)
    resp = c.post("/login", json={"username": "julia", "password": "demo-analyst"})
    assert resp.status_code == 200, resp.text
    assert c.get("/ingest/jobs").status_code == 403
    assert c.get("/ingest/jobs/abc123abc123").status_code == 403
    auth.reset_rate_limiter()
