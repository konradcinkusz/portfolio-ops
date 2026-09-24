"""The account scan (spec §7.12, ADR 0008): which repositories the owner worked on.

The adapter half of A1–A3. It asks the GitHub REST API, through github.py, which
repositories the token's account owns and, for each one pushed within the window, when
the owner last acted in it. The rules in rules/account.py judge the typed scan it
returns.

The scan is optional (P8). Without ``PORTFOLIO_ACCOUNT_TOKEN`` nothing is asked. A token
that is set but fails gives an Account that says why, and the command goes on with the
same exit code. The token is sent in a header and never appears in a message (P5).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import replace

from portfolio_ops.github import API_URL, GitHubClient, GitHubError, Transport
from portfolio_ops.model import (
    ACCOUNT_TOKEN,
    NOT_SCANNED,
    Account,
    AccountRepository,
    AccountScan,
)
from portfolio_ops.rules.account import window_start

CLASSIC_PREFIX = "ghp_"  # a classic personal access token; fine-grained ones differ
NEXT_RUN = "the next run scans again"


def utc_date(stamp: str | None) -> dt.date | None:
    """The UTC date of an ISO 8601 timestamp from GitHub, or None."""
    if not stamp:
        return None
    try:
        moment = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return moment.astimezone(dt.UTC).date()


def scan_account(
    client: GitHubClient,
    *,
    today: dt.date,
    listed: frozenset[str],
    left_out: str | None,
    hide_private: bool,
) -> AccountScan:
    """Ask GitHub about the account. ``listed`` holds the repositories that ``repos`` lists,
    in lower case: a fork counts only when it is listed. Raises GitHubError."""
    login = client.login()
    since = window_start(today)
    repositories = []
    unreadable = ""
    for owned in client.owned_repositories():
        key = owned.name.lower()
        if left_out is not None and key == left_out.lower():
            continue
        pushed_on = utc_date(owned.pushed_at)
        repository = AccountRepository(
            owned.name, owned.private, owned.fork, owned.archived, pushed_on
        )
        candidate = (
            pushed_on is not None
            and since <= pushed_on <= today
            and not owned.archived
            and (not owned.fork or key in listed)
        )
        if candidate:
            try:
                latest = client.latest_activity(owned.name, login)
            except GitHubError as exc:
                if exc.rate_limited or exc.status not in (403, 404):
                    raise
                repository = replace(repository, activity="unreadable")
                unreadable = unreadable or _unreadable(exc)
            else:
                repository = replace(repository, activity="read", owner_active_on=utc_date(latest))
        repositories.append(repository)
    return AccountScan(
        login=login,
        since=since,
        until=today,
        repositories=tuple(repositories),
        left_out=left_out,
        hide_private=hide_private,
        unreadable=unreadable,
    )


def _unreadable(exc: GitHubError) -> str:
    asks = f"; GitHub asks for {exc.permissions}" if exc.permissions else ""
    return f"the token cannot read the repositories' activity lists (HTTP {exc.status}{asks})"


def read_account(
    env: Mapping[str, str],
    transport: Transport,
    *,
    today: dt.date,
    listed: frozenset[str],
    left_out: str | None,
    hide_private: bool,
) -> Account:
    """The account as the report and the dashboard show it: scanned when the token is set,
    or the reason it was not."""
    token = (env.get(ACCOUNT_TOKEN) or "").strip()
    if not token:
        return NOT_SCANNED
    if token.startswith(CLASSIC_PREFIX):
        return Account(
            problem=(
                f"{ACCOUNT_TOKEN} is a classic personal access token, which cannot be "
                "read-only — replace it with a fine-grained token that has read-only access "
                "to all of the account's repositories"
            ),
            failed=True,
        )
    client = GitHubClient(transport, token, env.get("GITHUB_API_URL") or API_URL)
    try:
        scan = scan_account(
            client, today=today, listed=listed, left_out=left_out, hide_private=hide_private
        )
    except GitHubError as exc:
        return Account(problem=_failure(exc), failed=True)
    return Account(scan=scan)


def _failure(exc: GitHubError) -> str:
    if exc.status == 401:
        return (
            "GitHub rejected PORTFOLIO_ACCOUNT_TOKEN (HTTP 401): it has expired or been "
            "revoked — create a new fine-grained token and replace the secret"
        )
    if exc.rate_limited:
        return f"the token's GitHub rate limit is spent — {NEXT_RUN}"
    if exc.status == 403:
        return (
            f"the token may not list the account's repositories ({exc}) — give it access to "
            "all repositories, with the read-only Metadata permission"
        )
    if exc.status is None:
        return f"GitHub could not be reached: {exc} — {NEXT_RUN}"
    return f"{exc} — {NEXT_RUN}"
