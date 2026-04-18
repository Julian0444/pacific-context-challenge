# SHOULD-A Execution Plan — IDEA 9 + IDEA 10

Date: 2026-04-17
Branch: `codex/must-a-idea1-2`
Scope: Frontend-only onboarding polish. IDEA 9 adds a live role description under the role selector. IDEA 10 replaces the passive `#empty-state` block with three clickable scenario cards. No backend, no new tests required.

Preflight: `python3 -m pytest -q` → 172 passed / 14 skipped / 0 failed. Baseline clean.

---

## Executive summary

Two additive frontend passes that layer onboarding affordances onto surfaces already mutated by MUST-A (`.policy-description`) and MUST-B1/C (card redesign, trace narrative). IDEA 9 mirrors the existing `updatePolicyDescription` pattern (`frontend/app.js:95`). IDEA 10 replaces the current `#empty-state` body (`frontend/index.html:128-143`) with a three-card scenario grid that reuses the `.example-btn` click handler (app.js:138) by class-sharing, not forking logic. Both must survive `switchMode` transitions and must continue to honor the existing "empty-state is removed on first query" behavior (app.js:228).

---

## Missing / weak areas in the prompts (call-outs, not blockers)

1. **IDEA 9 typo — "internamos".** Analyst description contains the string "internamos" — treat as "internal memos". Write the corrected phrase ("internal memos, financial models, or board materials") in the plan and the final copy.
2. **IDEA 9 categorical drift vs. MUST-D.** Prompt says "no hardcoded numbers" (good — MUST-D lets the corpus grow), but the descriptions enumerate specific *doc_type categories* ("public filings, research notes, press releases" for analyst). If a future ingest uses a new `doc_type` value, those enumerations become incomplete rather than wrong. Accept as residual risk; document that descriptions describe the seed corpus, not the live metadata.
3. **IDEA 9 insertion point ambiguity.** Prompt says "below `.role-options`". The role selector today is a bare `.selector-group` laid out as a flex row (styles.css:325/343), unlike the policy selector which lives inside a `.policy-selector-group` flex-column wrapper (index.html:72-94). Mirror the policy pattern: wrap the role block in a new `.role-selector-group` flex-column container so the `<p>` stacks cleanly without breaking the `.controls-row` alignment. Safer than inserting the `<p>` directly inside the flex-row `.selector-group`.
4. **IDEA 9 event propagation from `.example-btn` / onboard cards.** Clicking an example/scenario/onboard button sets `roleRadio.checked = true` imperatively (app.js:149) but does not fire a `change` event. Listeners attached via `radio.addEventListener("change", …)` will not run. Decision: call `updateRoleDescription(role)` explicitly in the `.example-btn` handler (and the onboard handler inherits it via class reuse). This is the same class of bug the policy description does *not* currently trip because policy isn't reset by example buttons.
5. **IDEA 10 hardcoded "7" contradicts IDEA 9's non-numeric rule.** "See 7 documents blocked by RBAC" on the analyst card. The seed corpus has exactly 7 blocked analyst docs, so it's correct today but drifts if MUST-D ingests VP/Partner docs. Keep the "7" (matches the pre-existing hint copy on index.html:142) and add a `title=` explaining the number is seed-corpus-specific. Alternative — soften to "See documents blocked by RBAC" — is rejected: the specificity is what makes the card a wow-moment invitation.
6. **IDEA 10 reuse of `.example-btn` handler.** Simplest implementation: add `.example-btn` class alongside `.onboard-card` on the scenario cards. The existing selector `document.querySelectorAll(".example-btn")` picks them up automatically at page load; no new event wiring needed. Cards get both `data-query` / `data-role` / `data-mode="compare"` AND the visual `.onboard-card` styling.
7. **IDEA 10 line reference is slightly off.** Prompt says "line ~121-136"; actual `#empty-state` is `index.html:128-143`. Not a blocker; noting for accuracy.
8. **IDEA 10 doesn't specify what the current `.empty-icon` SVG does.** It's a decorative hexagon. Decision: drop it — the three cards provide enough visual weight. Keep the `.empty-title` slot (upgraded headline) and the `.empty-description` slot (new subtitle). Replace `.empty-hint` with the "Or type your own query…" closing line.
9. **No Playwright assertions in the prompt.** See verification plan below.
10. **`escapeHTML` — not applicable this batch.** All strings in IDEA 9/10 are static literals in the HTML/JS source, not API-derived. No new XSS surface.

---

## Hidden risks

