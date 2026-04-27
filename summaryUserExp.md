# QueryTrace: Complete User Experience Summary

---

## 1. What is QueryTrace and what does it do

QueryTrace is a lab tool that simulates how an enterprise AI search system assembles the context it would pass to a language model (LLM) to answer questions.

**It is not a chatbot.** It does not answer questions. It does not generate text with AI. What it does is show *which documents the system would choose* to build the context package an LLM would use as its source of truth, and *why it chose those and not others*.

The simulated scenario is the following: a private equity firm called **Atlas Capital Partners** is evaluating the acquisition of a fintech company called **Meridian Technologies** (internal project: "Project Clearwater"). The document corpus contains 16 realistic files that any investment firm would have in a deal like this:

| Document type | Example | Who can see it |
|---|---|---|
| Public filings (10-K) | Meridian annual report FY2023 | Everyone (Analyst, VP, Partner) |
| Research notes | Summit Financial Research coverage | Everyone |
| Press releases | Meridian Series C announcement | Everyone |
| Public news | Press article with valuation rumor | Everyone |
| Sector overview | Atlas internal fintech overview | Everyone |
| Due diligence memos | Atlas Phase 1 findings | VP and Partner only |
| Financial models | Deal model v1.0 and v2.0 | VP and Partner only |
| Internal emails | Integration risks | VP and Partner only |
| Internal CTO memo | CTO departure context and retention risk | VP and Partner only |
| Customer concentration analysis | ARR breakdown by customer | VP and Partner only |
| Investment Committee memo | Formal IC recommendation | Partner only |
| Legal memo | Regulatory risk and revenue recognition | Partner only |
| LP update | Quarterly letter to investors | Partner only |

The central point is: **not all users should see all documents**. A junior analyst should not see the Investment Committee memo. A VP should not see the LP letter. The system must enforce this.

---

## 2. The three roles: who you are when using the app

When you open QueryTrace, the first thing you choose is **your role**. There are three:

### Analyst (Rank 1 - lowest)
- Can see: public filings, research notes, press releases, sector overview, and public news.
- **Cannot see**: internal memos, financial models, emails, customer analyses, legal memo, IC memo, or LP updates.
- The most restrictive role. Out of 16 documents, has access to **6**.

### VP (Rank 2 - intermediate)
- Can see everything the analyst can **plus**: due diligence memos, financial models, internal emails, CTO memo, and customer concentration analysis.
- **Cannot see**: IC memo, legal memo, or LP updates (those are partner-only).
- Out of 16 documents, has access to **12**.

### Partner (Rank 3 - full access)
- Sees absolutely everything. All 16 documents.
- The only role that can see the Investment Committee memo, the legal memo, and the LP letter.

**What you see in the UI:** In the controls bar there are three buttons (Analyst, VP, Partner). Selecting one tells the system "let's simulate that I'm this person" and all searches will respect that role's permissions.

**Why this matters to the user:** To understand and demonstrate that the search system does not filter documents blindly, but respects access hierarchies. If you are an analyst and search for something, the system shows you only what your role is allowed to see, and also tells you how many documents *were blocked* and why.

---

## 3. The three policies: how context is assembled

In addition to the role, you can choose an **assembly policy** (visible only in Query mode). This controls *which pipeline stages are applied* to the retrieved documents:

### No Filters (naive_top_k)
- **What it does:** Searches for documents and returns them as-is, with no filters.
- **Does not filter by permissions.** An analyst would see confidential IC documents.
- **Does not evaluate freshness.** An outdated document appears the same as a new one.
- **Does not enforce a token budget.** Includes everything it finds with no limit.
- **Why it exists:** It is the "dangerous baseline". It exists so the user can compare and see what happens when a system has NO controls. It is the "anything goes" version to demonstrate by contrast why the other policies matter.

### Permissions Only (permission_aware)
- **What it does:** Searches for documents and then filters by role permissions.
- **Does filter by permissions.** Documents your role cannot see are blocked.
- **Does not evaluate freshness.** Old documents are not penalized.
- **Does enforce a token budget.** There is a maximum limit of tokens that can enter the context.
- **Why it exists:** Shows the effect of adding only the security layer (RBAC = Role-Based Access Control). It is the middle ground.

