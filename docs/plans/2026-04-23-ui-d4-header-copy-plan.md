# UI-D4: Mode tabs, placeholder, warning & role descriptions

## Motivation

The copy a first-time visitor hits before any click — mode tabs, search placeholder, warning text, role descriptions — either assumes prior knowledge ("Single / Compare / Evals / Admin", "Ask about Meridian Technologies…") or reads as boilerplate. UI-D4 replaces them with intent-first copy and adds corpus counts so the role selector telegraphs what each role actually sees.

## Preflight: corpus count verification

Computed from `corpus/metadata.json` + `corpus/roles.json` using the access rule `user.access_rank >= doc.min_role.access_rank`:

| Role | Accessible | Total |
|------|-----------|-------|
| analyst | 5 | 12 |
| vp | 10 | 12 |
| partner | 12 | 12 |

These counts match the expected values. Role descriptions use these exact numbers.

## Decision 1 — Mode tab labels

| Before | After | `data-mode` (unchanged) |
|--------|-------|------------------------|
| Single | Query | `single` |
| Compare | Side-by-side | `compare` |
| Evals | Metrics | `evals` |
| Admin | Upload | `admin` |

`data-mode` values, `aria-pressed` wiring, and all event handlers unchanged.

## Decision 2 — Search placeholder

Before: `Ask about Meridian Technologies…`
After: `Try: 'ARR growth', 'integration risks', 'IC recommendation'…`

## Decision 3 — No Filters warning

Before: `⚠ This policy skips all access controls. Restricted documents will appear in results regardless of role.`
After: `⚠ Baseline only — no access controls. Use for comparison.`

The `<span aria-hidden="true">⚠</span>` wrapper was inlined to a plain `⚠` character — no functional change.

## Decision 4 — ROLE_DESCRIPTIONS

Before: multi-sentence descriptions (3 lines each).
After: single-line strings with corpus counts:
- analyst: "Sees 5 of 12 docs — public filings, research notes, press release, sector overview."
- vp: "Sees 10 of 12 docs — adds deal memos, financial models, diligence analyses."
- partner: "Sees 12 of 12 docs — full corpus including IC memo and LP update."

Consumer `updateRoleDescription(role)` uses `textContent` assignment — plain text, no HTML needed.

## Files changed

| File | Change |
|------|--------|
| `frontend/index.html` | Mode tab labels, search placeholder, warning text |
| `frontend/app.js` | `ROLE_DESCRIPTIONS` object rewritten |
| `CLAUDE.md` | Mode section header and four bullet headers updated with new visible labels + `data-mode` keys |
| `README.md` | Scenario table and file tree comment updated |

## Verification

- `grep -n '>Single<\|>Compare<\|>Evals<\|>Admin<' frontend/index.html` — zero (only `.examples-label` rows reference Single/Compare as shortcut row labels, not mode buttons)
- `grep -n 'Ask about Meridian' frontend/index.html` — zero
- `pytest tests/ -v` — 172 passed, 14 skipped, 0 failed
