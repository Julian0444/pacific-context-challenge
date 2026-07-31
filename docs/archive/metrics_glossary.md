# QueryTrace — Metrics & Variables Glossary

This glossary covers every metric, label, and concept visible in the QueryTrace interface. All of these metrics evaluate **how context is assembled before it reaches the LLM** — they do not evaluate whether the LLM's final answer "sounds good."

---

## Quick read

- **Recall** = we did not miss the expected important documents.
- **Permission Violations** = restricted documents did not leak into context.
- **Budget / Freshness / Blocked** explain *why* the final context was assembled that way.

---

## Current UI label inventory

Source: `frontend/app.js`, `frontend/index.html` — discovered from `POLICY_META`, `buildTracePanelHTML()`, `renderSingleResult()`, `renderCompare()`, `renderEvals()`, `renderSessionAudit()`, metric card array, and summary bar template.

### Policies

| UI label | Backend key | Description |
|----------|-------------|-------------|
| No Filters | `naive_top_k` | Raw retrieval — no permissions, no freshness, no budget. Exists as a dangerous baseline for comparison. |
| Permissions Only | `permission_aware` | Role-based access control (RBAC) + token budget. No freshness scoring. |
| Full Pipeline | `full_policy` | Permissions + freshness + token budget. Production mode. |

### Roles

| UI label | Rank | Access |
|----------|------|--------|
| Analyst | 1 | 6 of 16 docs — public filings, research notes, press release, sector overview, public news. |
| VP | 2 | 12 of 16 docs — adds deal memos, financial models, diligence analyses, internal memos. |
| Partner | 3 | 16 of 16 docs — full corpus including IC memo, LP update, and legal diligence. |

### Modes

| UI label | Internal key | Function |
|----------|-------------|----------|
| Query | `single` | Query with one policy. Detailed result with cards, blocked section, and Decision Trace. |
| Side-by-side | `compare` | Same query, three policies in parallel. Three comparative columns. |
| Metrics | `evals` | Benchmark (q001–q012) + Session Audit (q013+). |
| Upload | `admin` | PDF ingestion. May be disabled on public deploys. |

---

## Detailed metrics

### Precision@5 / P@5

| | |
|---|---|
| **UI label** | `Precision@5` (Metrics cards), `P@5` (benchmark table column) |
| **Where it appears** | Metrics tab — aggregate cards and per-query table |
| **What it measures** | Of the top 5 documents returned by the pipeline, how many were in the predefined "expected" set for that test query? |
| **High value** | More of the expected documents appear in the top 5 positions. |
| **Low value** | The system included additional relevant documents beyond the strict "expected" list. In a 16-document corpus with broad queries, this is expected. |
| **Caveat** | **Does not mean the answer is "33% correct."** It measures whether predefined expected documents fell within the top 5 context slots. A value of 0.33 with Recall=1.0 means all expected docs appeared, just not always in the top 5. Not shown in Session Audit — live queries have no `expected_doc_ids`. |

---

### Recall

| | |
|---|---|
| **UI label** | `Recall` (Metrics card and benchmark table column) |
| **Where it appears** | Metrics tab — aggregate cards and per-query table |
| **What it measures** | Of all documents that *should* have appeared in context (per the test definition), how many actually did? |
| **High value (1.0)** | No expected document was missed. The system found everything it should have. |
| **Low value** | Some expected document did not make it to the final context — it may have been filtered by permissions, dropped by budget, or not retrieved. |
| **Caveat** | Measures coverage of the assembled context, not quality of a text answer. Not shown in Session Audit — live queries have no `expected_doc_ids`. |

---

### Permission Violations / Violations

| | |
|---|---|
| **UI label** | `Permission Violations` (Metrics card), `Violations` (benchmark table column) |
| **Where it appears** | Metrics tab — aggregate cards and per-query table. The narrative banner also mentions it. |
| **What it measures** | Percentage of queries where a restricted document appeared in the final context when it should not have. |
| **Value 0.0% / "none"** | The system never let a restricted document through. This is correct. |
| **Value > 0%** | A restricted document leaked into context — security failure. |
| **Caveat** | Only computed against the 12 benchmark queries that have defined `forbidden_doc_ids`. Live queries in Session Audit do not measure violations because they have no forbidden document lists. |

---

### Relevance / score / avg score

| | |
|---|---|
| **UI label** | `Relevance` (bar on Query mode cards), `score` (tooltip on Decision Trace included chips), `avg score` (trace metrics strip) |
| **Where it appears** | Query mode — result bars. Side-by-side — mini bars. Decision Trace — included chip tooltips and metrics strip. |
| **What it measures** | How relevant a document is to your query. Value from 0 to 1. Combines semantic search (FAISS) and lexical search (BM25) fused via Reciprocal Rank Fusion (RRF), then normalized. |
| **High value (→ 1.0)** | The document is highly relevant to the query. |
| **Low value** | Less relevant *compared to the other documents in the corpus for this query*. Does not mean irrelevant in absolute terms. |
| **Caveat** | Scores are relative to the corpus and query. A score of 0.20 doesn't mean "bad" — it means "less relevant than the other documents *in this corpus* for this query." In a 16-document corpus, even the least relevant can have reasonable scores. |

