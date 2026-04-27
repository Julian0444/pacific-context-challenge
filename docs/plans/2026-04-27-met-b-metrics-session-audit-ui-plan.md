# MET-B: Metrics Dashboard — Benchmark + Session Audit UI

**Date:** 2026-04-27
**Depends on:** MET-A (commit `2513838`, merged to main)
**Scope:** Frontend-only. No backend changes.
**Files:** `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`

## Executive Summary

The Metrics tab currently shows 12 benchmark queries with text truncated to 50 characters, making them unreadable. The backend `GET /session-audit` endpoint (MET-A) exists but the frontend has zero awareness of it. This plan adds: full-text benchmark questions, a Session Audit section for live queries (q013+), and clear visual separation between the two.

---

## Layout (top → bottom)

1. **Section header** — "Evaluation Dashboard" (existing)
2. **Narrative banner** — "Zero permission violations…" (existing, unchanged)
3. **Aggregate metric cards** — 10 cards (existing, unchanged)
4. **Section label** — "Benchmark Questions" (new `<h3>`)
5. **Benchmark table** — 12 rows, q001–q012, full query text (modified)
6. **Benchmark footer** — "Queries run: 12 · Failed: 0" (existing, unchanged)
7. **Visual divider** — `<hr>` or styled border
8. **Session Audit header** — "Session Audit" `<h3>` + session-started timestamp + disclaimer
9. **Session Audit content** — live entry cards/rows or empty state

---

## Task Blocks

### P0-1: Remove 50-char truncation from benchmark table

**What:** In `app.js` line 936, remove the `qText.length > 50` truncation. Render full `qText` inline. Keep the `title=` tooltip (harmless). Remove the `…` suffix logic entirely.

**Why:** Benchmark questions are currently unreadable — "What did Summit Financial Research revise about Me…" conveys nothing. The demo story requires the audience to read the questions to understand what was tested.

**Acceptance criteria:**
- All 12 benchmark rows show the full query text with no ellipsis
- Text wraps naturally inside `.evals-query-cell`
- No horizontal scroll on the table at ≥960px viewport

**Files:** `frontend/app.js` (line 936), `frontend/styles.css` (`.evals-query-cell` max-width)

---

### P0-2: Widen the Query column for full text

**What:** In `styles.css`, change `.evals-query-cell` from `max-width: 320px` to `max-width: none` (or remove the rule). Set `min-width: 280px` so the column doesn't collapse. Keep `white-space: normal`.

**Why:** The 320px cap plus 50-char truncation was a double constraint. Removing truncation without widening would cause an ugly narrow column of wrapped text.

**Acceptance criteria:**
- Query column expands to fit natural text length
- Other columns (Role, P@5, etc.) remain compact mono-cell
- Table is horizontally scrollable on mobile (≤640px) via existing `.evals-table-wrap`

**Files:** `frontend/styles.css` (`.evals-query-cell`)

---

### P0-3: Add "Benchmark Questions" section label

**What:** In `renderEvals()`, insert an `<h3 class="evals-section-label">Benchmark Questions</h3>` above the `.evals-table-wrap` div. This labels the benchmark portion explicitly.

**Why:** Once Session Audit appears below, the benchmark section needs a visible label so the user understands the split. Even standalone, "Benchmark Questions" frames the 12 rows as a test suite, not decoration.

**Acceptance criteria:**
- "Benchmark Questions" heading appears between the metric cards and the table
- Styled consistently with existing `.evals-title` weight/family but smaller (h3)

**Files:** `frontend/app.js` (`renderEvals`), `frontend/styles.css` (new `.evals-section-label`)

---

### P1-1: Fetch `GET /session-audit` on every Metrics tab switch

**What:** Add `fetchSessionAudit()` async function in `app.js`. Call it inside `switchMode()` whenever `isEvals` is true — unconditionally (not gated by a loaded flag). The fetch result is stored in a module-level variable (`_sessionAuditData`). On success, call `renderSessionAudit(data)`. On error, render an inline error in the session audit container.

**Why:** Unlike `/evals` (deterministic, cached), session audit changes every time the user runs a query. It must re-fetch on every tab switch so that q013+ entries appear immediately after a query run.

**Acceptance criteria:**
- Switching to Metrics always fetches `/session-audit` (network tab shows the request)
- `/evals` is still fetched only once (existing `evalsLoaded` gate unchanged)
- A failed `/session-audit` fetch does not break the benchmark section
- The session audit section updates independently of benchmark rendering

**Files:** `frontend/app.js` (new function + `switchMode` modification)

---

### P1-2: Render Session Audit section

**What:** Add `renderSessionAudit(data)` function. It targets a `<div id="session-audit-content">` container that lives inside `#evals-section` below the benchmark footer. Structure:

```
<div class="session-audit-section">
  <h3 class="evals-section-label">Session Audit</h3>
  <p class="session-audit-meta">
    Session started: <time>...</time> · <span class="session-audit-count">N</span> queries
  </p>
  <div class="session-audit-disclaimer">
    Shared demo log — do not enter sensitive information. Resets on server restart.
  </div>
  <!-- entries or empty state -->
</div>
```

Each entry renders as a row in a session audit table with columns:
- **Query**: qid pill + full query text (no truncation)
- **Time**: relative timestamp (e.g., "2m ago") with `title=` showing ISO timestamp
- **Role**: role chip
- **Policy**: policy label from `POLICY_META`
- **Docs**: included count
- **Tokens**: total tokens
- **Freshness**: avg freshness score, or "N/A" if `POLICY_META[policy].skipFreshness`
- **Blocked**: count (red highlight if >0)
- **Stale**: count (yellow highlight if >0)
- **Dropped**: count
- **Budget**: utilization percentage

No P@5 or Recall columns — live entries have null values for those. This avoids showing misleading "0.00" or needing a "—" column that matches no benchmark column.

**Why:** This is the core deliverable. Live queries from Query mode appear as q013+ in the Metrics tab, creating the demo story: "benchmark credibility plus live context audit."

**Acceptance criteria:**
- After running a query in Query mode and switching to Metrics, the query appears as q013
- Entry shows full query text, role, policy, and all pipeline metrics
- Freshness shows "N/A" for `naive_top_k` and `permission_aware` policies
- Multiple entries accumulate (q013, q014, q015…)

**Files:** `frontend/app.js` (new function), `frontend/index.html` (container div), `frontend/styles.css` (new styles)

---

### P1-3: Session Audit empty state

**What:** When `data.entries` is empty (no live queries yet), render:

```html
<div class="session-audit-empty">
  Run a query in <strong>Query</strong> mode and it will appear here as q013.
</div>
```

Styled as a muted centered message, similar to existing empty-state patterns.

**Why:** On first Metrics visit (before any queries), the session audit section would be blank. The empty state guides the user to the Query tab.

**Acceptance criteria:**
- Empty state visible on first Metrics visit before any query is run
- Disappears once entries exist
- Text mentions "q013" specifically (grounded in `benchmark_count = 12`)

**Files:** `frontend/app.js` (inside `renderSessionAudit`), `frontend/styles.css`

---

### P1-4: Session Audit disclaimer banner

**What:** A small disclaimer block above the session audit entries:

> Shared demo log — visible to all visitors on this server instance. Do not enter sensitive information. Resets on server restart.

Styled with a muted border-left accent (similar to `.evals-narrative` but subdued — use `var(--text-tertiary)` border, not `var(--accent)`).

**Why:** The audit log is globally shared across all demo visitors in a single process. Users need to know their queries are visible to others and ephemeral.

**Acceptance criteria:**
- Disclaimer is always visible in the session audit section (even in empty state)
- Visually subdued — not alarming, but clearly readable
- Does not interfere with entry rendering

**Files:** `frontend/app.js`, `frontend/styles.css`

---

### P2-1: Expandable doc ID chips on session audit entries

**What:** Each session audit entry has a collapsible detail row showing included/blocked/stale/dropped doc IDs as compact chips (reusing existing trace chip styles). Collapsed by default. A small toggle ("▸ docs" / "▾ docs") reveals the row.

**Why:** The session audit entry shows counts (Blocked: 10), but seeing *which* docs were blocked is useful for the demo story — it mirrors the Decision Trace in Query mode.

**Acceptance criteria:**
- Clicking the toggle reveals doc ID chips below the entry row
- Chips use existing color coding (green included, red blocked, yellow stale, grey dropped)
- Toggle is compact and does not break table layout

**Files:** `frontend/app.js`, `frontend/styles.css`

---

### P2-2: Copy affordances

**What:** Add a small copy button (clipboard icon) next to each query text in both the benchmark table and session audit table. On click, copies the full query text to clipboard. Brief "Copied" tooltip feedback.

**Why:** Demo users often want to paste a benchmark question into the search bar to run it themselves, or share a live query. Currently requires manual selection.

**Acceptance criteria:**
- Copy button appears on hover (or always visible — decide during implementation)
- `navigator.clipboard.writeText()` with fallback
- Visual feedback (brief tooltip or icon change)
- Works in both benchmark and session audit sections

**Files:** `frontend/app.js`, `frontend/styles.css`

---

### P2-3: Add `#session-audit-content` container to `index.html`

**What:** Inside `#evals-section`, after `#evals-content`, add:

```html
<div id="session-audit-content">
  <!-- Injected by app.js -->
</div>
```

**Why:** Provides a stable DOM target for `renderSessionAudit()` that is independent of `#evals-content`, so benchmark rendering and session audit rendering don't clobber each other.

