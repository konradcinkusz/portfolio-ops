"""The account scan through the command line (spec §7.12): report and dashboard scan the
account when PORTFOLIO_ACCOUNT_TOKEN is set, nothing else does, and the token never shows.

Every name here is invented.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from helpers import FakeGitHub, GitRepo, copy_fixture, run_cli, write_files

TOKEN = "github_pat_example_sentinel_that_must_not_print"  # noqa: S105 — invented
LOGIN = "example-owner"


@pytest.fixture
def data(tmp_path: Path) -> Path:
    """The valid fixture with repositories on alpha (active) and beta (paused), committed on
    1 August: report reads the clocks from git history."""
    repo = GitRepo(tmp_path / "data")
    root = copy_fixture("valid", repo.root / "portfolio")
    products = (root / "products.yaml").read_text(encoding="utf-8")
    for pid, name in (("alpha", "Alpha"), ("beta", "Beta")):
        entry = f"  - id: {pid}\n    name: {name}\n"
        products = products.replace(entry, f"{entry}    repos: [example-owner/{pid}]\n")
    write_files(root, {"products.yaml": products})
    repo.commit(dt.date(2026, 8, 1))
    return root


def account(*, data_repository: bool = False) -> FakeGitHub:
    """alpha and a side project were worked on this week, beta too although it is paused;
    only Dependabot pushed to bot-only."""
    repos = [
        {
            "full_name": f"{LOGIN}/{name}",
            "private": False,
            "fork": False,
            "archived": False,
            "pushed_at": "2026-09-20T09:00:00Z",
        }
        for name in ("alpha", "beta", "side-project", "bot-only", "core")
    ]
    if data_repository:
        repos.append(
            {
                "full_name": f"{LOGIN}/portfolio-data",
                "private": False,
                "fork": False,
                "archived": False,
                "pushed_at": "2026-09-21T07:00:00Z",
            }
        )
    fake = FakeGitHub().on("GET", "/user", body={"login": LOGIN})
    fake.on("GET", "/user/repos", body=repos)
    for name in ("alpha", "beta", "side-project", "core"):
        fake.on(
            "GET", f"/repos/{LOGIN}/{name}/activity", body=[{"timestamp": "2026-09-20T09:00:00Z"}]
        )
    fake.on("GET", f"/repos/{LOGIN}/bot-only/activity", body=[])
    return fake


def test_report_shows_the_accounts_work_outside_the_plan(data: Path) -> None:
    fake = account()

    run = run_cli(
        ["report", "--path", str(data)], env={"PORTFOLIO_ACCOUNT_TOKEN": TOKEN}, github=fake
    )

    assert run.code == 0, run.err
    assert "| `example-owner/side-project` | 2026-09-20 |" in run.lines
    assert "| Beta (`beta`) | paused | `example-owner/beta` | 2026-09-20 |" in run.lines
    assert "bot-only`" not in run.out
    assert (
        "- Account: 4 repositories worked on since 2026-09-15, 1 of them outside the portfolio"
        in run.lines
    )
    assert "note: the account scan read 5 repositories of example-owner\n" in run.err
    assert TOKEN not in run.out + run.err


def test_in_github_actions_the_data_repository_is_left_out(data: Path) -> None:
    fake = account(data_repository=True)
    env = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "example-owner/portfolio-data",
        "GITHUB_TOKEN": "workflow-token-sentinel",
        "PORTFOLIO_ACCOUNT_TOKEN": TOKEN,
    }

    run = run_cli(["report", "--path", str(data)], env=env, github=fake)

    assert run.code == 0, run.err
    assert "portfolio-data" not in run.out
    assert not any("portfolio-data" in path for path in fake.paths())
    # The fixture sets allow_public, so the guard asks nothing: every request is the scan's,
    # and each carries the account token, never the workflow's.
    assert {r.headers["Authorization"] for r in fake.requests} == {f"Bearer {TOKEN}"}


def test_a_rejected_token_is_a_report_item_and_changes_no_exit_code(data: Path) -> None:
    fake = FakeGitHub().on("GET", "/user", 401, {"message": "Bad credentials"})

    run = run_cli(
        ["report", "--path", str(data)], env={"PORTFOLIO_ACCOUNT_TOKEN": TOKEN}, github=fake
    )

    assert run.code == 0
    assert (
        "- **The account was not scanned.** GitHub rejected PORTFOLIO_ACCOUNT_TOKEN (HTTP 401): "
        "it has expired or been revoked — create a new fine-grained token and replace the "
        "secret." in run.lines
    )
    assert run.err.startswith("warning: the account was not scanned: GitHub rejected ")
    assert TOKEN not in run.out + run.err


def test_without_a_token_nothing_is_asked(data: Path) -> None:
    fake = FakeGitHub()

    run = run_cli(["report", "--path", str(data)], github=fake)

    assert run.code == 0
    assert "The account was not scanned: PORTFOLIO_ACCOUNT_TOKEN is not set" in run.out
    assert fake.requests == []


def test_the_dashboard_shows_the_accounts_repositories(data: Path) -> None:
    run = run_cli(
        ["dashboard", "--path", str(data)],
        env={"PORTFOLIO_ACCOUNT_TOKEN": TOKEN},
        github=account(),
    )

    assert run.code == 0, run.err
    assert '<h2 id="repositories-title">Repositories <span class="count">5</span></h2>' in run.out
    assert '<dt>Outside the plan</dt><dd class="value">2</dd>' in run.out
    assert TOKEN not in run.out + run.err


@pytest.mark.parametrize(
    "args",
    [
        ["validate"],
        ["export"],
        ["gate", "alpha", "--context", "store"],
        ["lookup", "alpha", "claim"],
    ],
)
def test_no_other_command_scans_the_account(data: Path, args: list[str]) -> None:
    fake = account()

    run = run_cli([*args, "--path", str(data)], env={"PORTFOLIO_ACCOUNT_TOKEN": TOKEN}, github=fake)

    assert run.code in (0, 1), run.err
    assert fake.requests == []


def test_invalid_data_is_not_scanned(tmp_path: Path) -> None:
    root = copy_fixture("S4", tmp_path / "S4")
    fake = account()

    run = run_cli(
        ["report", "--path", str(root)], env={"PORTFOLIO_ACCOUNT_TOKEN": TOKEN}, github=fake
    )

    assert run.code == 1
    assert fake.requests == []
