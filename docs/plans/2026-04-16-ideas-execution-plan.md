# IDEAs Execution Plan — Retroactive Backfill
# Date: 2026-04-16
# Scope: MUST-A (IDEA 1 + IDEA 2), MUST-B1 (IDEA 3 + IDEA 7), MUST-B2 (IDEA 5)
# Status: All batches committed and verified. This file is the canonical planning artifact.
# Supersedes: docs/plans/2026-04-16-ideas-1-2-3-5-7-execution-summary.md (deleted)

---

## Executive Summary

Three batches of UX and data-plumbing improvements were executed against the QueryTrace Context Policy Lab across Sessions 19–22 on branch `codex/must-a-idea1-2`. All three batches are now committed (`78cdaf1`/`719e03f`, `6ac80a6`, `6122d94`) and verified in-browser via Playwright. Backend pipeline logic was not changed in any batch; the work focused on propagating existing metadata through the API boundary (MUST-A IDEA 2) and reshaping the frontend to expose that metadata (MUST-A IDEA 1, MUST-B1, MUST-B2). No tests regressed: 149 passed / 14 skipped / 0 failed, stable since Session 11.

The original prompts were generally well-scoped but had a handful of minor under-specifications that the implementation resolved with documented, justified deviations (e.g., timezone fix in `formatDate`, security hardening in excerpt expand/collapse, signature enhancement for `buildBlockedSectionHTML`). No implementation gaps. No verification gaps beyond one low-risk `unclear` item (explicit compare-column-header label assertion under IDEA 1).

| Batch | Commit(s) | Code Files | Checks | Test Count |
|-------|-----------|-----------|--------|-----------|
| MUST-A | `78cdaf1` + `719e03f` | 8 | 20/20 (Session 20) | 149/14/0 |
| MUST-B1 | `6ac80a6` | 2 | 19/19 (Session 20) | 149/14/0 |
| MUST-B2 | `6122d94` | 4 | 7/7 (Session 22) | 149/14/0 |

---

## Batch 1 — MUST-A (IDEA 2 + IDEA 1)

**Commits:** `78cdaf1` (WIP: MUST-A idea 1 and 2 — code) + `719e03f` (MUST-A idea 1 and 2 — docs)

### What was done

**IDEA 2 — Backend metadata plumbing**
- `src/retriever.py` — `_build_results()` emits `"doc_type": p.get("type")` alongside the existing `"type"` key. `ScoredDocument` uses `extra="ignore"` so `"type"` was silently dropped before; `doc_type` is the correctly-named key.
- `src/models.py` — four targeted additions, all `Optional[str] = None`:
  - `ScoredDocument`: `doc_type`
  - `FreshnessScoredDocument`: `doc_type`
  - `IncludedDocument`: `title`, `doc_type`, `date`, `superseded_by`
  - `DocumentChunk`: `title`, `doc_type`, `date`, `superseded_by`
- `src/stages/freshness_scorer.py` — `FreshnessScoredDocument(...)` constructor passes `doc_type=doc.doc_type`.
- `src/stages/budget_packer.py` — `IncludedDocument(...)` constructor passes `title`, `doc_type`, `date`, `superseded_by`.
- `src/main.py` — both `DocumentChunk(...)` constructors (in `query()` and `compare()`) pass all four fields.

**IDEA 1 — Frontend policy labels and description area**
- `frontend/app.js` — `POLICY_META` relabeled: `naive_top_k` → "No Filters", `permission_aware` → "Permissions Only", `full_policy` → "Full Pipeline". Bug fix: `permission_aware.skipFreshness` corrected from `false` to `true` (backend skips freshness for this policy; UI was rendering misleading `0.00` bars).
- `frontend/app.js` — `updatePolicyDescription(policy)` function with 80ms opacity fade; event listeners on all `input[name="policy"]` radios; init call on page load.
- `frontend/index.html` — `#single-policy-selector` restructured with `.policy-selector-group` wrapper; `<p id="policy-description">` added below chips; `<div id="policy-warning" hidden>` added as amber banner for No Filters; chip labels updated.
- `frontend/styles.css` — `.policy-selector-group { align-self: flex-start }`, `.policy-description { opacity 80ms transition }`, `.policy-warning` amber palette with flex-safe emoji alignment.

### Why it mattered

