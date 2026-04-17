# Execution Summary — IDEAs 1, 2, 3, 5, 7
# Retroactive synthesis — 2026-04-16
# Source of truth: docs/HANDOFF.md + observed repo state
# NOT a forward plan. Do not use as an implementation checklist.

---

## Completed

### IDEA 1 — Policy Names + Description Area (frontend-only)
**Intent:** Rename POLICY_META labels, add per-policy description text, amber warning banner for No Filters, fix permission_aware freshness N/A.
**Implemented:** ✅
- `POLICY_META` labels: `naive_top_k`→"No Filters", `permission_aware`→"Permissions Only", `full_policy`→"Full Pipeline"
- `permission_aware.skipFreshness` corrected: `false`→`true` (was showing `0.00` bars instead of N/A)
- `updatePolicyDescription()` with 80ms opacity fade wired to all policy radios
- `#policy-description` `<p>` and `#policy-warning` banner added to `index.html`
- CSS: `.policy-selector-group`, `.policy-description`, `.policy-warning` added
- Compare column headers inherit from `POLICY_META.label` automatically — no separate change needed
**Committed:** ✅ `78cdaf1` (WIP: MUST-A idea 1 and 2)
**Verified:** ✅ Session 20 — 20/20 MUST-A Playwright checks. Confirmed: chips show new labels, description updates on switch, warning banner appears only for No Filters, permission_aware freshness renders as N/A.
**Documented:** ✅ CLAUDE.md (frontend section), HANDOFF.md (Session 19)

---

### IDEA 2 — DocumentChunk Metadata Plumbing (backend)
**Intent:** Propagate `title`, `doc_type`, `date`, `superseded_by` from corpus through the full pipeline chain to the API response `context[]`.
**Implemented:** ✅
- `retriever.py` `_build_results()`: emits `"doc_type": p.get("type")` alongside `"type"`
- `models.py`: `doc_type` added to `ScoredDocument`, `FreshnessScoredDocument`; `title/doc_type/date/superseded_by` added to `IncludedDocument` and `DocumentChunk` (all `Optional[str] = None`)
- `freshness_scorer.py`: `doc_type=doc.doc_type` passed in `FreshnessScoredDocument` constructor
- `budget_packer.py`: `title/doc_type/date/superseded_by` passed in `IncludedDocument` constructor
- `main.py`: both `DocumentChunk` constructors (`query()` and `compare()`) pass all four fields
**Committed:** ✅ `78cdaf1` (WIP: MUST-A idea 1 and 2)
**Verified:** ✅ Session 20 — 20/20 Playwright checks (metadata fields used by IDEA 3 + IDEA 7 were verified as part of MUST-B1 verification). No test regression (149 passed).
**Documented:** ✅ CLAUDE.md (contract models section), HANDOFF.md (Session 19)

---

