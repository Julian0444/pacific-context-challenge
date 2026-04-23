# UI-A Execution Plan — Demo Data Cleanup (remove `doc_013` / `agenda.txt`)

Date: 2026-04-22
Branch: `codex/must-a-idea1-2`
Scope: Corpus + artifacts + docs/copy alignment. **No `src/` code changes.** No new tests. No new deps.
Out of scope: `roadmap.md`. Any logic changes. Any new features.

---

## 1. Executive summary

The corpus has accidentally been left at **13 documents** after a MUST-D ingest verification probe (see `docs/HANDOFF.md:702–708`) that was *supposed* to be rolled back to 12. The leftover doc is `doc_013` / `agenda.txt` / title `"Agenda"` / `min_role: partner` / `sensitivity: confidential`, with a body about "Kailash / OmniClaude / OmniCursor" — entirely unrelated to the Atlas Capital / Meridian Technologies "Project Clearwater" narrative the rest of the corpus tells.

**Verdict: remove `doc_013`.** It is unambiguous test contamination, not authored content. It contradicts every existing demo, doc, and copy claim ("12 documents", "7 blocked"), and pollutes partner-rank queries with an off-narrative confidential doc that makes the demo look broken.

The fix is mechanical: delete the metadata entry + `.txt` file, rebuild the three `artifacts/*` files, re-measure the four evaluator metrics that drift, and verify the existing `12 docs` / `7 blocked` copy in five docs is still accurate (it should be — that copy was authored against the intended baseline).

---

## 2. Preflight findings (verified this step)

### `doc_013` is verification-smoke contamination

- `docs/HANDOFF.md:702` documents the exact ingest that produced `doc_013` / `agenda.txt` (`total_documents: 13`) and a "Rollback: Corpus restored to pre-test state (12 docs, 12 .txt files, artifacts/* restored from snapshots)" claim at line 708 — **the rollback was not actually applied** to the working tree.
- `docs/backendSummary*.md:7,9,82–83,413–414` calls the contamination out as a CR-1 issue and notes `corpus/documents/agenda.txt` untracked + `corpus/metadata.json` + `artifacts/*` modified.
- `evals/test_queries.json` references `doc_001`–`doc_012` only. No `expected_doc_ids` / `forbidden_doc_ids` mention `doc_013`. **No `evals/` change needed.**
- All five demo-facing docs (CLAUDE.md, README.md, demo.md, summaryUserExp.md, docs/backendSummarySpanish.md) were authored assuming **12 docs** and the **7-blocked-for-analyst** invariant. Removing `doc_013` *restores* the documented state.

### Tests do not hardcode `doc_013` or the count

- `tests/test_retriever.py::test_top_k_clamped_to_corpus_size` already reads `corpus_size` dynamically from `metadata.json` (line 74) — **`docs/backendSummary*.md` is stale on this point** (it still describes a hardcoded `assert len(results) == 12`, fixed since).
- `tests/test_retriever.py:129` asserts `hybrid[0]["doc_id"] == "doc_012"` for a customer-concentration query — unrelated to doc_013.
- No other test references `doc_013` or asserts on `len(corpus) == 12|13`.

### Stats that will drift after removal

- `doc_013` is `min_role: partner`, so on a typical analyst Compare query it appears in `blocked_by_permission`, inflating analyst `blocked_count` from the documented **7** to **8**, and inflating `avg_blocked_count` in the evaluator.
- `doc_013` is partner-only, so on partner queries it can join the `included` set; on analyst/VP queries it stays blocked. Net effect: `avg_blocked_count`, `avg_dropped_count`, `avg_budget_utilization`, `avg_context_docs`, `avg_freshness_score`, possibly `precision@5` (drops if doc_013 displaces an expected doc in the partner-role queries q006, q008).
- `recall` should remain 1.0 (no expected doc is doc_013); `permission_violation_rate` should remain 0% (RBAC unchanged).

### Files that encode corpus assumptions (full audit)