- The pipeline already computed `title`/`doc_type`/`date`/`superseded_by` but discarded them at the API boundary, forcing the frontend to work from `doc_id` alone. MUST-B1 and MUST-B2 both depended on this metadata being available — IDEA 2 unblocked those batches.
- Policy labels like "NAIVE"/"RBAC"/"FULL" were jargon-heavy and unfriendly. Product-grade labels + a description area + the warning banner made the policy-selection affordance self-explanatory at demo time.
- The `permission_aware.skipFreshness` bug caused every card in that policy to show a misleading `0.00` freshness bar instead of a truthful "N/A — skipped by policy" label.

### Acceptance criteria effectively satisfied

- Response `context[]` carries `title`, `doc_type`, `date`, `superseded_by` on every chunk.
- All new Pydantic fields are `Optional[str] = None` — backward compatible; no test broke.
- UI shows "No Filters" / "Permissions Only" / "Full Pipeline" chips; description updates on switch; amber warning shows only for No Filters.
- Permissions-Only freshness renders as "N/A — skipped by policy" (not `0.00`).
- No backend business logic changed; no API path names altered.

### Files affected

- `src/retriever.py`
- `src/models.py`
- `src/stages/freshness_scorer.py`
- `src/stages/budget_packer.py`
- `src/main.py`
- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`

### Verification evidence

- **Session 20 browser verification:** 20/20 Playwright checks. Confirmed new chip labels, description updates on switch, warning banner shown only for No Filters, freshness renders as "N/A — skipped by policy" (12 elements, no `0.00` bars), result cards returned from Full Pipeline query.
- **Tests:** 149 passed, 14 skipped, 0 failed after backend changes.
- **Evaluator:** precision@5=0.3000, recall=1.0000, permission_violation_rate=0% (unchanged — no pipeline logic changed).

### Prompt gaps / weak specification areas

- **IDEA 1 — compare column header verification.** Prompt asked to "verify that column headers and badges display the new names correctly" in Compare mode. The code path is correct by construction (`buildCompareColumnHTML` reads `POLICY_META[policyName].label`), but the explicit labeled assertion in Compare mode was not itemized in the MUST-A browser check. MUST-B1 later ran four compare-mode checks which de-facto exercised this path without regression. Low risk; left as `unclear` in consistency reviews rather than a real gap.
- **IDEA 2 — bug-for-free in `ScoredDocument`.** The prompt asked to add `doc_type` to `ScoredDocument`, but before the change `ScoredDocument` was already `extra="ignore"` and silently discarding the retriever's `"type"` key. Implementation correctly noted this and added a parallel `"doc_type"` emit in the retriever dict rather than renaming the key, preserving backward compatibility.

### Remaining follow-ups

- **None** functionally. Optional: a Playwright assertion on compare column header labels could close the `unclear` item, but it is low-value and not required.

---

## Batch 2 — MUST-B1 (IDEA 3 + IDEA 7)

**Commit:** `6ac80a6` (MUST-B1)

### What was done

**IDEA 3 — Document card redesign + excerpt expand/collapse**
- `frontend/app.js` `singleCardHTML`:
  - Card header shows `chunk.title` (fallback `chunk.doc_id`) as `.card-title` with rank on the right.
  - New `.card-meta` line: `.card-meta-badge` with `doc_id` (mono font, light gray bg) · formatted doc type · formatted date (e.g., "Mar 2024"), joined with " · ".
  - Default excerpt reduced from 480 → 200 chars.
  - `Show more ▾ / Hide ▴` button toggles to the full ~500-char indexer excerpt.
  - **Security hardening:** raw content stored in `_cardExcerpts` Map keyed by `data-card-idx`; toggle uses `textContent`, not `innerHTML` from data attributes.
  - **Timezone fix:** `new Date(year, month-1, 1)` instead of `new Date(dateStr)` to avoid UTC offset shifting months (e.g., "2024-03-01" rendering as "Feb 2024").
- `frontend/app.js` `buildCompareCardHTML`:
  - Title truncated to 60 chars, `.card-meta` line, snippet 160 → 120 chars, no expand button.
- `frontend/app.js` helpers: `formatDocType(raw)` (generic title-case), `formatDate(dateStr)` (timezone-safe), `wireExpandButtons(container)`.
- `frontend/styles.css` new rules: `.card-title`, `.card-meta`, `.card-meta-badge`, `.compare-card-title`, `.card-content` (collapsed `max-height: 4.8em` → expanded `max-height: 600px` with `0.3s ease` transition), `.card-content-text`, `.card-expand-btn`, `.compare-card-meta`.

**IDEA 7 — Stale/superseded badge**
- Two-method detection:
  - Primary (Option A): `chunk.superseded_by != null` (enabled by IDEA 2).
  - Fallback (Option B): cross-reference `chunk.doc_id` against `trace.demoted_as_stale` via `staleMap` built in `renderSingleResult()`.
- Single mode `.stale-badge`: ⚠ icon + "Superseded by **doc_XXX** — freshness penalized 0.5×". Inserted between `.card-meta` and `.card-content`. Penalty pulled from `staleInfo.penalty_applied` (fallback `0.5×`).
- Compare mode `.compare-stale-badge`: compact inline "⚠ Superseded" chip using option A only.
- CSS: `.stale-badge`, `.stale-icon`, `.stale-text`, `.stale-text strong`, `.compare-stale-badge`.

### Why it mattered

- The pre-redesign card showed only `doc_id` and an excerpt, forcing the reader to guess at document identity and recency.
- Excerpts were being truncated to 480 chars by default with no way to see more without clicking through to the (nonexistent) source document; 200-char default + Show more exposed the full indexer excerpt without the user leaving the result list.
- Superseded-by pairs (doc_002→doc_003, doc_007→doc_008) carry a 0.5× freshness penalty in the pipeline, but this was only visible by expanding the Decision Trace. A visible badge on the card itself surfaces a compliance-relevant signal inline.

### Acceptance criteria effectively satisfied

- Each Single-mode card shows: title heading, metadata line (badge + type + date), 200-char excerpt with functional Show more/Hide toggle, stale badge (where applicable), relevance/freshness bars, tags.
- Expand/collapse uses CSS transition on a fixed `max-height: 600px` (not `auto`) — prompt's hard constraint satisfied.
- Compare cards use a compact version of the same layout without the expand button.
- Security: no raw content is interpolated as HTML from data attributes — verified by reading the toggle handler.
- Both known stale pairs render the badge on the demoted document; fresh docs do not.

### Files affected

- `frontend/app.js`
- `frontend/styles.css`

### Verification evidence

- **Session 20 browser verification:** 19/19 Playwright checks — IDEA 3 × 8, IDEA 7 × 5, Compare × 4, Evals regression × 1, JS errors × 1. 0 JS console errors.
- **Tests:** 149 passed, 14 skipped, 0 failed (unchanged — no backend touched).
- **JS syntax:** `node --check frontend/app.js` clean.

### Prompt gaps / weak specification areas

- **`formatDocType` mapping.** Prompt specified an explicit 10-entry dictionary (`"public_filing" → "Public Filing"`, etc.). Implementation uses generic title-casing: `(raw || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())`. Functionally equivalent for all 10 known corpus doc_types because they all follow snake_case. If a future corpus adds a doc_type that doesn't follow this pattern (e.g., `"10-K"`, `"SEC_filing_K"`), the generic implementation could produce an unexpected label. Acceptable for the current demo corpus.
- **`formatDate` deviation.** Prompt supplied `new Date(dateStr)` directly. Implementation deliberately uses `new Date(year, month-1, 1)` to avoid a UTC-offset bug where `"2024-03-01"` was rendering as "Feb 2024" on browsers east of UTC. This is a bug fix over the prompt's suggestion, documented in HANDOFF Session 20.
- **Excerpt storage mechanism.** Prompt suggested "a data attribute or variable to store the full excerpt content". Implementation uses a module-level `_cardExcerpts` Map with `textContent` assignment rather than an HTML data attribute. This avoids any `innerHTML` path for user-origin content — security hardening over the prompt's suggestion.
- **IDEA 7 badge insertion point.** Prompt said "Insert after card-header, before card-content." Implementation inserts after `.card-meta` (which sits between `.card-header` and `.card-content` after IDEA 3). Valid interpretation; visually cleaner. Documented in the prompt's own prerequisite statement that IDEA 2 + IDEA 3 must already be in place.

### Remaining follow-ups

- **None.** `formatDocType` drift is a future-corpus concern, not a current gap.

---

## Batch 3 — MUST-B2 (IDEA 5)

**Commit:** `6122d94` (MUST-B2)

### What was done

**Backend enrichment**
- `src/models.py` — `BlockedDocument` gained two optional fields: `title: Optional[str] = None`, `doc_type: Optional[str] = None`.
- `src/stages/permission_filter.py` — both `BlockedDocument(...)` constructors (unknown-role path and insufficient-role path) now pass `title=doc.title, doc_type=doc.doc_type`. Direct attribute access because `ScoredDocument` guarantees both fields as `Optional[str]`.

**Frontend section**
- `frontend/app.js`:
  - `buildBlockedSectionHTML(blocked, userRole)` — returns `<section class="blocked-section">` with a collapsible header (🔒 + "N document(s) blocked by permissions" + caret) and a body of `.blocked-card` entries (title, `doc_id` badge, doc type, reason). Signature takes `userRole` — an enhancement over the prompt's `(blocked)` spec — to produce the "you are X" clause in the reason text. Returns `""` when the list is empty.
  - Reason text: `"Requires <strong>X</strong> role — you are <strong>Y</strong>"` for `insufficient_role`; `"Unknown role requirement: <strong>X</strong>"` for `unknown_min_role`.
  - `wireBlockedSectionToggle(container)` — toggles `.open` class on header click; updates `aria-expanded`.
  - `renderSingleResult()` — `blockedSectionHTML` computed from `trace?.blocked_by_permission || []` and inserted between `cardsHTML` and `traceHTML`.
- `frontend/styles.css` — new block `/* ─── Blocked Documents Section (single mode) ─── */`:
  - `.blocked-section`, `.blocked-header` (amber `border-left 3px solid var(--trace-blocked)`, `var(--trace-blocked-bg)` background), `.blocked-header-icon`, `.blocked-caret` (rotates 180° on `.open`), `.blocked-body` (`max-height: 0 → 2000px` with `0.3s ease` transition), `.blocked-body-inner`, `.blocked-card`, `.blocked-card-title`, `.blocked-card-meta`, `.blocked-card-reason`.

### Why it mattered

- Before this batch, the only evidence of permission-blocked documents was a row of chips inside the collapsible Decision Trace panel. For a permission-aware context gateway, the blocked set is compliance-relevant — it belongs above the fold, readable, with the reason for each block.
- For the Analyst + ARR scenario, seven out of twelve corpus documents are blocked. Without a visible section, an analyst can't easily tell that the scant result set is the product of access control, not lack of relevance.

### Acceptance criteria effectively satisfied

- Section appears only when `blocked_by_permission` is non-empty; otherwise nothing renders (no empty affordance).
- Collapsed by default; expands on header click; collapses again on a second click.
- Each card shows: title (fallback `doc_id`), `doc_id` badge, doc type, and a human-readable reason distinguishing `insufficient_role` from `unknown_min_role`.
- Partner-role flows (where nothing is blocked) render no section at all.
- No document content, excerpts, or scores are surfaced in the blocked section — blocked metadata only.
- All new backend fields are `Optional[str] = None` — no test regression.

### Files affected

- `src/models.py`
- `src/stages/permission_filter.py`
- `frontend/app.js`
- `frontend/styles.css`

### Verification evidence

- **Session 22 browser verification:** 7/7 Playwright checks:
  1. Analyst + ARR query → "7 documents blocked by permissions"
  2. Collapsed by default (body height = 0 on load)
  3. Click header → expands, 7 blocked cards rendered
  4. Reason text human-readable: "Requires vp role — you are analyst"
  5. Click again → collapses
  6. Partner + same query → no blocked section rendered
  7. 0 JS console errors
- **Additive-only audit:** confirmed empty-list guard (`if (!blocked || blocked.length === 0) return "";`) and no content/excerpt/score leakage in any card path.
- **Tests:** 149 passed, 14 skipped, 0 failed.

### Prompt gaps / weak specification areas

- **`buildBlockedSectionHTML` signature.** Prompt specified `buildBlockedSectionHTML(blocked)`. Implementation uses `(blocked, userRole)` because the "you are X" clause in the reason text requires the requesting role, which is not carried on each `BlockedDocument` (`user_role` is populated per-item by the backend, but threading it through the section header and ensuring consistency was simpler via a single `userRole` parameter). Strict enhancement over the prompt.
- **`getattr(doc, 'doc_type', None)` vs direct access.** Prompt suggested `getattr(doc, 'doc_type', None)` in `permission_filter.py`. Implementation uses `doc.doc_type` because `ScoredDocument` declares `doc_type: Optional[str] = None` — the attribute is guaranteed to exist. Functionally equivalent; cleaner.
- **Reason text not specified.** Prompt required "readable reason" but did not specify the exact string format. Implementation chose two canonical forms based on the backend's `reason` discriminator (`insufficient_role` vs `unknown_min_role`).

### Remaining follow-ups

- **None.**

---

## Cross-Batch Prompt Gaps Summary

Across all three batches, the original prompts had a consistent pattern: they were concrete about **what** to build and usually accurate about **where** to put it, but occasionally under-specified on:

1. **Security-relevant mechanisms.** IDEA 3 suggested a data attribute for the expand/collapse excerpt; the implementation chose a safer Map + `textContent` pattern. Future prompts touching user-origin content in HTML should explicitly mandate `textContent`-only interpolation.
2. **Timezone safety.** IDEA 3 supplied `new Date(dateStr)` for date parsing; this constructor has documented UTC-offset behaviour for `YYYY-MM-DD` input. Future date-rendering prompts should call out the timezone semantics explicitly.
3. **Enumeration vs generic mapping.** IDEA 3 specified an explicit 10-entry doc_type dict, but the implementation uses a generic title-casing pattern because every entry in the corpus follows snake_case. The generic pattern will silently drift if a future corpus entry breaks this convention; the prompt gave no guidance on which approach to prefer.
4. **Signature flexibility for derived values.** IDEA 5's `buildBlockedSectionHTML(blocked)` signature did not pass `userRole`, needed for the "you are X" reason. The implementation added the parameter. Future prompts specifying function signatures should be explicit when derived-from-context values are needed.
5. **Insertion points that shift across batches.** IDEA 7 said "after card-header, before card-content," but IDEA 3 (applied earlier) inserted `.card-meta` between those points. The implementation correctly placed the badge after `.card-meta`. Future prompts should either be relative to sibling elements that are guaranteed to exist or explicitly acknowledge prerequisite batches.
6. **Verification asks without matching automated assertions.** IDEA 1 said "verify column headers and badges display the new names correctly" but no specific Playwright assertion was itemized in the MUST-A check. The code path is correct by construction, but future prompts with explicit verify steps should list the specific assertion.

---

## Residual Risks / Cleanup

| Item | Risk level | Status |
|------|-----------|--------|
| `docs/plans/2026-04-10-pipeline-integration-plan.md` still in default restore flow | Low (noise) | Resolved — ARCHIVED banner added to file header (2026-04-16) |
| 3-line trailing-whitespace diff in the 04-10 plan file | Low | Folded into `6122d94` |
| `formatDocType` generic title-casing could drift if non-snake_case doc_types are added | Low (future corpus only) | Accepted |
| `apply_freshness()` in `freshness.py` and `filter_by_role()` in `policies.py` are unreachable | Low (dead code) | Accepted — 14 tests already skipped and labeled legacy |
| `run_evals()` re-reads corpus/roles independently of `main.py`'s loaded copies | Low (cosmetic) | Accepted |

---

## Priority-Banded Follow-ups (Actionable Only)

The three implementation batches are complete. The only actionable follow-ups identified are documentation hygiene:

### P2 — Restore flow consolidation ✅ RESOLVED (2026-04-16)

- **What was done:** Added an `[ARCHIVED]` banner to the header of `docs/plans/2026-04-10-pipeline-integration-plan.md` explicitly stating it is not part of the default restore flow, kept on disk as audit record only, and documenting the canonical restore sequence: `HANDOFF.md` → `CLAUDE.md` (extended: + this file).
- **Why:** The 04-10 plan covers work complete since Session 16 and adds cold-start noise. Readers waste attention on archived content.
- **Files affected:** `docs/plans/2026-04-10-pipeline-integration-plan.md` (ARCHIVED banner added), `docs/plans/2026-04-16-ideas-execution-plan.md` (this entry + residual risks table updated).

### P3 — Optional verification polish ✅ RESOLVED (2026-04-16)

- **What was done:** Ran an explicit Playwright assertion via the `webapp-testing` skill. Clicked the "Analyst wall ↔" scenario button (triggers Compare mode), waited for `.col-badge` elements, asserted exactly 3 present with text `["No Filters", "Permissions Only", "Full Pipeline"]` in order. Result: **PASS**.
- **Evidence:** `Found 3 .col-badge elements: ['No Filters', 'Permissions Only', 'Full Pipeline']` — exact match.
- **Files affected:** ad-hoc script at `/tmp/check_compare_headers.py` (verification only, not committed to repo).

**Counts:** P0 = 0, P1 = 0, P2 = 0 (resolved), P3 = 0 (resolved). All follow-ups closed.

---

## Archival Notes

- This file replaces `docs/plans/2026-04-16-ideas-1-2-3-5-7-execution-summary.md` (deleted on creation of this canonical plan to avoid duplicate overlapping artifacts).
- `docs/plans/2026-04-10-pipeline-integration-plan.md` is historical; all items complete since Session 16. Kept on disk as an audit record but should not be part of the default restore flow.
- The running audit trail is `docs/HANDOFF.md`. `CLAUDE.md` carries the architecture-level description of the production state. This file is the last-mile planning backfill — it can be skipped on a cold restore if `HANDOFF.md` is current.
