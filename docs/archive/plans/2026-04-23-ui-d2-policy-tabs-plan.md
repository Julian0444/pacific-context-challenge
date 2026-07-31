# UI-D2: Policy selector as tabs with stage sub-labels

## Motivation

The three policy chips ("No Filters / Permissions Only / Full Pipeline") look like toggles without conveying what each policy enables or disables. Replacing the chip row with a tab-style selector adds a mono sub-label per tab that lists the active pipeline stages, bridging the gap between the UI label and the pipeline-stage reality.

## Token audit (preflight)

Verified tokens in `styles.css :root`:
- `--text-tertiary` (#9e968e) — used for sub-label text
- `--accent-subtle` (rgba(139, 105, 20, 0.09)) — used for tab hover background
- `--accent` (#8b6914) — available but not used (tabs use per-policy severity colors instead)
- `--border` (#e0d9cf) — used for the shared bottom border
- `--font-mono` — used for label and sub-label
- `--dur` (180ms) / `--ease` — used for transitions
- `--policy-naive` / `--policy-rbac` / `--policy-full` and their `-bg` variants — reused for active-tab border and background
- NOT defined: `--text-muted`, `--surface-subtle`

All CSS in this batch uses only tokens from this verified set.

## Sub-label content

| Tab label | Sub-label |
|-----------|-----------|
| No Filters | Retrieval only |
| Permissions Only | Retrieval + RBAC + Budget |
| Full Pipeline | Retrieval + RBAC + Freshness + Budget |

## Visual pattern

- Three tabs share a `1px solid var(--border)` bottom border.
- Active tab: `2px` bottom border in the policy's severity color + severity-bg background.
- Inactive tabs: transparent bottom border, `var(--accent-subtle)` on hover.
- Label uses `--font-mono` at 0.7rem/600 weight; sub-label at 0.6rem/normal in `--text-tertiary`.

## Decisions

- **No JS changes.** `app.js` never targeted `.policy-chip` by selector — it queries `input[name="policy"]` directly. The `variant` field in `POLICY_META` feeds Compare-mode column classes, not the selector.
- **Kept per-policy color tokens.** `--policy-naive`, `--policy-rbac`, `--policy-full` (and `-bg`, `-border`) are reused extensively in Compare columns, summary stats, and trace badges.
- **Retired chip-only selectors.** `.policy-chip`, `.policy-chip.policy-naive/rbac/full`, `.policy-chip:hover`, `input:checked + .policy-chip.*` — all replaced by `.policy-tab` equivalents.

## Files changed

| File | Change |
|------|--------|
| `frontend/index.html` | Replaced 3 `<span class="policy-chip ...">` with `<span class="policy-tab ...">` containing `.policy-tab-label` + `.policy-tab-sublabel`. Radio inputs unchanged. |
| `frontend/styles.css` | Removed `.policy-chip` block and all modifiers. Added `.policy-tab`, `.policy-tab-label`, `.policy-tab-sublabel`, per-policy label colors, hover, and `input:checked + .policy-tab-*` active states. Changed `.policy-options` gap from `0.3rem` to `0` and added shared bottom border. |
| `CLAUDE.md` | Updated "selector chips" → "selector tabs" in Single-mode paragraph; replaced Policy labels paragraph with tab pattern + sub-label description. |

## Verification

- `grep -rn 'policy-chip' frontend/` — zero hits.
- `grep -rn 'policy-tab' frontend/` — 9 hits in index.html, 10+ in styles.css.
- `pytest tests/ -v` — 172 passed, 14 skipped, 0 failed.
- DevTools: sub-label computed color resolves to `--text-tertiary` (#9e968e), hover background to `--accent-subtle`.
