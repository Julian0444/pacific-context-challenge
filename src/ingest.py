"""
ingest.py — PDF ingestion pipeline for QueryTrace.

Exposes four helpers plus the orchestrator `ingest_document()`:
- extract_text_from_pdf(file_bytes) -> str
- generate_next_doc_id(metadata_path) -> str
- sanitize_filename(title) -> str
- ingest_document(pdf_bytes, title, date, min_role, doc_type, sensitivity,
                  tags, superseded_by=None) -> dict

Writes extracted text as a .txt file under corpus/documents/ (matching the
existing indexer contract), appends an entry to corpus/metadata.json, and
triggers a full FAISS + BM25 rebuild via src.indexer.build_and_save().

A module-level lock serializes metadata writes and reindex so concurrent
uploads cannot corrupt the corpus.
"""

import io
import json
import os
import re
import threading
from typing import Optional

import pdfplumber

from src import indexer

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "corpus", "documents")
METADATA_PATH = os.path.join(os.path.dirname(__file__), "..", "corpus", "metadata.json")

VALID_MIN_ROLES = frozenset({"analyst", "vp", "partner"})
VALID_DOC_TYPES = frozenset({
    "board_memo", "deal_memo", "financial_model", "internal_analysis",
    "internal_email", "internal_memo", "legal_memo", "lp_update",
    "news_article", "press_release", "public_filing", "research_note",
    "sector_overview",
})
VALID_SENSITIVITY = frozenset({"low", "medium", "high", "confidential"})

MAX_PDF_BYTES = 10 * 1024 * 1024
MIN_EXTRACTED_CHARS = 50
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_INGEST_LOCK = threading.Lock()


class IngestError(ValueError):
    """Raised when ingest input is invalid or extraction fails."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract concatenated page text from a PDF byte stream.

    Returns whitespace-joined text across pages. Raises IngestError on
    unreadable PDFs or when extracted content is shorter than
    MIN_EXTRACTED_CHARS (scanned/image-only PDFs typically yield nothing).
    """
    if not file_bytes:
        raise IngestError("Uploaded file is empty.", status_code=400)
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
    except Exception as e:
        raise IngestError(f"Unreadable PDF: {e}", status_code=422) from e

    text = "\n\n".join(p.strip() for p in pages if p and p.strip())
    if len(text) < MIN_EXTRACTED_CHARS:
        raise IngestError(
            "No extractable text in PDF (scanned/image-only PDFs are not supported).",
            status_code=422,
        )
    return text


def generate_next_doc_id(metadata_path: Optional[str] = None) -> str:
    """Return the next doc_NNN id based on the current metadata file."""
    if metadata_path is None:
        metadata_path = METADATA_PATH
    with open(metadata_path, "r") as f:
        metadata = json.load(f)
    max_n = 0
    for entry in metadata.get("documents", []):
        m = re.match(r"doc_(\d+)$", entry.get("id", ""))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"doc_{max_n + 1:03d}"


def sanitize_filename(title: str) -> str:
    """Produce a safe base filename (no extension) from a user title.

    Lowercase alphanumerics and underscores only, collapsing runs of other
    characters to a single underscore, trimmed to 60 chars. Falls back to
    'document' if the result is empty. Guarantees no path separators or
    traversal sequences.
    """
    s = (title or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")[:60]
    return s or "document"


def _validate_inputs(
    title: str,
    date: str,
    min_role: str,
    doc_type: str,
    sensitivity: str,
) -> None:
    if not title or not title.strip():
        raise IngestError("title must not be empty.")
    if not DATE_RE.match(date or ""):
        raise IngestError("date must be in YYYY-MM-DD format.")
    if min_role not in VALID_MIN_ROLES:
        raise IngestError(
            f"min_role must be one of {sorted(VALID_MIN_ROLES)}."
        )
    if doc_type not in VALID_DOC_TYPES:
        raise IngestError(
            f"doc_type must be one of {sorted(VALID_DOC_TYPES)}."
        )
    if sensitivity not in VALID_SENSITIVITY:
        raise IngestError(
            f"sensitivity must be one of {sorted(VALID_SENSITIVITY)}."
        )


def _unique_filename(base: str, doc_id: str, directory: str) -> str:
    """Return a filename that does not already exist in `directory`.

    Appends the doc_id when the plain base collides.
    """
    candidate = f"{base}.txt"
    if not os.path.exists(os.path.join(directory, candidate)):
        return candidate
    return f"{base}_{doc_id}.txt"


def ingest_document(
    pdf_bytes: bytes,
    title: str,
    date: str,
    min_role: str,
    doc_type: str,
    sensitivity: str,
    tags: list,
    superseded_by: Optional[str] = None,
    metadata_path: Optional[str] = None,
    corpus_dir: Optional[str] = None,
) -> dict:
    """Extract, persist, and reindex a new document.

    Returns the metadata entry that was appended. Raises IngestError on
    validation failure or PDF extraction failure.
    """
    if metadata_path is None:
        metadata_path = METADATA_PATH
    if corpus_dir is None:
        corpus_dir = CORPUS_DIR
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise IngestError(
            f"PDF exceeds {MAX_PDF_BYTES // (1024 * 1024)} MB size limit.",
            status_code=413,
        )
    _validate_inputs(title, date, min_role, doc_type, sensitivity)
    if not isinstance(tags, list):
        raise IngestError("tags must be a list of strings.")
    clean_tags = [t.strip() for t in tags if isinstance(t, str) and t.strip()]

    text = extract_text_from_pdf(pdf_bytes)

    with _INGEST_LOCK:
        doc_id = generate_next_doc_id(metadata_path)
        base = sanitize_filename(title)
        file_name = _unique_filename(base, doc_id, corpus_dir)

        os.makedirs(corpus_dir, exist_ok=True)
        with open(os.path.join(corpus_dir, file_name), "w") as f:
            f.write(text)

        short_summary = text[:200].strip()

        entry = {
            "id": doc_id,
            "file_name": file_name,
            "title": title.strip(),
            "type": doc_type,
            "date": date,
            "min_role": min_role,
            "sensitivity": sensitivity,
            "superseded_by": superseded_by,
            "tags": clean_tags,
            "short_summary": short_summary,
        }

        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        metadata.setdefault("documents", []).append(entry)
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        indexer.build_and_save()

    return entry