---

### Freshness / Avg Freshness / N/A — skipped by policy

| | |
|---|---|
| **UI label** | `Freshness` (bar on cards, column in benchmark and Session Audit tables), `Avg Freshness` (Metrics card), `avg freshness` (trace metrics strip), `N/A — skipped by policy` (on cards when the policy does not score freshness) |
| **Where it appears** | Query mode — bar on result cards. Side-by-side — mini bar. Metrics — aggregate card and tables. Decision Trace — metrics strip. |
| **What it measures** | How recent a document is relative to the newest document in the corpus. Value from 0 to 1 (1.0 = the newest document). Superseded documents receive an additional 0.5× penalty. |
| **High value (→ 1.0)** | The document is recent compared to the corpus. |
| **Low value** | The document is old or has been superseded. |
| **N/A** | Shown when the policy is **No Filters** or **Permissions Only**, because those policies do not run freshness scoring. Only **Full Pipeline** computes freshness. |
| **Caveat** | Relative to the corpus, not to the calendar. A score of 0.91 does not mean "91% fresh" — it means "very close to the date of the newest document in the corpus." |

---

### Tokens / Avg Total Tokens

| | |
|---|---|
| **UI label** | `tokens` (summary bar in Query mode, stats strip in Side-by-side, column in tables), `Avg Total Tokens` (Metrics card) |
| **Where it appears** | Query mode — summary bar. Side-by-side — stats strip per column. Metrics — aggregate card and tables. Session Audit — column. |
| **What it measures** | Total tokens consumed by the documents included in the assembled context. |
| **High value** | More content in the context. May approach the budget limit (2048 tokens by default). |
| **Low value** | Less content made it to context — either few relevant documents or permission blocks. |
| **Caveat** | Not a real LLM token count — it is the pipeline's estimate based on text tokenization. |

---

### Docs / Avg Context Docs / Included

| | |
|---|---|
| **UI label** | `docs` (summary bar in Query mode), `included` (stats strip in Side-by-side), `Docs` (column in tables), `Avg Context Docs` (Metrics card), `✓ Included` (section in Decision Trace), `Included` (chips in Session Audit detail) |
| **Where it appears** | All views. |
| **What it measures** | How many documents passed all pipeline stages and were packed into the final context. |
| **High value** | More documents in the context — more information sources for the LLM. |
| **Low value** | Few documents survived the filters — may be due to permission blocks, budget constraints, or low relevance. |

---

### Blocked / Avg Blocked / 🔒 Blocked

| | |
|---|---|
| **UI label** | `blocked` (summary bar and stats strip), `Blocked` (column in tables), `Avg Blocked` (Metrics card), `🔒 Blocked` (section in Decision Trace), `🔒 N documents blocked by permissions` (expandable section in Query mode), `Blocked` (chips in Session Audit detail) |
| **Where it appears** | All views except with the No Filters policy (which does not filter permissions). |
| **What it measures** | Documents that the retriever found as relevant but that were excluded from context because the user's role does not have access. |
| **High value** | The user has a low role (e.g., analyst) and there are many higher-access documents. This is expected. |
| **Value 0** | The user has full access (partner) or the policy is No Filters. |
| **Caveat** | A blocked document is a correct security decision, not an error. In the expandable section in Query mode, each block includes the reason: "Requires VP role — you are analyst." |

---

### Stale / Avg Stale / ⏱ Stale / ⚠ Superseded

| | |
|---|---|
| **UI label** | `stale` (summary bar and stats strip), `Stale` (column in tables), `Avg Stale` (Metrics card), `⏱ Stale` (section in Decision Trace), `⚠ Superseded by doc_XXX — freshness penalized 0.5×` (badge on Query cards), `⚠ Superseded` (compact badge in Side-by-side), `Stale` (chips in Session Audit detail) |
| **Where it appears** | Query mode — badges on cards and chips in trace. Side-by-side — compact badges. Metrics — card and tables. Session Audit — column and detail chips. |
| **What it measures** | Documents that have been replaced by a newer version (superseded). In the current corpus there are three pairs: doc_002→doc_003 (research note), doc_007→doc_008 (financial model), doc_014→doc_010 (IC draft → final). |
| **Value > 0** | The pipeline detected outdated documents and demoted them with a 0.5× freshness penalty. Stale documents are **not removed** — they remain in context but with lower weight. |
| **Value 0** | No superseded documents in the results, or the policy does not run freshness scoring (No Filters, Permissions Only). |
| **Caveat** | **Stale does not mean removed.** The superseded document stays in context but with a 0.5× penalty on its freshness score, so the LLM weighs it less. Only Full Pipeline detects stale documents. |

---

### Dropped / Avg Dropped / ✂ Dropped

