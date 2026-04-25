# MUST-D Execution Plan — IDEA 8 (PDF Ingestion + Admin Panel)

Date: 2026-04-17
Branch: `codex/must-a-idea1-2`
Scope: First backend-expanding batch since MUST-A. New `POST /ingest` endpoint, new `src/ingest.py`, new frontend Admin mode. Writes to `corpus/documents/`, `corpus/metadata.json`, and `artifacts/*` at runtime. Two new runtime dependencies.

---

## Executive summary

IDEA 8 adds a runtime PDF ingestion path: upload PDF + metadata → extract text → write `.txt` into `corpus/documents/` → append `metadata.json` entry → trigger full reindex (FAISS + BM25) → invalidate in-process caches. A new Admin frontend mode exposes the upload form. Unlike MUST-A/B/C, this batch has real side effects on disk and touches live module state that was previously loaded only at startup. It also introduces the first new runtime dependencies since the initial build.

The original prompt is clear on the mechanics but under-specifies several failure modes, validation rules, and concurrency guarantees. None are blockers; they need decisions before implementation.

---

## Missing / weak areas in the prompt (call-outs, not blockers)

1. **Where extracted text goes.** Prompt says "extracts text, adds it to the corpus" but not *as what*. Existing indexer reads `.txt` files from `corpus/documents/` (`src/indexer.py:19`, `load_documents()`). Decision: write extracted text as `<sanitized_title>.txt` in `corpus/documents/`. Do **not** persist the PDF itself (wastes disk, no reader uses it).
2. **`short_summary` field.** `load_documents()` → `_build_results()` in `retriever.py:156` accesses `p["short_summary"]` with `[...]` (not `.get()`). If the ingest payload omits this key, every retrieval involving the new doc will KeyError. Prompt does not mention it. Decision: auto-populate `short_summary` as the first ~200 chars of extracted text (or empty string); add defensive `.get()` fallback.
3. **`min_role` / `doc_type` / `sensitivity` enums.** Prompt says `<select>` with no values. Existing `min_role`: `analyst | vp | partner` (from `corpus/roles.json`). Existing `doc_type` values observed: `public_filing, research_note, press_release, financial_model, due_diligence, deal_memo, internal_memo` (+ others). Existing `sensitivity`: `low | medium | high`. Decision: validate `min_role` against `roles.json`; enumerate the other two to match existing corpus values so filters downstream stay consistent.
4. **Date format.** Existing corpus uses `YYYY-MM-DD`. Prompt says `date` field with no format. Decision: require `YYYY-MM-DD`; reject malformed dates with 400.
5. **Tags parsing.** Prompt says "tags (text)". Decision: comma-separated, trimmed, non-empty filter → list of strings.
6. **Duplicate filenames.** Two uploads with identical sanitized titles would collide on `.txt` path. Decision: `sanitize_filename()` appends `_<doc_id>` when the base filename already exists.
7. **Concurrent uploads.** No locking. For a demo this is acceptable, but two simultaneous requests could race on `metadata.json` write and `generate_next_doc_id()`. Decision: accept the race (documented), single `threading.Lock` around the critical section as low-cost belt-and-suspenders.
8. **PDF with no extractable text.** Scanned / image-only PDFs return empty string. Decision: if extracted text is empty or < N chars (pick 50), return 422 with an explanatory message instead of indexing an empty doc.
9. **PDF size limit.** Prompt silent. Decision: cap at 10 MB via `len(file_bytes)`; reject with 413 above.
10. **Superseded_by field.** Prompt lists `superseded_by=None` default but the form schema in STEP 2 does not include the field. Decision: omit from the form for this batch (ingest of freshly uploaded docs never supersedes existing ones in practice); keep the parameter in `ingest_document()` signature for programmatic callers.
11. **PDF library choice.** Prompt offers `pdfplumber OR PyPDF2`. `PyPDF2` is deprecated (replaced by `pypdf`). Decision: use `pdfplumber` (actively maintained, better layout handling, licensed MIT).
12. **`invalidate_caches()` placement.** Prompt says "In retriever.py, add `invalidate_caches()` that only resets `_bm25`." Verified correct: `load_persisted_index()` in `indexer.py:91` is called inside `retrieve()` on every request (no in-process FAISS cache), so rewriting `artifacts/querytrace.index` + `artifacts/index_documents.json` is sufficient for FAISS. BM25 is the only in-memory singleton. Embeddings *model* stays cached (corpus-independent).
13. **Verification asks not itemized.** Neither STEP 1 nor STEP 2 list acceptance tests (curl, pytest, Playwright). See verification plan below.
14. **Index rebuild UX.** Prompt says "Reindexing takes 5-15 seconds — show clear lng state" but doesn't say whether the request is synchronous or async. Decision: synchronous endpoint; the client shows a blocking loader. No background job, no WebSocket — matches MUST-A through MUST-C simplicity budget.
15. **No RBAC on `/ingest`.** Anyone can upload. Prompt says "No auth — this is a demo". Accept, but note in CLAUDE.md so reviewers don't flag it as missed.

