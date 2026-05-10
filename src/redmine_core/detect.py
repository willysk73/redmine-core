"""Issue ID detection from cwd. Strategies, in order:
1. .redmine file in cwd or any ancestor (just contains the integer ID).
2. Git branch name with a leading or `XX/` prefixed integer ID.
   matches: `1234-foo`, `feat/1234-foo`, `1234`, `bugfix/1234`.
3. None.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


_BRANCH_PATTERNS = [
    re.compile(r"^(?P<id>\d+)(?:[-_/].*)?$"),
    re.compile(r"^[^/]+/(?P<id>\d+)(?:[-_].*)?$"),
]


def _walk_up(start: Path) -> list[Path]:
    out = [start]
    cur = start
    while cur.parent != cur:
        cur = cur.parent
        out.append(cur)
    return out


def _from_marker(cwd: Path) -> int | None:
    for d in _walk_up(cwd):
        marker = d / ".redmine"
        if marker.is_file():
            try:
                txt = marker.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if txt.isdigit():
                return int(txt)
    return None


def _git_branch(cwd: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    branch = proc.stdout.strip()
    return branch or None


def _from_git(cwd: Path) -> int | None:
    branch = _git_branch(cwd)
    if not branch:
        return None
    for pat in _BRANCH_PATTERNS:
        m = pat.match(branch)
        if m:
            return int(m.group("id"))
    return None


def detect(cwd: Path | None = None) -> int | None:
    cwd = (cwd or Path.cwd()).resolve()
    return _from_marker(cwd) or _from_git(cwd)