| File | What it claims | Action after cleanup |
|---|---|---|
| `corpus/metadata.json` | Currently 13 entries | **Remove `doc_013` block** (lines 233–246) |
| `corpus/documents/agenda.txt` | Exists | **Delete file** |
| `artifacts/querytrace.index` | 13-vector FAISS | **Rebuild** |
| `artifacts/index_documents.json` | 13 entries | **Rebuild** |
| `artifacts/bm25_corpus.json` | 13 tokenized rows | **Rebuild** |
| `README.md:5` | "Corpus: 12 documents…" | Verify still accurate (yes) |
| `README.md:30` | "Analyst wall … shows 7 blocked" | Verify still accurate (expect yes) |
| `README.md:129–134` | precision@5=0.3000, recall=1.0000, perm_viol=0%, avg_blocked=3.38, avg_stale=1.62, avg_budget_util=53% | **Re-measure all six and update if drifted** |
| `README.md:145` | "384-dim, 12 vectors" | Verify "12 vectors" after rebuild |
| `CLAUDE.md` (evaluator section) | "Current metrics: precision@5=0.3000, recall=1.0000, permission_violation_rate=0%" | **Re-measure; update precision if drifted** |
| `CLAUDE.md` (corpus & access control) | Two stale pairs — unchanged | Verify (yes) |
| `demo.md:9` | "doce documentos" | Verify (yes) |
| `demo.md:92,93,161` | "7 blocked", "1 stale" Single mode summary | Verify against fresh `/compare` analyst run (expect 7) |
| `demo.md:301,302` | "Precision@5 = 0.30", "12 documentos" | Update precision if drifted |
| `summaryUserExp.md:37,42,45,156,234,240,242` | "12 documentos", per-role visibility (5/10/12) | Verify still accurate (yes) |
| `summaryUserExp.md:324,331,341,345` | "5 docs, 571 tokens, … 7 blocked, 1 stale", per-role blocked counts (analyst 7 / VP 2 / partner 0), "Precision@5 de 0.30" | Verify; update precision if drifted |
| `docs/backendSummarySpanish.md:7,9,413,414,486,496` | Describes 13-doc state and a stale `== 12` test failure | **Update to reflect cleaned state and dynamic-corpus test** |
| `docs/backendSummary.md:7,9,82,83,154` | Same as Spanish twin | **Update in parallel** |
| `docs/HANDOFF.md:702–708` | "Rollback: Corpus restored…" | **Add a closing note** that the rollback was reapplied 2026-04-22 (or leave historical, see §6 risks) |
| `.claude/settings.local.json:15` | Curl allowlist for `Agenda` probe | **Cosmetic — leave as-is** (no functional impact) |

---

## 3. Execution shape (do NOT execute in this preflight)

