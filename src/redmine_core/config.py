"""Config loading: env vars override config file. No external deps."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


CONFIG_PATH_ENV = "REDMINE_CONFIG"
DEFAULT_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "redmine-core"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.toml"


@dataclass
class Config:
    url: str
    api_key: str
    user_login: str | None = None  # used by `list --filter mine`

    @property
    def base_url(self) -> str:
        return self.url.rstrip("/")


class ConfigError(Exception):
    pass


def _read_toml(path: Path) -> dict:
    # Python 3.11+ has tomllib; we use a minimal hand parser to keep 3.9+ working
    # without bringing in `tomli`. This parser only handles the keys we need:
    # top-level `key = "value"` lines and a single `[default]` table.
    data: dict[str, dict[str, str]] = {"_default": {}}
    section = "_default"
    if not path.exists():
        return {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            data.setdefault(section, {})
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        data[section][key] = value
    return data


def load(path: str | Path | None = None) -> Config:
    file_path = Path(path) if path else Path(os.environ.get(CONFIG_PATH_ENV, DEFAULT_CONFIG_FILE))
    file_data = _read_toml(file_path)
    flat = {**file_data.get("_default", {}), **file_data.get("default", {})}

    url = os.environ.get("REDMINE_URL") or flat.get("url")
    api_key = os.environ.get("REDMINE_API_KEY") or flat.get("api_key")
    user_login = os.environ.get("REDMINE_USER") or flat.get("user_login") or flat.get("user")

    if not url:
        raise ConfigError(
            "REDMINE_URL not set. Set REDMINE_URL env var or url in "
            f"{file_path}"
        )
    if not api_key:
        raise ConfigError(
            "REDMINE_API_KEY not set. Set REDMINE_API_KEY env var or api_key in "
            f"{file_path}"
        )
    return Config(url=url, api_key=api_key, user_login=user_login)