### Full Pipeline (full_policy)
- **What it does:** Applies all pipeline stages.
- **Does filter by permissions.** Restricted documents are blocked.
- **Does evaluate freshness.** Newer documents score higher. Documents that have been replaced by a newer version (like a financial model v1 replaced by v2) receive a 50% penalty.
- **Does enforce a token budget.** There is a limit (2048 tokens by default) and if everything does not fit, the least relevant documents are dropped.
- **Why it exists:** This is the "production" policy. It represents how a real system should work in an enterprise.

**What you see in the UI:** In Query mode, there are three policy tabs ("No Filters", "Permissions Only", "Full Pipeline"). Each tab shows a sub-label listing the active pipeline stages (e.g., "Retrieval + RBAC + Freshness + Budget"). The selected policy is applied when you click "Run". In Side-by-side mode this selector does not appear because the system automatically runs all three policies in parallel.

---

## 4. The four modes of the interface

### 4.1 Query mode — "Search with one policy"

**What you see:** A search bar, a role selector, a policy selector (tabs), and when you run a query, a list of documents as cards.

**What it does:**
1. You type a question in natural language (example: "What is Meridian's ARR growth rate?")
2. You choose a role (Analyst, VP, Partner)
3. You choose a policy (No Filters, Permissions Only, Full Pipeline)
4. You click "Run"
5. The system finds the most relevant documents, applies the selected policy, and shows you the results

**What it shows for each document:**
- **doc_id**: Document identifier (e.g., doc_001)
- **Position in ranking**: #1, #2, etc.
- **Content excerpt**: The first ~200 characters, with "Show more / Hide" expand/collapse to the full ~500-char indexer excerpt
- **Relevance bar**: A value from 0 to 1 indicating how relevant the document is to your query. 1.00 = perfectly relevant. A combined score from semantic and lexical (BM25) search.
- **Freshness bar**: A value from 0 to 1 indicating how recent/current the document is relative to the newest document in the corpus. If the policy is No Filters or Permissions Only, it shows "N/A" because those policies do not evaluate freshness.
- **Tags**: Descriptive labels for the document (e.g., "meridian", "public", "financials", "arr")

**Top summary bar:**
- Number of documents included
- Total tokens consumed
- Role used
- Policy applied
- Documents blocked by permissions
- Documents marked as "stale" (obsolete/superseded)
- Export JSON button (downloads the full `/query` response)

**Blocked documents section (collapsible):**
Below the result cards, a "N documents blocked by permissions" section shows one mini-card per blocked document with title, doc_id badge, doc type, and a human-readable reason ("Requires partner role — you are analyst"). Hidden when no documents are blocked.

**Decision Trace panel (collapsible):**
At the bottom of the results there is an expandable panel called "Decision Trace". This is the heart of the system's transparency. It opens with a natural-language summary paragraph translating the counts into prose — e.g., "6 documents were included (675 tokens, 33% of budget). 10 documents were blocked — your role (analyst) cannot access vp- and partner-level materials." Below the summary it shows:

- **Included**: Green chips with the IDs of documents that made it into the final context. Hovering shows the score and token count.
- **Blocked**: Red chips with the IDs of documents blocked by permissions. Shows which role is needed to access them.
- **Stale**: Yellow chips with the IDs of documents that have a newer version. Shows which document superseded them (e.g., "doc_002 -> doc_003").
- **Dropped**: Grey chips with the IDs of documents that passed all filters but did not fit in the token budget.
- **Budget**: A progress bar showing what percentage of the token budget was used. Tooltip explains the metric.
- **Metrics**: Average score, average freshness, and a Time-to-First-Token (TTFT) estimate in milliseconds. Tooltips explain each metric.

**Controls-results coherence (UI-B):**
If you change the role or policy after running a query, the new controls are selected but the results still reflect the previous run. To make this clear, a banner appears above the results ("Controls changed — press Run to refresh these results.") and the old cards fade to 60% opacity. The banner and fade disappear when you press **Run** (or when you set the controls back to match the last render). The example buttons in the "Single" row (`Diligence risks` / `IC recommendation`) and the `Run in Single` buttons from the empty state are **deterministic presets**: they always run with **Full Pipeline** policy and sync the policy tab, so the demo behaves identically regardless of which policy was previously selected.

