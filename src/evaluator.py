"""
evaluator.py — Runs the QueryTrace pipeline against test queries and reports
retrieval quality metrics (precision@k, recall) and permission safety metrics.

Evaluates against the final assembled context produced by run_pipeline(), which
is exactly what the HTTP endpoint surfaces to users.  The token budget is owned
by the pipeline's policy preset (PolicyConfig.token_budget); it is not a
per-eval knob.

Usage:
    python3 -m src.evaluator
    python3 -m src.evaluator --workspace saas-internal
    python3 -m src.evaluator --evals corpora/pe-deal/evals.json --k 5 --top-k 8
"""

import argparse
import json
import os
from datetime import date
from functools import partial
from typing import Callable, Optional

from src.workspaces import get_workspace

_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "evals", "results")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_test_queries(path: str) -> list:
    """Load evaluation queries from a JSON file.

    Expects a top-level 'queries' array. Each entry must have:
        id, query, role, expected_doc_ids
    and may optionally have:
        forbidden_doc_ids, notes
    """
    with open(path) as f:
        data = json.load(f)
    if "queries" not in data:
        raise ValueError(f"Expected a top-level 'queries' key in {path}")
    return data["queries"]


def precision_at_k(retrieved_ids: list, expected_ids: list, k: int) -> float:
    """Precision@k: fraction of top-k assembled results that are expected.

    If fewer than k documents were assembled, k is clamped to the actual count
    so short results (due to role filtering or token budget) are not penalized
    for items the system could not have returned.
    """
    effective_k = min(k, len(retrieved_ids))
    if effective_k == 0:
        return 0.0
    top_k = retrieved_ids[:effective_k]
    hits = sum(1 for doc_id in top_k if doc_id in expected_ids)
    return hits / effective_k


def _recall(retrieved_ids: list, expected_ids: list) -> float:
    """Recall: fraction of expected docs found anywhere in the assembled context."""
    if not expected_ids:
        return 1.0  # nothing expected → nothing missed
    hits = sum(1 for doc_id in retrieved_ids if doc_id in expected_ids)
    return hits / len(expected_ids)


