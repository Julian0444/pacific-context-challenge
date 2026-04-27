# QueryTrace — Reviewer Demo Guide

A self-service companion for reviewers exploring the deployed QueryTrace app. For the live presenter script see [`demo.md`](../demo.md); for the Loom/video narration see [`script_en.md`](../script_en.md).

---

## Quick orientation

| Concept | What it means |
|---------|---------------|
| **Role** (Analyst / VP / Partner) | Who you are. Each role has different document access. Analyst sees 6 of 16 docs; VP sees 12; Partner sees all 16. |
| **Policy** (No Filters / Permissions Only / Full Pipeline) | How context is assembled. No Filters = dangerous baseline with no controls. Permissions Only = RBAC filtering + budget. Full Pipeline = RBAC + freshness scoring + budget (production mode). |
| **Query mode** | Run one query with one policy. See result cards, blocked documents, and a Decision Trace. |
| **Side-by-side mode** | Same query through all three policies in parallel. Three columns, instant visual comparison. |
| **Metrics mode** | Two sections: Benchmark (12 static test queries) and Session Audit (live queries from your session). |
| **Upload mode** | PDF ingestion form (may be disabled on public deploys). |

For a deeper explanation of each mode and metric, see [`summaryUserExp.md`](../summaryUserExp.md).

---

## Benchmark questions (q001–q012)

These 12 queries run automatically when you open the Metrics tab. They use `full_policy` and cover all three roles. The table below shows the full query text, the role, and what each query is designed to test.

### Analyst queries (rank 1 — sees 6 of 16 documents)

| ID | Query | What it tests |
|----|-------|---------------|
| q001 | What is Meridian's annual recurring revenue growth rate and net revenue retention? | Normal retrieval. Expects the 10-K (doc_001) and the Q4 research note (doc_003). |
| q002 | What did Summit Financial Research revise about Meridian's growth estimates and enterprise value target? | Stale-document behavior. doc_003 is current; doc_002 (stale Q3 note) may appear alongside it with a freshness penalty, showing demotion-not-removal. |
| q003 | What risks did Atlas Capital identify in their due diligence assessment of Meridian? | Permission filtering. The retriever finds VP/partner docs as top matches, but analyst-role filtering blocks all 10 restricted docs. Only the sector overview (doc_005) and public docs remain. |

### VP queries (rank 2 — sees 12 of 16 documents)

| ID | Query | What it tests |
|----|-------|---------------|
| q004 | What is the breakdown of Meridian's ARR by top customers and what is the customer concentration risk? | Customer concentration. Expects doc_012 (VP-level concentration analysis) and doc_001 (10-K). Partner-only docs (doc_010, doc_011, doc_013, doc_014) must be blocked. |
| q005 | How did the Atlas Capital financial model for Project Clearwater change between version 1 and version 2? | Stale model pair. doc_008 (v2, current) and doc_007 (v1, stale) should both appear; doc_007 is demoted 0.5x. |
| q007 | What are the operational integration risks for Meridian including the CTO departure and customer renewal exposure? | Integration risk. Expects doc_009 (integration email), doc_006 (DD memo), and doc_016 (CTO departure memo). Partner-only docs blocked. |
| q011 | What valuation figures exist for Meridian from public rumors versus Atlas internal diligence? | Contradictory sources. doc_015 (public rumor: $500M) vs doc_008 (internal model: $340M). Partner-only docs blocked. |
| q012 | What did Atlas learn about Meridian's CTO departure and engineering retention risk? | CTO continuity. Expects doc_016 (CTO departure context) and doc_009 (integration email). Partner-only docs blocked. |

### Partner queries (rank 3 — sees all 16 documents)

| ID | Query | What it tests |
|----|-------|---------------|
| q006 | What is the Investment Committee recommendation and proposed deal structure for acquiring Meridian Technologies? | IC/deal terms. Expects doc_010 (IC memo: $340M EV, 8.9x ARR). Partner access required. |
| q008 | What did the Atlas LP quarterly update communicate about the Project Clearwater pipeline activity? | LP reporting. Expects doc_011 (Q1 2024 LP letter). Partner access required. |
| q009 | What legal or regulatory risk did Atlas identify around Meridian's revenue recognition? | Legal diligence. Expects doc_013 (regulatory inquiry into revenue recognition). Partner access required. |
| q010 | How did the Investment Committee recommendation change between the draft and final Meridian acquisition memos? | Stale governance pair. doc_014 (draft: DEFER) is superseded by doc_010 (final: APPROVE at $340M). Both should appear; doc_014 is demoted. |