**Why it is useful to the user:**
- To understand *exactly* which documents entered the context and why.
- To see the impact of changing the policy: switching from "Full Pipeline" to "No Filters" reveals blocked documents appearing and stale documents losing their penalty.
- To verify that the permission system works correctly.

---

### 4.2 Side-by-side mode — "Same query, three policies"

**What you see:** Three columns side by side, one per policy (No Filters, Permissions Only, Full Pipeline).

**What it does:**
1. You type a question and choose a role
2. You click "Run"
3. The system runs the same query three times, once with each policy
4. It shows the results in three columns for comparison

**What it shows in each column:**
- **Color-coded header**: With the policy name and its severity color
- **Stats strip**: A row with 6 quick metrics:
  - `included`: how many documents made it into the final context
  - `tokens`: total tokens used
  - `blocked`: how many documents were blocked by permissions
  - `stale`: how many documents are marked as obsolete
  - `dropped`: how many documents were dropped by budget
  - `ttft`: Time-to-First-Token estimate in milliseconds

- **Document cards**: Compact version of each document with title heading, doc_id badge + type + date metadata, 120-char snippet, mini relevance/freshness bars, compact "Superseded" badge on stale docs
- **"blocked in full" annotation**: In the No Filters column, if a document appears there but would be blocked under the full policy, it gets a red label saying "blocked in full". This visually shows the "leak" that No Filters allows.
- **Decision Trace per column**: Each column has its own trace panel expanded by default, opening with a compact narrative summary.
- **Export JSON button**: In the banner area, downloads the full `/compare` response.

**Pre-built scenarios (post UI-C):**

The three base stories (Permission Wall / Financial model access / Stale Detection) live as **cards in the Query empty state**. Each card has two buttons: `Run in Single` (runs in Query mode with full_policy, **does not** switch mode) and `Open in Compare →` (explicitly jumps to Side-by-side). UI-C eliminated the "silent teleport" from the previous onboarding.

The shortcut row for Compare has **one button**: `Stale detection →` (previously "Partner view"). The query and role (partner, IC + LP update) did not change; the narrative refocuses on the 3 superseded documents (doc_002, doc_007, doc_014) that the full pipeline demotes 0.5x, instead of emphasizing "partner has no blocks". The shortcuts "Analyst wall" and "VP deal view" were removed to avoid duplicating the onboarding cards.

The "Single" row keeps `Diligence risks` (VP) and `IC recommendation` (partner) — distinct queries from the onboarding, with no mode change.

**The three base stories:**

1. **Permission Wall** (analyst, ARR query): No Filters returns 16 docs, RBAC + Full block 10. The most dramatic case of "look what happens without permissions".
2. **Financial model access** (VP, financial model query): VP accesses the models, 4 docs blocked (partner-only), and in Full the model v1 is demoted as stale.
3. **Stale Detection** (partner, IC + LP query): full access (0 blocks across all three policies), but Full pipeline demotes 3 superseded docs (doc_002, doc_007, doc_014) — demonstrates that freshness and permissions are orthogonal.

**Side-by-side also has an empty state (UI-C):** if the user enters Side-by-side without having run anything, they see three preview cards reflecting the same three stories, with summarized quantitative hints. A single click runs `/compare` and the cards disappear to reveal the banner + three columns.

**Why it is useful to the user:**
- It is the most powerful feature for understanding **why policies matter**.
- Seeing three columns side by side makes the difference between "no filters", "with permissions", and "full pipeline" immediately visible.
- The "blocked in full" annotations in the No Filters column are especially useful because they show exactly which documents "would leak" under the full policy.
- Ideal for demos and explaining to non-technical audiences why a context system needs security layers.

---

### 4.3 Metrics mode — "Evaluation dashboard"

**What you see:** A narrative banner at the top, 10 aggregate metric cards, and a table with 12 rows (one per test query).

**What it does:**
1. When you click the "Metrics" tab, the system automatically runs 12 predefined queries through the full pipeline (full_policy).
2. It calculates retrieval quality and security metrics.
3. It shows the results.

**Narrative banner:**
An executive-summary banner renders three sentences: a permission-violations line (celebratory when rate=0), a recall line (100% or fallback), and a budget-utilization tier line.