def run_evals(
    queries: list,
    k: int = 5,
    top_k: int = 8,
    policy_name: str = "default",
    workspace: Optional[str] = None,
) -> dict:
    """Run all test queries through the pipeline orchestrator and compute metrics.

    Each query is executed via run_pipeline():
        retrieve(query, top_k × 3)  →  permission_filter  →  freshness_scorer
        →  budget_packer  →  trace_builder

    Metrics are extracted from PipelineResult and DecisionTrace, not raw dicts.
    The token budget is set by the pipeline's policy preset (default 2048) and
    is not configurable here.

    Args:
        queries:     List of query dicts from load_test_queries().
        k:           k for precision@k (default 5).
        top_k:       Top-k passed to QueryRequest (pipeline over-retrieves by 3×).
        policy_name: Policy preset to evaluate (default "default" = full_policy).
                     Pass "naive_top_k" to measure the unfiltered baseline.
        workspace:   Workspace slug whose corpus/roles the queries run against
                     (default: the default workspace).

    Returns:
        {
            "per_query": [...],   # one result dict per query (includes trace metrics)
            "aggregate": {...},   # summary metrics across all queries
        }
    """
    # Lazy import to avoid loading models at import time
    from src.retriever import retrieve
    from src.pipeline import run_pipeline
    from src.models import QueryRequest

    ws = get_workspace(workspace)
    roles = ws.roles
    metadata = ws.metadata
    retriever = partial(retrieve, workspace=ws.slug)

    per_query = []

    for q in queries:
        qid = q["id"]
        query_text = q["query"]
        role = q["role"]
        expected_ids = q.get("expected_doc_ids", [])
        forbidden_ids = q.get("forbidden_doc_ids", [])

        try:
            request = QueryRequest(
                query=query_text, role=role, top_k=top_k, policy_name=policy_name,
            )
            result = run_pipeline(request, retriever, roles, metadata)
        except Exception as exc:
            per_query.append({
                "id": qid,
                "query": query_text,
                "role": role,
                "error": str(exc),
            })
            continue

        if result.trace is None:
            per_query.append({
                "id": qid,
                "query": query_text,
                "role": role,
                "error": "pipeline returned PipelineResult with trace=None",
            })
            continue

        # Context items are chunks (Fase 5 Etapa B); expected_doc_ids stay at
        # doc level, so dedupe to unique parent docs in first-seen order
        # before computing P@k / recall — keeps metrics comparable pre/post.
        assembled_ids = list(dict.fromkeys(doc.doc_id for doc in result.context))
        prec = precision_at_k(assembled_ids, expected_ids, k=k)
        rec = _recall(assembled_ids, expected_ids)
        violations = [did for did in assembled_ids if did in forbidden_ids]

        freshness_vals = [doc.freshness_score for doc in result.context]
        avg_fresh = sum(freshness_vals) / len(freshness_vals) if freshness_vals else 0.0

        trace = result.trace
        per_query.append({
            "id": qid,
            "query": query_text,
            "role": role,
            "assembled_ids": assembled_ids,
            "expected_ids": expected_ids,
            "forbidden_ids": forbidden_ids,
            f"precision_at_{k}": round(prec, 4),
            "recall": round(rec, 4),
            "permission_violations": violations,
            "context_docs": len(assembled_ids),
            "total_tokens": result.total_tokens,
            "avg_freshness_score": round(avg_fresh, 8),
            # Trace-level metrics — doc-level counts (chunk entries are
            # deduped to parent docs) so numbers stay comparable pre/post
            # chunking; falls back to raw counts for pre-chunking traces.
            "blocked_count": trace.metrics.blocked_doc_count
            if trace.metrics.blocked_doc_count is not None
            else trace.metrics.blocked_count,
            "stale_count": trace.metrics.stale_doc_count
            if trace.metrics.stale_doc_count is not None
            else trace.metrics.stale_count,
            "dropped_count": trace.metrics.dropped_doc_count
            if trace.metrics.dropped_doc_count is not None
            else trace.metrics.dropped_count,
            "budget_utilization": trace.metrics.budget_utilization,
        })

    valid = [r for r in per_query if "error" not in r]
    n = len(valid)

    prec_key = f"precision_at_{k}"
    aggregate = {
        "queries_run": len(queries),
        "queries_failed": len(queries) - n,
        f"avg_precision_at_{k}": round(sum(r[prec_key] for r in valid) / n, 4) if n else 0.0,
        "avg_recall": round(sum(r["recall"] for r in valid) / n, 4) if n else 0.0,
        "permission_violation_rate": (
            sum(1 for r in valid if r["permission_violations"]) / n if n else 0.0
        ),
        "avg_context_docs": round(sum(r["context_docs"] for r in valid) / n, 2) if n else 0.0,
        "avg_total_tokens": round(sum(r["total_tokens"] for r in valid) / n, 1) if n else 0.0,
        "avg_freshness_score": round(
            sum(r["avg_freshness_score"] for r in valid) / n, 8
        ) if n else 0.0,
        "avg_blocked_count": round(sum(r["blocked_count"] for r in valid) / n, 2) if n else 0.0,
        "avg_stale_count": round(sum(r["stale_count"] for r in valid) / n, 2) if n else 0.0,
        "avg_dropped_count": round(sum(r["dropped_count"] for r in valid) / n, 2) if n else 0.0,
        "avg_budget_utilization": round(
            sum(r["budget_utilization"] for r in valid) / n, 4
        ) if n else 0.0,
    }

    return {"per_query": per_query, "aggregate": aggregate}


# ---------------------------------------------------------------------------
# Ask-mode evals (Fase 4) — opt-in: every query spends model tokens
# ---------------------------------------------------------------------------

