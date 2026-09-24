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
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from portfolio_ops import __version__

API_URL = "https://api.github.com"


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
    headers: Mapping[str, str] = field(default_factory=dict)  # names in lower case


Transport = Callable[[Request], Response]


def urllib_transport(request: Request) -> Response:
    """Send one request with the standard library. Network failures raise OSError."""
    prepared = urllib.request.Request(  # noqa: S310 — the URL is https, built by GitHubClient
        request.url, data=request.body, method=request.method, headers=dict(request.headers)
    )
    try:
        with urllib.request.urlopen(prepared, timeout=20) as reply:  # noqa: S310 — same
            return Response(reply.status, reply.read(), _headers(reply.headers.items()))
    except urllib.error.HTTPError as reply:
        return Response(reply.code, reply.read(), _headers(reply.headers.items()))


def _headers(items: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {name.lower(): value for name, value in items}


class GitHubError(Exception):
    """A request that did not succeed. ``status`` is None when nothing came back.

    ``permissions`` is what GitHub's ``X-Accepted-GitHub-Permissions`` header says the
    request needs, when it says so; ``rate_limited`` is true when the token's rate limit is
    spent.
    """

    def __init__(
        self,
        status: int | None,
        message: str,
        *,
        permissions: str | None = None,
        rate_limited: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.permissions = permissions
        self.rate_limited = rate_limited


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    created_at: str


@dataclass(frozen=True)
class OwnedRepository:
    """One repository of the account, as ``GET /user/repos`` lists it."""

    name: str  # OWNER/NAME, as GitHub spells it
    private: bool
    fork: bool
    archived: bool
    pushed_at: str | None  # ISO 8601, UTC; None for a repository never pushed to


class GitHubClient:
    def __init__(self, transport: Transport, token: str | None, api_url: str = API_URL) -> None:
        self._transport = transport
        self._token = token
        self._api_url = api_url.rstrip("/")

    def _call(self, method: str, path: str, payload: Any = None) -> tuple[int, Any]:
        status, data, _ = self._send(method, path, payload)
        return status, data

    def _send(
        self, method: str, path: str, payload: Any = None
    ) -> tuple[int, Any, Mapping[str, str]]:
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
        return response.status, data, response.headers

    def _expect(
        self, method: str, path: str, payload: Any = None, ok: tuple[int, ...] = (200,)
    ) -> Any:
        status, data, headers = self._send(method, path, payload)
        if status not in ok:
            detail = data.get("message") if isinstance(data, dict) else None
            suffix = f": {detail}" if isinstance(detail, str) else ""
            raise GitHubError(
                status,
                f"{method} {path} returned HTTP {status}{suffix}",
                permissions=headers.get("x-accepted-github-permissions") or None,
                rate_limited=status == 429
                or (status == 403 and headers.get("x-ratelimit-remaining") == "0"),
            )
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

    # ------------------------------------------------------------ the account (§7.12)

    def login(self) -> str:
        """The login of the account the token belongs to."""
        data = self._expect("GET", "/user")
        login = data.get("login") if isinstance(data, dict) else None
        if not isinstance(login, str) or not login:
            raise GitHubError(200, "GET /user returned no login")
        return login

    def owned_repositories(self) -> list[OwnedRepository]:
        """Every repository the token's account owns, page by page."""
        found: list[OwnedRepository] = []
        query = urllib.parse.urlencode({"affiliation": "owner", "per_page": 100})
        for page in range(1, 51):
            data = self._expect("GET", f"/user/repos?{query}&page={page}")
            if not isinstance(data, list):
                raise GitHubError(200, "GET /user/repos returned no list")
            for item in data:
                if not isinstance(item, dict) or not isinstance(item.get("full_name"), str):
                    continue
                pushed = item.get("pushed_at")
                found.append(
                    OwnedRepository(
                        name=item["full_name"],
                        private=item.get("private") is True,
                        fork=item.get("fork") is True,
                        archived=item.get("archived") is True,
                        pushed_at=pushed if isinstance(pushed, str) else None,
                    )
                )
            if len(data) < 100:
                break
        return found

    def latest_activity(self, repository: str, actor: str) -> str | None:
        """When ``actor`` last acted in the repository — pushed, force-pushed, created or
        deleted a branch, or merged — as its activity list records it; None if never."""
        query = urllib.parse.urlencode({"actor": actor, "direction": "desc", "per_page": 1})
        data = self._expect("GET", f"/repos/{repository}/activity?{query}")
        if not isinstance(data, list):
            raise GitHubError(200, f"GET /repos/{repository}/activity returned no list")
        entry = data[0] if data else None
        stamp = entry.get("timestamp") if isinstance(entry, dict) else None
        return stamp if isinstance(stamp, str) else None