**The 10 aggregate metrics (top cards):**

| Metric | What it means to the user |
|---|---|
| **Precision@5** | Of the top 5 documents the system returns, what percentage are truly the correct ones. 0.3333 = ~33% accuracy in the top 5. |
| **Recall** | Of all documents that should appear, what percentage actually did. 1.0000 = never lost an expected document. |
| **Permission Violations** | Percentage of queries where a restricted document appeared in the final context. 0.0% = perfect, never had a permission leak. |
| **Avg Context Docs** | Average number of documents included per query. |
| **Avg Total Tokens** | Average tokens consumed per query. |
| **Avg Freshness** | Average freshness score of included documents. |
| **Avg Blocked** | Average number of documents blocked by permissions per query. |
| **Avg Stale** | Average number of documents marked as obsolete per query. |
| **Avg Dropped** | Average number of documents dropped by budget per query. |
| **Avg Budget Util** | Average budget utilization (~71% = roughly two-thirds of the available budget is used). |

Each card includes a one-line micro-explanation hint.

**The per-query table (12 rows):**
Each row is a different test query. Columns:
- **Query**: A query ID pill (q001–q012) plus the query text truncated to 50 characters (full text via tooltip)
- **Role**: The role used for that query
- **P@5**: Precision in the top 5 for that specific query
- **Recall**: Recall for that query
- **Docs**: How many documents were included
- **Tokens**: How many tokens were used
- **Freshness**: Average freshness score
- **Blocked**: How many documents were blocked (highlighted in red if >0)
- **Stale**: How many documents are obsolete (highlighted in yellow if >0)
- **Dropped**: How many documents were dropped by budget
- **Budget**: Budget utilization percentage
- **Violations**: Whether there was any permission leak ("none" = all correct)

**Why it is useful to the user:**
- It is the quantitative proof that the system works. Not a subjective demo — numbers.
- The most important figure for a business user is that **Permission Violations = 0.0%** and **Recall = 1.0000**. That means: "we never leaked a restricted document" and "we never missed a relevant document".
- Precision@5 of 0.3333 may seem low, but context matters: the system returns more documents than strictly "expected" because it includes additional relevant context. This is not necessarily a problem but a consequence of the small corpus where many documents are partially relevant across queries.

**Session Audit (below the benchmark table):**

Below the benchmark table, a Session Audit section shows every query run in Query mode during the current server session. It is fetched from `GET /session-audit` on every Metrics tab switch (not cached).

- **ID numbering:** IDs start at q013 because q001–q012 are reserved for the benchmark queries.
- **Table columns:** Query (full text), Time (relative timestamp, ISO on hover), Role, Policy (human-readable label), Docs, Tokens, Freshness (N/A for policies that skip freshness scoring), Blocked, Stale, Dropped, Budget.
- **Expandable doc chips:** Each row has a toggle to reveal color-coded chips for included (green), blocked (red), stale (yellow), and dropped (gray) document IDs.
- **Precision@5 and Recall are not available** for live queries because there are no predefined `expected_doc_ids` to evaluate against.
- **Copy button:** A hover-reveal copy button on each query cell copies the full query text to the clipboard.
- **Empty state:** If no live queries have been run, the section shows: "Run a query in Query mode and it will appear here as q013."
- **Persistence:** The audit log is in-memory only — no disk persistence. It resets when the server process restarts or redeploys. On shared/public deploys, all visitors see the same log.
- **Scope:** Only `POST /query` calls are logged. Side-by-side (`/compare`) and Metrics (`/evals`) calls do not create audit entries.

---

## 5. How the search actually works

### What kind of search it performs

The search combines **two methods** that are fused together:

1. **Semantic search (FAISS + sentence-transformers):** Converts your question into a numerical vector and finds documents with similar meaning. Good for conceptual questions like "what are the acquisition risks?" because it understands meaning, not just words.

