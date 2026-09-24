"""Shared test helpers: fictional data directories, the CLI run in-process, git repositories.

Every test is independent (TESTING-STRATEGY.md §6): it builds its own data in a temporary
directory, talks to no network, and never sleeps.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import shutil
import subprocess
import textwrap
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # imported lazily, so a test that needs no CLI never loads one
    from portfolio_ops.github import Request, Response
    from portfolio_ops.model import Portfolio

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = dt.date(2026, 9, 22)


def write_files(root: Path, files: Mapping[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (root / name).write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return root


def copy_fixture(name: str, dest: Path) -> Path:
    shutil.copytree(FIXTURES / name, dest)
    return dest


def match_golden(path: Path, text: str, update: bool) -> None:
    """``text`` equals the golden file ``path``, byte for byte.

    With ``pytest --update-golden`` it rewrites the file instead; review the diff like any
    other change.
    """
    if update:
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    assert text == path.read_text(encoding="utf-8")


def load_valid(root: Path, files: Mapping[str, str] | None = None) -> Portfolio:
    """The typed model of the valid fixture, copied to ``root``, with ``files`` replaced.

    The data must still load without a shape problem; rule violations are the caller's
    business.
    """
    from portfolio_ops.loading import DataDir, load_portfolio, read_config

    copy_fixture("valid", root)
    write_files(root, files or {})
    data = DataDir(root)
    loaded = load_portfolio(data, read_config(data))
    assert loaded.problems == (), [p.render() for p in loaded.problems]
    return loaded.portfolio


# --------------------------------------------------------------------------- GitHub


@dataclass
class FakeGitHub:
    """A scripted transport for the real GitHub client: records every request.

    The client's own URL building, JSON handling and error mapping all run; only the
    socket is replaced. Tests assert on ``requests`` — for example that a dry run sent
    nothing but reads.
    """

    routes: dict[tuple[str, str], Response | Exception] = field(default_factory=dict)
    requests: list[Request] = field(default_factory=list)

    def on(
        self,
        method: str,
        path: str,
        status: int = 200,
        body: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> FakeGitHub:
        """Answer requests for ``path``. A path with a query answers only that exact query;
        one without answers every query."""
        from portfolio_ops.github import Response

        payload = b"" if body is None else json.dumps(body).encode()
        self.routes[(method, path)] = Response(status, payload, dict(headers or {}))
        return self

    def fail(self, method: str, path: str, error: Exception) -> FakeGitHub:
        self.routes[(method, path)] = error
        return self

    def __call__(self, request: Request) -> Response:
        from portfolio_ops.github import Response

        self.requests.append(request)
        path = "/" + request.url.split("://", 1)[-1].split("/", 1)[-1]
        route = self.routes.get((request.method, path))
        if route is None:
            route = self.routes.get((request.method, path.split("?", 1)[0]))
        if route is None:
            return Response(404, b'{"message": "Not Found"}')
        if isinstance(route, Exception):
            raise route
        return route

    def paths(self) -> list[str]:
        """The path and query of every request, in order."""
        return ["/" + r.url.split("://", 1)[-1].split("/", 1)[-1] for r in self.requests]

    @property
    def writes(self) -> list[Request]:
        return [r for r in self.requests if r.method != "GET"]


# --------------------------------------------------------------------------- CLI


@dataclass
class Run:
    code: int
    out: str
    err: str

    @property
    def lines(self) -> list[str]:
        return self.out.splitlines()


def run_cli(
    args: list[str],
    *,
    env: Mapping[str, str] | None = None,
    github: Callable[[Request], Response] | None = None,
    today: dt.date = TODAY,
) -> Run:
    from portfolio_ops import cli

    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        args,
        env=dict(env or {}),
        stdout=out,
        stderr=err,
        transport=github or FakeGitHub(),
        today=lambda: today,
    )
    return Run(code, out.getvalue(), err.getvalue())


# --------------------------------------------------------------------------- git


class GitRepo:
    """A throwaway repository whose commits carry scripted dates (AC5)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.git("init", "--quiet", "--initial-branch=main")

    def git(self, *args: str, date: dt.date | str | None = None) -> str:
        env = dict(os.environ)
        env.update(
            GIT_AUTHOR_NAME="Test Author",
            GIT_AUTHOR_EMAIL="author@example.invalid",
            GIT_COMMITTER_NAME="Test Author",
            GIT_COMMITTER_EMAIL="author@example.invalid",
        )
        if date is not None:
            # A date commits at noon UTC; a string is an exact timestamp with its offset.
            stamp = date if isinstance(date, str) else f"{date.isoformat()}T12:00:00+00:00"
            env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
        result = subprocess.run(
            ["git", *args], cwd=self.root, env=env, check=True, capture_output=True, text=True
        )
        return result.stdout

    def write(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")

    def commit(self, date: dt.date | str, message: str = "update data") -> None:
        self.git("add", "--all")
        self.git("commit", "--quiet", "--no-verify", "--allow-empty", "-m", message, date=date)

    def shallow_clone(self, dest: Path) -> Path:
        """A clone with only the latest commit, as actions/checkout makes by default."""
        subprocess.run(
            ["git", "clone", "--quiet", "--depth", "1", self.root.as_uri(), str(dest)],
            check=True,
            capture_output=True,
        )
        return dest