---

## Hidden risks

### Backend
- **Module-level `_metadata` mutation.** `src/main.py:38` loads metadata once at startup and passes it to `run_pipeline()` on every request. If `/ingest` reassigns the module-level `_metadata`, closures in other threads may still see the old list. Safer: mutate the existing dict in place (`_metadata["documents"].append(entry)`) so all callers see the new entry.
- **`_evals_cache` reset.** Straightforward — `/evals` is cache-gated by a single module-level variable; resetting to `None` triggers a fresh run on next call. Does *not* affect current in-flight requests.
- **Full corpus re-embed per upload.** `build_index()` re-encodes every document, not just the new one. 13 docs + MiniLM on CPU ≈ 5-10s. Acceptable for demo; scales poorly.
- **File layout coupling.** Ingest must mirror the existing corpus contract exactly: `{id, file_name, title, type, date, min_role, sensitivity, superseded_by, tags, short_summary}`. Any missing field risks a downstream `[...]` access crash in `retriever._build_results`.
- **FAISS write atomicity.** `faiss.write_index` is not atomic — a crash mid-write leaves a corrupt file. `indexer.save_index` writes via `faiss.write_index(index, INDEX_PATH)` directly. For demo, accept; document as a known limitation.
- **Doc ID scheme.** `generate_next_doc_id()` must read existing `metadata.json`, find max `doc_NNN`, and emit the next. Must handle the (unlikely) case where the corpus is empty or IDs aren't zero-padded 3-digit.

### Frontend
- **Form validation.** If any field is empty or malformed, server returns 400/422. Frontend must render the error text clearly — existing error rendering patterns are in `renderSingleResult` error paths; reuse that style.
- **Blocking UI during reindex.** 5-15s sync wait. Button must be disabled; loader must be visible; existing mode-toggle must not permit navigation mid-upload (or must safely handle it).
- **Post-upload state.** After success, the corpus has a new doc but the current Single/Compare mode results still reflect pre-upload state. Decision: show a "✓ Uploaded & indexed — searchable now" toast; do *not* auto-refresh existing results. User can re-query.
- **Admin mode visibility.** Prompt says "Add fourth button in mode-toggle". This changes the header layout. Confirm it still fits on narrow viewports.

### Dependencies
- **`pdfplumber`** pulls `pdfminer.six` (large). Install time may be noticeable. Check Python 3.9 / LibreSSL compatibility.
- **`python-multipart`** is required for `File`/`Form` in FastAPI. Missing today.
- **`tiktoken`** already present; no action.
- **Pin-vs-unpinned.** Existing `requirements.txt` has no version pins. Match that style.

### Persistence / deploy implications
- **Disk writes in repo paths.** Every upload writes `corpus/documents/*.txt` and mutates `corpus/metadata.json` — both tracked in git. Running the demo on a dev machine dirties the working tree. Decision: add a note in CLAUDE.md under "Known non-blocking"; optionally add a `.gitignore` carve-out for post-seed docs (deferred).
- **Artifact writes.** `artifacts/querytrace.index`, `artifacts/index_documents.json`, `artifacts/bm25_corpus.json` are regenerated per upload. These *may* already be gitignored — verify (not in scope; note only).
- **Ephemeral filesystems.** Most container hosts (Vercel, Netlify, stock Cloud Run) have ephemeral disks. Uploaded docs would vanish on restart. This demo is assumed to be local-only. Call out in CLAUDE.md.
- **No backup / rollback.** If a bad ingest writes garbage into `metadata.json`, recovery is manual (git checkout). Acceptable for demo.