| | |
|---|---|
| **UI label** | `dropped` (stats strip in Side-by-side), `Dropped` (column in tables), `Avg Dropped` (Metrics card), `✂ Dropped` (section in Decision Trace), `Dropped` (chips in Session Audit detail) |
| **Where it appears** | Side-by-side — stats strip. Metrics — card and tables. Decision Trace — section with gray chips. Session Audit — column and detail chips. |
| **What it measures** | Documents that passed permission and freshness filters but did not fit in the token budget (2048 by default). |
| **Value > 0** | The budget filled up before all eligible documents could be packed. The lowest-scoring documents are the ones dropped. |
| **Value 0** | All eligible documents fit in the budget. |
| **Caveat** | A "dropped" document is not irrelevant or blocked — it passed all previous filters but doesn't fit in the context. This is a prioritization decision, not a security one. Only applies with policies that enforce a budget (Permissions Only, Full Pipeline). |

---

### Budget / Avg Budget Util / Budget utilization

| | |
|---|---|
| **UI label** | `Budget` (bar in Decision Trace, column in tables), `Avg Budget Util` (Metrics card) |
| **Where it appears** | Decision Trace — progress bar with tooltip "Percentage of the 2048-token budget used by assembled context." Metrics — aggregate card. Benchmark and Session Audit tables — column. |
| **What it measures** | Percentage of the token budget (2048 by default) used by documents packed into the final context. |
| **High value (>80%)** | Heavy context — nearly all the budget is in use. |
| **Medium value (60–80%)** | Moderate use. |
| **Low value (<60%)** | Efficient use — unused budget headroom. |
| **Caveat** | The Metrics narrative banner classifies utilization into three tiers: efficient (<60%), moderate (60–80%), heavy (>80%). These are descriptive, not prescriptive — there is no "correct" value. |

---

### TTFT / ttft / TTFT proxy

| | |
|---|---|
| **UI label** | `ttft` (stats strip in Side-by-side), `ttft Xms` (metrics strip in Decision Trace) |
| **Where it appears** | Side-by-side — stats strip per column. Decision Trace — metrics strip (tooltip: "Time-to-First-Token proxy — estimated latency before an LLM starts generating"). |
| **What it measures** | Estimated time an LLM would take to start generating a response with this context. Calculated from context size and pipeline timings. |
| **Low value** | Less estimated latency before the LLM starts responding. |
| **High value** | More estimated latency — larger context or slower pipeline. |
| **Caveat** | **This is a proxy, not a real measurement.** The project does not call a real LLM. The value is an estimate based on token count and pipeline timings. Do not use it as a performance benchmark. |

---

### blocked in full

| | |
|---|---|
| **UI label** | `blocked in full` (red label on Side-by-side cards, No Filters column) |
| **Where it appears** | Side-by-side — No Filters column only. |
| **What it measures** | This document appears unfiltered in the No Filters column, but *would be* blocked under Full Pipeline for this role. It is a contrast annotation, not a pipeline state. |
| **Caveat** | Only appears in the No Filters column as a visual aid. Shows the "leak" that would occur without access controls. |

---

### Decision Trace

| | |
|---|---|
| **UI label** | `Decision Trace` (expandable panel at the bottom of each result) |
| **Where it appears** | Query mode — collapsible panel. Side-by-side — open by default in each column. |
| **What it contains** | Natural-language narrative summary + four chip sections (✓ Included, 🔒 Blocked, ⏱ Stale, ✂ Dropped) + Budget bar + metrics strip (avg score, avg freshness, ttft). |
| **Purpose** | Full audit of each pipeline decision. Each chip has a tooltip with detail (score, tokens, required role, superseding doc). |

---

## Benchmark vs Session Audit

### Benchmark (q001–q012)

| | |
|---|---|
| **What they are** | 12 predefined test queries from `evals/test_queries.json`. |
| **How they run** | Automatically on first Metrics tab visit. Cached after that. |
| **Policy** | Always `full_policy`. |
| **Metrics available** | P@5, Recall, Violations, Docs, Tokens, Freshness, Blocked, Stale, Dropped, Budget. |
| **IDs** | q001 through q012. |

### Session Audit (q013+)

| | |
|---|---|
| **What they are** | Live queries run in Query mode during the current server session. |
| **How they run** | The user runs them manually. They are logged automatically. |
| **Policy** | Whichever the user selected (No Filters, Permissions Only, or Full Pipeline). |
| **Metrics available** | Docs, Tokens, Freshness, Blocked, Stale, Dropped, Budget. **No** P@5, Recall, or Violations (no `expected_doc_ids` or `forbidden_doc_ids`). |
| **IDs** | q013 onward (auto-incrementing). |

---

## Session Audit persistence

- The Session Audit log lives **in server memory** — no disk persistence.
- It is **shared** across all visitors to the same server instance.
- **Do not enter sensitive or personal information** — queries are visible to anyone who opens the Metrics tab.
- The log **resets** when the server process restarts or redeploys. On Render or other ephemeral hosting, each deploy clears the log.
- Benchmark queries (q001–q012) are unaffected by the reset because they are recomputed from the static test file.
- Only `POST /query` calls are logged. Side-by-side (`/compare`) and Metrics (`/evals`) do **not** create audit entries.
