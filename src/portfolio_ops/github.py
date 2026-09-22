"""The GitHub REST adapter (P11): the only place the engine speaks HTTP.

The client takes a *transport* — a function from a request to a response. In
production it is ``urllib_transport``; tests pass a scripted one. That seam lives in
the product rather than in a parallel fake (TESTING-STRATEGY.md §5), so the URL
building, JSON handling and error mapping below are exactly what runs in CI.

The token is sent in a header and never appears in a message: errors name the method,
the path and the status, nothing else (P5).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from portfolio_ops import __version__

API_URL = "https://api.github.com"
REPOSITORY = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}")


@dataclass(frozen=True)
class Request:
    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes | None = None


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes


Transport = Callable[[Request], Response]


def urllib_transport(request: Request) -> Response:
    """Send one request with the standard library. Network failures raise OSError."""
    prepared = urllib.request.Request(  # noqa: S310 — the URL is https, built by GitHubClient
        request.url, data=request.body, method=request.method, headers=dict(request.headers)
    )
    try:
        with urllib.request.urlopen(prepared, timeout=20) as reply:  # noqa: S310 — same
            return Response(reply.status, reply.read())
    except urllib.error.HTTPError as reply:
        return Response(reply.code, reply.read())


class GitHubError(Exception):
    """A request that did not succeed. ``status`` is None when nothing came back."""

    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    created_at: str


class GitHubClient:
    def __init__(self, transport: Transport, token: str | None, api_url: str = API_URL) -> None:
        self._transport = transport
        self._token = token
        self._api_url = api_url.rstrip("/")

    def _call(self, method: str, path: str, payload: Any = None) -> tuple[int, Any]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"portfolio-ops/{__version__}",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(method, f"{self._api_url}{path}", headers, body)
        try:
            response = self._transport(request)
        except OSError as exc:
            reason = getattr(exc, "reason", None) or exc.strerror or type(exc).__name__
            raise GitHubError(None, f"{method} {path} failed: {reason}") from exc
        data: Any = None
        if response.body:
            try:
                data = json.loads(response.body)
            except ValueError:
                data = None
        return response.status, data

    def _expect(
        self, method: str, path: str, payload: Any = None, ok: tuple[int, ...] = (200,)
    ) -> Any:
        status, data = self._call(method, path, payload)
        if status not in ok:
            detail = data.get("message") if isinstance(data, dict) else None
            suffix = f": {detail}" if isinstance(detail, str) else ""
            raise GitHubError(status, f"{method} {path} returned HTTP {status}{suffix}")
        return data

    def repository_private(self, repository: str) -> bool | None:
        """Whether the repository is private; None when GitHub answers 404."""
        path = f"/repos/{repository}"
        status, data = self._call("GET", path)
        if status == 404:
            return None
        if status != 200 or not isinstance(data, dict) or not isinstance(data.get("private"), bool):
            raise GitHubError(status, f"GET {path} returned HTTP {status}")
        return bool(data["private"])

    def open_issues(self, repository: str, label: str) -> list[Issue]:
        """Open issues carrying ``label``, oldest first. Pull requests are not issues."""
        issues: list[Issue] = []
        query = urllib.parse.urlencode(
            {
                "state": "open",
                "labels": label,
                "per_page": 100,
                "sort": "created",
                "direction": "asc",
            }
        )
        for page in range(1, 51):
            data = self._expect("GET", f"/repos/{repository}/issues?{query}&page={page}")
            if not isinstance(data, list):
                raise GitHubError(200, f"GET /repos/{repository}/issues returned no list")
            for item in data:
                if isinstance(item, dict) and "pull_request" not in item:
                    issues.append(
                        Issue(
                            int(item["number"]),
                            str(item.get("title", "")),
                            str(item.get("created_at", "")),
                        )
                    )
            if len(data) < 100:
                break
        return sorted(issues, key=lambda issue: (issue.created_at, issue.number))

    def label_exists(self, repository: str, label: str) -> bool:
        path = f"/repos/{repository}/labels/{urllib.parse.quote(label)}"
        status, _ = self._call("GET", path)
        if status == 404:
            return False
        if status != 200:
            raise GitHubError(status, f"GET {path} returned HTTP {status}")
        return True

    def create_label(self, repository: str, label: str, color: str, description: str) -> None:
        payload = {"name": label, "color": color, "description": description}
        self._expect("POST", f"/repos/{repository}/labels", payload, ok=(201,))

    def create_issue(self, repository: str, title: str, body: str, label: str) -> int:
        payload = {"title": title, "body": body, "labels": [label]}
        data = self._expect("POST", f"/repos/{repository}/issues", payload, ok=(201,))
        return int(data["number"]) if isinstance(data, dict) else 0

    def update_issue(self, repository: str, number: int, title: str, body: str) -> None:
        self._expect(
            "PATCH", f"/repos/{repository}/issues/{number}", {"title": title, "body": body}
        )

    def close_issue(self, repository: str, number: int) -> None:
        payload = {"state": "closed", "state_reason": "completed"}
        self._expect("PATCH", f"/repos/{repository}/issues/{number}", payload)
