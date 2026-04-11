"""
policies.py — Role-based access control and policy presets for the pipeline.

Policy presets:
  naive_top_k       — raw retrieval, no filtering, no freshness
  permission_aware  — retrieval + role-based access control, no freshness
  full_policy       — full pipeline: retrieval + RBAC + freshness + budget packing
  default           — alias for full_policy
"""

import json

from src.models import PolicyConfig


# ---------------------------------------------------------------------------
# Policy presets
# ---------------------------------------------------------------------------

POLICY_PRESETS = {
    "naive_top_k": PolicyConfig(
        name="naive_top_k",
        skip_permission_filter=True,
        skip_freshness=True,
        skip_budget=True,
    ),
    "permission_aware": PolicyConfig(
        name="permission_aware",
        skip_freshness=True,
    ),
    "full_policy": PolicyConfig(name="full_policy"),
    "default": PolicyConfig(name="default"),
}


def resolve_policy(name: str, top_k: int) -> PolicyConfig:
    """Look up a named policy preset and apply the request's top_k override.

    Raises ValueError if the name is not a known preset.
    """
    base = POLICY_PRESETS.get(name)
    if base is None:
        raise ValueError(
            f"Unknown policy: {name!r}. Valid policies: {list(POLICY_PRESETS.keys())}"
        )
    if top_k != base.top_k:
        return base.model_copy(update={"top_k": top_k})
    return base


# ---------------------------------------------------------------------------
# Role loading and filtering (unchanged from original)
# ---------------------------------------------------------------------------

def load_roles(roles_path: str) -> dict:
    """Load role definitions from a roles JSON file.

    Returns the 'roles' dict mapping role name → {name, description, access_rank}.
    """
    with open(roles_path, "r") as f:
        data = json.load(f)
    return data["roles"]


def filter_by_role(chunks: list, role: str, roles: dict) -> list:
    """Remove chunks that the given role is not permitted to access.

    Access rule: role's access_rank >= document's min_role access_rank.
    Raises ValueError if the role is not defined.
    """
    if role not in roles:
        raise ValueError(f"Unknown role: {role!r}. Valid roles: {list(roles.keys())}")

    user_rank = roles[role]["access_rank"]

    return [
        chunk for chunk in chunks
        if roles.get(chunk["min_role"], {}).get("access_rank", float("inf")) <= user_rank
    ]
