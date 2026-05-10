"""HTTP client for Redmine REST API. stdlib only."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import Config


class APIError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class AuthError(APIError):
    """HTTP 401 / 403."""


class Client:
    def __init__(self, config: Config, timeout: float = 15.0):
        self.config = config
        self.timeout = timeout

    def _request(self, method: str, path: str, params: dict | None = None, body: Any = None) -> dict:
        url = f"{self.config.base_url}{path}"
        if params:
            qs = urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None},
                doseq=True,
            )
            if qs:
                url = f"{url}?{qs}"

        headers = {
            "X-Redmine-API-Key": self.config.api_key,
            "Accept": "application/json",
        }
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url=url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            text = ""
            try:
                text = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            msg = f"HTTP {e.code} on {method} {path}: {text[:300]}"
            if e.code in (401, 403):
                raise AuthError(msg, status=e.code) from e
            raise APIError(msg, status=e.code) from e
        except urllib.error.URLError as e:
            raise APIError(f"network error on {method} {path}: {e.reason}") from e

    # --- public, narrow surface used by CLI commands -----------------

    def list_issues(
        self,
        *,
        assigned_to: str | int | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        project_id: str | int | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if assigned_to is not None:
            params["assigned_to_id"] = assigned_to
        if status is not None:
            params["status_id"] = status
        if project_id is not None:
            params["project_id"] = project_id
        data = self._request("GET", "/issues.json", params=params)
        return data.get("issues", [])

    def get_issue(self, issue_id: int, *, includes: list[str] | None = None) -> dict:
        params = {}
        if includes:
            params["include"] = ",".join(includes)
        data = self._request("GET", f"/issues/{issue_id}.json", params=params)
        return data.get("issue", {})

    def current_user(self) -> dict:
        data = self._request("GET", "/users/current.json")
        return data.get("user", {})

    # --- M2 surface ---------------------------------------------------

    def list_statuses(self) -> list[dict]:
        data = self._request("GET", "/issue_statuses.json")
        return data.get("issue_statuses", [])

    def list_project_memberships(self, project: str | int) -> list[dict]:
        data = self._request("GET", f"/projects/{project}/memberships.json", params={"limit": 100})
        out = []
        for m in data.get("memberships", []):
            user = m.get("user")
            if not user:
                continue  # group memberships skipped
            out.append({"id": user.get("id"), "name": user.get("name")})
        return out

    def update_issue(self, issue_id: int, *, fields: dict) -> None:
        self._request("PUT", f"/issues/{issue_id}.json", body={"issue": fields})

    def list_time_entry_activities(self) -> list[dict]:
        data = self._request("GET", "/enumerations/time_entry_activities.json")
        return data.get("time_entry_activities", [])

    def add_time_entry(self, issue_id: int, *, hours: float, activity_id: int | None = None,
                       comments: str | None = None) -> dict:
        body: dict = {"time_entry": {"issue_id": issue_id, "hours": hours}}
        if activity_id is not None:
            body["time_entry"]["activity_id"] = activity_id
        if comments:
            body["time_entry"]["comments"] = comments
        data = self._request("POST", "/time_entries.json", body=body)
        return data.get("time_entry", {})

    def get_attachment(self, attachment_id: int) -> dict:
        data = self._request("GET", f"/attachments/{attachment_id}.json")
        return data.get("attachment", {})

    def download_attachment_bytes(self, content_url: str) -> bytes:
        # content_url is absolute (returned by Redmine); we still authenticate
        # via the API key header.
        headers = {"X-Redmine-API-Key": self.config.api_key}
        req = urllib.request.Request(url=content_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise AuthError(f"HTTP {e.code} on attachment download", status=e.code) from e
            raise APIError(f"HTTP {e.code} on attachment download", status=e.code) from e
        except urllib.error.URLError as e:
            raise APIError(f"network error on attachment download: {e.reason}") from e