### IDEA 3 — Document Card Redesign + Excerpt Expand/Collapse
**Intent:** Show title heading, metadata line (doc_id badge + type + date), 200-char default excerpt with expand/collapse button. Compact version for Compare columns.
**Implemented:** ✅
- `singleCardHTML`: title heading (fallback `doc_id`), `.card-meta` line, excerpt 480→200 chars, "Show more ▾ / Hide ▴" toggle
- `buildCompareCardHTML`: title heading (60-char truncation), `.card-meta` line, snippet 160→120 chars, no expand button
- Security hardening: `_cardExcerpts Map` stores raw content keyed by card index; toggle uses `textContent` (not `innerHTML` from data attrs) — this is an intentional improvement over the prompt's suggestion of a data attribute
- Timezone fix: `new Date(year, month-1, 1)` instead of `new Date(dateStr)` (avoids UTC offset month-shift)
- `formatDocType(raw)` and `formatDate(dateStr)` helpers added; type mapping implemented via generic `replace(/_/g,' ')` + title-case (equivalent result to prompt's explicit dict for all known corpus doc_types)
- CSS: `.card-title`, `.card-meta`, `.card-meta-badge`, `.card-content` max-height transitions (collapsed 4.8em → expanded 600px), `.card-expand-btn`, `.compare-card-title`, `.compare-card-meta`
**Committed:** ✅ `6ac80a6` (MUST-B1)
**Verified:** ✅ Session 20 — 19/19 MUST-B1 Playwright checks (IDEA 3 × 8 checks)
**Documented:** ✅ CLAUDE.md (frontend section updated), HANDOFF.md (Session 20)

---

### IDEA 7 — Stale/Superseded Badge
**Intent:** Visual badge on cards for superseded documents, showing which doc replaced them and the freshness penalty.
**Implemented:** ✅
- Two-method detection: primary `chunk.superseded_by != null` (from IDEA 2); fallback `staleMap` built from `trace.demoted_as_stale` in `renderSingleResult()`
- Single mode: `.stale-badge` with ⚠ icon, "Superseded by **doc_XXX** — freshness penalized 0.5×"; penalty pulled from `staleInfo.penalty_applied`
- Compare mode: compact `.compare-stale-badge` chip ("⚠ Superseded") using option A only (`doc.superseded_by != null`)
- CSS: `.stale-badge`, `.stale-icon`, `.stale-text`, `.stale-text strong`, `.compare-stale-badge`
**Committed:** ✅ `6ac80a6` (MUST-B1)
**Verified:** ✅ Session 20 — 19/19 MUST-B1 Playwright checks (IDEA 7 × 5 checks: badges on both known stale pairs `doc_002/doc_003` and `doc_007/doc_008`)
**Documented:** ✅ CLAUDE.md (frontend section), HANDOFF.md (Session 20)

---

### IDEA 5 — Blocked Documents Section in Single Mode
**Intent:** Collapsible section below result cards (above Decision Trace) showing each permission-blocked document with human-readable reason. Backend enrichment of `BlockedDocument` with `title`/`doc_type`.
**Implemented:** ✅
- `src/models.py`: `BlockedDocument` gained `title: Optional[str] = None` and `doc_type: Optional[str] = None`
- `src/stages/permission_filter.py`: both constructors (unknown-role path + insufficient-role path) pass `title=doc.title, doc_type=doc.doc_type` — note: direct attribute access, not `getattr`, because `ScoredDocument` guarantees both fields
- `frontend/app.js`: `buildBlockedSectionHTML(blocked, userRole)` — signature takes `userRole` (improvement over prompt spec's `(blocked)` only, enables better reason text); `wireBlockedSectionToggle(container)`; `renderSingleResult()` wired with `blockedSectionHTML` inserted between `cardsHTML` and `traceHTML`; section returns `""` when blocked list is empty
- `frontend/styles.css`: `.blocked-section`, `.blocked-header` (amber left border), `.blocked-header-icon`, `.blocked-header-label`, `.blocked-caret` (rotates 180° on `.open`), `.blocked-body` (max-height 0→2000px transition), `.blocked-body-inner`, `.blocked-card`, `.blocked-card-title`, `.blocked-card-meta`, `.blocked-card-reason`
**Committed:** ❌ Uncommitted — 4 code files pending commit
**Verified:** ✅ Session 22 — 7/7 Playwright checks:
  1. Analyst + ARR query → "7 documents blocked by permissions"
  2. Collapsed by default (body height = 0)
  3. Click → expands, 7 cards visible
  4. Reason text: "Requires vp role — you are analyst"
  5. Click again → collapses
  6. Partner → no blocked section rendered
  7. 0 JS console errors
- Additive-only confirmed: empty-list guard returns `""`, no content/excerpts/scores leaked
**Documented:** ✅ CLAUDE.md (frontend section + BlockedDocument contract note), HANDOFF.md (Sessions 21, 22)

---

## Open Gaps

**1. IDEA 5 uncommitted (blocking)**
The 4 MUST-B2 code files (`frontend/app.js`, `frontend/styles.css`, `src/models.py`, `src/stages/permission_filter.py`) are implemented and verified but not committed. This is the only real outstanding action item.

**2. formatDocType mapping (unclear)**
The prompt specified an explicit dictionary (e.g. `"public_filing"→"Public Filing"`). The implementation uses generic title-casing (`replace(/_/g,' ').replace(/\b\w/g,...)`). Functionally equivalent for all 10 known corpus doc_types. If custom display names ever diverge from the snake_case pattern, a future change would be needed. Not a gap for the current corpus.

**3. Compare column header verification for IDEA 1 (unclear)**
IDEA 1 explicitly says "Verify that column headers and badges display the new names correctly." The MUST-A browser check (20/20) confirmed chips in Single mode show new labels. The MUST-B1 check included "Compare × 4" checks but the HANDOFF doesn't itemise whether compare column headers specifically were confirmed. The code path is straightforward (`POLICY_META[policyName].label` used in `buildCompareColumnHTML`), but an explicit check was not recorded. Low risk; `unclear` rather than `missing`.

---

## Safe Next Step

**Do now:**
1. Commit the 4 MUST-B2 code files. The commit message should reference IDEA 5 / MUST-B2. Suggested files: `frontend/app.js`, `frontend/styles.css`, `src/models.py`, `src/stages/permission_filter.py`. The 3 modified doc files (`CLAUDE.md`, `docs/HANDOFF.md`, `docs/plans/...`) can be included in the same commit or a follow-up docs commit.

**Do not revisit:**
- IDEA 1, 2, 3, 7 — all committed, all verified, all documented. No rework warranted.
- formatDocType mapping — generic title-casing is correct for the current corpus. Not a gap.
- Backend pipeline logic — no changes were made to retrieval, freshness, budget, or evaluator in any of these IDEAs beyond the metadata plumbing in IDEA 2.
- Test suite — 149/14/0 is stable. No new tests are needed for the frontend-only changes (IDEA 1, 3, 5, 7).

---

## Docs Cleanup

**`docs/plans/2026-04-10-pipeline-integration-plan.md`**
This file is historical (all items complete since Session 16). It is currently included in the default restore flow as step 3 of the session-open instructions. This creates noise — readers spend time on archived content. Recommendation: stop including it in the restore flow. It can remain on disk as an audit record but should not be read at session start. The restore flow should be: `HANDOFF.md` → `CLAUDE.md` (→ this summary if needed).

**HANDOFF.md Session 21 "Current State" (stale — already corrected)**
Session 21 described MUST-B1 as uncommitted. Session 22 corrected this inline. No further action needed; the correction is now the record.

**HANDOFF.md Sessions 1–17 consolidated block**
Long but serves a purpose as the audit trail of the build history. No cleanup needed — it is read once at the start and understood as historical context. Acceptable as-is.

**This file (`2026-04-16-ideas-1-2-3-5-7-execution-summary.md`)**
This is the forward reference that replaces the need to re-read the original executed prompts or cross-reference `2026-04-10-pipeline-integration-plan.md`. Suggest referencing it from `HANDOFF.md` if a future restore flow consolidation is done.
