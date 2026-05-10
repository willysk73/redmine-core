"""Entry point: `redmine` subcommands.

Exit codes:
    0  success
    1  generic failure (e.g., detect: no id found)
    2  bad argv
   11  authentication failure (per spec §12)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, detect as detect_mod, frontmatter as fm_mod, paths as paths_mod, render
from .client import APIError, AuthError, Client
from .config import Config, ConfigError, load as load_config


EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_ARGV = 2
EXIT_AUTH = 11


def _emit(msg: str, *, err: bool = False) -> None:
    stream = sys.stderr if err else sys.stdout
    stream.write(msg)
    if not msg.endswith("\n"):
        stream.write("\n")
    stream.flush()


def _client(args: argparse.Namespace) -> Client:
    cfg = load_config(getattr(args, "config", None))
    return Client(cfg)


def _resolve_assignee(args: argparse.Namespace, cfg: Config | None = None) -> str:
    """Translate --filter into Redmine's assigned_to_id parameter."""
    flt = (getattr(args, "filter", None) or "open").lower()
    if flt == "all":
        return ""  # not used
    return "me"


# --- subcommands -----------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    client = _client(args)
    flt = (args.filter or "open").lower()

    kwargs: dict = {"limit": args.limit}
    if flt == "open":
        kwargs["assigned_to"] = "me"
        kwargs["status"] = "open"
    elif flt == "mine":
        kwargs["assigned_to"] = "me"
        kwargs["status"] = "*"  # all statuses
    elif flt == "all":
        kwargs["status"] = "*"
    else:
        _emit(f"unknown filter: {flt}", err=True)
        return EXIT_ARGV

    if args.project:
        kwargs["project_id"] = args.project

    issues = client.list_issues(**kwargs)
    out = [render.normalize_list_item(i) for i in issues]
    if args.json:
        _emit(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for it in out:
            line = f"#{it['id']:<6} {it['tracker']:<8} {it['status']:<10} {it['progress']:>3}%  {it['subject']}"
            _emit(line)
    return EXIT_OK


def cmd_fetch(args: argparse.Namespace) -> int:
    client = _client(args)
    issue = client.get_issue(args.id, includes=["journals", "attachments", "relations"])
    if args.format == "display":
        _emit(render.issue_display(issue))
    elif args.format == "json":
        _emit(json.dumps(issue, ensure_ascii=False, indent=2))
    elif args.format == "task":
        _emit(render.issue_task(issue))
    else:
        _emit(f"unknown format: {args.format}", err=True)
        return EXIT_ARGV
    return EXIT_OK


# --- M2 helpers ------------------------------------------------------

def _resolve_status_id(client: Client, value: str) -> int:
    """Accepts numeric id or status name; returns numeric id or raises."""
    if value.isdigit():
        return int(value)
    statuses = client.list_statuses()
    for s in statuses:
        if s.get("name", "").lower() == value.lower():
            return int(s["id"])
    raise APIError(f"unknown status name: {value!r}. Available: " +
                   ", ".join(repr(s.get("name")) for s in statuses))


def _resolve_user_id(client: Client, project: str | int | None, value: str) -> int | None:
    """Accepts numeric id or user name (display name). '' / 'none' → None (unassign)."""
    v = value.strip()
    if v == "" or v.lower() in ("none", "null", "unassign", "-"):
        return None
    if v.isdigit():
        return int(v)
    if project is None:
        raise APIError("--project required when --user is a name (cannot search globally)")
    members = client.list_project_memberships(project)
    for m in members:
        if (m.get("name") or "").lower() == v.lower():
            return int(m["id"])
    raise APIError(f"no project member matches {value!r}. Members: " +
                   ", ".join(repr(m.get("name")) for m in members))


# --- M2 subcommands --------------------------------------------------

def cmd_meta(args: argparse.Namespace) -> int:
    client = _client(args)
    if args.kind == "statuses":
        if args.issue:
            issue = client.get_issue(args.issue, includes=["allowed_statuses"])
            allowed = issue.get("allowed_statuses") or []
            if not allowed:
                # Some workflows return empty; fall back to global list.
                allowed = client.list_statuses()
            data = [{"id": s.get("id"), "name": s.get("name"), "is_closed": s.get("is_closed", False)}
                    for s in allowed]
        else:
            data = [{"id": s.get("id"), "name": s.get("name"), "is_closed": s.get("is_closed", False)}
                    for s in client.list_statuses()]
    elif args.kind == "members":
        if not args.project:
            _emit("meta members requires --project", err=True)
            return EXIT_ARGV
        data = client.list_project_memberships(args.project)
    else:
        _emit(f"unknown meta kind: {args.kind}", err=True)
        return EXIT_ARGV

    _emit(json.dumps(data, ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_update(args: argparse.Namespace) -> int:
    client = _client(args)
    fields: dict = {}
    if args.status is not None:
        fields["status_id"] = _resolve_status_id(client, args.status)
    if args.progress is not None:
        if not 0 <= args.progress <= 100:
            _emit("--progress must be 0..100", err=True)
            return EXIT_ARGV
        fields["done_ratio"] = args.progress
    if args.subject is not None:
        fields["subject"] = args.subject
    if args.description is not None:
        fields["description"] = args.description
    if args.notes is not None:
        fields["notes"] = args.notes

    if not fields:
        _emit("nothing to update — pass at least one of --status/--progress/--subject/--description/--notes", err=True)
        return EXIT_ARGV

    client.update_issue(args.id, fields=fields)
    _emit(json.dumps({"id": args.id, "updated": list(fields.keys())}, ensure_ascii=False))
    return EXIT_OK


def cmd_assign(args: argparse.Namespace) -> int:
    client = _client(args)
    issue = client.get_issue(args.id)
    project = (issue.get("project") or {}).get("id")
    user_id = _resolve_user_id(client, project, args.user)
    fields = {"assigned_to_id": user_id if user_id is not None else ""}
    client.update_issue(args.id, fields=fields)
    _emit(json.dumps({"id": args.id, "assigned_to_id": user_id}, ensure_ascii=False))
    return EXIT_OK


def _resolve_activity_id(client: Client, value: str | None) -> int | None:
    """Pick a TimeEntryActivity. Numeric → id, name → match, None → default."""
    activities = client.list_time_entry_activities()
    if not activities:
        return None
    if value is not None:
        v = value.strip()
        if v.isdigit():
            return int(v)
        for a in activities:
            if (a.get("name") or "").lower() == v.lower():
                return int(a["id"])
        raise APIError(f"unknown activity: {value!r}. Available: " +
                       ", ".join(repr(a.get("name")) for a in activities))
    for a in activities:
        if a.get("is_default"):
            return int(a["id"])
    return int(activities[0]["id"])


def cmd_log(args: argparse.Namespace) -> int:
    client = _client(args)
    if args.hours <= 0:
        _emit("--hours must be > 0", err=True)
        return EXIT_ARGV
    activity_id = _resolve_activity_id(client, args.activity)
    entry = client.add_time_entry(args.id, hours=args.hours, activity_id=activity_id,
                                  comments=args.comment)
    _emit(json.dumps({"id": args.id, "time_entry_id": entry.get("id"), "hours": args.hours,
                      "activity_id": activity_id}, ensure_ascii=False))
    return EXIT_OK


def cmd_path(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd) if args.cwd else None
    try:
        out = paths_mod.resolve(args.kind, issue_id=args.id, cwd=cwd,
                                config_file=getattr(args, "config", None))
    except ValueError as e:
        _emit(str(e), err=True)
        return EXIT_ARGV
    _emit(str(out))
    return EXIT_OK


def cmd_suggest(args: argparse.Namespace) -> int:
    """Suggest a default value for a frontmatter field.

    `assignee`: last commenter (last journal with non-empty notes), else the
    issue author. Emits a single line (the user's display name) on stdout, or
    exits 1 with empty stdout if nothing can be suggested.
    """
    client = _client(args)
    if args.kind == "assignee":
        issue = client.get_issue(args.id, includes=["journals"])
        for j in reversed(issue.get("journals") or []):
            if (j.get("notes") or "").strip():
                user = j.get("user") or {}
                name = user.get("name")
                if name:
                    _emit(name)
                    return EXIT_OK
        author = issue.get("author") or {}
        name = author.get("name")
        if name:
            _emit(name)
            return EXIT_OK
        return EXIT_GENERIC
    _emit(f"unknown suggest kind: {args.kind}", err=True)
    return EXIT_ARGV


def cmd_post(args: argparse.Namespace) -> int:
    file_path = Path(args.file)
    if not file_path.is_file():
        _emit(f"file not found: {file_path}", err=True)
        return EXIT_GENERIC
    text = file_path.read_text(encoding="utf-8")
    composed = fm_mod.split(text)
    fm = composed.fm

    issue_id = fm_mod.parse_int(fm.get("id"))
    if issue_id is None:
        _emit("frontmatter must contain `id: <issue id>`", err=True)
        return EXIT_GENERIC

    body = composed.body
    client = _client(args)

    fields: dict = {}
    actions: list[str] = []

    if body:
        fields["notes"] = body
        actions.append("comment")

    status_val = fm.get("status")
    if status_val:
        fields["status_id"] = _resolve_status_id(client, status_val)
        actions.append(f"status={status_val}")

    progress = fm_mod.parse_int(fm.get("progress"))
    if progress is not None:
        if not 0 <= progress <= 100:
            _emit("frontmatter progress must be 0..100", err=True)
            return EXIT_ARGV
        fields["done_ratio"] = progress
        actions.append(f"progress={progress}")

    assignee_val = fm.get("assignee") or fm.get("assigned_to")
    if assignee_val:
        issue = client.get_issue(issue_id)
        project = (issue.get("project") or {}).get("id")
        user_id = _resolve_user_id(client, project, assignee_val)
        fields["assigned_to_id"] = user_id if user_id is not None else ""
        actions.append(f"assignee={assignee_val}")

    hours = fm_mod.parse_float(fm.get("time"))
    has_time = hours is not None and hours > 0

    if not fields and not has_time:
        _emit("nothing to post (empty body and no frontmatter changes)", err=True)
        return EXIT_GENERIC

    if fields:
        client.update_issue(issue_id, fields=fields)

    time_entry_id = None
    if has_time:
        activity_id = _resolve_activity_id(client, fm.get("activity"))
        entry = client.add_time_entry(issue_id, hours=hours, activity_id=activity_id)
        time_entry_id = entry.get("id")
        actions.append(f"time={hours}h")

    result = {
        "id": issue_id,
        "actions": actions,
        "time_entry_id": time_entry_id,
    }
    _emit(json.dumps(result, ensure_ascii=False))
    return EXIT_OK


def cmd_detect(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd) if args.cwd else None
    issue_id = detect_mod.detect(cwd)
    if issue_id is None:
        return EXIT_GENERIC
    _emit(str(issue_id))
    return EXIT_OK


def cmd_whoami(args: argparse.Namespace) -> int:
    client = _client(args)
    user = client.current_user()
    if args.json:
        _emit(json.dumps(user, ensure_ascii=False, indent=2))
    else:
        _emit(f"{user.get('login', '?')} ({user.get('firstname', '')} {user.get('lastname', '')})".strip())
    return EXIT_OK


# --- arg parsing -----------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="redmine", description="Thin Redmine CLI for redmine.nvim")
    p.add_argument("--version", action="version", version=f"redmine-core {__version__}")
    p.add_argument("--config", help="Path to config TOML (default: $XDG_CONFIG_HOME/redmine-core/config.toml)")

    sub = p.add_subparsers(dest="cmd", required=True)

    sp_list = sub.add_parser("list", help="List issues")
    sp_list.add_argument("--filter", default="open", help="open|mine|all (default: open)")
    sp_list.add_argument("--project", help="Project id or identifier")
    sp_list.add_argument("--limit", type=int, default=50)
    sp_list.add_argument("--json", action="store_true")
    sp_list.set_defaults(func=cmd_list)

    sp_fetch = sub.add_parser("fetch", help="Fetch a single issue")
    sp_fetch.add_argument("id", type=int)
    sp_fetch.add_argument("--format", default="display", choices=["display", "json", "task"])
    sp_fetch.set_defaults(func=cmd_fetch)

    sp_detect = sub.add_parser("detect", help="Detect issue id from cwd; exit 1 if none")
    sp_detect.add_argument("--cwd", help="Directory to inspect (default: $PWD)")
    sp_detect.set_defaults(func=cmd_detect)

    sp_whoami = sub.add_parser("whoami", help="Show authenticated user (also a connectivity check)")
    sp_whoami.add_argument("--json", action="store_true")
    sp_whoami.set_defaults(func=cmd_whoami)

    # --- M2 ---
    sp_meta = sub.add_parser("meta", help="Fetch metadata (statuses, members)")
    sp_meta.add_argument("kind", choices=["statuses", "members"])
    sp_meta.add_argument("--issue", type=int, help="When kind=statuses, only allowed transitions for this issue")
    sp_meta.add_argument("--project", help="When kind=members, project id or identifier")
    sp_meta.add_argument("--json", action="store_true", help="(noop; meta output is always JSON)")
    sp_meta.set_defaults(func=cmd_meta)

    sp_update = sub.add_parser("update", help="Update issue fields")
    sp_update.add_argument("id", type=int)
    sp_update.add_argument("--status", help="Status id or name")
    sp_update.add_argument("--progress", type=int, help="Done ratio 0-100")
    sp_update.add_argument("--subject", help="New subject (rename)")
    sp_update.add_argument("--description", help="Replace description")
    sp_update.add_argument("--notes", help="Add a comment as part of the update")
    sp_update.set_defaults(func=cmd_update)

    sp_assign = sub.add_parser("assign", help="Change assignee (empty/none → unassign)")
    sp_assign.add_argument("id", type=int)
    sp_assign.add_argument("--user", required=True, help="User id, name, or one of: '', none, unassign")
    sp_assign.set_defaults(func=cmd_assign)

    sp_log = sub.add_parser("log", help="Log time on an issue")
    sp_log.add_argument("id", type=int)
    sp_log.add_argument("--hours", type=float, required=True)
    sp_log.add_argument("--activity", help="TimeEntryActivity id or name (default: server default)")
    sp_log.add_argument("--comment", help="Optional comment for the time entry")
    sp_log.set_defaults(func=cmd_log)

    sp_path = sub.add_parser("path", help="Print resolved path for draft/task/archive")
    sp_path.add_argument("kind", choices=["draft", "task", "archive"])
    sp_path.add_argument("--id", type=int, help="Issue id (required for templates that include {id})")
    sp_path.add_argument("--cwd", help="Override cwd for {worktree} resolution")
    sp_path.set_defaults(func=cmd_path)

    sp_post = sub.add_parser("post", help="Read draft file and apply frontmatter actions")
    sp_post.add_argument("--file", required=True, help="Path to compose draft (.md with frontmatter)")
    sp_post.set_defaults(func=cmd_post)

    sp_suggest = sub.add_parser("suggest", help="Suggest a default value (assignee)")
    sp_suggest.add_argument("kind", choices=["assignee"])
    sp_suggest.add_argument("--id", type=int, required=True)
    sp_suggest.set_defaults(func=cmd_suggest)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as e:
        _emit(str(e), err=True)
        return EXIT_GENERIC
    except AuthError as e:
        _emit(f"authentication failed: {e}\nrun `redmine whoami` to verify your token.", err=True)
        return EXIT_AUTH
    except APIError as e:
        _emit(f"API error: {e}", err=True)
        return EXIT_GENERIC
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
