# NICE-A Execution Plan — IDEA 12 (Export JSON) + IDEA 13 (Micro-interactions)

Date: 2026-04-18
Branch: `codex/must-a-idea1-2`
Last commit: `d72e5da` (NICE-B). Working tree clean. Tests baseline 172 / 14 / 0.
Scope: Frontend-only. No backend, no model, no tests, no deps. Two additive polish passes.

---

## 1. Executive summary

IDEA 12 adds a discrete "Export JSON" button in Single (inside `.summary-bar`) and Compare (inside `.compare-banner`) that downloads the full raw API response via a `Blob` + `createObjectURL`. No transformation, no redaction — the JSON matches what `/query` and `/compare` already return publicly.

IDEA 13 is a motion pass. Four of the seven sub-items are already partially in place (`card-in` for result cards, staggered `.compare-col` entrance, `.search-btn` color transition, `.onboard-card` hover lift); three are genuinely new (mode-switch fade, `.trace-body` max-height animation, `.metric-card` hover lift). Loading spinner pulse and the `translateY(6px)`→`8px` drift are cosmetic.

All changes live in `frontend/app.js` and `frontend/styles.css`. `index.html` is untouched unless a persistent Export slot in the Compare banner reads cleaner as markup (not required — renderers inject it).

---

## 2. Preflight (verified this step)

- `git status` clean; `git log` shows NICE-B landed at `d72e5da`.
- `frontend/app.js` 1174 lines; `renderSingleResult()` @334, `renderCompare()` @501, `switchMode()` @81, `escapeHTML()` @1099, `wireTraceToggles()` @1059.
- `frontend/index.html` has `#compare-banner` @185 and `#results-section` @130.
- `frontend/styles.css` 2377 lines. `--dur: 180ms` / `--ease: cubic-bezier(0.22, 1, 0.36, 1)` tokens exist (@70–71).
- Existing motion inventory relevant to IDEA 13 — see §5.
- No `prefers-reduced-motion` rule anywhere.
- NICE-B-era serving (`/app/` mount + `API_BASE` resolver + `/health` probe) is live and unaffected by this batch.

---

## 3. Missing / weak prompt areas

