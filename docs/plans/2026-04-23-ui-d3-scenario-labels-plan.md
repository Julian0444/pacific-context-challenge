# UI-D3: Scenario labels and tooltips reframed

## Motivation

"DD risks" and "IC memo" are insider jargon that presumes familiarity with Atlas Capital's vocabulary. Tooltips described the role ("VP · sees deal memos") rather than the phenomenon the user will observe. Reframing labels and tooltips to be phenomenon-first makes the UI parseable by non-finance readers.

## Label migration

| Location | Before | After |
|----------|--------|-------|
| Single row button | DD risks | Diligence risks |
| Single row button | IC memo | IC recommendation |
| Single onboard card title | VP Deal View | Financial model access |
| Compare onboard card title | VP Deal View | Financial model access |
| Stale Detection (all) | *(unchanged)* | *(unchanged)* |
| Permission Wall (all) | *(unchanged)* | *(unchanged)* |
| Compare row button label | Stale detection → | *(unchanged)* |

## Tooltip reframing

All tooltips rewritten to describe the phenomenon, not the role or codename:

- **Single shortcuts**: "Shows diligence risk findings from deal materials…" / "Shows the investment committee recommendation…"
- **Compare shortcuts**: "Opens side-by-side comparison — superseded documents get demoted only under Full Pipeline"
- **Onboard buttons**: each tooltip describes what appears in the result, not "Run this scenario in Single mode (full pipeline)"
- **No tooltip references "selected role"** — shortcuts set a fixed role via `data-role`, so the user didn't pick it

## Scope

Text-only changes to `frontend/index.html`. No CSS, no JS logic, no structural HTML changes. `data-query` attributes (the actual query text) are untouched — those are domain content. Docs updated to reflect the new labels.

## Files changed

| File | Change |
|------|--------|
| `frontend/index.html` | Rewrote 2 button labels, 3 onboard card titles, 9 `title=` tooltips, 4 `.onboard-hint` strings |
| `CLAUDE.md` | Updated scenario entry points paragraph and Single-mode card names |
| `README.md` | Updated scenario table row |
| `demo.md` | Updated 4 references to old labels |
| `summaryUserExp.md` | Updated 4 references to old labels |
| `docs/HANDOFF.md` | Updated 3 references; historical rename note preserved with "(later → Financial model access in UI-D3)" annotation |

## Not changed

- `frontend/app.js:45` — "IC memos" in `ROLE_DESCRIPTIONS` is domain vocabulary describing corpus document types, not a UI label
- `README.md:75` — "IC memos, LP updates" describes corpus access levels
- `data-query` attribute values — domain content, not UI labels
- `corpus/` documents — domain content

## Verification

- `grep -rn 'DD risks\|IC memo' frontend/` → only domain content in app.js role description
- `grep -n 'selected role' frontend/index.html` → zero
- `grep -rn 'VP Deal View' frontend/` → zero
- `pytest tests/ -v` — 172 passed, 14 skipped, 0 failed
