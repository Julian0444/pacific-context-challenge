"""
workspace.py — bring-your-own-corpus CLI (Fase 3 Etapa D).

Create a full QueryTrace workspace from a directory of documents:

  python -m src.workspace create my-company \\
      --from-dir ~/docs-to-index \\
      --roles roles.json \\          # optional; default: viewer(1) < editor(2) < admin(3)
      --name "My Company KB"
  python -m src.workspace list

The CLI is a thin loop over the existing ingest/indexer code: every file goes
through the same prepare_ingest() (magic bytes, extraction, dedup) and
finalize_ingest() (persist + incremental index) as an HTTP upload. Defaults
per document: min_role = the lowest-rank role, date = file mtime,
doc_type = "document", title = humanized filename.

The created workspace has no demo personas (users.json is empty) — explore it
through the Lab (guest mode) with the default roles, or add users by hand.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from typing import Optional

from src import workspaces
from src.ingest import (
    SUPPORTED_EXTENSIONS,
    IngestError,
    finalize_ingest,
    prepare_ingest,
)
from src.workspaces import (
    InvalidWorkspaceSlug,
    get_workspace,
    invalidate_workspace_cache,
    list_workspaces,
    validate_slug,
)

DEFAULT_ROLES = {
    "viewer": {
        "name": "viewer",
        "description": "Base access — sees documents marked viewer-level.",
        "access_rank": 1,
    },
    "editor": {
        "name": "editor",
        "description": "Elevated access — sees viewer- and editor-level documents.",
        "access_rank": 2,
    },
    "admin": {
        "name": "admin",
        "description": "Full access to every document in the workspace.",
        "access_rank": 3,
    },
}


def humanize_title(filename: str) -> str:
    """'q1_2024-board_notes.md' → 'Q1 2024 Board Notes'."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    words = re.sub(r"[_\-]+", " ", stem).strip()
    return words.title() or "Document"


def _load_roles(roles_path: Optional[str]) -> dict:
    if roles_path is None:
        return DEFAULT_ROLES
    with open(roles_path, "r") as f:
        data = json.load(f)
    roles = data.get("roles", data)  # accept {"roles": {...}} or a bare dict
    if not isinstance(roles, dict) or not roles:
        raise SystemExit(f"--roles file {roles_path!r} has no roles.")
    for role_name, role in roles.items():
        if not isinstance(role, dict) or not isinstance(role.get("access_rank"), int):
            raise SystemExit(
                f"Role {role_name!r} needs an integer 'access_rank' "
                f"(got: {role!r})."
            )
        role.setdefault("name", role_name)
        role.setdefault("description", "")
    return roles


def _scan_documents(from_dir: str) -> list:
    """Supported files under from_dir (recursive), sorted for stable ids."""
    found = []
    for dirpath, _dirnames, filenames in os.walk(from_dir):
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in SUPPORTED_EXTENSIONS:
                found.append(os.path.join(dirpath, fn))
    return sorted(found)