1. **Blob lifecycle.** Prompt says "Blob + createObjectURL" but does not mention `URL.revokeObjectURL`. Missing revoke leaks memory for the lifetime of the document. Decision: revoke via `setTimeout(() => URL.revokeObjectURL(url), 0)` after `click()`.
2. **Button placement in Single.** Prompt says "in `renderSingleResult()`" but not *where*. The cleanest anchor is the existing `.summary-bar` (right side, after the last stat) so it travels with the header and doesn't push below a tall doc list. Decision: render inside `.summary-bar`; align right with `margin-left: auto`.
3. **Button placement in Compare.** Prompt says "in compare-banner". The banner lives in HTML (`#compare-banner` @index.html:185), not in `renderCompare()`'s output — the renderer only rewrites `#compare-banner-text`. Decision: add a `#compare-export-slot` span to the banner in HTML **or** append the button to `#compare-banner` from `renderCompare()` via `innerHTML`/`appendChild`. Prefer the JS-injection path to keep HTML diffs to zero and keep the button adjacent to the banner text.
4. **Export state before first query.** On fresh Compare mode, `renderCompare()` has never run → no button visible. That's correct behavior (nothing to export), but call out: the button must not be rendered by HTML, only by the renderer, so it never appears before a response exists.
5. **Filename sanitization.** `role` is one of `analyst|vp|partner`; `policy` is one of `naive_top_k|permission_aware|full_policy`; `data.role` comes back from the server after validation. All ASCII-safe for filenames. No sanitizer needed. Decision: no `encodeURIComponent` — just template literal.
6. **Compare filename is policy-less.** `querytrace_compare_${data.role}.json` doesn't encode which policies were compared. Since `/compare` defaults to all three, this is usually redundant. Accept prompt's shape as-is; if a reviewer asks, a follow-up could append `_all3` or the policy tuple.
7. **What exactly is "data"?** In Single, `data` is the full `QueryResponse` (context + total_tokens + decision_trace). In Compare, `data` is the `CompareResponse` (role + query + results map). Export = `JSON.stringify(data, null, 2)` — pretty-printed, complete, no transformation. Confirms prompt.
8. **Trace panel open/close mechanism (IDEA 13.5).** Current code toggles `.trace-body` via `display: none` → `display: block` (styles.css:1096, 1127). `max-height` cannot animate across a `display` change. Decision: switch `.trace-body` to `max-height: 0; overflow: hidden;` default with `.trace-panel.open .trace-body { max-height: <N>px; }`, matching the existing `.blocked-body` pattern. Pick a max large enough for worst-case traces (use 4000px; `.blocked-body` uses 2000px and no reports of clipping). Flip the JS toggle to continue toggling the `.open` class only — no JS change needed.
9. **Mode-switch fade-in (IDEA 13.1).** `switchMode()` currently flips `.hidden`. A fade-in needs the incoming section to start at opacity 0 and animate to 1. Simplest: add a CSS animation (`@keyframes mode-fade`) and apply it to `#results-section`, `#compare-section`, `#evals-section`, `#admin-section` **when they become visible**. Use `animation` (not `transition`) so it re-fires each entrance without JS state. Don't cross-fade the outgoing section — just hide it as today.
10. **Reduced motion.** No `@media (prefers-reduced-motion: reduce)` today. Accessibility default: disable the new mode-fade, the trace max-height, the card hover lifts, and the spinner pulse under that media query. Retain instant functional behavior.
11. **Spinner pulse (IDEA 13.4).** Prompt says "subtle spinner pulse". The existing `.btn-spinner::after` is a rotating ring via `@keyframes spin`. Interpretation: add a gentle opacity pulse (e.g., 1 ↔ 0.75, 1.2s) **on top of** the spin — don't replace rotation.
12. **`translateY` drift (IDEA 13.2).** Existing `card-in` uses translateY(6px). Prompt asks 8px. Cosmetic — change to 8px; no perceptible regression.
13. **Compare banner HTML mutation.** `renderCompare()` currently only writes `compareBannerText.innerHTML`. If the export button is appended to `#compare-banner`, repeat calls must not stack duplicate buttons. Decision: on each render, remove any existing `.export-btn` in the banner before appending a fresh one; alternatively, keep a single DOM node ref updated.

---

## 4. Hidden frontend / UX / browser-behavior risks

- **Very large traces.** With `max-height: 4000px`, a trace that exceeds this clips. Current trace bodies (~200–600px measured in prior Playwright) are well below. Note as a residual risk; no mitigation required unless a reviewer flags it.
- **Compare mode with 3 trace panels open simultaneously.** Three 4000px caps × three columns = no issue; they're column-scoped.
- **Mode-switch fade + `hidden` timing.** If a section's animation uses the appearance of `.hidden = false`, it runs once per toggle. Good. If a user rapidly clicks Mode tabs, the animation will restart — acceptable and matches every other SPA.
- **`URL.revokeObjectURL` timing.** Revoking before the download dialog opens cancels the download in Safari. Best practice: revoke in `setTimeout(..., 0)` — the tick after `.click()` — or in a `setTimeout(..., 100)` to be safe across browsers. Plan uses 0.
- **Blob under `file://`.** Works in Chrome/Firefox/Safari for user-initiated anchor clicks. No special handling.
- **Filename collisions.** Running the same role/policy twice overwrites on default browser settings or gets ` (1).json` suffix. Acceptable demo behavior.
- **Escape-HTML for the Export button label.** The label ("Export JSON") is a static literal; no user input flows into the button text. Safe.
- **Onboard-card click path.** Onboard cards live in `#empty-state` → removed on first query. Export button only renders after a query, so no interaction overlap.
- **Compare export button when a response has zero rows in all columns.** The button still exports the (valid) response — empty arrays are meaningful.
- **Evals tab has no export (per prompt).** Do not add one. Scope creep.
- **Admin tab is hidden on Render prod.** Export button lives in Single/Compare only, so the `/health` probe has no effect on it.
- **Spinner pulse interaction.** Adding an opacity keyframe on `.btn-spinner::after` can conflict with the `rotate` keyframe. Avoid by attaching the pulse to `.btn-spinner` (wrapper) or compose a single keyframe that animates both transforms. Choose the wrapper to keep rules simple.
- **CSS animation restart on mode switch.** CSS `animation` restarts when the node appears with a fresh class each time only if the `animation` property changes or the element is re-mounted. Since `.hidden` is the trigger, the animation runs on load but not on subsequent toggles. Fix: attach the animation to a class (`.mode-enter`) that JS adds on visibility and removes after the animation ends — or use `animation-play-state`. Simpler: add the animation unconditionally to each mode section — browsers don't re-run CSS animations on a `hidden` flip. Decision: JS adds `.mode-enter` in `switchMode()` and removes it via `animationend`. Tiny JS surface.
- **`prefers-reduced-motion` for `setTimeout(80ms)` fades.** The existing role/policy description fades use JS `setTimeout` — out of scope; leave untouched.
- **No regression from NICE-B.** Static serving at `/app/` is path-agnostic for these changes — all new CSS/JS lives in the same files already served.