### Frontend layout / state
- **`.controls-row` alignment regression.** MUST-A already hit this when the Policy column grew taller than Role (fixed with `align-self: flex-start` on `.policy-selector-group`). Adding a `.role-selector-group` wrapper with its own description paragraph risks the inverse — Role column now grows taller than Policy on narrow widths. Mirror the `align-self: flex-start` fix for both groups.
- **Role description visible in all modes where `.search-section` is visible.** Currently: Single and Compare. Hidden in Evals and Admin via `search-section.hidden` (app.js:85). Correct behavior — no special-casing needed.
- **Empty-state removal on first query is permanent for the session.** `document.getElementById("empty-state")?.remove()` (app.js:228) destroys the node. If the user clears results and switches modes back to single, the onboard cards will not reappear. Pre-existing behavior, but now the lost UI is the main onboarding surface. Decision: accept the pre-existing behavior — do not re-implement a restore path for this batch; call it out in the plan and in CLAUDE.md so reviewers don't flag it as a new regression.
- **Mode switching before any query.** User can toggle Single → Compare → Evals → back to Single without ever querying. The empty-state must survive `switchMode` round-trips. Confirmed: `switchMode` only toggles `section.hidden`, doesn't mutate `#empty-state`. Safe.
- **`.onboard-card` click with no backend server.** If API is down, the existing `.example-btn` handler will surface the error in `resultsSection` via `renderError`. Acceptable — no new code path needed.

### Copy / content
- **Blocked-count truthiness.** "See 7 documents blocked by RBAC" is true for seed corpus (5 vp + 2 partner blocked for analyst). Verified via `corpus/metadata.json`. Ingest can drift this.
- **"Full Access" card wording.** Says "zero blocks" — true when role=partner, for any query. Independent of corpus size. Safe.
- **"Stale Detection" card wording.** "See how outdated financial models get demoted" — requires the VP query to actually retrieve `doc_007` (superseded financial model). Current VP scenario query is about Project Clearwater financial models; `doc_007` is in that set. Safe for seed corpus.

### Accessibility
- **Role description added as a `<p>` sibling to `.role-options`**: screen readers will announce it on focus into the radio group if `aria-describedby` is wired; prompt doesn't require it, but a low-cost improvement. Decision: defer; match MUST-A policy-description which also omits `aria-describedby`.
- **Onboard cards as `<button>` elements** (not `<div>`) — keyboard accessible, Enter/Space trigger click by default. Required; call out explicitly.

---

## Assumptions changed by MUST-D

- **Corpus is runtime-variable.** IDEA 9 wording avoids counts. IDEA 10 keeps "7" intentionally (seed-corpus claim) — document as accepted drift.
- **No new API dependencies.** IDEA 9/10 don't call `/ingest`; no cache invalidation concerns.
- **4-mode header layout.** Pre-existing. No new mode added.
- **`corpus/metadata.json` can grow.** Role descriptions describe access *categories* (analyst tier / vp tier / partner tier), not doc counts — so uploads change *which specific docs* each role sees but not the category-level access shape. IDEA 9 copy remains correct for any corpus that respects the analyst/vp/partner RBAC hierarchy.

No other MUST-D-driven changes affect this batch.

---

## Execution order (preserves batch intent: 9 → 10)

### IDEA 9 — Role description

1. **`frontend/index.html`** — wrap the existing role block (lines 53-69) in a new `<div class="role-selector-group">` mirroring `.policy-selector-group`. Insert `<p class="role-description" id="role-description"></p>` below `.role-options`.
2. **`frontend/app.js`** — add `ROLE_DESCRIPTIONS` object (three keys: analyst, vp, partner) with the corrected "internal memos" phrasing. Add `updateRoleDescription(role)` helper using the same 80ms opacity fade as `updatePolicyDescription` (app.js:95-106). Wire on page load (`document.querySelector('input[name="role"]:checked')`). Wire `change` listeners on all role radios. In the `.example-btn` click handler (app.js:138-164) call `updateRoleDescription(role)` after setting `roleRadio.checked = true` to close the "programmatic-set-does-not-fire-change" gap.
3. **`frontend/styles.css`** — add `.role-selector-group` (flex-column, `align-self: flex-start`), `.role-description` (mirror `.policy-description`: mono, 0.61rem, tertiary color, `max-width: 500px`, `transition: opacity 80ms ease`). Sanity-check `.controls-row` still aligns Role + Policy tops.

### IDEA 10 — Guided empty state

