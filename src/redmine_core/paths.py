"""Path resolution for compose drafts, task files, and archives.

Templates may reference {worktree} (git toplevel; falls back to cwd) and {id}.
Configurable via [paths] section in config.toml.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import DEFAULT_CONFIG_FILE, _read_toml


_DEFAULTS = {
    "draft_file":  "{worktree}/.redmine/drafts/comment-draft-{id}.md",
    "task_file":   "{worktree}/.redmine/task.md",
    "archive_dir": "{worktree}/.redmine/posted",
}


def _git_toplevel(cwd: Path) -> Path | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    return Path(out) if out else None


def _worktree(cwd: Path) -> Path:
    return _git_toplevel(cwd) or cwd


def _load_paths(config_file: Path | None = None) -> dict[str, str]:
    file_path = Path(config_file) if config_file else Path(os.environ.get("REDMINE_CONFIG", DEFAULT_CONFIG_FILE))
    cfg = _read_toml(file_path)
    user_paths = cfg.get("paths", {})
    return {**_DEFAULTS, **{k: str(v) for k, v in user_paths.items()}}


KIND_TO_KEY = {
    "draft":   "draft_file",
    "task":    "task_file",
    "archive": "archive_dir",
}


def resolve(kind: str, *, issue_id: int | None = None, cwd: Path | None = None,
            config_file: Path | None = None) -> Path:
    if kind not in KIND_TO_KEY:
        raise ValueError(f"unknown path kind: {kind} (expected: {', '.join(KIND_TO_KEY)})")
    paths = _load_paths(config_file)
    template = paths[KIND_TO_KEY[kind]]
    cwd = (cwd or Path.cwd()).resolve()
    worktree = _worktree(cwd)
    needs_id = "{id}" in template
    if needs_id and issue_id is None:
        raise ValueError(f"{kind} path template requires --id (template: {template})")
    sub = {"worktree": str(worktree), "id": str(issue_id) if issue_id is not None else ""}
    return Path(template.format(**sub))