def _ask_once(ws, retriever, query: str, role: str, top_k: int, call: Callable) -> dict:
    """One query through pipeline → prompt → model → mechanical citation check.

    Shared by run_ask_evals and run_ask_goldens so both measure exactly the
    /ask code path (full_policy, same prompt builder, same validator).
    """
    from src import ask as ask_mod
    from src.models import QueryRequest
    from src.pipeline import run_pipeline

    request = QueryRequest(query=query, role=role, top_k=top_k, policy_name="full_policy")
    result = run_pipeline(request, retriever, ws.roles, ws.metadata)
    prompt_docs = ask_mod.trim_to_context_cap(result.context)
    system, user = ask_mod.build_prompt(query, prompt_docs)
    reply = call(system, user)
    citations = ask_mod.extract_citations(reply.text, [d.doc_id for d in prompt_docs])
    return {
        "answer": reply.text,
        "model": reply.model,
        "citations": [{"doc_id": c.doc_id, "valid": c.valid} for c in citations],
        "cited_valid_ids": [c.doc_id for c in citations if c.valid],
        "invalid_citations": [c.doc_id for c in citations if not c.valid],
        "context_ids": [d.doc_id for d in result.context],
        "blocked_count": result.trace.metrics.blocked_count if result.trace else 0,
        "input_tokens": reply.input_tokens,
        "output_tokens": reply.output_tokens,
    }


def run_ask_evals(
    queries: list,
    top_k: int = 8,
    workspace: Optional[str] = None,
    call: Optional[Callable] = None,
) -> dict:
    """Run the benchmark through the Ask path and measure citation fidelity.

    Purely mechanical metrics (no LLM judge):
      - citation_validity_rate: valid citations / all citations (target 1.0)
      - groundedness_rate: answers citing ≥1 in-context doc / all answers
      - expected_cited_rate: queries whose expected_doc_ids appear among the
        valid citations (over queries that define expected_doc_ids)

    `call` defaults to the real model client (spends tokens); tests inject a
    fake with the same (system, user) -> ModelReply signature.
    """
    from src import ask as ask_mod
    from src.retriever import retrieve

    if call is None:
        call = ask_mod.call_model

    ws = get_workspace(workspace)
    retriever = partial(retrieve, workspace=ws.slug)

    per_query = []
    for q in queries:
        outcome = _ask_once(ws, retriever, q["query"], q["role"], top_k, call)
        expected = set(q.get("expected_doc_ids", []))
        cited_valid = set(outcome["cited_valid_ids"])
        per_query.append({
            "id": q["id"],
            "role": q["role"],
            "query": q["query"],
            "citations_total": len(outcome["citations"]),
            "citations_valid": len(outcome["cited_valid_ids"]),
            "invalid_citations": outcome["invalid_citations"],
            "grounded": bool(cited_valid),
            "expected_cited": bool(expected & cited_valid) if expected else None,
            "blocked_count": outcome["blocked_count"],
            "input_tokens": outcome["input_tokens"],
            "output_tokens": outcome["output_tokens"],
            "model": outcome["model"],
            "answer_preview": outcome["answer"][:160],
        })

    n = len(per_query)
    total_citations = sum(r["citations_total"] for r in per_query)
    total_valid = sum(r["citations_valid"] for r in per_query)
    with_expected = [r for r in per_query if r["expected_cited"] is not None]
    aggregate = {
        "queries_run": n,
        "citation_validity_rate": (
            round(total_valid / total_citations, 4) if total_citations else None
        ),
        "groundedness_rate": (
            round(sum(1 for r in per_query if r["grounded"]) / n, 4) if n else 0.0
        ),
        "expected_cited_rate": (
            round(sum(1 for r in with_expected if r["expected_cited"]) / len(with_expected), 4)
            if with_expected else None
        ),
        "total_input_tokens": sum(r["input_tokens"] for r in per_query),
        "total_output_tokens": sum(r["output_tokens"] for r in per_query),
        "model": per_query[0]["model"] if per_query else None,
    }
    return {"per_query": per_query, "aggregate": aggregate}