### Tests
- **New backend code without unit tests breaks precedent.** MUST-A IDEA 2 added code and left tests intact because it was purely additive `Optional` fields. IDEA 8 adds a new endpoint with side effects — needs unit tests for `ingest.py` helpers and at least a happy-path integration test for `/ingest`.

---

## Execution order

### Phase 0 — Dependencies
1. Add `pdfplumber` and `python-multipart` to `requirements.txt`.
2. `pip install -r requirements.txt`.
3. Smoke-test import in a Python shell (fail-fast on Python 3.9 / LibreSSL surprises).

### Phase 1 — Backend helpers (`src/ingest.py`)
4. `extract_text_from_pdf(file_bytes) -> str` using `pdfplumber`. Guard empty extraction.
5. `generate_next_doc_id(metadata_path) -> str` — read JSON, parse `doc_NNN`, return `doc_<max+1:03d>`.
6. `sanitize_filename(title) -> str` — lowercase, `\w`-only, max length 60, fallback to `document` if empty. Path traversal rejection by construction.
7. `ingest_document(pdf_bytes, title, date, min_role, doc_type, sensitivity, tags, superseded_by=None) -> dict` — orchestrates: extract → validate → pick id → write `.txt` → append metadata → save JSON → rebuild index + BM25. Returns the new entry dict for the caller to surface.
8. Module-level `threading.Lock()` guarding the critical section (doc_id generation + metadata.json write + reindex).

### Phase 2 — Endpoint wiring (`src/main.py` + `src/retriever.py`)
9. `invalidate_caches()` added to `retriever.py` — resets `_bm25 = None` only.
10. `POST /ingest` in `main.py`: multipart form → validation (role enum, date regex, size cap, empty text guard) → `ingest_document(...)` → mutate `_metadata["documents"]` in place → `retriever.invalidate_caches()` → `_evals_cache = None` → return `{status, doc_id, title, ...}`.
11. Pydantic response model (new: `IngestResponse`) with fields the frontend actually consumes.

### Phase 3 — Frontend Admin mode
12. `index.html`: fourth `.mode-btn data-mode="admin"`; new `<section id="admin-section" hidden>` containing the form with file/title/date/min_role/doc_type/sensitivity/tags inputs + submit button + status area.
13. `app.js`: extend `switchMode()` with `isAdmin` branch (hide all other panels, hide query form + search section); `uploadDocument()` function posting `FormData` to `/ingest`; loading / success / error rendering.
14. `styles.css`: `.admin-section`, `.admin-form`, `.admin-field`, `.admin-status` (loading / success / error variants).

### Phase 4 — Tests
15. `tests/test_ingest.py`: unit tests for `generate_next_doc_id`, `sanitize_filename` (including path-traversal attempts), `extract_text_from_pdf` (with a tiny fixture PDF or mocked `pdfplumber`), and an integration smoke via TestClient posting a small PDF.
16. Re-run `python3 -m pytest -q` — expect 149 → ~155 passed (exact count depends on ingest test surface), 14 skipped unchanged.

### Phase 5 — Verification (browser)
17. Playwright: switch to Admin tab → fill form with fixture PDF → submit → await success → switch to Single mode → query matches new doc → confirm new doc appears in results.

### Phase 6 — Docs
18. Update `CLAUDE.md`: new `POST /ingest` endpoint, new frontend mode, new deps, local-only persistence caveat.
19. Update `docs/HANDOFF.md`: Session 25 entry (MUST-D / IDEA 8).
20. Finalize this plan file (this document) in `docs/plans/`.

---

## Acceptance criteria