### Key benchmark results

- **Permission Violations: 0.0%** — across all 12 queries, no restricted document ever appeared in a context where the role should not see it.
- **Recall: 1.0** — every expected document was found.
- **Precision@5: ~0.33** — this looks low but is expected. The corpus has 16 documents and many queries are broad, so the system includes additional relevant context beyond the strict "expected" list. What matters is recall and zero violations.

---

## Try these live

These queries are not part of the benchmark. Run them in **Query mode** to explore different pipeline behaviors. Each one will appear in Session Audit as q013, q014, etc.

### 1. On-topic query

| Field | Value |
|-------|-------|
| Query | `What are the diligence risks for Meridian?` |
| Role | **VP** |
| Policy | **Full Pipeline** |
| What to look for | Due diligence docs (doc_006), integration email (doc_009), and CTO memo (doc_016) should surface. Partner-only docs (IC memo, LP update, legal memo) should be blocked. Check the blocked-documents section for the 4 partner-only blocks. |

### 2. Off-topic query

| Field | Value |
|-------|-------|
| Query | `What time is it?` |
| Role | **Analyst** |
| Policy | **Full Pipeline** |
| What to look for | The retriever still returns results (it ranks every corpus document by relevance and returns the top matches), but relevance scores will be low. This lets you inspect how the pipeline handles an out-of-domain prompt — permission filtering and budget packing still run normally. The query is also logged in Session Audit, so you can see the pipeline metrics for a query with no meaningful corpus match. |

### 3. Permission wall

| Field | Value |
|-------|-------|
| Query | `What is Meridian's ARR growth rate and net revenue retention?` |
| Role | **Analyst** |
| Policy | **Full Pipeline** |
| What to look for | Around 6 documents included, 10 blocked. Open the "documents blocked by permissions" section — each blocked doc shows the required role and why the analyst cannot access it. Open the Decision Trace for the full audit. |

### 4. Role escalation (same query, two roles)

Run the permission-wall query above as **Analyst**, then change the role to **Partner** and run it again.

| What changes | Analyst | Partner |
|--------------|---------|---------|
| Blocked docs | ~10 | 0 |
| Included docs | ~6 | More (full corpus accessible) |
| Budget utilization | Lower | Higher (more docs packed) |

The blocked-documents section disappears entirely for Partner. The Decision Trace narrative changes from "your role cannot access VP and partner level materials" to showing no blocks.

### 5. Stale detection

| Field | Value |
|-------|-------|
| Query | `What is the investment committee recommendation and LP update for the Meridian acquisition?` |
| Role | **Partner** |
| Policy | **Full Pipeline** |
| What to look for | Zero blocked documents (partner has full access). The Full Pipeline column shows 3 superseded documents with the "Superseded" badge: doc_002 (research note v1 → doc_003), doc_007 (financial model v1 → doc_008), and doc_014 (IC draft DEFER → doc_010 final APPROVE). Each is demoted 0.5x on freshness. |

### 6. Financial model comparison

| Field | Value |
|-------|-------|
| Query | `What are the financial model assumptions, revenue projections, and deal valuation for Project Clearwater?` |
| Role | **VP** |
| Policy | **Full Pipeline** |
| What to look for | doc_008 (financial model v2, current) ranks higher than doc_007 (v1, stale). doc_007 carries the "Superseded by doc_008" badge and a 0.5x freshness penalty. Partner-only docs are blocked. Compare this to **Permissions Only** policy — the stale badge disappears because that policy does not score freshness. |

---

## Live audit walkthrough: analyst vs partner

This walkthrough demonstrates how Session Audit captures pipeline behavior differences across roles for the same query.

### Steps

1. **Open Query mode.** Set role to **Analyst**, policy to **Full Pipeline**.
2. **Run:** `What did Atlas learn about Meridian's CTO departure and engineering retention risk?`
   - Note the included count, blocked count, and total tokens in the summary bar.
   - As analyst, several VP/partner-only docs about the CTO departure and integration risks should be blocked.