def goldens_path_for(ws) -> str:
    """corpora/<slug>/ask_goldens.json (next to the workspace's evals.json)."""
    return os.path.join(os.path.dirname(ws.evals_path), "ask_goldens.json")


def run_ask_goldens(
    workspace: Optional[str] = None,
    top_k: int = 8,
    call: Optional[Callable] = None,
    write: bool = True,
) -> dict:
    """Fill the workspace's ask_goldens.json snapshots (measured, dated).

    Each golden case runs the SAME question under two roles; the interesting
    artifact is the answer pair diverging because RBAC changed the context.
    Returns the updated goldens dict; with write=True it is persisted back.
    """
    from src import ask as ask_mod
    from src.retriever import retrieve

    if call is None:
        call = ask_mod.call_model

    ws = get_workspace(workspace)
    path = goldens_path_for(ws)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No ask_goldens.json for workspace {ws.slug!r} (expected {path})"
        )
    with open(path) as f:
        goldens = json.load(f)

    retriever = partial(retrieve, workspace=ws.slug)
    entries = []
    for case in goldens["cases"]:
        for role in case["roles"]:
            outcome = _ask_once(ws, retriever, case["query"], role, top_k, call)
            entries.append({
                "case_id": case["id"],
                "role": role,
                "model": outcome["model"],
                "answer": outcome["answer"],
                "citations": outcome["citations"],
                "blocked_count": outcome["blocked_count"],
                "input_tokens": outcome["input_tokens"],
                "output_tokens": outcome["output_tokens"],
            })

    goldens["snapshots"] = {
        "generated_at": date.today().isoformat(),
        "model": entries[0]["model"] if entries else None,
        "entries": entries,
    }
    if write:
        with open(path, "w") as f:
            json.dump(goldens, f, indent=2, ensure_ascii=False)
            f.write("\n")
    return goldens


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_results(results: dict, k: int) -> None:
    prec_key = f"precision_at_{k}"
    print()
    print("=" * 72)
    print("  QueryTrace — Evaluation Results")
    print("=" * 72)

    for r in results["per_query"]:
        if "error" in r:
            print(f"\n[{r['id']}] ERROR: {r['error']}")
            continue

        hit_marks = []
        for doc_id in r["assembled_ids"]:
            if doc_id in r["expected_ids"]:
                hit_marks.append(f"{doc_id}✓")
            elif doc_id in r["forbidden_ids"]:
                hit_marks.append(f"{doc_id}✗")
            else:
                hit_marks.append(doc_id)

        print(f"\n[{r['id']}] ({r['role']}) {r['query'][:65]}")
        print(f"  Assembled : {', '.join(hit_marks) if hit_marks else '(empty)'}")
        print(f"  Expected  : {r['expected_ids']}")
        print(
            f"  P@{k}={r[prec_key]:.2f}  Recall={r['recall']:.2f}"
            f"  Docs={r['context_docs']}  Tokens={r['total_tokens']}"
            f"  Blocked={r['blocked_count']}  Stale={r['stale_count']}"
            f"  Dropped={r['dropped_count']}  BudgetUtil={r['budget_utilization']:.0%}"
        )
        if r["permission_violations"]:
            print(f"  ⚠ PERMISSION VIOLATIONS: {r['permission_violations']}")

    agg = results["aggregate"]
    print()
    print("-" * 72)
    print("  Aggregate Summary")
    print("-" * 72)
    print(f"  Queries run          : {agg['queries_run']}  "
          f"(failed: {agg['queries_failed']})")
    print(f"  Avg Precision@{k}     : {agg[f'avg_precision_at_{k}']:.4f}")
    print(f"  Avg Recall           : {agg['avg_recall']:.4f}")
    print(f"  Permission viol rate : {agg['permission_violation_rate']:.0%}")
    print(f"  Avg context docs     : {agg['avg_context_docs']}")
    print(f"  Avg total tokens     : {agg['avg_total_tokens']}")
    print(f"  Avg freshness score  : {agg['avg_freshness_score']:.2e}")
    print(f"  Avg blocked count    : {agg['avg_blocked_count']}")
    print(f"  Avg stale count      : {agg['avg_stale_count']}")
    print(f"  Avg dropped count    : {agg['avg_dropped_count']}")
    print(f"  Avg budget util      : {agg['avg_budget_utilization']:.0%}")
    print("=" * 72)
    print()


