# MET-C: Demo Question Guide + Pacific Demo Narrative

**Date:** 2026-04-27
**Scope:** Documentation only — no application code changes
**Depends on:** MET-A (commit `2513838`), MET-B (commit `3567b1d`)

---

## Executive Summary

Session Audit (MET-A/B) shipped but no user-facing doc explains it. The 12 benchmark queries are buried in JSON. No self-service reviewer guide exists — reviewers must follow the Spanish demo script or read the dense UX summary. This batch creates `docs/pacific_demo_guide.md` as a reviewer companion and updates four existing docs to reflect Session Audit.

**Task count:** P0=1, P1=1, P2=3

---

## Tasks

### T1 — Create `docs/pacific_demo_guide.md` [P0]

**What:** Create the primary deliverable — an English, self-service reviewer companion guide.

**Why:** No doc currently tells a reviewer "try this query as this role, look for this result." The 12 benchmark queries are only in `evals/test_queries.json`. The live audit comparison (analyst vs partner → Session Audit) is the strongest unexplained feature.

**Structure:**

1. **Header + positioning** — 2 sentences: "Self-service companion for reviewers. For the live demo script see `demo.md`; for the video narration see `script_en.md`."
2. **Quick orientation** — Role/policy/mode cheat sheet (compact table). Link to `summaryUserExp.md` for depth.
3. **Benchmark questions (q001–q012)** — All 12 queries in readable form, grouped by role. For each: query text, role, what it tests (1 line), expected doc IDs. Source: `evals/test_queries.json`.
4. **Try these live** — 6+ guided queries:
   - **On-topic** — e.g. "What are the diligence risks for Meridian?" (vp, full_policy). Expected: due diligence + integration docs surface.
   - **Off-topic** — "What time is it?" or "Que hora es" (any role). Expected: low-relevance results, demonstrates retriever doesn't hallucinate.
   - **Permission wall** — ARR query as analyst with full_policy. Expected: 6 included, 10 blocked.
   - **Role escalation** — Same query as analyst then as partner. Expected: blocked count drops from 10 to 0.
   - **Stale detection** — IC + LP query as partner. Expected: 3 superseded docs demoted 0.5x.
   - **Financial model** — financial model query as VP. Expected: doc_007 (v1) demoted, doc_008 (v2) ranked higher.
5. **Live audit walkthrough** — The CTO comparison:
   - Step 1: Query "Who is Meridian's CTO?" as analyst (full_policy). Note included count and blocked count.
   - Step 2: Same query as partner. Note: more docs included, fewer/zero blocked, higher token usage.
   - Step 3: Open Metrics → Session Audit. Two entries (q013, q014) with visible differences in docs/tokens/blocked columns.
   - Explain: partner sees more docs, fewer blocked, higher budget utilization.
6. **Reading the Metrics tab** — Two sub-sections:
   - **Benchmark (q001–q012):** What the 12 queries test. Key metrics: violations=0, recall=1.0. De-emphasize precision@5 (explain why it looks low).
   - **Session Audit (q013+):** What it captures. P@5/recall are null for live queries (no expected_doc_ids). Metrics shown: docs, tokens, freshness, blocked, stale, dropped, budget.
7. **Public demo caveats:**
   - Session Audit is shared across all visitors in the current server process.
   - Do not enter sensitive or personal information.
   - Logs reset when the server restarts (in-memory, no disk persistence).
   - On Render/ephemeral hosting, logs also reset on redeploy.
8. **Pacific framing** — 2-3 sentences: context governance, permission-aware assembly, auditability, traceability, live session observability.

**Files affected:** `docs/pacific_demo_guide.md` (new)

**Acceptance criteria:**
- File exists with all 8 sections
- All 12 benchmark queries present with full text
- 6+ live query suggestions with role/policy/expected observations
- CTO audit walkthrough with step-by-step instructions
- "Session Audit" mentioned at least 5 times
- "q013" referenced at least once
- Public demo caveats present

---

### T2 — Update `script_en.md` PART 4 [P1]

**What:** Expand PART 4 (~30s → ~45s) to mention Session Audit after the benchmark section.

**Why:** PART 4 only covers benchmark metrics. Session Audit (q013+) is invisible in the video script.

**Changes (lines 97–110):**
- After the existing benchmark narration (line 109), add a new stage direction + ~3 narration sentences:
  - Point at Session Audit section below the benchmark table
  - "Below the benchmark, there's a Session Audit log. Every query I ran in Single mode — the Permission Wall, the Stale Detection — is logged here as q013, q014, with full pipeline metrics. If I'd run the same query as analyst and then as partner, you'd see the difference right here: more documents, fewer blocks, higher budget usage."
  - Brief caveat: "This is an in-memory log for the current session — it resets when the server restarts."
- Bump PART 4 header from "~30 seconds" to "~45 seconds"