4. **`frontend/index.html`** — replace the interior of `#empty-state` (lines 129-142) with: new `.empty-title` headline "How different policies change context assembly"; new `.empty-description` subtitle; a `<div class="onboard-grid">` with three `<button class="example-btn onboard-card">` elements carrying `data-query` / `data-role` / `data-mode="compare"` identical to the existing Compare scenario buttons (index.html:113-121); `.onboard-dot` role-color chip + title + hint inside each card; closing `<p class="empty-hint">` with the "Or type your own query…" line. Drop the decorative `.empty-icon` SVG block.
5. **`frontend/app.js`** — no new wiring. The existing `document.querySelectorAll(".example-btn").forEach(...)` (app.js:138) picks up the onboard cards at page load because they share the class. Confirm: `input.value = query`, role radio gets set, mode switches to compare, `runCompare` fires. IDEA 9's `updateRoleDescription` call added in step 2 also fires from onboard cards (shared handler).
6. **`frontend/styles.css`** — add `.onboard-grid` (CSS grid, `grid-template-columns: repeat(3, 1fr)`, gap ~1rem, `max-width: 780px`, `margin: 1.25rem auto 0`), `.onboard-card` (card styling: padding, border, border-radius, background `bg-surface`, hover → `box-shadow` lift + `border-color` accent, text-align left to override `.empty-state` center), `.onboard-dot` (reuse `.dot-analyst` / `.dot-vp` / `.dot-partner` color vars; 10px inline-block circle), `.onboard-card-title`, `.onboard-hint` (tertiary, smaller). Responsive: `@media (max-width: 720px)` collapse grid to 1 column.

---

## Acceptance criteria

### IDEA 9
- `#role-description` exists and renders with non-empty text on page load for the default-checked role (analyst).
- Clicking VP radio → text changes to VP description with a visible opacity fade (~80ms).
- Clicking Partner radio → text changes to Partner description.
- Clicking any `.example-btn` that sets a different role also updates the description (programmatic role changes must not desync the description).
- Text "internamos" does not appear in the final HTML / JS source.
- Role description is hidden in Evals and Admin modes (via `.search-section` already being hidden).
- `.controls-row` continues to align Role and Policy columns at their tops.

### IDEA 10
- `#empty-state` renders a headline, subtitle, a 3-card grid, and a closing hint line on page load.
- Three `.onboard-card` buttons exist, each with a role-color dot, title, and one-line hint matching the prompt copy.
- Each onboard card has `data-query` + `data-role` + `data-mode="compare"` attributes and is picked up by the existing `.example-btn` click handler.
- Clicking "Permission Wall" → switches to Compare mode, sets role=analyst, submits the ARR-growth query, and shows the 7-blocked-docs outcome identical to the existing "Analyst wall ↔" scenario button.
- Clicking "Stale Detection" → Compare mode, role=vp, financial-model query, stale-demotion chip visible in the Full Pipeline column.
- Clicking "Full Access" → Compare mode, role=partner, IC-memo query, FULL column shows `0 BLOCKED`.
- Decorative `.empty-icon` SVG is removed (confirmed absent from the rendered DOM).
- On viewport < 720px, the grid collapses to a single column without horizontal overflow.
- After any query runs, `#empty-state` is removed (pre-existing behavior, unchanged).

### Cross-batch
- `node --check frontend/app.js` clean.
- `python3 -m pytest -q` still 172 / 14 / 0.
- No backend file modified.
- 0 new JS console errors on Single, Compare, Evals, and Admin modes.
- `escapeHTML` not introduced for new surfaces (none needed — all copy is static).

---

## Verification commands

```bash
# JS syntax
node --check frontend/app.js

# Backend must remain untouched
python3 -m pytest -q

# Server for browser verification
python3 -m uvicorn src.main:app --reload
```

Playwright (via `webapp-testing` skill) — 12 assertions, patterned on MUST-C's 15-check sweep:

**IDEA 9**
1. Load frontend → `#role-description` text length > 0 and mentions "analyst" (case-insensitive).
2. Click VP radio → text changes and mentions "Vice President".
3. Click Partner radio → text changes and mentions "Partner".
4. Click an `.example-btn` with `data-role="partner"` → `#role-description` updates to the Partner copy (not stale on analyst).
5. The string `internamos` is absent from `document.documentElement.outerHTML`.
6. Switch to Evals mode → `.search-section` hidden → `#role-description` not visible.
7. Switch to Admin mode → `#role-description` not visible.

**IDEA 10**
8. Load frontend → `#empty-state` contains exactly 3 `.onboard-card` elements.
9. Each `.onboard-card` has non-empty `data-query`, a `data-role` in `{analyst, vp, partner}`, and `data-mode="compare"`.
10. Click the analyst card → compare mode active, 3 compare columns rendered, ≥7 `.flag-blocked` annotations in the NAIVE column (matches existing Analyst-wall scenario).
11. Reload, click the VP card → compare mode, VP banner visible, at least one `.compare-stale-badge` in the FULL column.
12. Reload, click the Partner card → compare mode, FULL column `.col-badge` stats show `0 BLOCKED`.

