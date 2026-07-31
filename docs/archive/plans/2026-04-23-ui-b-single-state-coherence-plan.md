# UI-B Execution Plan — Single Mode State Coherence

Date: 2026-04-23
Branch: `codex/must-a-idea1-2`
Scope: Frontend only. `frontend/app.js` + `frontend/styles.css`. **No `src/` changes. No new deps. No new tests.**
Out of scope: Compare shortcuts (UI-C), Compare/Evals/Admin state logic, `roadmap.md`.

---

## 1. Problem

Changing the role or policy radio in Single mode updates controls + descriptive copy but leaves the previously rendered result on screen. The summary-bar chips still show the old role/policy, contradicting the now-selected controls. Single example buttons inherit whatever policy is currently checked, so demo shortcuts are non-deterministic.

## 2. Product decisions (locked; not re-evaluated here)

1. **Mark-stale banner + require Run** — NOT auto-rerun, NOT clear-on-change.
2. **Single example buttons** = deterministic presets: force `policy=full_policy` and sync the policy radio + description accordingly.
3. **Compare shortcuts** out of scope (UI-C).
4. **Admin → Single** transition does NOT clear prior Single results; stale-banner rules apply as usual (trivial: controls are hidden in Admin so they cannot drift while away).
5. Visual style preserved: Bricolage Grotesque / IBM Plex Mono, existing color + motion tokens, card layout.

---

## 3. Stale banner — DOM + copy

**Placement.** First child of `#results-section`, above `.summary-bar`. Living inside `#results-section` lets `setLoadingSingle(true)` (skeleton swap) and `renderSingleResult` (full `innerHTML` replace) wipe it naturally; only the `.results-stale` class on the section itself needs separate cleanup.

**Markup (exact):**

```html
<div id="stale-results-banner"
     class="stale-results-banner"
     role="status"
     aria-live="polite"
     aria-atomic="true">
  <span class="stale-banner-icon" aria-hidden="true">↻</span>
  <span class="stale-banner-text">Controls changed — press <strong>Run</strong> to refresh these results.</span>
</div>
```

Copy is locked per decision ("Controls changed — press Run to refresh"); we only bold "Run" for scannability.

**No new copy in `#policy-description` or `#role-description`** — those describe the configuration, not the rendered state. The banner carries the "mismatch" signal.

## 4. De-emphasis of stale cards

Add class `results-stale` to `#results-section` while stale. CSS rules:

```css
#results-section.results-stale .summary-bar,
#results-section.results-stale .result-card,
#results-section.results-stale .blocked-section,
#results-section.results-stale .trace-panel {
  opacity: 0.6;
  transition: opacity var(--dur) var(--ease);
}
```

