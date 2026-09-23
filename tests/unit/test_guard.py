"""S7 (spec §7.3, AC4): a public data repository is refused unless it opts in."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path

import pytest

from helpers import FakeGitHub, GitRepo, copy_fixture, run_cli
from portfolio_ops.errors import EnvironmentProblem, Refused
from portfolio_ops.guard import check_visibility, github_repository
from portfolio_ops.loading import DataDir
from portfolio_ops.model import Diagnostic

ACTIONS = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "owner/name", "GITHUB_TOKEN": "t0ken"}
COMMANDS = [
    ["validate"],
    ["report", "--today", "2026-09-22"],
    ["report", "--publish", "--dry-run", "--repo", "owner/name"],
    ["gate", "alpha", "--context", "website"],
    ["idea-gate", "delta"],
    ["lookup", "delta", "name_check"],
]


def guard(
    github: FakeGitHub,
    *,
    allow_public: bool = False,
    env: dict[str, str] | None = None,
    origin: str | None = "https://github.com/owner/name.git",
) -> list[Diagnostic]:
    warnings: list[Diagnostic] = []
    check_visibility(
        allow_public=allow_public,
        flag_line=None,
        env=env or {},
        origin_url=lambda: origin,
        transport=github,
        warn=warnings.append,
    )
    return warnings


@pytest.mark.parametrize(
    ("url", "repository"),
    [
        ("https://github.com/owner/name.git", "owner/name"),
        ("https://github.com/owner/name", "owner/name"),
        ("https://token@github.com/owner/name.git", "owner/name"),
        ("git@github.com:owner/name.git", "owner/name"),
        ("ssh://git@github.com/owner/my.repo.git", "owner/my.repo"),
        ("https://gitlab.com/owner/name.git", None),
        ("/srv/git/name.git", None),
        (None, None),
    ],
)
def test_the_repository_is_derived_only_from_a_github_com_remote(
    url: str | None, repository: str | None
) -> None:
    assert github_repository(url) == repository


# ------------------------------------------------------------------ in GitHub Actions


def test_in_actions_a_public_repository_without_the_flag_is_refused() -> None:
    github = FakeGitHub().on("GET", "/repos/owner/name", body={"private": False})

    with pytest.raises(Refused) as refused:
        guard(github, env=ACTIONS)

    message = refused.value.render()
    assert refused.value.exit_code == 3
    assert message.startswith("error S7 config.yaml: owner/name is public")
    assert "allow_public: true" in message
    assert "risks, rejections and stalled projects" in message


def test_in_actions_the_guard_asks_github_with_the_workflow_token() -> None:
    github = FakeGitHub().on("GET", "/repos/owner/name", body={"private": True})

    assert guard(github, env=ACTIONS) == []
    (request,) = github.requests
    assert request.headers["Authorization"] == "Bearer t0ken"
    assert request.url == "https://api.github.com/repos/owner/name"


def test_in_actions_the_api_url_of_the_runner_is_used() -> None:
    github = FakeGitHub().on("GET", "/api/v3/repos/owner/name", body={"private": True})

    guard(github, env={**ACTIONS, "GITHUB_API_URL": "https://github.example.com/api/v3"})

    assert github.requests[0].url == "https://github.example.com/api/v3/repos/owner/name"


@pytest.mark.parametrize(
    "script",
    [
        lambda g: g.on("GET", "/repos/owner/name", status=500, body={"message": "Server Error"}),
        lambda g: g.on("GET", "/repos/owner/name", status=403, body={"message": "Forbidden"}),
        lambda g: g.fail("GET", "/repos/owner/name", OSError("network is unreachable")),
        lambda g: g,  # 404: the token cannot see the repository
    ],
    ids=["server-error", "forbidden", "network", "not-found"],
)
def test_in_actions_an_undeterminable_visibility_fails_closed_with_exit_2(
    script: Callable[[FakeGitHub], FakeGitHub],
) -> None:
    with pytest.raises(EnvironmentProblem) as stopped:
        guard(script(FakeGitHub()), env=ACTIONS)

    assert stopped.value.exit_code == 2
    assert stopped.value.render().startswith("error S7 config.yaml: cannot tell whether")
    assert "t0ken" not in stopped.value.render()


@pytest.mark.parametrize("missing", ["GITHUB_TOKEN", "GITHUB_REPOSITORY"])
def test_in_actions_a_missing_variable_fails_closed_and_is_named(missing: str) -> None:
    env = {k: v for k, v in ACTIONS.items() if k != missing}

    with pytest.raises(EnvironmentProblem) as stopped:
        guard(FakeGitHub(), env=env)

    assert f"{missing} is not set" in stopped.value.render()


def test_with_the_flag_set_nothing_is_asked_and_the_command_proceeds() -> None:
    github = FakeGitHub()

    assert guard(github, allow_public=True, env=ACTIONS) == []
    assert guard(github, allow_public=True) == []
    assert github.requests == []


# ------------------------------------------------------------------ locally


def test_locally_a_public_repository_without_the_flag_is_refused() -> None:
    github = FakeGitHub().on("GET", "/repos/owner/name", body={"private": False})

    with pytest.raises(Refused):
        guard(github)


def test_locally_the_guard_asks_without_a_token_and_a_404_means_not_public() -> None:
    github = FakeGitHub()

    assert guard(github, env={"GITHUB_TOKEN": "local-token"}) == []
    (request,) = github.requests
    assert "Authorization" not in request.headers


@pytest.mark.parametrize(
    ("origin", "github", "reason"),
    [
        (None, FakeGitHub(), "the origin remote is not a github.com repository"),
        ("https://gitlab.com/owner/name.git", FakeGitHub(), "not a github.com repository"),
        (
            "https://github.com/owner/name.git",
            FakeGitHub().fail("GET", "/repos/owner/name", OSError("offline")),
            "asking GitHub about owner/name failed",
        ),
        (
            "https://github.com/owner/name.git",
            FakeGitHub().on("GET", "/repos/owner/name", status=403, body={"message": "rate"}),
            "asking GitHub about owner/name failed",
        ),
    ],
    ids=["no-origin", "not-github", "offline", "rate-limited"],
)
def test_locally_an_undeterminable_visibility_warns_and_proceeds(
    origin: str | None, github: FakeGitHub, reason: str
) -> None:
    warnings = guard(github, origin=origin)

    assert len(warnings) == 1
    assert warnings[0].render().startswith("warning S7 config.yaml: cannot tell whether")
    assert reason in warnings[0].message


# ------------------------------------------------------------------ the whole command (AC4)


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every data file the command reads, in order."""
    seen: list[str] = []
    original = DataDir.read_text

    def recording(self: DataDir, name: str) -> str:
        seen.append(name)
        return original(self, name)

    monkeypatch.setattr(DataDir, "read_text", recording)
    return seen