---

## 5. Existing motion inventory (for IDEA 13 reconciliation)

| Feature | Current state | IDEA 13 ask | Delta |
|---|---|---|---|
| Mode sections | `.hidden` flip, instant | Fade-in 200ms ease-out | **Net-new** |
| Result doc cards | `card-in` 0.4s, translateY(6px)→0 | Slide-up translateY(8px)→0 | Cosmetic: 6→8 px |
| Result doc card hover | `transition: border-color` only | Shadow + translateY(-1px) | **Net-new** |
| Run button color | `transition: background var(--dur)` | Smoother color transition | **No-op** (already set) |
| Run button spinner | `@keyframes spin` (rotate only) | Subtle pulse | **Net-new** (opacity pulse) |
| Trace panel | `display: none` ↔ `block` | Smooth max-height open/close | **Net-new** (display → max-height) |
| Compare columns | translateY(8px)→0 staggered | Subtle slide-from-bottom | **No-op** (already done) |
| Compare card hover | border + shadow | implicit (not in prompt) | unchanged |
| Eval metric cards | `cardIn` entrance, no hover | Hover lift translateY(-2px) + shadow | **Net-new** |
| Onboard cards | hover translateY(-1px) | implicit (not in prompt) | unchanged |
| `prefers-reduced-motion` | absent | implicit accessibility default | **Add** |

Net: 4 genuinely new rules (mode fade, card hover lift, spinner pulse, metric hover lift), 1 mechanism swap (trace max-height), 2 no-ops, 1 cosmetic drift, 1 a11y media query.

---

## 6. Explicit assessments

### Export behavior in Single vs Compare
- **Single.** Injection point: end of `.summary-bar` inside `renderSingleResult()`. Handler captured via closure over `data`, `role`, `policy`. Filename: `querytrace_${role}_${policy}.json`. Payload: the full `QueryResponse` (context + total_tokens + decision_trace). No transformation.
- **Compare.** Injection point: `#compare-banner` (sibling of `#compare-banner-text`). Handler captured via closure over `data`. Filename: `querytrace_compare_${data.role}.json`. Payload: the full `CompareResponse`. Remove any prior `.export-btn` in the banner before appending to avoid duplicates across re-renders.

### Filename edge cases
- Role vocabulary is server-validated (`analyst|vp|partner`) — ASCII-only, safe.
- Policy vocabulary is radio-selected (`naive_top_k|permission_aware|full_policy`) — underscores, ASCII-only, safe.
- `data.role` in Compare echoes the validated request role.
- No query text in filename → avoids user-input sanitization.
- Timestamp is **not** in the filename per prompt; if reviewers want uniqueness, a follow-up could add `_<ISO>`.

### Blob / createObjectURL cleanup
- `const url = URL.createObjectURL(blob);` → create anchor → `a.click()` → `setTimeout(() => URL.revokeObjectURL(url), 0)`.
- Anchor is not appended to the DOM (not required by modern browsers for `.click()`), or appended + removed immediately — prefer the no-append path for simplicity.
- No persistent references; one download per click; GC reclaims.

