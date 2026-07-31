# UI-C Execution Plan — Scenario, Navigation, and Compare Clarity

Date: 2026-04-23
Branch: `codex/must-a-idea1-2`
Scope: `frontend/index.html` + `frontend/app.js` + `frontend/styles.css`. **No `src/` changes. No new files, no new deps, no new tests.** 3-file scope budget.
Out of scope: backend behavior, `/ingest` logic, Evals dashboard internals, `roadmap.md`, Admin form markup.

---

## 1. Problem

- Onboard-cards in Single's empty state silently teleport to Compare on click (`data-mode="compare"`) — no signposting.
- The same three base narratives are expressed 9× across the UI: 3 onboard-cards + 3 Single shortcuts + 3 Compare shortcuts.
- Compare has no empty state: entering Compare before a query shows a near-empty banner and a blank grid.
- The "Partner view" card is narratively weak — partner has full access, so no permission drama lands.

## 2. Product decisions (locked; not re-evaluated here)

1. Empty-state cards in Single no longer auto-switch modes. Primary click sets query + role + policy and runs **Single**. Each card carries a secondary "Open in Compare →" action that IS allowed to switch mode.
2. Shortcut rows stay but drop the three buttons that duplicate onboard-card queries.
3. Compare gets its own empty/onboarding state: 3 cards mirroring Single's layout.
4. The partner card is renamed "Stale Detection" and reframed around the 2 demoted stale docs.
5. Style preserved: Bricolage Grotesque, IBM Plex Mono, existing color tokens + card layout + motion tokens.
6. ≤6 scenario entry points visible on initial Single view.

---

## 3. Empty-state cards — DOM restructure

Cards become **wrappers with two buttons**, not single buttons. Nested `<button>` is invalid HTML; the current `.example-btn` handler dispatches on `data-mode`, so two sibling `.example-btn`s inside the same card work with no handler fork.

```html
<div class="onboard-card" data-story="permission-wall">
  <span class="onboard-card-head">
    <span class="onboard-dot dot-analyst" aria-hidden="true"></span>
    <span class="onboard-card-subtitle">Analyst</span>
  </span>
  <span class="onboard-card-title">Permission Wall</span>
  <span class="onboard-hint">See 7 documents blocked by RBAC.</span>

  <div class="onboard-actions">
    <button type="button"
            class="example-btn onboard-primary"
            data-query="What is Meridian's ARR growth rate and net revenue retention?"
            data-role="analyst"
            data-mode="single">
      Run in Single
    </button>
    <button type="button"
            class="example-btn onboard-secondary"
            data-query="What is Meridian's ARR growth rate and net revenue retention?"
            data-role="analyst"
            data-mode="compare">
      Open in Compare →
    </button>
  </div>
</div>
```

- Container is `<div class="onboard-card">` (not `<button>`) — removes nested-button invalidity.
- Both inner buttons reuse `.example-btn` so the existing click handler (`app.js:283-320`) covers both with zero branching.
- `data-mode="single"` on the primary triggers the deterministic-preset path (force `full_policy`, sync policy radio, clear stale, run Single). **No mode switch.**
- `data-mode="compare"` on the secondary switches mode and runs Compare.
- `data-story` attribute is for CSS only (optional accent), not read by JS.

### Three onboard-cards (final copy)

| # | story | role | query | title | subtitle | hint |
|---|-------|------|-------|-------|----------|------|
| 1 | `permission-wall` | analyst | "What is Meridian's ARR growth rate and net revenue retention?" | Permission Wall | Analyst | See 7 documents blocked by RBAC. |
| 2 | `mixed-view` | vp | "What are the financial model assumptions, revenue projections, and deal valuation for Project Clearwater?" | VP Deal View | VP | Mixed signal — some blocks + a stale financial model demoted. |
| 3 | `stale-detection` | partner | "What do the research notes and financial models say about Meridian's revenue growth?" | Stale Detection | Partner | Full access — watch two superseded documents get demoted 0.5×. |

Card 2 is renamed from "Stale Detection" → "VP Deal View" to resolve the naming collision introduced by the partner card's new label. Query for Card 2 unchanged. Flagged as a minor interpretive call (see §10).

---

## 4. Shortcut-row dedup

### Single row (`index.html:102-113`)

- **Remove** "ARR growth" (analyst) — duplicates Card 1 query verbatim.
- **Keep** "DD risks" (vp, "risks identified in the due diligence for Project Clearwater") — distinct query.
- **Keep** "IC memo" (partner, "IC recommendation for the Meridian acquisition") — distinct query.

Final: 2 buttons.

### Compare row (`index.html:114-125`)

- **Remove** "Analyst wall ↔" — duplicates Card 1 query.
- **Remove** "VP deal view ↔" — duplicates Card 2 query.
- **Keep** "Partner view ↔" (partner, "IC recommendation and LP update") — distinct query from new Card 3.

