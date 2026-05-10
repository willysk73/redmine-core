# redmine-core

Thin Python CLI for Redmine. Originally built as the backend for
[`redmine.nvim`](https://github.com/willysk73/redmine.nvim), but works
standalone — handy for quick CLI workflows against a Redmine instance.

- Stdlib-only (no `requests` / `httpx` — uses `urllib.request`)
- One narrow shape per subcommand; JSON output where it makes sense
- Exit codes are documented and stable so callers can branch on auth
  failure vs. config errors vs. generic failures

## Install

```bash
uv tool install redmine-core    # recommended (isolated, fastest)
# or
pipx install redmine-core
# or
pip install --user redmine-core
```

For local development / editable install:

```bash
git clone https://github.com/willysk73/redmine-core
cd redmine-core
uv pip install -e .             # or `pip install -e .`
```

## Build & publish

```bash
uv build                                          # → dist/*.whl + dist/*.tar.gz
uv publish --publish-url https://test.pypi.org/legacy/   # TestPyPI
uv publish                                        # PyPI (UV_PUBLISH_TOKEN env)
```

`uv build` replaces `python -m build`; `uv publish` replaces `twine
upload`. Both honor a standard `~/.pypirc` if you prefer that over env
vars.

## Configure

The CLI reads credentials from environment variables first, then from
`~/.config/redmine-core/config.toml`:

```bash
export REDMINE_URL=https://redmine.example.com
export REDMINE_API_KEY=<your-api-key>
# Optional, used by `list --filter mine`:
export REDMINE_USER=<your-login>
```

Or `~/.config/redmine-core/config.toml`:

```toml
url = "https://redmine.example.com"
api_key = "..."
user_login = "..."
```

Verify with:

```bash
redmine whoami
```

## Subcommands at a glance

| command                                                | what it does                                                                  |
|--------------------------------------------------------|-------------------------------------------------------------------------------|
| `redmine list [--filter mine\|open\|all] [--json]`     | List issues. JSON output for tooling.                                         |
| `redmine fetch <id> [--format display\|json\|task]`    | Fetch a single issue. `task` prints a markdown task-context block.            |
| `redmine detect [--cwd DIR]`                           | Resolve the current issue id from branch name / `.redmine` / cwd.             |
| `redmine whoami [--json]`                              | Authenticated user.                                                           |
| `redmine meta statuses [--issue N]`                    | Allowed status transitions (or global list).                                  |
| `redmine meta members --project <id\|identifier>`      | Project members for assignee pickers.                                         |
| `redmine update <id> [--status .. --progress .. --notes ..]` | Single-purpose update (one PUT, one journal).                           |
| `redmine assign <id> --user <name\|id\|""\|none>`      | Change assignee. Empty/`none` unassigns.                                      |
| `redmine log <id> --hours N [--activity .. --comment ..]` | Log a time entry.                                                          |
| `redmine post --file <draft.md>`                       | Compose-driven: bundle comment + status + progress + assignee + time. Single PUT, single journal. Empty body + frontmatter changes also accepted. |
| `redmine attachment download --id N [--issue M] [--out PATH] [--force]` | Download an attachment, print absolute path. Default: `/tmp/redmine-attachments/<issue>/<filename>`. Idempotent — re-runs reuse the cached file. |
| `redmine path draft\|task\|archive --id N`             | Print the resolved path for a compose draft / task / archive.                 |
| `redmine suggest assignee --id N`                      | Suggest a default assignee (last commenter, falls back to author).            |

## Compose drafts

`post --file <path>` reads a markdown draft with YAML-lite frontmatter:

```markdown
---
id: 123
status: Resolved
progress: 80
assignee: Alice
time: 1.5
---

본문 — 코멘트 텍스트.

<!-- ━━━ 아래는 참고용. post 시 무시됨. ━━━ -->
(이슈 컨텍스트, 이전 코멘트, 변경 로그 등 — 무시됨)
```

- All frontmatter fields are optional. `id` is the only required key.
- A single PUT bundles `notes` + `status_id` + `done_ratio` + `assigned_to_id`
  → exactly one journal entry.
- Empty body with frontmatter changes is allowed (status-only updates).
- `time:` triggers a separate `POST /time_entries.json`.

## Exit codes

| code | meaning                                              |
|------|------------------------------------------------------|
| 0    | success                                              |
| 1    | generic failure (e.g. detect found nothing)          |
| 2    | bad argv                                             |
| 11   | authentication failure (HTTP 401/403 from Redmine)   |

`11` is split out so callers can re-prompt for credentials without
having to parse error text.

## License

MIT — see [LICENSE](LICENSE).
