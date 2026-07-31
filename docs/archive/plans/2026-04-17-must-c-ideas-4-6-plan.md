# MUST-C Execution Plan — IDEA 4 + IDEA 6

Date: 2026-04-17
Branch: `codex/must-a-idea1-2`
Scope: Frontend-only explainability layer — Decision Trace natural-language summary (IDEA 4) + Evals narrative banner & query-text column (IDEA 6).
Preserves batch order. No backend changes. No new tests required (frontend behavior verified via Playwright, consistent with MUST-A/B1/B2 precedent).

---

## Executive summary

Two prompts that translate numbers into prose. IDEA 4 adds a paragraph above the existing chips in `buildTracePanelHTML` (app.js:769). IDEA 6 adds a narrative banner + per-card hints + real query text to `renderEvals` (app.js:685). Both are additive, conditionally rendered, and must not regress existing rendering in either Single or Compare mode. Backend `/evals` per-query response already carries `query` text (`src/evaluator.py:119`) — no API change needed for the table enrichment.

---

## Missing / weak areas in the prompts (call-outs, not blockers)

1. **REQUIRED_ROLES phrasing (IDEA 4 blocked sentence).** Prompt says "cannot access REQUIRED_ROLES-level materials" but does not define how to derive it from multiple blocked rows with mixed `required_role` values. Decision needed: deduplicate the set (e.g., "vp- and partner-level") vs. pick the highest rank. Default to deduped comma-joined set; document the choice.
2. **PENALTY source (IDEA 4 stale sentence).** Prompt uses `PENALTY×` singular. If `demoted_as_stale.length > 1`, phrase must handle multiple docs. Default: one sentence per stale doc, or a single compound sentence if 2+ exist. Cap at 2 in the summary; additional docs remain visible as chips below.
3. **Compare-mode conciseness rule (IDEA 4).** "More concise" is unquantified. Define: in Compare mode, drop the per-doc stale-ID parenthetical and the budget-percentage clause; keep it to one short sentence per non-zero category.
4. **Typos in source prompt.** "gng" (tooltip), "rey" (hint) — treat as "generating"/"recency" respectively. Call out explicitly when writing strings.
5. **Budget-tier thresholds (IDEA 6).** `<60% efficient / 60–80% moderate / >80% heavy` — boundaries implicit; treat `<60` as `< 0.60`, `60–80` as `[0.60, 0.80]`, `>80` as `> 0.80`.
6. **Zero-query edge case (IDEA 6).** If `queries_run === 0` or `queries_failed > 0`, the narrative should not claim "Zero permission violations across 0 test queries." Guard: skip narrative or emit a single "No eval data" line.
7. **Recall-not-1.0 case (IDEA 6).** Prompt only handles `avg_recall === 1.0`. Add a low-key fallback: "Recall: X.XX — some expected documents were missed" so the narrative doesn't silently drop the sentence in regressions.
8. **Query-text column width (IDEA 6 #3).** Prompt says "alongside query ID badge" but the table already has 12 columns. Either keep it in the `Query` cell (id badge + truncated text stacked) or add a `.evals-qid` badge + inline text in the same cell. Default: same cell, badge + text with 50-char truncation and `title` attr showing full query.
9. **Verification asks not itemized.** Neither prompt lists Playwright assertions. See verification plan below.
10. **`escapeHTML` on all dynamic strings.** Summary paragraph and hints must pass role names, doc_ids, and query text through `escapeHTML` — existing helper in app.js. Call out explicitly to avoid XSS regression (same class of issue fixed in Session 18).

---

## Edge cases in explainability / metrics UX

- **All-zero trace (Full Pipeline, permissive query):** blocked=0, stale=0, dropped=0. Summary must not emit empty clauses. Single sentence: "N documents were included (X tokens, Y% of budget). No documents were dropped by budget." (per prompt) — blocked/stale omitted entirely.
- **Naive policy trace:** blocked_count=0 by construction (filter disabled), `avg_freshness_score` may be 0/NaN. Summary must not claim "your role … cannot access" when filtering is off. Gate the blocked sentence on `blocked_count > 0`, not on role. Already prompt-compliant.
- **Empty context (all docs blocked or dropped):** `included=0`. Sentence must be grammatical ("0 documents were included" reads odd). Consider: if `included_count === 0`, render "No documents made it into context (0 tokens)."
- **Compare mode, 3 panels open simultaneously:** three paragraphs stack vertically; column is ~33% viewport width. Paragraph must wrap cleanly at 120-ch snippets width. CSS: no `max-width` override that beats column width.
- **Tooltip collisions:** adding `title=` to `.trace-numbers` spans works on desktop; mobile has no hover. Acceptable — tooltips are supplemental, the summary paragraph is primary.
- **Narrative banner with `permission_violation_rate > 0`:** `fmtPct` already returns `"X.X%"`. Append the queries-run count for context so "Warning: 12.5% had violations" doesn't float without denominator.
- **Metric card hint rendering:** current card is two spans (label + value). Adding a third span with smaller text must not break `animation-delay` or grid layout. Use a stacked flex; preserve existing `.metric-card` rules.
- **Budget tooltip text "2048-token budget":** Hard-coded number from prompt. If token budget is ever overridden via policy (`resolve_policy` signature takes `top_k` but not budget today), this becomes stale. Accept for now — matches `DEFAULT_TOKEN_BUDGET` in `policies.py`.

---

## Execution order (preserves batch intent)

Order is **IDEA 4 → IDEA 6** exactly as requested. No dependency forces re-order: both are independent frontend additions touching different functions. Within each idea, apply in this sub-order to minimize diff churn:

**IDEA 4**
1. Add `buildTraceSummary(trace, userRole, compact)` helper above `buildTracePanelHTML`.
2. Insert `<div class="trace-summary">` at the top of `.trace-body` in `buildTracePanelHTML`.
3. Add `title=` attributes on the four existing `.trace-numbers`/budget elements.
4. Add `.trace-summary` CSS rules (+ optional `.trace-summary strong`).
5. Wire `userRole` through call sites: `renderSingleResult` → `buildTracePanelHTML` and `buildCompareColumnHTML` → `buildTracePanelHTML`. (`userRole` currently not threaded in — needed for the "your role (ROLE)" clause. Low-risk signature extension with default `null`.)

**IDEA 6**
6. Add `METRIC_HINTS` object or inline `hint` field on each card entry in `renderEvals`.
7. Update card template to render `.metric-card-hint` span.
8. Add `buildEvalsNarrative(agg)` helper returning paragraph HTML (guarded on `queries_run > 0`).
9. Prepend `<div class="evals-narrative">` before `.metrics-grid`.
10. Update table body: Query cell becomes `<span class="evals-qid">${id}</span> <span class="evals-qtext">${truncated}</span>` with `title=` full query.
11. Add CSS: `.evals-narrative`, `.metric-card-hint`, `.evals-qid`, `.evals-qtext`.

---

## Acceptance criteria

### IDEA 4 — Decision Trace narrative

- `<div class="trace-summary">` renders as the first child of `.trace-body` in both Single and Compare modes.
- Paragraph is composed from up to four sentences (included, blocked, stale, dropped) with the documented conditional rules; never contains empty clauses or double spaces.
- `userRole` substituted correctly in the blocked sentence (e.g., "your role (analyst) cannot access vp-level materials"). `escapeHTML` applied to role names and doc IDs.
- Existing trace chips and `.trace-metrics-strip` render unchanged below the summary.
- Four `title=` tooltips present: avg score, avg freshness, ttft, Budget label. Typos from prompt (`gng`, `rey`) corrected to readable strings.
- Compare mode summary is demonstrably shorter than Single mode summary on the same trace (at least one clause dropped or compacted).
- No JS console errors on Single, Compare (3 columns), or when trace is empty.

### IDEA 6 — Evals narrative + card hints + query text

- `<div class="evals-narrative">` renders above `.metrics-grid` when `queries_run > 0`; absent otherwise.
- Narrative contains at least the three prompt-specified sentences (permission violations line, recall line, budget utilization line) under their documented conditions.
- Budget tier label maps correctly: `<0.60 → efficient`, `[0.60, 0.80] → moderate`, `>0.80 → heavy`.
- Every `.metric-card` has a `.metric-card-hint` child with the exact text from the hint dictionary (typos corrected: "rey" → "recency", period added where missing).
- Per-query table Query cell shows id badge + query text truncated at 50 chars with `…` suffix; full text surfaced via `title=`. Existing 12-column layout preserved; no horizontal overflow at standard viewport (≥1280px).
- Existing aggregate metrics (P@5=0.3000, recall=1.0000, violations=0.0%) still render with the correct values.
- No JS console errors on Evals mode switch; narrative re-renders cleanly if Evals tab is re-entered (cache hit).

### Cross-batch

- `node --check frontend/app.js` returns clean.
- `python3 -m pytest -q` still 149 / 14 / 0.
- No backend file modified.
- No existing CSS class renamed or removed.

---

## Verification plan

Commands:

```bash
# Syntax
node --check frontend/app.js

# Backend sanity (must be unchanged)
python3 -m pytest -q
python3 -m src.evaluator --k 5 --top-k 8   # optional — confirms evaluator still matches baseline

# Server for browser verification
python3 -m uvicorn src.main:app --reload
```

Browser (Playwright via `webapp-testing` skill — replicate MUST-B2's 7-check pattern):

**IDEA 4 assertions (both modes):**
1. Single mode · Full Pipeline · q001 analyst ARR query → `.trace-panel` opens → `.trace-summary` exists and contains non-empty text.
2. Summary text contains "documents were included" and a `%` budget token.
3. Blocked clause absent when `blocked_count === 0` (use a partner query); present and mentions role when `blocked_count > 0` (analyst ARR query).
4. Stale clause present for a query that demotes doc_002 or doc_007 (e.g., q002); absent for queries with zero stale.
5. Tooltips: four elements in `.trace-metrics-strip` + `.budget-label` carry non-empty `title` attributes.
6. Compare mode · "Analyst wall ↔" scenario → three `.trace-summary` elements exist, each shorter (by char count) than the corresponding Single-mode summary rendered with the same trace shape.
7. 0 JS console errors across Single and Compare runs.

**IDEA 6 assertions:**
8. Evals tab loads → `.evals-narrative` exists, contains "test queries" and a `%` token.
9. At least 3 sentences (split on `. `) in the narrative under default state.
10. Exactly 10 `.metric-card-hint` elements, each with non-empty text and matching the hint dictionary (spot-check 3).
11. Per-query table: 8 rows, each Query cell contains both `.evals-qid` and `.evals-qtext`. `.evals-qtext` text length ≤ 53 chars (50 + `…`).
12. Full query text available via `title=` on at least one row where the source query exceeds 50 chars (q001 does).
13. Budget tier label in narrative is one of "efficient" / "moderate" / "heavy" and matches thresholds against `agg.avg_budget_utilization`.
14. 0 JS console errors on Evals mode.

Accept criterion: **≥14/14 Playwright checks pass, 0 JS console errors, all backend verifications green.**

---

## Docs to update at end of batch

- **`docs/HANDOFF.md`** — new Session entry (next session number after 23): "Session 24 / MUST-C — IDEA 4 + IDEA 6". Record files modified, verification numbers, commit hash, stale-doc corrections.
- **`CLAUDE.md`** — Frontend section: amend Single and Compare mode descriptions to mention the Decision Trace narrative paragraph + tooltips; amend Evals mode description to mention the narrative banner, per-card hints, and query text column.
- **`docs/plans/2026-04-16-ideas-execution-plan.md`** — append a "Supersession / continuation note" line pointing to this MUST-C plan, or leave untouched if this plan is the canonical MUST-C artifact (decision at commit time). No P-item reopens.
- **This file (`2026-04-17-must-c-ideas-4-6-plan.md`)** — flip status to "implemented + verified" post-execution, with commit hash.

Do **not** modify `docs/plans/2026-04-10-pipeline-integration-plan.md` (ARCHIVED).

---

## Files expected to change

| File | Scope |
|------|-------|
| `frontend/app.js` | `buildTracePanelHTML` (summary insertion, tooltips, userRole threading), new `buildTraceSummary`, `renderEvals` (narrative, card hints, query text cell), new `buildEvalsNarrative`, `METRIC_HINTS` dict, two call-site signature touches (`renderSingleResult`, `buildCompareColumnHTML`) |
| `frontend/styles.css` | `.trace-summary`, `.trace-summary strong`, `.metric-card-hint`, `.evals-narrative`, `.evals-qid`, `.evals-qtext` |

No backend, test, or model files change.

---

## Risk register

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Summary paragraph breaks Compare column layout at narrow widths | Med | CSS: summary inherits column width; test at 1024px and 1440px during browser pass |
| `userRole` threading miss in one call site → "undefined" in blocked sentence | Med | Default-argument guard in `buildTraceSummary`; if missing, drop the clause entirely |
| XSS regression via query text in table `title=` | Low | `escapeHTML` on all interpolated strings (same pattern as Session 18 fix) |
| `renderEvals` re-render after cache hit leaves stale narrative DOM | Low | Narrative is part of the `innerHTML` template, re-written each call — no manual mount needed |
| Metric hint wrapping breaks `.metrics-grid` row height | Low | Set `min-height` on `.metric-card`; hint is a third flex child with `font-size < 0.75rem` |

---

**Counts:** P0=0, P1=2 (IDEA 4, IDEA 6), P2=0, P3=0. Plan ready for implementation approval.