- `pip install -r requirements.txt` succeeds on Python 3.9 / LibreSSL 2.8.3 with `pdfplumber` and `python-multipart` added.
- `POST /ingest` with a valid multipart request returns 200 and a JSON body containing the new `doc_id`.
- Sending an empty-text PDF returns 422 with a message indicating no extractable text.
- Sending a file >10 MB returns 413.
- Sending an invalid `min_role` (e.g., `"god"`) returns 400 listing valid roles.
- After a successful upload, `POST /query` for a term present in the PDF returns the new `doc_id` in the results.
- `GET /evals` after an upload recomputes (not cached from before upload).
- Existing 149 tests still pass. New ingest tests pass.
- Admin tab renders without layout regression on the existing three modes.
- All four existing Playwright scenarios (Analyst wall, VP deal view, Partner view, P3 compare-header assertion) still pass.
- No new JS console errors in any mode.
- `escapeHTML` applied to all user-origin strings rendered back to the DOM (PDF title, tags, error messages).

---

## Verification commands

```bash
# Phase 0
pip install -r requirements.txt
python -c "import pdfplumber, multipart; print('OK')"

# Phase 2 smoke
python3 -m uvicorn src.main:app &
curl -X POST http://localhost:8000/ingest \
  -F "file=@/path/to/test.pdf" \
  -F "title=Test Upload" \
  -F "date=2024-05-01" \
  -F "min_role=analyst" \
  -F "doc_type=research_note" \
  -F "sensitivity=low" \
  -F "tags=test,smoke"

# After successful upload
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" \
  -d '{"query":"<term from uploaded PDF>","role":"analyst"}'

# Phase 4
python3 -m pytest tests/test_ingest.py -v
python3 -m pytest -q   # full suite

# Phase 5 — Playwright via webapp-testing skill
```

---

## Docs to update at end of batch

- `CLAUDE.md` — Admin mode description, `POST /ingest` endpoint section, new dependencies line, local-only persistence caveat.
- `docs/HANDOFF.md` — Session 25 (MUST-D / IDEA 8) entry; update "Current State" and "Remaining Tasks".
- `docs/plans/2026-04-17-must-d-idea-8-plan.md` (this file) — finalize with commit SHA and verification evidence.
- No changes to `docs/plans/2026-04-16-ideas-execution-plan.md` (different batch scope).
- No changes to `docs/plans/2026-04-17-must-c-ideas-4-6-plan.md`.

---

## Residual risks accepted without mitigation

- FAISS write not atomic (crash mid-rebuild → corrupt index).
- Race on concurrent uploads (belt-and-suspenders lock in place; not a distributed solution).
- Repo pollution (uploaded docs dirty the working tree).
- Ephemeral filesystem on deploy (demo is local-only).
- No RBAC on `/ingest` (explicitly out of scope per prompt).
- No delete / edit path (explicitly out of scope per prompt).

All are documented; none are demo-blocking.

---

## Execution outcome (2026-04-17)

Status: **EXECUTED**. Batch landed on `codex/must-a-idea1-2` as commit `a6d1daa` (12 files, +1323 / −11).

Evidence:
- Tests: `python3 -m pytest -q` → **172 passed, 14 skipped, 0 failed** (149 → 172; +23 new ingest tests).
- Uvicorn smoke: server starts clean on :8000, `/docs` → 200.
- curl end-to-end: 415 (non-PDF), 400 (bad role), 400 (bad date), 422 (unreadable PDF), 413 (oversize), 200 (happy path with reportlab-generated PDF). All messages match spec.
- Search-after-ingest: `POST /query` for a sentinel phrase in the freshly-ingested doc returned that doc ranked **#1** — confirms `retriever.invalidate_caches()` + reindex path.
- Playwright Admin flow (via `webapp-testing` skill): Admin tab → form-fill → upload `/tmp/real.pdf` → status reached `admin-status-success` with `Indexed doc_014 — Playwright Admin Flow Doc. Corpus now contains 14 documents.`
- Corpus/artifacts rolled back to 12-doc baseline after verification.

Deviations from plan: none significant.
- Added 23 tests (plan estimate was "~155 passed"); final count is 172 passed.
- `metadata_path` / `corpus_dir` in `ingest_document()` and `generate_next_doc_id()` are `Optional[str] = None` with runtime fallback to module-level constants (required for test monkeypatching of the module-level paths).
- `IngestResponse` fields match the plan; no extra fields added.
