# UI-D1: Drop scenario micro-dots

## Motivation

The `.ex-role-dot` / `.onboard-dot` micro-circles next to scenario labels silently encode which role a button will set on click. They read as decorative, collide visually with the role selector chips above, and generate confusion when the dot color doesn't match the currently selected role. Removing them is a pure visual simplification — click handlers still set the correct role from `data-*` attributes, and tooltips describe the scenario in plain text.

## Scope

Remove every `<span>` with class `ex-role-dot` or `onboard-dot` from `frontend/index.html`. Delete all orphan CSS: `.ex-role-dot`, `.onboard-dot`, `.dot-analyst`, `.dot-vp`, `.dot-partner`, and `.scenario-btn.dot-*-border` colored-border rules. The `.scenario-btn` base rule and `:hover` rule are retained. No JS changes needed — `app.js` never references dot classes at runtime.

## Decisions

- **Colored button borders removed.** The `.scenario-btn.dot-partner-border` class on the Compare shortcut button was the only `dot-*-border` usage. Removing it makes the Compare shortcut visually consistent with Single shortcuts (neutral border). The button is still distinguishable via its `→` suffix and "Compare" row label.
- **No padding adjustment needed.** The dot spans were `inline-block` with `flex-shrink: 0`; removing them does not leave a visible gap because the parent flexbox reflows naturally.

## Files changed

| File | Change |
|------|--------|
| `frontend/index.html` | Removed 9 `<span>` elements (3 `.ex-role-dot`, 6 `.onboard-dot`). Removed `dot-partner-border` class from Compare shortcut button. |
| `frontend/styles.css` | Deleted `.ex-role-dot` block, `.dot-analyst`/`.dot-vp`/`.dot-partner` rules, `.scenario-btn.dot-*-border` rules (3), `.onboard-dot` block. |

## Verification

- `grep -rn 'ex-role-dot\|onboard-dot' frontend/` — zero hits.
- `grep -rn 'dot-analyst\|dot-vp\|dot-partner' frontend/` — zero hits.
- `pytest tests/ -v` — 172 passed, 14 skipped, 0 failed.
- Manual: all shortcut buttons and onboard cards fire correctly with no dots visible and no layout shift.
