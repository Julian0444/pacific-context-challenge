"""
policies.py — Enforces role-based access control on retrieved document chunks.

A document is accessible if the requesting role's access_rank >= the document's
min_role access_rank.
"""

import json


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