3. **Change role to Partner.** Run the same query again.
   - With partner access, the blocked count should drop to zero.
   - More documents are accessible, so included count and token usage should generally be higher.
4. **Open the Metrics tab.** Scroll down past the benchmark table to the **Session Audit** section.
5. **Compare the two entries** (q013 and q014, or whatever the next IDs are):
   - The analyst entry should show more blocked docs and fewer included docs.
   - The partner entry should show zero blocked, more included docs, and higher budget utilization.
   - Both entries show full pipeline metrics (Docs, Tokens, Freshness, Blocked, Stale, Dropped, Budget).

### What this demonstrates

The same query produces different context packages depending on who is asking. The Session Audit table makes this comparison visible without re-running queries — every live query is logged with its full pipeline metrics.

---

## Reading the Metrics tab

The Metrics tab has two sections, separated by a divider.

### Benchmark (q001–q012)

The top section loads automatically on the first Metrics tab visit. It runs 12 predefined test queries (from `evals/test_queries.json`) through `full_policy` and shows:

- **Narrative banner** — Executive summary: permission violations, recall, budget utilization tier.
- **10 metric cards** — Aggregate metrics across all 12 queries. The three that matter most: Permission Violations (0.0%), Recall (1.0), and Avg Blocked.
- **Benchmark table** — One row per test query with role, precision, recall, docs, tokens, freshness, blocked, stale, dropped, budget, and violations columns.

Benchmark results are cached after the first load — subsequent tab switches are instant.

### Session Audit (q013+)

Below the benchmark table, the Session Audit section shows every query you (or anyone using the current server session) have run in Query mode.

- **IDs start at q013** because q001–q012 are reserved for benchmark queries.
- **Columns**: Query (full text), Time (relative, with ISO timestamp on hover), Role, Policy (human-readable label), Docs, Tokens, Freshness, Blocked, Stale, Dropped, Budget.
- **Expandable doc chips**: Click the "docs" toggle on any row to see color-coded chips for included (green), blocked (red), stale (yellow), and dropped (gray) document IDs.
- **Precision@5 and Recall are not shown** for live queries. These metrics require predefined `expected_doc_ids` to compute, which only the benchmark queries have. Live queries show pipeline metrics (docs, tokens, blocked, etc.) but not retrieval-quality scores.
- **Fetched on every tab switch** — Session Audit refreshes each time you click the Metrics tab, so new queries appear immediately.
- **Empty state**: If no live queries have been run, the section shows: "Run a query in Query mode and it will appear here as q013."

### What does NOT appear in Session Audit

- Queries run via **Side-by-side mode** (`/compare` endpoint) are not logged.
- The **Metrics tab itself** (`/evals` endpoint) is not logged.
- Only `POST /query` calls are recorded.

---

## Public demo caveats

If you are using the deployed Render app (or any shared server):

- **Session Audit is shared.** All visitors to the same server process see the same audit log. Your queries are visible to other concurrent users.
- **Do not enter sensitive or personal information.** Queries are stored in server memory and visible to anyone who opens the Metrics tab.
- **In-memory only.** The audit log lives in server memory with no disk persistence. It survives for the lifetime of the server process.
- **Resets on restart.** When the server process restarts (or Render redeploys), the entire Session Audit log is cleared. Benchmark queries (q001–q012) are unaffected because they are recomputed from the static test file.
- **Upload mode** may be disabled on public deploys (`ALLOW_INGEST=false`). If the Upload tab is not visible, this is intentional.

---

## Why this matters

QueryTrace demonstrates a concrete approach to a real enterprise AI problem: **LLMs have no concept of who is asking.** If you pass a confidential document into the context window, the LLM will use it — regardless of whether the user should have access.

The project implements the governance layer that sits **before** the LLM prompt:

- **Permission-aware context assembly** — RBAC filtering ensures each role only sees documents at or below their access level.
- **Freshness scoring** — Superseded documents are demoted, not removed, so the LLM prioritizes current information.
- **Token budgeting** — Context is packed within a budget, so the LLM receives a curated, right-sized package.
- **Full decision traceability** — Every query produces an auditable Decision Trace showing what was included, blocked, demoted, or dropped, and why.
- **Live session observability** — Session Audit provides a running log of pipeline decisions across queries, making it possible to compare behavior across roles, policies, and query types without re-running anything.
