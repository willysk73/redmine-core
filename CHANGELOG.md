# Changelog

All notable changes to `redmine-core` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-05-10

### Changed
- **Default draft / archive paths moved from `{worktree}/.claude/` to
  `{worktree}/.redmine/{drafts,posted}/`**. The previous default was a
  development-environment artifact (Claude Code's data dir) and has no
  business being the published default. Users with `[paths]` overrides
  in `~/.config/redmine-core/config.toml` are unaffected.

### Yanked
- 0.1.0 was yanked because it shipped the `.claude/` default.

## [0.1.0] - 2026-05-10

### Added
- Initial PyPI release.
- Subcommands: `list`, `fetch`, `detect`, `whoami`, `meta`,
  `update`, `assign`, `log`, `path`, `post`, `suggest`,
  `attachment download`.
- Single-PUT bundling for `post` (comment + status + progress +
  assignee in one journal entry; time entry as a separate POST).
- Empty body + frontmatter-only posts accepted.
- src/ layout, stdlib-only.
- Exit code 11 reserved for auth failures.