def create_workspace(
    slug: str,
    from_dir: str,
    roles_path: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """Create corpora/<slug>/ from a directory of documents. Returns a summary.

    Raises SystemExit with a human message on unusable input (bad slug,
    duplicate workspace, empty directory, nothing ingestable).
    """
    try:
        validate_slug(slug)
    except InvalidWorkspaceSlug as e:
        raise SystemExit(str(e))

    root = os.path.join(workspaces.CORPORA_DIR, slug)
    if os.path.exists(root):
        raise SystemExit(
            f"Workspace {slug!r} already exists at {root} — pick another slug."
        )
    if not os.path.isdir(from_dir):
        raise SystemExit(f"--from-dir {from_dir!r} is not a directory.")

    files = _scan_documents(from_dir)
    if not files:
        raise SystemExit(
            f"No supported documents ({', '.join(SUPPORTED_EXTENSIONS)}) "
            f"found under {from_dir!r}."
        )

    roles = _load_roles(roles_path)
    min_role = min(roles.values(), key=lambda r: r["access_rank"])["name"]
    display_name = name or humanize_title(slug)

    # Workspace skeleton — everything the resolver requires.
    os.makedirs(os.path.join(root, "documents"))
    with open(os.path.join(root, "metadata.json"), "w") as f:
        json.dump({"documents": []}, f, indent=2)
    with open(os.path.join(root, "roles.json"), "w") as f:
        json.dump({"roles": roles}, f, indent=2)
    with open(os.path.join(root, "users.json"), "w") as f:
        json.dump({"users": []}, f, indent=2)
    manifest = {
        "slug": slug,
        "name": display_name,
        "description": description
        or f"Workspace created from {os.path.basename(os.path.abspath(from_dir))!r} via the CLI.",
        "doc_types": ["document"],
        "blocked_disclosure": "count",
        "role_hints": {},
        "search_placeholder": f"Ask about the {display_name} documents…",
        "empty_state_description": f"Search across the {display_name} corpus.",
        "scenarios": [],
        "example_queries": [],
    }
    with open(os.path.join(root, workspaces.MANIFEST_FILE), "w") as f:
        json.dump(manifest, f, indent=2)

    invalidate_workspace_cache(slug)
    ws = get_workspace(slug)

    ingested, skipped = [], []
    for path in files:
        rel = os.path.relpath(path, from_dir)
        with open(path, "rb") as f:
            file_bytes = f.read()
        date = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d")
        try:
            prepared = prepare_ingest(
                file_bytes=file_bytes,
                title=humanize_title(path),
                date=date,
                min_role=min_role,
                doc_type="document",
                sensitivity="low",
                tags=[],
                workspace=ws,
                filename=os.path.basename(path),
            )
            entry = finalize_ingest(prepared)
        except IngestError as e:
            reason = "duplicate" if e.status_code == 409 else str(e)
            skipped.append({"file": rel, "reason": reason})
            print(f"  ! skipped {rel}: {reason}", file=sys.stderr)
            continue
        ingested.append({"file": rel, "doc_id": entry["id"], "title": entry["title"]})
        print(f"  + {entry['id']}  {rel}")

    if not ingested:
        # Nothing landed — remove the skeleton instead of leaving a corpse.
        import shutil

        shutil.rmtree(root, ignore_errors=True)
        invalidate_workspace_cache(slug)
        raise SystemExit(
            f"No document under {from_dir!r} could be ingested "
            f"({len(skipped)} skipped) — workspace not created."
        )

    invalidate_workspace_cache(slug)
    summary = {
        "slug": slug,
        "name": display_name,
        "root": root,
        "ingested": ingested,
        "skipped": skipped,
        "roles": sorted(roles, key=lambda r: roles[r]["access_rank"]),
        "min_role": min_role,
    }
    return summary


def _cmd_create(args) -> None:
    summary = create_workspace(
        args.slug,
        from_dir=args.from_dir,
        roles_path=args.roles,
        name=args.name,
        description=args.description,
    )
    roles_line = " < ".join(summary["roles"])
    print(
        f"\nCreated workspace {summary['slug']!r} ({summary['name']}) at {summary['root']}\n"
        f"  documents: {len(summary['ingested'])} ingested, {len(summary['skipped'])} skipped\n"
        f"  roles: {roles_line} (documents default to {summary['min_role']!r})\n"
        f"\nTry it:\n"
        f"  python -m uvicorn src.main:app --reload\n"
        f"  open http://localhost:8000/app/ and pick {summary['name']!r} in the workspace switcher\n"
        f"  (no demo personas — use the Lab / guest mode, or add users to users.json)"
    )


def _cmd_list(_args) -> None:
    summaries = list_workspaces()
    if not summaries:
        print("No workspaces under corpora/.")
        return
    for s in summaries:
        print(f"  {s['slug']:<20} {s['doc_count']:>3} docs  {s['name']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m src.workspace",
        description="Create and list QueryTrace workspaces.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create a workspace from a directory")
    p_create.add_argument("slug", help="Workspace slug (lowercase, digits, dashes)")
    p_create.add_argument("--from-dir", required=True, help="Directory with .pdf/.txt/.md/.docx files")
    p_create.add_argument("--roles", default=None, help="Optional roles.json (default: viewer/editor/admin)")
    p_create.add_argument("--name", default=None, help="Display name for the workspace")
    p_create.add_argument("--description", default=None, help="Manifest description")
    p_create.set_defaults(func=_cmd_create)

    p_list = sub.add_parser("list", help="List workspaces")
    p_list.set_defaults(func=_cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
