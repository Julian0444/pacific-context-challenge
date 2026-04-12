"""
evaluator.py — Runs the QueryTrace pipeline against test queries and reports
retrieval quality metrics (precision@k, recall) and permission safety metrics.

Evaluates against the final assembled context produced by run_pipeline(), which
is exactly what the HTTP endpoint surfaces to users.  The token budget is owned
by the pipeline's policy preset (PolicyConfig.token_budget); it is not a
per-eval knob.

Usage:
    python3 -m src.evaluator
    python3 -m src.evaluator --evals evals/test_queries.json --k 5 --top-k 8
"""

import argparse
import json
import os

_DIR = os.path.dirname(__file__)
_CORPUS_ROOT = os.path.join(_DIR, "..")
_ROLES_PATH = os.path.join(_CORPUS_ROOT, "corpus", "roles.json")
_METADATA_PATH = os.path.join(_CORPUS_ROOT, "corpus", "metadata.json")
_DEFAULT_EVALS = os.path.join(_CORPUS_ROOT, "evals", "test_queries.json")


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
) -> dict:
    """Run all test queries through the pipeline orchestrator and compute metrics.

    Each query is executed via run_pipeline():
        retrieve(query, top_k × 3)  →  permission_filter  →  freshness_scorer
        →  budget_packer  →  trace_builder

    Metrics are extracted from PipelineResult and DecisionTrace, not raw dicts.
    The token budget is set by the pipeline's policy preset (default 2048) and
    is not configurable here.

    Args:
        queries: List of query dicts from load_test_queries().
        k:       k for precision@k (default 5).
        top_k:   Top-k passed to QueryRequest (pipeline over-retrieves by 3×).

    Returns:
        {
            "per_query": [...],   # one result dict per query (includes trace metrics)
            "aggregate": {...},   # summary metrics across all queries
        }
    """
    # Lazy import to avoid loading models at import time
    from src.retriever import retrieve
    from src.policies import load_roles
    from src.pipeline import run_pipeline
    from src.models import QueryRequest

    roles = load_roles(_ROLES_PATH)
    with open(_METADATA_PATH) as f:
        metadata = json.load(f)

    per_query = []

    for q in queries:
        qid = q["id"]
        query_text = q["query"]
        role = q["role"]
        expected_ids = q.get("expected_doc_ids", [])
        forbidden_ids = q.get("forbidden_doc_ids", [])

        try:
            request = QueryRequest(query=query_text, role=role, top_k=top_k)
            result = run_pipeline(request, retrieve, roles, metadata)
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

        assembled_ids = [doc.doc_id for doc in result.context]
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
            "context_docs": len(result.context),
            "total_tokens": result.total_tokens,
            "avg_freshness_score": round(avg_fresh, 8),
            # Trace-level metrics
            "blocked_count": trace.metrics.blocked_count,
            "stale_count": trace.metrics.stale_count,
            "dropped_count": trace.metrics.dropped_count,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run QueryTrace evals")
    parser.add_argument("--evals", default=_DEFAULT_EVALS,
                        help="Path to test_queries.json")
    parser.add_argument("--k", type=int, default=5,
                        help="k for precision@k (default 5)")
    parser.add_argument("--top-k", type=int, default=8,
                        help="Retrieval candidates passed to QueryRequest (default 8); "
                             "pipeline internally over-retrieves by 3×")
    args = parser.parse_args()

    queries = load_test_queries(args.evals)
    print(f"Loaded {len(queries)} queries from {args.evals}")
    print("Running pipeline (this may take a moment for model loading)...")

    results = run_evals(
        queries,
        k=args.k,
        top_k=args.top_k,
    )
    _print_results(results, k=args.k)


if __name__ == "__main__":
    main()