### Complete payload vs transformed view
- **Complete, verbatim.** The API response is already what the user sees in the UI; transforming here would drift from the `/query` and `/compare` contracts and complicate debugging. `JSON.stringify(data, null, 2)` — pretty-printed for human readability.

### Animation scope and subtlety
- Motion tokens already standardized: `--dur: 180ms`, `--ease: cubic-bezier(0.22,1,0.36,1)`. Reuse across all new transitions where possible. The two prompt-specified durations that diverge: mode fade = 200ms ease-out (use `ease-out`, not `--ease`, per prompt); spinner pulse ≈ 1.2s (slow enough to be ambient, not attention-grabbing).
- Translate distances ≤ 8px. Shadow deltas match existing `--shadow-card` → `--shadow-card-hover` vars.
- Zero new dependencies, zero layout thrash — all transforms and opacity.

### Trace / compare / eval animation edge cases
- **Trace panel** switch from `display` to `max-height` must preserve open-on-render behavior (`startOpen` writes `.open` class into markup). Confirmed — `.trace-panel.open .trace-body { max-height: 4000px; }` handles it.
- **Compare column stagger.** Already runs; don't change timing — just re-verify that adding mode-enter fade on `#compare-section` doesn't compound visibly. If it does, scope the mode-fade to `opacity` only (no transform) so it composes cleanly with the column-level translateY.
- **Eval metric cards.** Entrance + hover compose cleanly; hover uses `transition`, entrance uses `animation`.
- **Evals narrative banner** (`.evals-narrative`) — not in prompt; leave untouched.
- **Skeleton loaders.** `@keyframes shimmer` already exists (styles.css:1728). Don't touch.

### NICE-B static-serving effect on verification
- Frontend is served at `http://localhost:8000/app/` (same origin) and `file://` (cross-origin to `:8000` via CORS). Blob downloads are origin-local data URLs — identical behavior under both.
- `/health` capability probe still hides Admin on prod; doesn't touch Export.
- Playwright should verify at `/app/` — matches production.

---

## 7. Acceptance criteria

- **IDEA 12.**
  - `.export-btn` appears in `.summary-bar` after any successful Single query; absent on "No Results".
  - `.export-btn` appears in `#compare-banner` after any successful Compare render; re-render replaces (does not stack) the button.
  - Clicking Single export downloads `querytrace_<role>_<policy>.json` containing `JSON.stringify(data, null, 2)` identical to the `/query` response.
  - Clicking Compare export downloads `querytrace_compare_<role>.json` containing the full `/compare` response.
  - No console errors. No memory growth after 10 repeated clicks (Blob URL revoked).
  - Button style: mono, right-aligned via `margin-left: auto`, download glyph (unicode ⤓ or ↓), subtle hover (bg + color shift).
- **IDEA 13.**
  - Switching between Single/Compare/Evals/Admin shows a 200ms ease-out fade-in of the incoming section. No flicker in the outgoing one.
  - Result doc cards slide up from 8px with existing stagger preserved.
  - Result doc cards lift translateY(-1px) + shadow on hover; 180ms.
  - Run button hover uses the existing smoother color transition; loading spinner pulses opacity in addition to rotating.
  - Trace panel opens/closes with a smooth `max-height` transition — no flash of full-height content. Already-open traces (`startOpen=true`) render open without animation jank.
  - Compare columns retain staggered slide-in (unchanged visually).
  - Eval metric cards lift translateY(-2px) + shadow on hover.
  - `@media (prefers-reduced-motion: reduce)` disables the new animations and the new hover transforms.
- **Global.**
  - `python3 -m pytest -q` → 172 / 14 / 0 (unchanged).
  - `node --check frontend/app.js` → clean.
  - No JS console errors across Single / Compare / Evals / Admin at `http://localhost:8000/app/`.
  - No new `escapeHTML` gaps (no user input flows into exported filename in a way that could escape the template).

---

## 8. Verification commands