**Acceptance criteria:**
- Container exists in the HTML
- `renderEvals()` writes to `#evals-content` (unchanged)
- `renderSessionAudit()` writes to `#session-audit-content` (new)
- Both render independently

**Files:** `frontend/index.html`

---

### P2-4: Responsive layout for session audit

**What:** At ≤640px, the session audit table should either horizontally scroll (like the benchmark table via `.evals-table-wrap`) or collapse into a card layout. Given that session entries have fewer columns than benchmark (no P@5, Recall, Violations), horizontal scroll should suffice.

**Why:** Mobile readability is a stated requirement. The session audit table will have 11 columns — narrower than the 12-column benchmark table but still needs scroll on small screens.

**Acceptance criteria:**
- Session audit table is readable on 375px viewport (iPhone SE)
- No content overflow or clipping
- Font sizes match existing `.evals-table` mobile rules

**Files:** `frontend/styles.css`

---

## Execution Order

```
P0-1 + P0-2 + P0-3  (parallel — benchmark readability)
    ↓
P2-3                 (HTML container — prerequisite for P1-*)
    ↓
P1-1                 (fetch logic)
    ↓
P1-2 + P1-3 + P1-4  (parallel — session audit rendering)
    ↓
P2-4                 (responsive)
    ↓
P2-1 + P2-2          (parallel — polish)
```

## Count Summary

P0=3, P1=4, P2=4, P3=0

---

## Acceptance Criteria (batch-level)

1. **Benchmark readability**: All 12 benchmark questions fully readable in the table — no truncation, no ellipsis.
2. **Session audit fetch**: `GET /session-audit` fires on every Metrics tab switch.
3. **Session audit rendering**: Live entries (q013+) appear with full query, role, policy, metrics.
4. **Empty state**: "Run a query…" message when no live queries exist.
5. **Disclaimer**: Public-demo warning visible in session audit section.
6. **Freshness N/A**: Policies that skip freshness show "N/A" in session audit.
7. **No P@5/Recall columns** in session audit (live entries have null values).
8. **No regression**: Query mode, Compare mode, Upload mode unchanged.
9. **Desktop + mobile**: Both layouts readable (test at 1440px and 375px).

---

## Verification Plan

### Automated
```bash
# Existing test suite — must remain green
.venv/bin/python -m pytest tests/ -v
# Expected: 184 passed, 14 skipped (no new backend tests needed)
```

### Manual browser checks
1. Start server: `.venv/bin/python -m uvicorn src.main:app --reload`
2. Open `http://localhost:8000/app/`
3. **Metrics tab (cold):**
   - Narrative banner renders ("Zero permission violations…")
   - 10 metric cards render
   - "Benchmark Questions" label visible
   - All 12 rows show full query text, no ellipsis
   - Session Audit section shows empty state: "Run a query… q013"
   - Disclaimer visible
4. **Run a query in Query mode:**
   - Analyst + "What is Meridian's ARR growth rate…" + Full Pipeline → Run
5. **Switch to Metrics:**
   - Session Audit section now shows q013
   - q013 row shows: full query, analyst, full_policy, docs, tokens, freshness value, blocked=10, stale=1, dropped, budget
6. **Run another query (VP + different text) and switch to Metrics:**
   - q014 appears below q013
7. **Check freshness N/A:**
   - Run a query with `naive_top_k` policy → switch to Metrics → freshness column shows "N/A" for that entry
8. **No regression checks:**
   - Query mode: run Permission Wall preset → results render, blocked section works, Decision Trace opens
   - Compare mode: run ARR query → three columns render
   - Upload mode (if enabled): form visible
9. **Mobile (375px):**
   - Metrics tab: metric cards in 2-column grid, benchmark table horizontally scrollable, session audit table horizontally scrollable
10. **Copy affordance (if implemented):**
    - Hover over benchmark query → copy button appears → click → clipboard contains query text

### Network verification
- On first Metrics visit: one `GET /evals` + one `GET /session-audit`
- On subsequent Metrics visits: only `GET /session-audit` (no `/evals` re-fetch)

---

## Docs to Update During Execution

- `CLAUDE.md` — Add Session Audit UI section under Frontend description
- `docs/HANDOFF.md` — Add MET-B completion entry
- `summaryUserExp.md` — Update Metrics mode description to include session audit
- `demo.md` — Update Demo E (Metrics) to mention session audit section

---

## No-Regression Areas

| Area | What must not change |
|------|---------------------|
| Query mode | Stale-results banner (UI-B), preset buttons, empty-state cards, blocked section, Decision Trace, Export JSON |
| Compare mode | Three-column layout, compare empty state, export JSON, compact trace summaries |
| Upload mode | Ingest form, ALLOW_INGEST gating via /health |
| Evals narrative | Green banner text and three-sentence structure |
| Metric cards | 10 cards with animation delays and hover lift |
| Backend | No backend files modified |
