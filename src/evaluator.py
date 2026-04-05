"""
evaluator.py — Runs the retrieval pipeline against a set of test queries and
reports precision@k and other eval metrics.
"""


def load_test_queries(path: str) -> list:
    """Load evaluation queries from evals/test_queries.json."""
    # TODO: implement
    raise NotImplementedError


def precision_at_k(retrieved_ids: list, expected_ids: list, k: int) -> float:
    """Compute Precision@k for a single query."""
    # TODO: implement
    raise NotImplementedError


def run_evals(queries: list, retrieval_fn) -> dict:
    """
    Run all test queries through the retrieval pipeline and aggregate metrics.
    Returns a dict with mean Precision@k and per-query results.
    """
    # TODO: implement
    raise NotImplementedError