- **Pointer events: kept enabled.** The user must still be able to expand cards, toggle the trace panel, hit Export JSON on the last trusted result, or scroll before re-running. Disabling interaction would be a regression.
- **ARIA.** No `aria-hidden` (content is still semantically valid, just not matching controls). No `aria-busy` (we are not loading; banner's `role="status"` + `aria-live="polite"` carries the announcement).
- **Reduced motion.** Extend the existing `@media (prefers-reduced-motion: reduce)` block to set `transition: none` on the opacity change and suppress any banner entry animation.

## 5. State machine — when the banner appears / clears

Module-level state in `app.js`:

```js
let _lastRenderedRole = null;    // set by renderSingleResult
let _lastRenderedPolicy = null;  // set by renderSingleResult
```

A "rendered result" is defined authoritatively as: `resultsSection.querySelector(".summary-bar") !== null`. This excludes `#empty-state`, skeleton, `.no-results`, and `.error-state` — none of which need staleness signaling.

**Appears when:** a role or policy `change` event fires AND `.summary-bar` is present AND the new current pair `(role, policy)` !== `(_lastRenderedRole, _lastRenderedPolicy)`.

**Does NOT appear when:** radios are toggled back to the last-rendered value (banner removed if it was up). This handles keyboard arrow-key traversal that passes through other values and returns to the original — no flicker.

**Clears when:**
- Run / `renderSingleResult` completes (full `innerHTML` swap removes the banner; `setLoadingSingle(true)` also removes the `.results-stale` class — see §8).
- Single `.example-btn` click (the click is about to run deterministically; banner would be stale advice).
- `switchMode` leaves Single (banner + `.results-stale` class both removed; `_lastRenderedRole/Policy` preserved so stale state re-evaluates correctly on return; per decision 4 this is effectively a no-op since Admin hides the controls).

## 6. `.example-btn` click handler — exact change

Current handler (`app.js:217–245`) is one `forEach` over all `.example-btn` nodes. The only behavioral change is for Single presets; Compare presets and onboard cards (`data-mode="compare"`) stay exactly as-is.

Inside the handler, right after `updateRoleDescription(role)` and before the `targetMode` switch:

```js
// Deterministic Single presets: force full_policy, sync the radio + description.
if (targetMode === "single") {
  const policyRadio = document.querySelector('input[name="policy"][value="full_policy"]');
  if (policyRadio) policyRadio.checked = true;
  updatePolicyDescription("full_policy");  // also hides #policy-warning
}

clearSingleStale(); // remove banner + .results-stale before the upcoming skeleton
```

And in the dispatch branch:

```js
if (currentMode === "compare") {
  runCompare(query, role);
} else {
  runSingleQuery(query, role, "full_policy");  // preset is authoritative
}
```

The previous `document.querySelector('input[name="policy"]:checked')?.value` fallback is removed for the Single preset path. For the form `submit` path (manual Run), the checked-radio lookup is preserved — user-driven policy choice must still flow through.

HTML does NOT need `data-policy="full_policy"` on the Single buttons — JS enforces the preset. Keeping HTML unchanged avoids a spurious diff.

## 7. `updatePolicyDescription` / `updateRoleDescription` side effects

Both helpers already do an 80ms fade-out/in on the description text and (for policy) toggle `#policy-warning`. They do NOT touch results. They stay untouched.

The `change` listeners on the role and policy radios get a new call:

```js
radio.addEventListener("change", () => {
  updateRoleDescription(radio.value);     // or updatePolicyDescription
  evaluateSingleStale();                  // new
});
```

`evaluateSingleStale()` reads both currently-checked radios, compares to `_lastRenderedRole/Policy`, and either inserts/removes the banner and toggles `.results-stale` accordingly. Called from both role and policy change handlers.

## 8. `setLoadingSingle(true)` — required tweak

Current body (`app.js:305–312`) wipes `#results-section.innerHTML` with the skeleton, which removes any banner inside. BUT the `.results-stale` class lives on `#results-section` itself and would persist, rendering the skeleton at 60% opacity. Fix: one line inside `if (on)`:

```js
resultsSection.classList.remove("results-stale");
```

This is the only change to `setLoadingSingle`. No other callers need changes.

## 9. `renderSingleResult` — required additions

At the end of a successful render (inside the non-empty branch), record last-rendered state:

```js
_lastRenderedRole = role;
_lastRenderedPolicy = policy;
```

The `innerHTML` replacement already removes any prior banner; `setLoadingSingle(true)` already removed `.results-stale`. No other changes.

On the empty (`data.context.length === 0`) branch and on error: do NOT update `_lastRenderedRole/Policy` (there is no trusted rendered result). The banner gate (`.summary-bar` present) naturally disables staleness signaling for these cases.

## 10. `switchMode` — required addition

On switch OUT of Single: call `clearSingleStale()` (removes banner + `.results-stale`). Do not clear `_lastRenderedRole/Policy`. On switch IN to Single: no action needed — the user cannot have changed Single controls while in Admin (hidden) or Evals/Compare (no effect on single radios in current code), so `_lastRenderedRole/Policy` still matches.

## 11. Acceptance criteria

- **AC1** — With a Single result rendered, changing the role radio shows the stale banner above the summary-bar; summary-bar + cards + blocked section + trace panel drop to 60% opacity. Summary-bar role chip still displays the old role.
- **AC2** — Same for changing the policy radio. `#policy-warning` (separate element for `naive_top_k`) behaves independently of the stale banner.
- **AC3** — Toggling the radio back to the last-rendered value removes the banner and restores full opacity. Arrow-key traversal through other values and back does not leave the banner behind.
- **AC4** — Clicking Run with a banner visible clears the banner, runs the query, and renders a result whose summary-bar role+policy chips match the current radios.
- **AC5** — Clicking any Single example button ("ARR growth" / "DD risks" / "IC memo") with any current policy forces the policy radio to "Full Pipeline", hides `#policy-warning`, updates `#policy-description`, sets role + query, runs, and renders with `policy_name=full_policy`. Summary-bar shows "Full Pipeline".
- **AC6** — Clicking a Single example button clears any existing stale banner before the fetch.
- **AC7** — Switching Single → Compare/Evals/Admin removes the banner + `.results-stale` class. Returning to Single without changing controls shows the prior result at full opacity and no banner.
- **AC8** — Empty state visible (no prior query): changing radios does NOT show the banner.
- **AC9** — Error state or "no documents matched" visible: changing radios does NOT show the banner.
- **AC10** — `role="status"` + `aria-live="polite"` on the banner; it does not steal focus or trap keyboard navigation. Banner icon has `aria-hidden="true"`.
- **AC11** — `prefers-reduced-motion: reduce` disables the opacity transition and any banner entry animation; banner still appears/disappears instantly.
- **AC12** — No regressions in Compare, Evals, Admin: all existing flows (runCompare, renderCompare, runEvals, renderEvals, uploadDocument) untouched.

## 12. Verification plan

**Automated (no-regression safety net only — no `src/` changes):**

```bash
python3 -m pytest tests/ -v
```

Expected: all existing tests pass unchanged.

**Manual click sequence (must be walked start to finish):**

1. Start server: `python3 -m uvicorn src.main:app --reload`. Open `http://localhost:8000/app/`.
2. Default view: analyst + Full Pipeline, onboard empty state visible. Change VP radio → **no banner** (AC8).
3. Click **ARR growth** — result renders. Summary-bar shows analyst / Full Pipeline.
4. Click VP radio → banner appears, cards at 60% opacity (AC1). Click Analyst → banner gone (AC3).
5. Click Partner → banner appears. Click Run → banner clears; new summary-bar reads partner / Full Pipeline (AC4).
6. Click "No Filters" policy → banner appears; `#policy-warning` also visible (separate concern) (AC2). Click Run → banner gone, warning still visible.
7. Click "Full Pipeline" policy → banner appears. Click **DD risks** example → policy radio snaps back to Full Pipeline, warning hidden, role becomes VP, query runs, banner gone, summary-bar reads VP / Full Pipeline (AC5, AC6).
8. Change role radio → banner appears. Switch to Compare → banner gone. Switch to Evals → loads evals. Switch to Admin (if enabled) → shows ingest form. Back to Single → no banner, previous result visible at full opacity (AC7).
9. Enter a gibberish query that returns no results, Run → `.no-results` view. Change role → no banner (AC9).
10. Simulate error (stop the server, Run) → error state. Change role → no banner. Restart server.
11. Arrow-key test: focus an analyst radio with `Tab`, arrow-key through VP/Partner and back to Analyst → banner never persists at rest on Analyst (AC3, AC8-style for keyboard).
12. DevTools → Rendering → Emulate `prefers-reduced-motion: reduce`. Repeat step 4 → no opacity transition, banner instantaneous (AC11).

## 13. Docs updated after execution (NOT in this step)

- `CLAUDE.md` — Frontend section, Single mode paragraph: append stale-banner behavior and deterministic Single example-button semantics. Update the line that currently describes `.example-btn` click handling.
- `demo.md` — Single flow narrative: note that example buttons always run with the full pipeline.
- `summaryUserExp.md` — Single mode description: add the banner + deterministic presets.
- `docs/HANDOFF.md` — new session entry for UI-B (what shipped, files touched, acceptance checklist result).
- This plan file — append an "Execution outcome" section with the verified AC grid.

## 14. Execution shape (summary)

- `frontend/app.js`:
  - Add `_lastRenderedRole` / `_lastRenderedPolicy` module state.
  - Add `clearSingleStale()` + `evaluateSingleStale()` helpers; the banner is created via a dedicated builder that escapes no user input (static copy).
  - Wire both into the role radio `change` listener and the policy radio `change` listener.
  - In the `.example-btn` handler: for `data-mode="single"`, force `policy=full_policy`, sync the radio, call `updatePolicyDescription("full_policy")`, call `clearSingleStale()`, and pass `"full_policy"` into `runSingleQuery`.
  - In `setLoadingSingle(true)`: `resultsSection.classList.remove("results-stale")`.
  - In `renderSingleResult` success branch: set `_lastRenderedRole/Policy`.
  - In `switchMode`: when leaving Single, call `clearSingleStale()`.
- `frontend/styles.css`:
  - `.stale-results-banner` — flex row, icon + text, muted accent bg (reuse `--accent` + low-alpha), IBM Plex Mono for the `<strong>Run</strong>`, respects existing radii/spacing scale.
  - `#results-section.results-stale` descendant rules (opacity + transition).
  - Reduced-motion overrides.
- No HTML changes. No test changes. No backend changes.

## 15. Rollback

Revert the two frontend files. No data, no index, no corpus touched.