def _print_compare(
    naive: dict, full: dict, k: int, n_queries: int = 12, workspace: str = "",
) -> None:
    """Side-by-side aggregate table: naive_top_k vs full_policy."""
    prec_key = f"avg_precision_at_{k}"
    rows = [
        ("Permission viol rate",
         f"{naive['permission_violation_rate']:.0%}",
         f"{full['permission_violation_rate']:.0%}"),
        ("Avg blocked count", naive["avg_blocked_count"], full["avg_blocked_count"]),
        ("Avg context docs", naive["avg_context_docs"], full["avg_context_docs"]),
        (f"Avg Precision@{k}", f"{naive[prec_key]:.4f}", f"{full[prec_key]:.4f}"),
        ("Avg recall", f"{naive['avg_recall']:.4f}", f"{full['avg_recall']:.4f}"),
        ("Avg total tokens", naive["avg_total_tokens"], full["avg_total_tokens"]),
    ]
    ws_label = f" · workspace {workspace}" if workspace else ""
    print()
    print("=" * 64)
    print(f"  QueryTrace — Policy Comparison ({n_queries}-query benchmark{ws_label})")
    print("=" * 64)
    print(f"  {'Metric':<24} {'naive_top_k':>16} {'full_policy':>16}")
    print("-" * 64)
    for label, naive_val, full_val in rows:
        print(f"  {label:<24} {str(naive_val):>16} {str(full_val):>16}")
    print("=" * 64)
    print()


def _print_ask_results(results: dict) -> None:
    agg = results["aggregate"]
    print()
    print("=" * 72)
    print("  QueryTrace — Ask-mode Evaluation (citation fidelity)")
    print("=" * 72)
    for r in results["per_query"]:
        flag = "✓" if r["grounded"] else "∅"
        exp = (
            "-" if r["expected_cited"] is None
            else ("✓" if r["expected_cited"] else "✗")
        )
        print(f"\n[{r['id']}] ({r['role']}) {r['query'][:60]}")
        print(
            f"  citations={r['citations_valid']}/{r['citations_total']} valid"
            f"  grounded={flag}  expected_cited={exp}"
            f"  tokens={r['input_tokens']}in/{r['output_tokens']}out"
        )
        if r["invalid_citations"]:
            print(f"  ⚠ INVALID CITATIONS: {r['invalid_citations']}")
    print()
    print("-" * 72)
    validity = agg["citation_validity_rate"]
    expected = agg["expected_cited_rate"]
    print(f"  Model                  : {agg['model']}")
    print(f"  Citation validity rate : "
          f"{'n/a (no citations)' if validity is None else f'{validity:.0%}'}")
    print(f"  Groundedness rate      : {agg['groundedness_rate']:.0%}")
    print(f"  Expected-cited rate    : "
          f"{'n/a' if expected is None else f'{expected:.0%}'}")
    print(f"  Tokens                 : {agg['total_input_tokens']} in / "
          f"{agg['total_output_tokens']} out")
    print("=" * 72)
    print()


