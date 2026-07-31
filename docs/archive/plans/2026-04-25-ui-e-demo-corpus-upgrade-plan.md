# UI-E Execution Plan — Demo Corpus Narrative Upgrade

Date: 2026-04-25
Branch: `codex/must-a-idea1-2`
Scope: Corpus narrative content, metadata, eval queries, frontend copy, demo docs, rebuilt artifacts. No pipeline logic changes.

---

## 1. Goal

Make the demo corpus more visually obvious in a short screen-recorded demo:

- More sensitive partner-only material visible in No Filters and blocked by RBAC/Full.
- A governance stale pair where the recommendation changes from DEFER to APPROVE.
- A public rumor source that conflicts with internal valuation diligence.
- A VP-level CTO departure memo that makes the integration-risk story easier to explain.

The implementation keeps the Atlas Capital / Meridian Technologies Project Clearwater narrative intact and expands the corpus from 12 to 16 authored docs.

---

## 2. Corpus Changes

### New documents

| ID | File | Role | Purpose |
|---|---|---|---|
| `doc_013` | `atlas_meridian_legal_diligence_regulatory_inquiry.txt` | partner | Legal diligence memo: pending regulatory inquiry into revenue recognition. |
| `doc_014` | `atlas_ic_memo_draft_v09_meridian_defer.txt` | partner | Superseded IC draft recommending DEFER; stale pair to final approval memo `doc_010`. |
| `doc_015` | `fintech_press_meridian_500m_valuation_rumor.txt` | analyst | Public article with rumored $500M valuation, contrasting internal $340M diligence. |
| `doc_016` | `atlas_meridian_cto_departure_context_memo.txt` | vp | Structured CTO departure and engineering retention memo. |

Each new doc is 600-1500 chars and puts its demo hook in the first 200 chars so the 500-char indexer excerpt is useful in cards.

### Modified existing documents

- `doc_010` IC memo now begins with `PARTNER-ONLY · DO NOT DISTRIBUTE`.
- `doc_011` LP update now begins with `PARTNER-ONLY · DO NOT DISTRIBUTE`.
- `doc_011` also received a one-line key update near the top so the first 500 chars still carry the Project Clearwater pipeline fact.

Core facts in both existing documents were preserved.

---

## 3. Metadata And Access Model

Post-UI-E distribution:

- Analyst: 6 of 16 docs.
- VP: 12 of 16 docs.
- Partner: 16 of 16 docs.

Stale/superseded pairs:

- `doc_002 → doc_003` (research note Q3 → Q4 revision)
- `doc_007 → doc_008` (financial model v1 → v2)
- `doc_014 → doc_010` (IC draft defer recommendation → final approval memo)

---

## 4. Evals

`evals/test_queries.json` now has 12 queries:

- Original 8 retained and updated where needed.
- New q009: legal/regulatory risk (`doc_013`).
- New q010: draft vs final IC recommendation (`doc_014`, `doc_010`).
- New q011: public valuation rumor vs internal diligence (`doc_015`, `doc_008`).
- New q012: CTO departure and engineering retention risk (`doc_016`, `doc_009`).

Fresh evaluator aggregate after rebuild:

```text
Queries run: 12 (failed: 0)
Avg Precision@5: 0.3333
Avg Recall: 1.0000
Permission violation rate: 0%
Avg context docs: 11.83
Avg total tokens: 1448.0
Avg freshness score: 0.807
Avg blocked count: 4.17
Avg stale count: 2.08
Avg dropped count: 0.0
Avg budget util: 71%
```

No `dropped_by_budget` claim is made; the corpus upgrade did not force drops under the current 2048-token budget.

---

## 5. Verification

Commands run:

```bash
.venv/bin/python -m src.indexer
.venv/bin/python -m src.evaluator
.venv/bin/python -m pytest
```

Results:

- Indexer loaded 16 documents and wrote 16 FAISS/BM25 rows.
- Evaluator ran 12 queries with 0 failures, 0 permission violations, and recall 1.0000.
- Pytest: 172 passed, 14 skipped, 4 warnings.

Scenario smoke via FastAPI TestClient:

```text
analyst ARR:
  naive_top_k=(included 16, blocked 0, stale 0)
  permission_aware=(included 6, blocked 10, stale 0)
  full_policy=(included 6, blocked 10, stale 1)

vp financial model:
  permission_aware/full_policy blocked 4 partner-only docs
  full_policy stale 2

partner IC + LP:
  blocked 0 across policies
  full_policy stale 3, including doc_014 -> doc_010

partner draft-vs-final query:
  context includes doc_014 with superseded_by doc_010
```

Artifact excerpt checks:

- `doc_010` first 500 chars still include the approval recommendation and `$340 million`.
- `doc_011` first 500 chars include the Project Clearwater advanced-diligence update.
- New docs' first 500-char excerpts include their intended demo hooks.

---

## 6. Files Touched

- `corpus/documents/*.txt`
- `corpus/metadata.json`
- `artifacts/querytrace.index`
- `artifacts/index_documents.json`
- `artifacts/bm25_corpus.json`
- `evals/test_queries.json`
- `frontend/app.js`
- `frontend/index.html`
- `README.md`
- `CLAUDE.md`
- `demo.md`
- `summaryUserExp.md`
- `script_es.md`
- `script_en.md`
- `docs/backendSummary.md`
- `docs/backendSummarySpanish.md`
- `docs/HANDOFF.md`
- `tests/test_main.py`
- `tests/test_evaluator.py`
- `src/pipeline.py` (comment only)

---

## 7. Residual Risks

- Historical docs and prior plan files still mention old 12-doc / 7-blocked states as history. Live docs and frontend copy were updated.
- Compare No Filters still returns `top_k * 3` candidates because that pre-existing behavior is pipeline logic and out of scope for UI-E.
- Budget drops remain zero in current evals; do not demo `Dropped` as newly improved.