```bash
# Baseline
python3 -m pytest -q                      # expect 172 / 14 / 0
node --check frontend/app.js              # expect OK

# Serve
python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000 &
UVICORN_PID=$!
sleep 2
curl -s -I http://localhost:8000/app/     # expect 200
curl -s http://localhost:8000/health      # expect ingest_enabled: true

# Playwright sweep (webapp-testing skill) at http://localhost:8000/app/
# - Single mode: run "ARR growth" / analyst / Full Pipeline
#   · click .export-btn#export-single
#   · verify a download event occurs with filename 'querytrace_analyst_full_policy.json'
#   · verify no console errors
#   · repeat ×10, verify Blob URL count does not accumulate (page.evaluate())
# - Compare mode: click "Analyst wall ↔"
#   · click .export-btn#export-compare
#   · verify filename 'querytrace_compare_analyst.json'
#   · re-click "VP deal view ↔" → verify banner has exactly one .export-btn
# - Mode fade: switch Single→Compare→Evals→Admin→Single; observe 200ms fade on each
# - Trace panel: click Decision Trace toggle; observe smooth open; click again; observe smooth close
# - Doc card hover: hover a result card; observe lift + shadow
# - Metric card hover: in Evals, hover a .metric-card; observe lift + shadow
# - prefers-reduced-motion: emulate reduced motion; verify mode fade and hovers are instant
# - 0 JS console errors overall

kill $UVICORN_PID
```

---

## 9. Docs to update at end of batch

- `CLAUDE.md` — amend the Frontend section to mention: (a) Export buttons in Single (`.summary-bar`) and Compare (`#compare-banner`) producing `querytrace_<role>_<policy>.json` / `querytrace_compare_<role>.json`; (b) that trace panels open/close with a smooth max-height transition; (c) the `prefers-reduced-motion` fallback. Keep additions to ≤6 lines total.
- `docs/HANDOFF.md` — new Session 28 entry: files changed, verification evidence, commit SHA, carry-forward.
- `docs/plans/2026-04-18-nice-a-ideas-12-13-plan.md` (this file) — finalize with commit SHA + Playwright evidence at end of batch.
- No other plan files change. `roadmap.md` does not exist and is not used.

---

## 10. Priority-banded task list

**P0 — must ship**
- `downloadJSON(data, filename)` helper in `app.js`.
- Export button + handler in `renderSingleResult()` (inside `.summary-bar`).
- Export button + handler appended to `#compare-banner` in `renderCompare()` (dedupe on re-render).
- `.export-btn` styling in `styles.css` (discrete, right-aligned, hover).
- Trace panel: swap `.trace-body` from `display` toggle to `max-height` transition.
- Mode-switch fade: `.mode-enter` class added in `switchMode()`; `@keyframes mode-fade` 200ms ease-out; `animationend` cleanup.

**P1 — polish (IDEA 13 net-new)**
- Result doc card hover lift (transform + shadow).
- Evals metric card hover lift.
- Spinner pulse on `.btn-spinner`.
- `translateY(6px)` → `translateY(8px)` in `card-in` (result doc card entrance).
- `@media (prefers-reduced-motion: reduce)` global disable of new transforms/fades.

**P2 — verification only**
- Playwright sweep at `/app/` covering the 8 checks above.
- Memory/Blob-URL accumulation check (≥10 exports, no retained references).

**P3 — deferred**
- Include timestamp or policy tuple in Compare filename.
- Persistent `.export-btn` markup in `index.html` (current plan injects via JS — zero diff to HTML).
- A visible "Download started" toast — too much UX for a discrete export.

**Counts:** P0 = 6 · P1 = 5 · P2 = 2 · P3 = 3

---

## 11. Safety assessment

Frontend-only, additive. No API, model, test, or deps changes. NICE-B static-serving path is unaffected. Existing motion tokens (`--dur`, `--ease`) already standardize timings. All new motion is scoped, subtle, and opt-out under `prefers-reduced-motion`. Expected test delta: zero. Expected Playwright delta: new assertions only, no prior assertions regress.

**Safe to execute in the current session.**