**Files affected:** `script_en.md` (edit lines 97–110)

**Acceptance criteria:**
- `grep -c "Session Audit" script_en.md` → ≥1
- PART 4 timing updated to ~45 seconds
- Narration mentions q013+, role comparison value, reset caveat
- No other PARTs modified
- Video-narration style preserved (stage directions in `> *[...]*`, speech in quotes)

---

### T3 — Update `demo.md` Demo E [P2]

**What:** Add a brief Session Audit paragraph to Demo E (Spanish, ~5 lines).

**Why:** Demo E only covers the benchmark dashboard. A presenter should know Session Audit exists below.

**Changes (after line 198, before the `---` at line 201):**
- Add "**Session Audit (debajo de la tabla de benchmark):**" heading
- 2-3 lines: scroll down, point at session audit section, mention q013+ entries from earlier queries, note that P@5/Recall are null for live queries, mention reset-on-restart caveat.
- Keep in Spanish, same style as surrounding Demo E content.

**Files affected:** `demo.md` (edit around lines 198–201)

**Acceptance criteria:**
- `grep -c "Session Audit" demo.md` → ≥1
- Addition is in Spanish
- Does not modify the 3-5 minute script in Section 5 (only Demo E in Section 4)
- Presenter-script style preserved

---

### T4 — Update `summaryUserExp.md` Section 4.3 [P2]

**What:** Add a "Session Audit" sub-section after the per-query table description (after line 235).

**Why:** Section 4.3 only documents the benchmark layer. Session Audit is undocumented in the UX reference.

**Changes (insert after line 235, before "Why it is useful"):**
- New sub-heading: `**Session Audit (below the benchmark table):**`
- Describe: fetched on every Metrics tab switch, shows live `/query` entries starting at q013, table columns (Query, Time, Role, Policy, Docs, Tokens, Freshness, Blocked, Stale, Dropped, Budget), expandable doc ID chips, empty state message, null P@5/recall explanation, public-demo caveat (shared state, no persistence, reset on restart).

**Files affected:** `summaryUserExp.md` (edit around line 235)

**Acceptance criteria:**
- `grep -c "Session Audit" summaryUserExp.md` → ≥1
- Describes table columns, q013+ numbering, null P@5/recall, persistence caveat
- Does not modify existing benchmark description
- Same factual/descriptive style as surrounding content

---

### T5 — Update `README.md` Metrics scenario row [P2]

**What:** Expand the Metrics row in the scenarios table and add the `/session-audit` endpoint to the Architecture code block.

**Why:** README only says "12 test queries" for Metrics. Session Audit endpoint is missing from the API list.

**Changes:**
- Line 33: Expand Metrics description from "Live pipeline metrics: precision@5, recall, permission violation rate, trace counts across 12 test queries." to also mention "+ live Session Audit log (q013+) of every query run in the current server session."
- Line 42: Add `GET  /session-audit → in-memory query log` after the `/evals` line.

**Files affected:** `README.md` (edit lines 33, 42)

**Acceptance criteria:**
- `grep -c "Session Audit\|session-audit" README.md` → ≥1
- `/session-audit` appears in Architecture code block
- No other README sections modified

---

## Execution Order

1. **T1** — Create `docs/pacific_demo_guide.md` (standalone, no dependencies)
2. **T2** — Update `script_en.md` (standalone)
3. **T3** — Update `demo.md` (standalone)
4. **T4** — Update `summaryUserExp.md` (standalone)
5. **T5** — Update `README.md` (standalone)

T2–T5 are independent of each other and can run in any order after T1. T1 first because it's the primary deliverable and informs the framing for the other updates.

## Verification Commands

```bash
# Content checks
grep -c "Session Audit" docs/pacific_demo_guide.md    # → ≥5
grep -c "q013" docs/pacific_demo_guide.md              # → ≥1
grep -c "Session Audit" script_en.md                   # → ≥1
grep -c "Session Audit" demo.md                        # → ≥1
grep -c "Session Audit" summaryUserExp.md              # → ≥1
grep -c "session-audit\|Session Audit" README.md       # → ≥1

# No application code modified
git diff --name-only src/ frontend/ tests/              # → empty

# Test suite unchanged
python3 -m pytest tests/ -q                            # → 184 passed, 14 skipped
```

## Docs Updated During Execution

| File | Action |
|------|--------|
| `docs/pacific_demo_guide.md` | **Create** — primary deliverable |
| `script_en.md` | **Edit** — PART 4 Session Audit addition |
| `demo.md` | **Edit** — Demo E Session Audit addition |
| `summaryUserExp.md` | **Edit** — Section 4.3 Session Audit addition |
| `README.md` | **Edit** — Metrics row + Architecture block |
| `docs/HANDOFF.md` | **Append** — MET-C session entry (at execution end) |