2. **Lexical search (BM25):** Finds exact word matches. Good for specific terms like "MRDN" (Meridian's ticker) or "Section 13D" that semantic search may not capture.

The two rankings are fused using **Reciprocal Rank Fusion (RRF)**, a standard method that combines both rankings into one. The final score ranges from 0 to 1 (normalized).

### What it returns

It does not return an "answer" to your question. It returns a **ranked list of documents** with their excerpts, scores, and metadata. These are the documents an LLM *would use* to answer your question if you were in a RAG (Retrieval-Augmented Generation) system.

### What it searches over

It searches over the **16 documents in the corpus**. These are simulated but realistic documents from an M&A (mergers and acquisitions) deal in fintech. The search runs over the full text of each document, while the UI shows an excerpt of approximately 500 characters.

### Search limitations

1. **It does not search within documents with surgical precision.** It is not a plain-text search like Ctrl+F. If you search for "4.1M deferred revenue adjustment" it will probably find the internal email that mentions it (doc_009), but it returns it as a *complete* document result, not highlighting the exact line where it appears.

2. **The base corpus is small (16 documents).** It can be extended by editing `corpus/documents/`, updating `metadata.json`, and rebuilding the index with `python3 -m src.indexer`; Upload mode allows ingestion testing in environments where it is enabled.

3. **Relevance scores are relative, not absolute.** A score of 0.20 does not mean "not very relevant in general", but "less relevant than the other documents *within this corpus* for this query". In a corpus of 16 documents, even the least relevant can have decent scores.

4. **There is no filtering by exact tag text or document type.** The user cannot filter by "only research notes" or "only documents with tag 'arr'". Everything goes through natural-language search.

5. **There is no pagination.** The system returns the top-K documents (default 8 candidates, then filtered by policy) and there is no way to request "the next 8".

6. **The search has no autocomplete, suggestions, or history.** It is a plain text field.

---

## 6. What information the user sees on each screen and why it is useful

### In Query mode

| Element | What it tells the user |
|---|---|
| Document cards | "These are the documents the system chose to answer your question" |
| Relevance bar | "This document is more/less relevant than the others for your query" |
| Freshness bar | "This document is more/less recent compared to the newest in the corpus" |
| Tags | "What topics this document is about" |
| Summary bar (docs/tokens/blocked/stale) | "Quick summary of what happened with your query" |
| Blocked section | "These documents exist but your role cannot access them — here's why" |
| Decision Trace | "Want to know exactly why the system made each decision? Open this panel" |
| Export JSON | "Download the full response as a JSON file for auditing or sharing" |

### In Side-by-side mode

| Element | What it tells the user |
|---|---|
| Three columns side by side | "This is what the same query looks like with three different protection levels" |
| Stats strip per column | "Quick comparison: how many documents, tokens, blocks in each policy" |
| "blocked in full" label | "This document appears in No Filters but would be blocked under the full policy — careful, this is a leak" |
| Decision Trace per column | "The complete detail of each decision, policy by policy" |
| Export JSON | "Download the full comparison as a JSON file" |

### In Metrics mode

| Element | What it tells the user |
|---|---|
| Narrative banner | "Executive summary: zero violations, perfect recall, budget efficiency tier" |
| Permission Violations = 0% | "The system never leaked a restricted document. Permissions work." |
| Recall = 1.0 | "The system never lost a document it should have included." |
| Precision@5 | "Of the top 5 results, this percentage were the correct ones." |
| Metric card hints | "One-line explanation of what each metric measures" |
| Per-query table | "For each test query, this is how the system behaved." |

---

## 7. Classification: what is for the end user vs. evaluation/demo

### End-user features

1. **Query mode with "Full Pipeline" policy**: The main experience. Search for relevant documents while respecting permissions, freshness, and token budget. The Decision Trace is useful for auditing decisions.

2. **Document cards with excerpts and scores**: Tell the user which documents the system found and with what confidence. Expand/collapse reveals more of the excerpt.

3. **Tags on cards**: Help quickly identify what each document is about.

4. **Role selector**: Useful if a user wants to verify what someone at a different access level would see (e.g., a partner checking what analysts see).

5. **Export JSON**: Download the full response for auditing, sharing, or integration with other tools.

### Policy comparison features

6. **Side-by-side mode**: A comparison tool, not for daily use. Useful for demonstrating and validating that policies work as expected. Ideal for presentations, internal audits, and stakeholder validation.

7. **Pre-built scenarios (Permission Wall, Financial model access, Stale Detection — post UI-C)**: Shortcuts for quick demos. They live as cards in the Query empty state (with two buttons: `Run in Single` and `Open in Compare →`), and as a single shortcut `Stale detection →` in the Compare row. Old names were "Analyst wall", "VP deal view", and "Partner view".

8. **Policy selector in Query mode (No Filters / Permissions Only / Full Pipeline)**: Allows the user to manually switch between policies to see the difference. More an exploration tool than a production feature. Selecting "No Filters" triggers a warning banner.

9. **"blocked in full" labels in the No Filters column of Side-by-side**: A visual aid for understanding the leak.

### Internal metrics/evaluation features

10. **Metrics mode**: A benchmarking tool. Demonstrates with numbers that the pipeline works. Useful for engineers, QA, and technical documentation.

11. **Detailed metrics (budget utilization, TTFT proxy, avg score, avg freshness)**: Internal pipeline data. A business user does not need to know that "budget utilization" is 71% or that the TTFT proxy is 8ms. But an engineer does. Tooltips explain each one.

12. **Precision@5 and Recall**: Standard information retrieval metrics. They have precise technical meaning. A non-technical user probably will not understand them without context.

---

## 8. Screenshot analysis

### Screenshot 1 and 4: Query mode (Analyst + Full Pipeline)

The query "What is Meridian's ARR growth rate and net revenue retention?" executed with Analyst role and Full Pipeline policy.

**What works well:**
- The summary bar clearly shows: 6 docs, 675 tokens, analyst role, Full Pipeline, 10 blocked, 1 stale.
- The 10 blocked make sense: they are the VP/partner documents an analyst cannot see (doc_006 through doc_014 and doc_016, excluding the public news doc_015).
- The 1 stale is doc_002 (the old Q3 2023 research note replaced by doc_003).
- doc_001 (the 10-K with ARR data) appears first with relevance 1.00 and freshness 0.91 — correct, it is the most relevant document.
- doc_003 (the updated research note) appears in the visible context — correct, it is the revised estimates.

**What might confuse:**
- Tags (meridian, public, financials, etc.) are informative but there is no way to click them to filter.

### Screenshot 2: Metrics mode

The 10 metric cards and the 12-query table are visible.

**What works well:**
- Permission Violations at 0.0% is highlighted in green — immediately communicates that permissions are safe.
- The table shows a clear pattern: analyst queries (q001–q003) have 10 blocked, VP queries have 4 blocked, and partner queries have 0 blocked. This is consistent with the role hierarchy.
- All queries have recall 1.00 and violations "none".

**What might confuse:**
- Precision@5 of 0.3333 may seem low and alarm someone who does not understand the context. In a corpus of 16 docs with broad queries, this is expected.
- "Avg Context Docs = 11.8" and "Avg Budget Util = 71%" do not say much to a business user.

### Screenshot 3: Side-by-side mode (Analyst, ARR query)

The three columns No Filters, Permissions Only, Full Pipeline with Decision Traces expanded.

**What works well:**
- The visual difference is striking: No Filters has 0 blocked, Permissions Only has 10 blocked, Full Pipeline has 10 blocked + stale. The value of each layer is immediately visible.
- In the No Filters column, the Decision Trace chips show documents like doc_010, doc_011, and doc_013 included without restriction — these are partner-level documents an analyst should not see.
- The Blocked chips in Permissions Only and Full Pipeline clearly show `vp` and `partner` documents, including the legal memo.
- The Stale chips in Full Pipeline show pairs like "doc_002 -> doc_003", indicating that newer versions replaced the old ones.

**What might confuse:**
- The Budget bar percentages lack context for what is "good". The user does not know if they should aim for 100% or if 63% is fine.
- "avg freshness 0.00" in No Filters and Permissions Only is because those policies do not calculate freshness, but the user might think it is an error. (The label shows "N/A" for those policies.)
- TTFT values: the user has no way to know if 38ms is fast or slow without context.

### Screenshots 5 and 6: Controls bar

The top controls are visible: search bar, role selector, policy selector, and scenario buttons.

**What works well:**
- Controls are clear and compact.
- Scenario buttons have descriptive tooltips explaining what will happen.
- The separation of "SINGLE" vs "COMPARE" labels for scenario buttons is clear.

**What might confuse:**
- The policy selector disappears in Side-by-side mode. If someone notices, the explanation is: "in Side-by-side we run all three policies in parallel, so there is no selector".
- There is no visual indication of which scenario is currently selected after clicking.

---

## 9. Summary: what value the user receives

### If you are a business decision-maker or stakeholder:
- **Side-by-side mode + the three pre-built scenarios** are the most valuable. In seconds you see the difference between "no controls", "with permissions", and "full pipeline".
- **Permission Violations = 0%** in Metrics is the number that matters: the system is safe.
- The "blocked in full" labels in the No Filters column show you exactly what would be leaked.

### If you are an engineer or technical evaluator:
- **Metrics mode** gives you hard numbers: precision, recall, budget utilization.
- **Decision Trace** in any mode shows you each pipeline decision as structured data.
- Scores, freshness, and token counts let you validate that each pipeline stage works correctly.
- **Export JSON** lets you capture any query or comparison response for offline analysis.

### If you are an end user doing searches:
- **Query mode with Full Pipeline** is your mode. Type a question, choose your role, and see the relevant documents the system would give you as context.
- Cards with excerpts, tags, and scores help you quickly evaluate whether the results are useful.
- The Decision Trace gives you full transparency if you need to audit why a certain document was included or excluded.

---

## 10. Current UX limitations and ambiguities

1. **Relevance scores lack a reference point.** A relevance score of 0.54 says nothing without context. The user cannot tell if that is "good" or "bad".

2. **The Decision Trace is powerful but dense.** It has a lot of valuable information, but a non-technical user may feel overwhelmed. The narrative summary at the top helps, but the chip section below can be intimidating.

3. **The corpus is small (16 documents).** This is a demo; the pipeline has no size dependency — the retriever is built on FAISS and BM25 which scale to millions. But the small corpus means scores are relative and precision metrics look lower than they would on a production-sized corpus.

4. **No full-document view.** Cards show a ~200-char excerpt that expands to ~500 chars (the indexer excerpt length), but there is no way to read the entire source document from the UI.

5. **No filtering by tags or document type.** Tags appear on cards as descriptive metadata but are not clickable filters. The user cannot say "show me only research notes".

6. **The interface is in English.** Consistent with the financial content, but could be a barrier for Spanish-speaking audiences. Mention this if asked.

7. **TTFT proxy is an estimate.** The "ttft 38ms" number estimates how long an LLM would take to start generating, not an actual measurement. If asked, be honest: "it is a proxy based on token count; we are not calling a real LLM".

8. **Precision@5 = 0.3333 may seem low.** If asked: "The corpus has 16 documents and many queries are broad, so the 'expected top 5' bar is very high. What matters is Recall = 1.0 — we never lost a doc — and Permission Violations = 0%."

---

## 11. Executive summary

QueryTrace is not an ordinary search engine. It is a **transparency lab** for enterprise AI search systems. Its value lies in making the invisible visible: why an AI system chose certain documents and not others to build the context for a response.

It has three layers of value:

1. **Search layer (Query mode):** Demonstrates that hybrid search (semantic + lexical) works, that permissions are respected, that old documents are penalized, and that there is a controlled token budget.

2. **Comparison layer (Side-by-side mode):** Visually demonstrates what happens when we remove protection layers. It is the project's storytelling tool: "look what happens without permissions, look what happens without freshness, look what happens with everything enabled".

3. **Evaluation layer (Metrics mode):** Demonstrates with numbers that the system is safe (0% violations), exhaustive (100% recall), and efficient (controlled budget).

The project is designed as a demonstration and technical validation tool, not as a final product for end users. Its strength lies in the transparency and rigor of the pipeline. UX improvements should focus on making that transparency more accessible without sacrificing technical depth.

---

*Key files referenced:*
- Frontend: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
- API: `src/main.py` (endpoints `/query`, `/compare`, `/evals`)
- Pipeline: `src/pipeline.py`
- Search: `src/retriever.py` (hybrid FAISS + BM25)
- Stages: `src/stages/permission_filter.py`, `src/stages/freshness_scorer.py`, `src/stages/budget_packer.py`
- Policies: `src/policies.py`
- Models: `src/models.py`
- Evaluator: `src/evaluator.py`
- Corpus: `corpus/metadata.json`, `corpus/roles.json`, `corpus/documents/`
- Test queries: `evals/test_queries.json`
