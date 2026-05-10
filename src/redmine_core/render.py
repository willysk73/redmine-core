"""Human-readable rendering (`--format=display`)."""
from __future__ import annotations

from typing import Any


def _g(d: dict | None, key: str, default: str = "") -> str:
    if not isinstance(d, dict):
        return default
    v = d.get(key)
    return str(v) if v is not None else default


def _named(d: dict, key: str) -> str:
    return _g(d.get(key) or {}, "name", "-")


def issue_display(issue: dict) -> str:
    iid = issue.get("id")
    subject = issue.get("subject", "")
    status = _named(issue, "status")
    progress = issue.get("done_ratio", 0)
    assigned = _named(issue, "assigned_to")
    due = issue.get("due_date") or "-"
    author = _named(issue, "author")
    tracker = _named(issue, "tracker")
    priority = _named(issue, "priority")
    description = (issue.get("description") or "").rstrip()

    lines: list[str] = []
    lines.append(f"#{iid} — {subject}")
    lines.append("")
    lines.append(f"상태   : {status:<14} 진척 : {progress}%")
    lines.append(f"담당   : {assigned:<14} 마감 : {due}")
    lines.append(f"트래커 : {tracker:<14} 우선 : {priority}")
    lines.append(f"작성   : {author}")
    lines.append("")
    lines.append("▾ 본문")
    if description:
        for ln in description.splitlines():
            lines.append(f"  {ln}")
    else:
        lines.append("  (본문 없음)")

    journals = issue.get("journals") or []
    comments = [j for j in journals if (j.get("notes") or "").strip()]
    lines.append("")
    lines.append(f"▾ 코멘트 ({len(comments)})")
    if not comments:
        lines.append("  (코멘트 없음)")
    for j in comments:
        user = _named(j, "user")
        when = (j.get("created_on") or "").replace("T", " ").rstrip("Z")
        lines.append(f"  ─── {user}  {when} ───")
        notes = (j.get("notes") or "").rstrip()
        for ln in notes.splitlines():
            lines.append(f"    {ln}")

    attachments = issue.get("attachments") or []
    lines.append("")
    lines.append(f"▸ 첨부 ({len(attachments)})")
    for a in attachments:
        fn = a.get("filename", "?")
        aid = a.get("id", "?")
        size = a.get("filesize")
        size_str = f" ({size}B)" if size else ""
        lines.append(f"  - [#{aid}] {fn}{size_str}")

    relations = issue.get("relations") or []
    lines.append(f"▸ 관련 ({len(relations)})")
    for r in relations:
        kind = r.get("relation_type", "?")
        lines.append(f"  - {kind}: #{r.get('issue_id')} ↔ #{r.get('issue_to_id')}")

    return "\n".join(lines) + "\n"


def issue_task(issue: dict) -> str:
    """task.md flavor — markdown summary used as compose-buffer context.

    Includes: header, key fields table, body, recent comments. Suitable for
    embedding under the cutoff marker in a compose draft.
    """
    iid = issue.get("id")
    subject = issue.get("subject", "")
    status = _named(issue, "status")
    progress = issue.get("done_ratio", 0)
    assigned = _named(issue, "assigned_to")
    due = issue.get("due_date") or "-"
    description = (issue.get("description") or "").rstrip()

    lines: list[str] = []
    lines.append(f"# #{iid} — {subject}")
    lines.append("")
    lines.append(f"**Status**: {status}  **Progress**: {progress}%  **Assignee**: {assigned}  **Due**: {due}")
    lines.append("")
    lines.append("## 본문")
    lines.append(description if description else "(본문 없음)")

    journals = issue.get("journals") or []
    comments = [j for j in journals if (j.get("notes") or "").strip()]
    if comments:
        lines.append("")
        lines.append(f"## 이전 코멘트 ({len(comments)})")
        for j in comments[-5:]:
            user = _named(j, "user")
            when = (j.get("created_on") or "").split("T", 1)[0]
            lines.append(f"**{user}** — {when}")
            for ln in (j.get("notes") or "").rstrip().splitlines():
                lines.append(f"> {ln}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def normalize_list_item(issue: dict) -> dict:
    """Trim REST response to fields the plugin renders. Keeps spec contract stable."""
    return {
        "id": issue.get("id"),
        "subject": issue.get("subject", ""),
        "tracker": _named(issue, "tracker"),
        "status": _named(issue, "status"),
        "progress": issue.get("done_ratio", 0),
        "priority": _named(issue, "priority"),
        "due_date": issue.get("due_date"),
        "assigned_to": _named(issue, "assigned_to") or None,
        "project": {
            "id": (issue.get("project") or {}).get("id"),
            "name": _named(issue, "project"),
        },
    }