Final: 1 button. Row container stays (label + single shortcut) so the row chrome is preserved for future additions.

### Entry-point count (Single-default view)

| source | count |
|---|---|
| Onboard cards (primary + secondary) | 3 + 3 = 6 |
| Single row | 2 |
| Compare row | 1 |
| **Visible on Single open** | 6 story-level + 3 non-base → within ≤6 base-story budget |

Compare empty state adds 3 Compare-only entries, but these are only seen after switching to Compare without a query — never visible at Single-open.

---

## 5. Compare empty state — DOM + copy

New `<div id="compare-empty-state" class="empty-state compare-empty">` inserted as the **first child of `#compare-section`**, above `.compare-banner`. Hidden/removed on first successful `runCompare` (mirrors Single's `setLoadingCompare(true)` removal flow).

```html
<div id="compare-empty-state" class="empty-state compare-empty">
  <h2 class="empty-title">Compare policies side by side</h2>
  <p class="empty-description">
    Run the same query through No Filters, Permissions Only, and Full Pipeline
    — see exactly which documents each policy includes, blocks, or demotes.
    Pick a scenario to preview the contrast.
  </p>
  <div class="onboard-grid">
    <button type="button" class="example-btn onboard-card onboard-card-compact"
            data-query="..." data-role="analyst" data-mode="compare"
            data-story="permission-wall">
      <span class="onboard-card-head">
        <span class="onboard-dot dot-analyst"></span>
        <span class="onboard-card-subtitle">Analyst · ARR query</span>
      </span>
      <span class="onboard-card-title">Permission Wall</span>
      <span class="onboard-hint">Naive surfaces 12 docs · RBAC + Full block 7.</span>
    </button>
    <!-- VP Deal View card (compare variant) -->
    <!-- Stale Detection card (compare variant) -->
  </div>
  <p class="empty-hint">Or type your own query above and choose a role.</p>
</div>
```

- In the Compare empty state each card is a **single** `.example-btn` (not the dual-action wrapper) — the user is already in Compare, so a single click to run Compare is the natural affordance.
- `.onboard-card-compact` is a CSS-only modifier preserving the compact preview feel (tighter spacing, qualitative preview copy instead of a secondary action row).
- Preview copy is **qualitative** ("Naive surfaces 12 · RBAC blocks 7") not numeric-precise — avoids drift when top_k / budget changes.

### Three Compare empty-state cards (final copy)

| # | role | query | title | subtitle | preview hint |
|---|------|-------|-------|----------|--------------|
| 1 | analyst | (same as onboard Card 1) | Permission Wall | Analyst · ARR growth | Naive surfaces 12 docs · RBAC + Full block 7. |
| 2 | vp | (same as onboard Card 2) | VP Deal View | VP · financial model | All three policies include the deal memo · only Full demotes the stale v1 model. |
| 3 | partner | (same as onboard Card 3) | Stale Detection | Partner · research + models | Full corpus retrievable · Full pipeline demotes two superseded docs 0.5×. |

---

## 6. JS changes (`frontend/app.js`)

- Existing `.example-btn` click handler (`app.js:283-320`) works unchanged — dispatches on `data-mode`. No new listeners.
- Add `setLoadingCompare(true)` → remove `#compare-empty-state` (mirrors `setLoadingSingle`'s `#empty-state` removal at `app.js:384`).
- `renderCompare(data)` — ensure any lingering `#compare-empty-state` is removed before injecting the grid (defensive; the skeleton swap already covers it).
- **No changes** to `switchMode`, `probeIngestCapability`, `evaluateSingleStale`, `_lastRenderedRole/_lastRenderedPolicy`, `downloadJSON`, Export JSON flow.
- **No changes** to Evals or Admin paths.

## 7. CSS changes (`frontend/styles.css`)

- Add `.onboard-actions` (flex row, gap ~0.5rem, wired to existing `--dur` / `--ease`).
- Add `.onboard-primary` + `.onboard-secondary` button styles — primary reuses `.btn` filled look; secondary is ghost/outlined with `→` emphasis. Both honour `prefers-reduced-motion`.
- Add `.onboard-card-compact` modifier for the Compare empty state (tighter padding, no actions row).
- Add `#compare-empty-state` spacing inside `#compare-section`.
- Card container (`.onboard-card`) restyled as a non-interactive block: remove `cursor: pointer` / hover lift from the card itself; move hover affordance onto the two inner buttons.
- Reuse existing color tokens (`dot-analyst` / `dot-vp` / `dot-partner`, badge variants). No new fonts, no new colors.

## 8. No-regression contract

- **Admin tab hide** — `probeIngestCapability()` (`app.js:247-260`) untouched. When `/health` returns `ingest_enabled=false`, `.mode-btn[data-mode="admin"]` and `#admin-section` stay hidden. Verified by leaving that block of code unedited and asserting Admin is not referenced by any new scenario markup.
- **Single post-UI-B** — stale banner, `_lastRenderedRole/_lastRenderedPolicy`, `.results-stale` opacity, `evaluateSingleStale()` gating on `.summary-bar` unchanged. New empty-state cards with `data-mode="single"` go through the existing deterministic-preset branch → `clearSingleStale()` is already invoked.
- **Evals** — unchanged; `evalsLoaded` latch unaffected.
- **Export JSON** — `renderCompare`'s dedup of `.export-btn` inside `#compare-banner` preserved.
- **Policy warning** — `#policy-warning` behavior unchanged; onboard-primary still forces `full_policy` so the warning clears.

## 9. Acceptance criteria

1. Clicking an onboard-card's **primary** button stays in Single mode, fills the query input, checks the matching role radio, forces `full_policy`, and renders a single-policy result. The mode toggle does not change.
2. Clicking the same card's **"Open in Compare →"** secondary button switches the mode toggle to Compare (aria-pressed updated) and runs `/compare` for the same query + role.
3. Switching to Compare without a prior query renders `#compare-empty-state` with three preview cards. Clicking any card runs `/compare` and the empty state disappears.
4. `GET /health` returning `{"ingest_enabled": false}` still hides the Admin mode button and `#admin-section` on load.
5. Counting scenario entry points visible on initial Single open: ≤6 for the three base stories (onboard 3 + onboard-secondary 3 = 6; shortcut-row entries are non-duplicative).
6. The Partner onboard-card reads "Stale Detection" (title) / "Partner" (subtitle) and its hint references the two superseded documents demoted 0.5×.
7. No console errors in Single, Compare, Evals, or Admin modes.
8. `python3 -m pytest tests/ -v` passes with the same pass count as on `main` (frontend-only changes).

## 10. Assumptions / open items

- **Card 2 rename** ("Stale Detection" → "VP Deal View"): implied by the partner rename; resolves the duplicate "Stale Detection" label. Flagged so it can be reverted in review if the product owner prefers keeping both labelled "Stale Detection".
- **New query for Card 3** ("research notes and financial models"): chosen to span both stale pairs (doc_002→doc_003, doc_007→doc_008). If retrieval doesn't surface both, fall back to the VP financial-model query with role=partner (single-pair stale demo).
- **Compare row retention**: kept "Partner view ↔" as the sole survivor to preserve the row label; if that feels orphaned in review, drop the row.

## 11. Verification plan

Manual click sequence (dev server at `http://localhost:8000/app/`):

1. Open app → confirm onboard-grid renders; count ≤6 base-story entries.
2. Click Card 1 primary → Single mode retained, result renders for analyst / ARR / full_policy.
3. Click Card 2 "Open in Compare →" → Compare mode active, `/compare` result renders, Export JSON button visible.
4. Switch mode back to Single → empty state is gone (first-query rule), prior Single result still visible.
5. Reload page, switch straight to Compare → `#compare-empty-state` renders with 3 cards. Click Card 3 → Compare result with stale demotions visible in Full column.
6. Toggle `ALLOW_INGEST=false` in the server env and reload → Admin button absent from header, Admin section absent from DOM.
7. Radio-change staleness (UI-B regression): run a Single query, flip role → stale banner appears. Still works.
8. `python3 -m pytest tests/ -v` — expect green.

## 12. Docs to update at the end

- `CLAUDE.md` — Single-mode paragraph (current `:145`): drop the claim that onboard-cards auto-switch to Compare; document the primary/secondary split. "Three one-click compare scenarios" line (`:152`): update names + drop the two retired buttons. Add a Compare-mode paragraph describing `#compare-empty-state`.
- `demo.md` — Demo A/B/C table "Cómo llegar" rows: onboard-card click now runs Single unless secondary is clicked. Rename Demo C from "Partner view" to "Stale Detection" and rewrite narrative around demoted docs.
- `summaryUserExp.md` — §Escenarios pre-armados: rename "Partner view" → "Stale Detection", note the Single-default onboard flow, note Compare empty state.
- `docs/HANDOFF.md` — append UI-C to the batch log with commit summary.

---

## 13. Files touched

- `frontend/index.html` — onboard-card DOM restructure, shortcut-row dedup, `#compare-empty-state` insertion.
- `frontend/app.js` — Compare empty-state removal on first `runCompare` / `setLoadingCompare`. No handler fork.
- `frontend/styles.css` — `.onboard-actions`, `.onboard-primary`, `.onboard-secondary`, `.onboard-card-compact`, `#compare-empty-state` spacing.

3 files total. Within scope budget.