**Regression (cross-batch)**
13. 0 JS console errors across all interactions.
14. Existing Compare-mode column headers still match `['No Filters', 'Permissions Only', 'Full Pipeline']` (MUST-A P3 assertion must not regress).
15. Evals narrative banner still renders with 3 sentences (MUST-C IDEA 6 must not regress).

Accept: **≥15/15 Playwright checks, 0 JS console errors, 172/14/0 tests.**

---

## Docs to update at end of batch

- **`docs/HANDOFF.md`** — new session entry (next #): "SHOULD-A — IDEA 9 + IDEA 10". Files modified, Playwright count, commit hash, plus a single line documenting the accepted residual: "onboard cards do not restore after first query — pre-existing empty-state-removal behavior; not newly broken".
- **`CLAUDE.md`** — Frontend section: amend Single/Compare descriptions to mention the role description paragraph under the role selector; replace the empty-state reference with the onboarding scenario grid.
- **This file** — flip status to "implemented + verified" post-execution with the commit hash.
- **Do not modify** `docs/plans/2026-04-10-pipeline-integration-plan.md` (ARCHIVED), `docs/plans/2026-04-17-must-c-ideas-4-6-plan.md`, `docs/plans/2026-04-17-must-d-idea-8-plan.md`.

---

## Files expected to change

| File | Scope |
|------|-------|
| `frontend/index.html` | New `.role-selector-group` wrapper + `<p class="role-description">`; replacement of `#empty-state` interior with 3-card onboard grid |
| `frontend/app.js` | `ROLE_DESCRIPTIONS`, `updateRoleDescription`, role radio change listeners, `updateRoleDescription(role)` call inside the existing `.example-btn` handler |
| `frontend/styles.css` | `.role-selector-group`, `.role-description`, `.onboard-grid`, `.onboard-card`, `.onboard-card:hover`, `.onboard-card-title`, `.onboard-dot`, `.onboard-hint`, responsive collapse |

No backend, test, or model files change.

---

## Risk register

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| `.controls-row` alignment breaks when Role column grows | Med | `align-self: flex-start` on `.role-selector-group` (mirror MUST-A fix) |
| `.example-btn` programmatic role set does not fire change → stale role description | High → fixed | Call `updateRoleDescription(role)` explicitly in the example-btn handler |
| "7 blocked" card copy drifts after a VP/Partner ingest | Low | Documented in CLAUDE.md; seed-corpus-specific claim |
| `.onboard-card` inherits `.empty-state { text-align: center }` and mis-aligns card internals | Low | Explicit `text-align: left` on `.onboard-card` |
| Narrow viewport 3-col grid overflows | Low | `@media (max-width: 720px)` single-column fallback |
| Role description wording becomes incomplete if a new `doc_type` ships | Low | Descriptions describe tiers, not exhaustive type lists — residual, accepted |

---

**Counts:** P0=0, P1=2 (IDEA 9, IDEA 10), P2=0, P3=0.

---

## Execution outcome (2026-04-17)

Status: **EXECUTED + VERIFIED**. Batch landed on `codex/must-a-idea1-2` as commit `0315c59` ("SHOULD-A: IDEA 9 (role description) + IDEA 10 (guided empty state)").

Evidence (captured at execution time):
- `python3 -m pytest -q` → **172 passed, 14 skipped, 0 failed** (unchanged from pre-batch baseline).
- `node --check frontend/app.js` → OK.
- Playwright via `webapp-testing` skill → **15/15 checks passed**, 0 JS console errors. Covered: role description updates on radio switch + on programmatic role set from `.example-btn`; "internamos" not present in rendered HTML; three `.onboard-card` buttons render and each dispatches the correct scenario (Permission Wall → analyst/ARR, Stale Detection → vp/financial model with stale demotion chip in Full column, Full Access → partner/IC memo with `0 BLOCKED` in Full column); decorative `.empty-icon` SVG absent; MUST-A P3 compare-header assertion and MUST-C evals narrative both clean.
- Files changed (per commit `0315c59`): `CLAUDE.md`, `docs/HANDOFF.md`, `docs/plans/2026-04-17-should-a-ideas-9-10-plan.md` (this file), `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`.

Deviations from plan: none. Accepted residual ("onboard cards do not restore after first query — pre-existing empty-state-removal behavior") documented in HANDOFF / CLAUDE.

Superseded by subsequent batches: NICE-B / IDEA 11 (deploy packaging) has since been executed on top of this work — see `docs/plans/2026-04-17-nice-b-idea-11-plan.md`.