def _print_goldens(goldens: dict) -> None:
    print()
    print("=" * 72)
    print("  QueryTrace — Ask goldens (same question, different role)")
    print("=" * 72)
    entries = goldens["snapshots"]["entries"]
    for case in goldens["cases"]:
        print(f"\n◆ [{case['id']}] {case['query']}")
        for e in [x for x in entries if x["case_id"] == case["id"]]:
            cited = ", ".join(
                c["doc_id"] + ("" if c["valid"] else "⚠") for c in e["citations"]
            ) or "(none)"
            preview = e["answer"][:140].replace("\n", " ")
            print(f"  [{e['role']:8s}] cites: {cited} · blocked_docs={e['blocked_count']}")
            print(f"             {preview}…")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run QueryTrace evals")
    parser.add_argument("--workspace", default=None,
                        help="Workspace slug to evaluate (default: the default workspace)")
    parser.add_argument("--evals", default=None,
                        help="Path to an evals JSON file "
                             "(default: the workspace's evals.json)")
    parser.add_argument("--k", type=int, default=5,
                        help="k for precision@k (default 5)")
    parser.add_argument("--top-k", type=int, default=8,
                        help="Retrieval candidates passed to QueryRequest (default 8); "
                             "pipeline internally over-retrieves by 3×")
    parser.add_argument("--compare", action="store_true",
                        help="Run naive_top_k and full_policy side by side and "
                             "print a comparison table")
    parser.add_argument("--ask", action="store_true",
                        help="Run the benchmark through the Ask path and measure "
                             "citation validity (requires ANTHROPIC_API_KEY; "
                             "spends tokens — cents with the default Haiku model)")
    parser.add_argument("--ask-goldens", action="store_true",
                        help="Regenerate the workspace's ask_goldens.json snapshots "
                             "(requires ANTHROPIC_API_KEY; spends tokens)")
    args = parser.parse_args()

    ws = get_workspace(args.workspace)

    if args.ask or args.ask_goldens:
        from src.ask import ask_enabled

        if not ask_enabled():
            parser.error(
                "--ask/--ask-goldens call the live model and need "
                "ANTHROPIC_API_KEY in the environment (never committed anywhere). "
                "A full run costs cents with the default Haiku model."
            )

    if args.ask_goldens:
        print(f"[{ws.slug}] Regenerating ask goldens (live model calls)...")
        goldens = run_ask_goldens(workspace=ws.slug, top_k=args.top_k)
        _print_goldens(goldens)
        print(f"Snapshots written to {goldens_path_for(ws)}")
        return

    evals_path = args.evals if args.evals is not None else ws.evals_path
    queries = load_test_queries(evals_path)
    print(f"[{ws.slug}] Loaded {len(queries)} queries from {evals_path}")
    print("Running pipeline (this may take a moment for model loading)...")

    if args.ask:
        results = run_ask_evals(queries, top_k=args.top_k, workspace=ws.slug)
        _print_ask_results(results)
        os.makedirs(_RESULTS_DIR, exist_ok=True)
        snapshot_path = os.path.join(
            _RESULTS_DIR, f"ask-{date.today().isoformat()}-{ws.slug}.json"
        )
        with open(snapshot_path, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Snapshot written to {snapshot_path}")
        return

    if args.compare:
        naive = run_evals(queries, k=args.k, top_k=args.top_k,
                          policy_name="naive_top_k", workspace=ws.slug)
        full = run_evals(queries, k=args.k, top_k=args.top_k,
                         policy_name="full_policy", workspace=ws.slug)
        _print_compare(naive["aggregate"], full["aggregate"], k=args.k,
                       n_queries=len(queries), workspace=ws.slug)
        # Smoke assertion for CI: the full pipeline must be violation-free.
        assert full["aggregate"]["permission_violation_rate"] == 0.0, (
            "full_policy produced permission violations"
        )
        return

    results = run_evals(
        queries,
        k=args.k,
        top_k=args.top_k,
        workspace=ws.slug,
    )
    _print_results(results, k=args.k)


if __name__ == "__main__":
    main()