@pytest.mark.parametrize("command", COMMANDS, ids=" ".join)
def test_every_command_refuses_a_public_repository_before_reading_other_files(
    command: list[str], tmp_path: Path, reads: list[str]
) -> None:
    root = copy_fixture("S7", tmp_path / "data")
    github = FakeGitHub().on("GET", "/repos/owner/name", body={"private": False})

    run = run_cli([*command, "--path", str(root)], env=ACTIONS, github=github)

    assert run.code == 3
    assert run.out == ""
    assert run.err.startswith("error S7 ")
    assert reads == ["config.yaml"]


def test_a_local_run_in_a_public_clone_is_refused(tmp_path: Path, reads: list[str]) -> None:
    repo = GitRepo(tmp_path / "clone")
    copy_fixture("S7", repo.root / "data")
    repo.git("remote", "add", "origin", "git@github.com:owner/name.git")
    github = FakeGitHub().on("GET", "/repos/owner/name", body={"private": False})

    run = run_cli(["validate", "--path", str(repo.root / "data")], github=github)

    assert run.code == 3
    assert reads == ["config.yaml"]


@pytest.mark.parametrize("command", COMMANDS, ids=" ".join)
def test_with_the_flag_set_every_command_proceeds_in_a_public_repository(
    command: list[str], tmp_path: Path
) -> None:
    repo = GitRepo(tmp_path / "data")
    copy_fixture("valid", repo.root / "d")
    repo.commit(date=dt.date(2026, 9, 1))
    github = (
        FakeGitHub()
        .on("GET", "/repos/owner/name", body={"private": False})
        .on("GET", "/repos/owner/name/issues", body=[])
    )

    run = run_cli([*command, "--path", str(repo.root / "d")], env=ACTIONS, github=github)

    assert run.code == 0, run.err
    assert all(r.url != "https://api.github.com/repos/owner/name" for r in github.requests)


def test_locally_a_command_warns_and_proceeds_outside_any_repository(tmp_path: Path) -> None:
    root = copy_fixture("S7", tmp_path / "data")

    run = run_cli(["validate", "--path", str(root)])

    assert run.code == 0
    assert "warning S7" in run.err


def test_the_token_is_never_printed(tmp_path: Path) -> None:
    root = copy_fixture("S7", tmp_path / "data")
    sentinel = "sentinel-value-that-must-never-be-printed"
    github = FakeGitHub().on("GET", "/repos/owner/name", status=500, body={"message": "boom"})

    run = run_cli(
        ["validate", "--path", str(root)], env={**ACTIONS, "GITHUB_TOKEN": sentinel}, github=github
    )

    assert run.code == 2
    assert sentinel not in run.out + run.err
