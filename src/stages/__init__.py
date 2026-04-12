"""
stages/ — Typed, pure compute stages for the QueryTrace pipeline.

Each stage is a standalone function with no I/O and no side effects.
The trace_builder is a reducer that aggregates outputs from all stages.
"""

from src.stages.permission_filter import filter_permissions, PermissionResult
from src.stages.freshness_scorer import score_freshness, FreshnessResult
from src.stages.budget_packer import pack_budget, BudgetResult
from src.stages.trace_builder import build_trace

__all__ = [
    "filter_permissions", "PermissionResult",
    "score_freshness", "FreshnessResult",
    "pack_budget", "BudgetResult",
    "build_trace",
]
