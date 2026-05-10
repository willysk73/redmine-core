"""Tiny YAML-like frontmatter parser for compose drafts.

Supports only the keys the spec defines (id, status, progress, time, assignee).
Empty / missing values are returned as None. No nested structures.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# The cutoff marker is shared with the plugin (lua/redmine/config.lua).
# Anything from the first matching line onward is treated as context, not body.
CUTOFF_RE = re.compile(r"^<!--.*━━━.*-->\s*$")


@dataclass
class Composed:
    raw: str
    fm: dict          # frontmatter values, lower-cased keys, str|None
    body: str         # text between frontmatter and cutoff (stripped)


def split(text: str) -> Composed:
    lines = text.splitlines()
    fm: dict[str, str | None] = {}
    body_start = 0

    if lines and lines[0].strip() == "---":
        # Find closing fence.
        for i, ln in enumerate(lines[1:], start=1):
            if ln.strip() == "---":
                # Parse frontmatter lines.
                for raw in lines[1:i]:
                    if ":" not in raw:
                        continue
                    key, _, value = raw.partition(":")
                    k = key.strip().lower()
                    v = value.strip()
                    fm[k] = v if v else None
                body_start = i + 1
                break

    # Find cutoff in body region.
    body_end = len(lines)
    for i in range(body_start, len(lines)):
        if CUTOFF_RE.match(lines[i]):
            body_end = i
            break

    body = "\n".join(lines[body_start:body_end]).strip()
    return Composed(raw=text, fm=fm, body=body)


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
