# QueryTrace — Evaluation

Every number the project claims comes from a reproducible harness, not from a one-off run.
Each workspace ships a 12-query benchmark that exercises the production pipeline end to end:

```bash
python -m src.evaluator                              # pe-deal, full_policy
python -m src.evaluator --workspace saas-internal
python -m src.evaluator --compare                    # naive_top_k vs full_policy
python -m src.evaluator --ask                        # Ask-mode citation fidelity (needs ANTHROPIC_API_KEY)
```

## Baseline metrics (`pe-deal`, full_policy, post-chunking)

| Metric | Value | What it means |
|---|---|---|
| Avg Precision@5 | 0.30 | Fraction of the top-5 unique documents that were expected (expected sets have 1–3 docs, so the achievable average tops out well below 1.0)¹ |
| Avg Recall | 1.00 | Every expected document is retrieved somewhere in the assembled context |
| Permission violations | 0% | No role ever sees a document above its clearance |
| Avg budget utilization | 98% | The 2048-token budget is packed with real chunk content, not teasers |
| Avg blocked | 4.17 | Average docs filtered by RBAC per query |
| Avg stale demoted | 2.08 | Average superseded docs penalized per query |

¹ `precision_at_k` clamps k to the number of assembled documents, so short results (role
filtering, token budget) are not penalized for items the system could not have returned.
Context items are chunks; metrics dedupe them to unique parent documents, keeping numbers
comparable across the chunking migration.

## Naive vs full pipeline (`--compare`)

**`pe-deal`** (Atlas Capital, 16 docs · 28 chunks):

| Metric | `naive_top_k` | `full_policy` |
|---|---|---|
| **Permission violation rate** | **50%** | **0%** |
| Avg blocked count | 0.0 | 4.17 |
| Avg context docs | 16.0 | 6.67 |
| Avg Precision@5 | 0.2667 | 0.3000 |
| Avg total tokens | 7151 | 2017 |

**`saas-internal`** (Nimbus Analytics, 14 docs · 28 chunks):

| Metric | `naive_top_k` | `full_policy` |
|---|---|---|
| **Permission violation rate** | **58%** | **0%** |
| Avg blocked count | 0.0 | 4.67 |
| Avg context docs | 14.0 | 5.83 |
| Avg Precision@5 | 0.2667 | 0.2500 |
| Avg total tokens | 6592 | 2022 |

Without the permission filter, half the PE queries — and 7 of 12 SaaS queries — leak documents
the requesting role is not cleared to see (salary bands to employees, board decks to managers).
The full pipeline eliminates every violation on both corpora while holding recall at 100% and
cutting the packed context by ~70%: the naive baseline stuffs every retrieved chunk into the
prompt (~7,000 tokens) with no budget and no document cap.

Benchmark coverage: revenue growth, stale document handling, permission walls, customer
concentration, model revisions, board access, integration risks, compensation data, incident
postmortems, compliance audits, governance changes, and roadmap drift.

## Chunking — before vs after (full_policy)

Documents are indexed as ~350-token paragraph-aware chunks with ~15% overlap (`src/chunker.py`)
instead of one embedding per document. Two problems this fixed: the embedder read only the start
of each document (the rest was semantically invisible), and the packed "context" was a fixed
500-char teaser rather than real content. The same 12-query benchmarks, before and after:

| Metric (pe-deal / saas-internal) | Pre-chunking | Post-chunking |
|---|---|---|
| Permission violation rate | 0% / 0% | 0% / 0% |
| Avg Recall | 1.00 / 1.00 | 1.00 / 1.00 |
| Avg Precision@5 | 0.3333 / 0.2500 | 0.3000 / 0.2500 |
| Avg context docs | 11.83 / 9.33 | 6.67 / 5.83 |
| Avg total tokens | 1448 / 1262 | 2017 / 2022 |
| Budget utilization | ~71% / ~62% | ~98% / ~98% |
| Packed content per doc | 500-char teaser | full ~350-token chunks |

The trade-off, stated plainly: the context now holds **fewer documents with far more substance
each** — the budget is spent on real chunk text, and `top_k` is redefined as a cap on *unique
documents* (the token budget is the second limit). pe-deal P@5 dips 0.033 because contexts hold
fewer documents overall, while recall and safety hold at 100%/0%.

Deep-content probes confirm the point of the change: queries targeting text at the *end* of long
documents (a revenue-concentration covenant, a media-contact line) now rank the right document in
the top 3 via a late chunk — that text was beyond the embedder's window before. One probe keeps
the story straight: a query for doc_010's closing recommendation still loses to its near-duplicate
draft memo. Chunking doesn't fix near-duplicate confusion; the stale-pair demotion does.

The ONNX migration (torch/sentence-transformers → fastembed) used this same harness as its
acceptance gate: retrieval metrics held within ±0.02 across the swap.

## Ask mode — citation fidelity

`python -m src.evaluator --ask` runs the 12-query benchmark through the Ask path and measures:

- **Citation validity rate** — valid citations / all citations (target 100%)
- **Groundedness rate** — answers citing ≥1 in-context document
- **Expected-cited rate** — whether each query's expected documents appear among the citations

Measured 2026-07-06 with `claude-haiku-4-5` over the pe-deal benchmark: **citation validity 100%,
groundedness 100%, expected-cited 100%** (26,612 tokens in / 2,909 out ≈ USD 0.04 — dated snapshot
in [`evals/results/`](../evals/results/)). The eval is opt-in because it spends tokens; CI never
needs a key — the entire Ask surface is tested against a mocked client, including the security
test that blocked documents can never reach the prompt.

Three role-pair goldens (same question, different clearance, different answer) live in
[`corpora/pe-deal/ask_goldens.json`](../corpora/pe-deal/ask_goldens.json) with measured snapshots;
regenerate with `python -m src.evaluator --ask-goldens`.
