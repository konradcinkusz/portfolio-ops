"""The visibility guard (S7, spec §7.3 and §8.8): private by default.

What these files hold — risks, rejections, stalled projects — is a list of the owner's
weak spots, and publishing it by accident cannot be undone. So every command, after
checking ``schema_version`` and before reading any data file but config.yaml, asks
whether the repository is public, and refuses a public one unless config.yaml says
``allow_public: true``.

With the flag set there is nothing to refuse, so the guard does not ask (AC4: "with the
flag set, commands proceed").
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

from portfolio_ops.errors import EnvironmentProblem, Refused
from portfolio_ops.github import API_URL, GitHubClient, GitHubError, Transport
from portfolio_ops.model import CONFIG_FILE, Diagnostic

_REMOTE = re.compile(
    r"^(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"(?P<repository>[A-Za-z0-9-]+/[A-Za-z0-9._-]+?)(?:\.git)?/?$"
)
EXPOSED = "the products, risks, rejections and stalled projects in these files"


def github_repository(remote_url: str | None) -> str | None:
    """``owner/name`` of a github.com remote URL, or None for anything else."""
    match = _REMOTE.match(remote_url or "")
    return match.group("repository") if match else None


def check_visibility(
    *,
    allow_public: bool,
    flag_line: int | None,
    env: Mapping[str, str],
    origin_url: Callable[[], str | None],
    transport: Transport,
    warn: Callable[[Diagnostic], None],
) -> None:
    """Return when the command may read the data; raise Refused or EnvironmentProblem."""
    if allow_public:
        return
    if env.get("GITHUB_ACTIONS") == "true":
        _check_in_actions(env, transport, flag_line)
        return
    repository = github_repository(origin_url())
    if repository is None:
        warn(_warning("the origin remote is not a github.com repository"))
        return
    client = GitHubClient(transport, token=None)  # locally the guard asks without a token
    try:
        private = client.repository_private(repository)
    except GitHubError as exc:
        warn(_warning(f"asking GitHub about {repository} failed ({exc})"))
        return
    if private is False:
        raise Refused(_refusal(repository, flag_line))


def _check_in_actions(env: Mapping[str, str], transport: Transport, flag_line: int | None) -> None:
    repository = env.get("GITHUB_REPOSITORY", "")
    token = env.get("GITHUB_TOKEN", "")
    if not repository or not token:
        missing = "GITHUB_REPOSITORY" if not repository else "GITHUB_TOKEN"
        raise EnvironmentProblem(
            _undeterminable(f"{missing} is not set", "pass the workflow's token as github-token")
        )
    client = GitHubClient(transport, token, env.get("GITHUB_API_URL") or API_URL)
    try:
        private = client.repository_private(repository)
    except GitHubError as exc:
        raise EnvironmentProblem(_undeterminable(str(exc), "check the token's access")) from exc
    if private is None:
        raise EnvironmentProblem(
            _undeterminable(f"GitHub does not show {repository} to this token", "check its access")
        )
    if not private:
        raise Refused(_refusal(repository, flag_line))


def _refusal(repository: str, flag_line: int | None) -> Diagnostic:
    return Diagnostic(
        "error",
        "S7",
        CONFIG_FILE,
        flag_line,
        f"{repository} is public and {CONFIG_FILE} does not set allow_public: true — publishing "
        f"would expose {EXPOSED} to everyone; make the repository private, or set "
        "allow_public: true if you deliberately build in public",
    )


def _undeterminable(reason: str, fix: str) -> Diagnostic:
    return Diagnostic(
        "error",
        "S7",
        CONFIG_FILE,
        None,
        f"cannot tell whether the data repository is public: {reason} — in GitHub Actions this "
        f"check fails closed; {fix}, or set allow_public: true if the data may be public",
    )


def _warning(reason: str) -> Diagnostic:
    return Diagnostic(
        "warning",
        "S7",
        CONFIG_FILE,
        None,
        f"cannot tell whether the data repository is public: {reason} — continuing locally; "
        "in GitHub Actions this check fails closed",
    )