**Step 1 — Remove contamination (one commit's worth of work).**
1. Delete entry `doc_013` from `corpus/metadata.json` (drop the trailing comma on `doc_012`'s closing brace).
2. Delete `corpus/documents/agenda.txt`.
3. Run `python3 -m src.indexer`. Confirms three rewrites:
   - `artifacts/querytrace.index` (FAISS, 384-dim, **12 vectors**)
   - `artifacts/index_documents.json` (12 entries, ordered to match FAISS rows)
   - `artifacts/bm25_corpus.json` (12 tokenized rows)

**Step 2 — Re-measure evaluator metrics.**
4. Run `python3 -m src.evaluator` (default `--k 5 --top-k 8`). Capture the printed aggregate block.
5. Diff against the documented baseline (README.md:130–133 + CLAUDE.md). Specifically check:
   - `precision@5` (currently 0.3000 — could change if doc_013 displaced an expected doc in q006/q008 partner queries; otherwise stable)
   - `recall` (expect 1.0000 unchanged)
   - `permission_violation_rate` (expect 0% unchanged)
   - `avg_blocked_count` (currently 3.38 — **will drop** because doc_013 was contributing partner-blocked count on 6/8 analyst+vp queries)
   - `avg_stale_count` (expect 1.625 unchanged — doc_013 has no `superseded_by`)
   - `avg_budget_utilization` (currently ~0.53 — may shift slightly because the included set composition changes on partner queries)
   - `avg_context_docs`, `avg_total_tokens`, `avg_freshness_score` (mentioned in CLAUDE.md as "current metrics" lineage; re-read post-run)

**Step 3 — Verify UI scenarios end-to-end.**
6. Boot server, run the three demo Compare scenarios via `/compare` and confirm: Analyst wall = 7 blocked in `permission_aware`/`full_policy`, VP deal view = ~2 blocked, Partner view = 0 blocked.
7. Run a `naive_top_k` ARR query at `top_k=12` and confirm `len(context) ≤ 12` (cap is now corpus size).

**Step 4 — Update docs/copy.**
8. Update only the lines that drifted. Targets: README.md:130–133 (and 145 if rebuild count differs), CLAUDE.md evaluator metric block, demo.md:301 / summaryUserExp.md:345 if `precision@5` shifted, `docs/backendSummary*.md` to reflect cleaned corpus + already-fixed dynamic-count test.
9. `docs/HANDOFF.md:702–708`: add a small "2026-04-22: rollback reapplied" addendum (preferred — keeps historical trace) rather than rewriting the original record.

**Step 5 — Final verification.**
10. `python3 -m pytest tests/ -v` → must be green (current baseline 172 passed / 14 skipped per `2026-04-18-nice-a-ideas-12-13-plan.md:5`; `test_top_k_clamped_to_corpus_size` should now pass against `corpus_size == 12`).

---

## 4. Acceptance criteria

- `corpus/metadata.json` has exactly 12 entries (`doc_001`–`doc_012`); JSON parses cleanly.
- `corpus/documents/` has exactly 12 `.txt` files; `agenda.txt` absent.
- `artifacts/index_documents.json` has 12 entries; FAISS index has 12 vectors.
- `python3 -m pytest tests/ -v` → **all green**, 14 skipped (legacy).
- `python3 -m src.evaluator` runs without error and prints the aggregate block.
- `permission_violation_rate == 0%` and `recall == 1.0000` post-cleanup (non-negotiable invariants).
- `precision@5` re-measured; if drifted, README.md + CLAUDE.md + demo.md + summaryUserExp.md updated to the new value.
- `avg_blocked_count`, `avg_stale_count`, `avg_budget_utilization`, `avg_context_docs`, `avg_total_tokens`, `avg_freshness_score` re-measured; README.md updated to new values where they appear.
- Compare scenario verification: analyst wall query returns `blocked_count == 7` in `permission_aware` and `full_policy`; partner view returns `blocked_count == 0`.
- `naive_top_k` ARR query at `top_k=12` returns `len(context) <= 12` (proves index is no longer 13 wide).
- No `grep -rn "doc_013\|agenda\.txt"` hit in `corpus/`, `artifacts/`, `src/`, `tests/`, `frontend/`, or any non-historical doc. Historical mentions in `docs/HANDOFF.md:702–708` and `docs/plans/*.md` may remain as audit trail.

---

## 5. Verification commands (explicit, ordered)

```bash
# A. Pre-cleanup snapshot (capture for diff)
python3 -m src.evaluator > /tmp/evaluator_pre.txt
python3 -c "import json; print(len(json.load(open('corpus/metadata.json'))['documents']))"
ls corpus/documents/ | wc -l

# B. Cleanup (executed in implementation step, not here)
#    - edit corpus/metadata.json (drop doc_013 block)
#    - rm corpus/documents/agenda.txt
python3 -m src.indexer

# C. Post-cleanup state checks
python3 -c "import json; print(len(json.load(open('corpus/metadata.json'))['documents']))"   # → 12
python3 -c "import json; print(len(json.load(open('artifacts/index_documents.json'))))"      # → 12
ls corpus/documents/ | wc -l                                                                  # → 12

# D. Consistency greps (must return zero hits in code/runtime paths)
grep -rn "doc_013\|agenda\.txt" corpus/ artifacts/ src/ tests/ frontend/ evals/
grep -rn "doc_013\|agenda\.txt" CLAUDE.md README.md demo.md summaryUserExp.md
# (docs/HANDOFF.md and docs/plans/ may legitimately retain historical references)

# E. Test + evaluator
python3 -m pytest tests/ -v
python3 -m src.evaluator > /tmp/evaluator_post.txt
diff /tmp/evaluator_pre.txt /tmp/evaluator_post.txt   # inspect drift, update docs accordingly

# F. UI scenarios (server up: python3 -m uvicorn src.main:app --reload)
curl -s -X POST http://localhost:8000/compare \
  -H "Content-Type: application/json" \
  -d '{"query":"What is Meridian'\''s ARR growth rate and net revenue retention?","role":"analyst","top_k":8}' \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['results']; \
    print({k: r[k]['decision_trace']['metrics']['blocked_count'] for k in r})"
# Expect: {'naive_top_k': 0, 'permission_aware': 7, 'full_policy': 7}

curl -s -X POST http://localhost:8000/compare \
  -H "Content-Type: application/json" \
  -d '{"query":"What are the financial model assumptions for Project Clearwater?","role":"vp","top_k":8}' \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['results']; \
    print({k: r[k]['decision_trace']['metrics']['blocked_count'] for k in r})"
# Expect: naive=0, permission_aware ~2, full_policy ~2 (partner-only docs blocked)

curl -s -X POST http://localhost:8000/compare \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the IC recommendation and LP update for Meridian?","role":"partner","top_k":8}' \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['results']; \
    print({k: r[k]['decision_trace']['metrics']['blocked_count'] for k in r})"
# Expect: {'naive_top_k': 0, 'permission_aware': 0, 'full_policy': 0}

# G. Naive cap check
curl -s -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query":"ARR growth","role":"partner","top_k":12,"policy_name":"naive_top_k"}' \
  | python3 -c "import sys,json; print(len(json.load(sys.stdin)['context']))"
# Expect: <= 12
```

---

## 6. Risks

1. **Frontend hardcoded "7" copy on the onboard card** (per `docs/plans/2026-04-17-should-a-ideas-9-10-plan.md:23,177`) — already documented as seed-corpus-specific. Cleanup *restores* that "7" claim, so no risk; just verify post-cleanup that analyst Compare still shows 7 blocked.
2. **`docs/HANDOFF.md` historical record** — rewriting line 708 ("Rollback: Corpus restored…") would erase audit trail of the original incident. Prefer an additive 2026-04-22 addendum.
3. **Plan files under `docs/plans/`** legitimately reference `doc_013`/`agenda.txt`/13-doc state as a historical record (`2026-04-17-must-d-idea-8-plan.md`, `2026-04-17-should-a-ideas-9-10-plan.md`). **Do not rewrite plan history.**
4. **Pytest baseline drift** — recent batch summaries claim 172/14/0; `docs/backendSummary*.md:7` claims 171/1/14 (one failure). Re-baseline pre-cleanup (`pytest -v`) to pin the actual current count before claiming "stayed green".
5. **`avg_budget_utilization` re-measure may show small float drift** even where it doesn't change semantically (e.g., 53% → 52% rounding). Update the documented value to whatever the post-cleanup run prints; don't argue the delta.
6. **`precision@5` could drop on partner queries** if `doc_013` was previously displacing a correct doc — the new value could go up *or* down. Both are fine; the metric is not a regression target, just a documented number.
7. **No frontend code change needed**, but if any `data-query`/`data-role` onboard card copy implicitly depends on the "7 blocked" outcome, double-check via §5.F.
8. **`.claude/settings.local.json:15`** carries an old `curl … "Agenda"` allowlist entry. Harmless; leave alone unless asked.
9. **Render deploy** — `artifacts/*` are committed and read at boot. The cleanup commit must include the rebuilt artifacts or production will continue serving 13 docs.

---

## 7. Docs to update at the end

| Doc | Likely changes |
|---|---|
| `README.md` | Verify line 5 / 30 / 145 (12 docs / 7 blocked / 12 vectors); rewrite the metric block at lines 129–134 with re-measured numbers. |
| `CLAUDE.md` | Update the "Current metrics: precision@5=0.3000, recall=1.0000, permission_violation_rate=0%" line in the evaluator section if precision drifts. |
| `demo.md` | Verify §4 Demo A "7 blocked" copy and Demo D "5 docs, ~570 tokens, … 7 blocked, 1 stale" still hold; update §8 part `Precision@5 = 0.30` if drifted. |
| `summaryUserExp.md` | Verify "12 documentos" and "7/2/0 blocked" per role; update line 345 precision if drifted. |
| `docs/backendSummarySpanish.md` | Remove "13 documentos" / "agenda.txt untracked" / "stale `== 12` assertion" CR-1 callouts (lines 7, 9, 413–414, 486, 496); reflect cleaned 12-doc state. |
| `docs/backendSummary.md` | Mirror the Spanish-twin updates. |
| `docs/HANDOFF.md` | Add a `2026-04-22 — UI-A: rollback reapplied; corpus is 12 docs again.` addendum near §702–708 rather than mutating the original record. |
| `docs/plans/` | **Do not edit** prior plan files; this plan documents the cleanup. |
| `.claude/settings.local.json` | Leave as-is. |

---

## 8. Out of scope (explicit non-goals)

- Adding a new "do not allow Admin re-ingestion in dev" guard.
- Refactoring evaluator metric printing.
- Touching `roadmap.md`.
- Changing tests, fixtures, models, or pipeline behavior.
- Adding `prefers-reduced-motion` or other frontend polish.
- Changing the `ALLOW_INGEST` env semantics or the `/ingest` HTTP behavior.
