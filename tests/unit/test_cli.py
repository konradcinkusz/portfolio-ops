"""The command line (spec §7.6–§7.8): commands, options, exit codes and message lines."""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import FIXTURES, FakeGitHub, GitRepo, copy_fixture, run_cli
from portfolio_ops import __version__

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "starter"
LINE = re.compile(r"^(error|warning) (\S+) (\S+):(\d+): (.+ — .+)$")


# ------------------------------------------------------------------ AC1 and AC2


def test_the_starter_example_validates_without_errors() -> None:
    run = run_cli(["validate", "--path", str(EXAMPLES)])

    assert run.code == 0
    assert run.out == ""
    assert "0 errors, 0 warnings" in run.err


@pytest.mark.parametrize(
    ("rule", "file", "line"),
    [
        ("S1", "kernels.yaml", 7),
        ("S2", "risks.yaml", 4),
        ("S3", "products.yaml", 14),
        ("S4", "products.yaml", 3),
        ("S5", "config.yaml", 13),
        ("P2", "findings.yaml", 3),
        ("L1", "products.yaml", 25),
    ],
)
def test_each_rule_fixture_prints_exactly_one_error_line_naming_file_and_line(
    rule: str, file: str, line: int
) -> None:
    run = run_cli(["validate", "--path", str(FIXTURES / rule)])

    assert run.code == 1
    (only,) = run.lines
    match = LINE.match(only)
    assert match, only
    assert match.group(1, 2) == ("error", rule)
    assert match.group(3).endswith(f"/{rule}/{file}")
    assert int(match.group(4)) == line


def test_the_l2_fixture_prints_one_warning_and_exits_0() -> None:
    run = run_cli(["validate", "--path", str(FIXTURES / "L2")])

    assert run.code == 0
    (only,) = run.lines
    assert only.startswith("warning L2 ")
    assert only.endswith(
        "/L2/config.yaml:10: wip_limit 6 exceeds 30 / 7 × 1 = 4.3 — the weekly report will flag "
        "most active products"
    )


def test_the_valid_fixture_is_the_passing_case() -> None:
    assert run_cli(["validate", "--path", str(FIXTURES / "valid")]).code == 0


def test_diagnostics_go_to_stdout_and_the_summary_to_stderr() -> None:
    run = run_cli(["validate", "--path", str(FIXTURES / "S4")])

    assert run.out.startswith("error S4 ")
    assert run.err.endswith(": 1 error, 0 warnings\n")


# ------------------------------------------------------------------ usage


def test_version_prints_the_engine_version() -> None:
    run = run_cli(["--version"])

    assert run.code == 0
    assert run.out == f"portfolio-ops {__version__}\n"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "the following arguments are required"),
        (["lint"], "invalid choice: 'lint'"),
        (["validate", "--today", "2026-09-22"], "unrecognized arguments: --today"),
        (["report", "--today", "22.09.2026"], "expected a real date written YYYY-MM-DD"),
        (["report", "--today", "2026-02-30"], "expected a real date written YYYY-MM-DD"),
        (["report", "--publish", "--repo", "not-a-repository"], "expected OWNER/NAME"),
        (["report", "--publish", "--repo", "owner/.."], "expected OWNER/NAME"),
    ],
)
def test_usage_errors_exit_2(args: list[str], message: str) -> None:
    run = run_cli(args)

    assert run.code == 2
    assert message in run.err


def test_dry_run_without_publish_is_a_usage_error() -> None:
    run = run_cli(["report", "--dry-run", "--path", str(FIXTURES / "valid")])

    assert run.code == 2
    assert run.err == "error: --dry-run previews publishing, so it needs --publish\n"


def test_the_help_lists_both_commands() -> None:
    run = run_cli(["--help"])

    assert run.code == 0
    assert "validate" in run.out
    assert "report" in run.out


def test_the_module_runs_as_a_program() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "portfolio_ops", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == f"portfolio-ops {__version__}\n"


# ------------------------------------------------------------------ --path


def test_path_defaults_to_the_root_of_the_git_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = GitRepo(tmp_path / "data")
    copy_fixture("S4", repo.root / "tmp-copy")
    for item in (repo.root / "tmp-copy").iterdir():
        item.rename(repo.root / item.name)
    (repo.root / "notes").mkdir()
    monkeypatch.chdir(repo.root / "notes")

    run = run_cli(["validate"])

    assert run.code == 1
    assert run.out.startswith("error S4 ../products.yaml:3: ")


def test_path_defaults_to_the_current_directory_outside_a_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_fixture("S4", tmp_path / "plain")
    monkeypatch.chdir(root)

    run = run_cli(["validate"])

    assert run.out.startswith("error S4 products.yaml:3: ")


# ------------------------------------------------------------------ report (AC7)


@pytest.fixture
def data_repo(tmp_path: Path) -> GitRepo:
    """The valid fixture, committed on 1 August with a history of next actions."""
    repo = GitRepo(tmp_path / "data")
    copy_fixture("valid", repo.root / "portfolio")
    repo.commit(dt.date(2026, 8, 1))
    return repo


def test_report_with_a_fixed_date_is_deterministic(data_repo: GitRepo) -> None:
    args = ["report", "--path", str(data_repo.root / "portfolio"), "--today", "2026-09-22"]

    first, second = run_cli(args), run_cli(args)

    assert first.code == 0, first.err
    assert first.out == second.out
    assert re.findall(r"^## (.+)$", first.out, re.MULTILINE) == [
        "Stale",
        "Escalations",
        "Overdue reviews",
        "Focus",
        "Health",
    ]
    assert (
        "| Alpha (`alpha`) | 52 days | Write the first draft of the sync protocol |" in first.lines
    )
    assert "- Last commit touching the data: 2026-08-01" in first.lines


def test_report_on_invalid_data_renders_only_validation_errors_and_exits_1(
    data_repo: GitRepo,
) -> None:
    products = data_repo.root / "portfolio" / "products.yaml"
    products.write_text(
        products.read_text().replace(
            "    next_action: Write the first draft of the sync protocol\n", ""
        )
    )

    run = run_cli(["report", "--path", str(data_repo.root / "portfolio"), "--today", "2026-09-22"])

    assert run.code == 1
    assert re.findall(r"^## (.+)$", run.out, re.MULTILINE) == ["Validation errors"]
    assert "products.yaml:2: product 'alpha' is active but has no next_action" in run.out


def test_report_prints_warnings_to_stderr_and_still_exits_0(data_repo: GitRepo) -> None:
    config = data_repo.root / "portfolio" / "config.yaml"
    config.write_text(config.read_text().replace("wip_limit: 4", "wip_limit: 6"))

    run = run_cli(["report", "--path", str(data_repo.root / "portfolio")])

    assert run.code == 0
    assert "warning L2 " in run.err
    assert "warning L2" not in run.out


# ------------------------------------------------------------------ publishing (AC8)


PUBLISH_ENV = {"GITHUB_REPOSITORY": "owner/data", "GITHUB_TOKEN": "t"}


def test_publish_without_a_token_exits_2_and_names_the_variable(data_repo: GitRepo) -> None:
    run = run_cli(
        ["report", "--path", str(data_repo.root / "portfolio"), "--publish"],
        env={"GITHUB_REPOSITORY": "owner/data"},
    )

    assert run.code == 2
    assert run.out == ""
    assert "--publish needs GITHUB_TOKEN" in run.err


def test_publish_without_a_repository_exits_2_and_names_both_sources(data_repo: GitRepo) -> None:
    run = run_cli(
        ["report", "--path", str(data_repo.root / "portfolio"), "--publish"],
        env={"GITHUB_TOKEN": "t"},
    )

    assert run.code == 2
    assert "--repo OWNER/NAME" in run.err
    assert "GITHUB_REPOSITORY" in run.err


def test_a_dry_run_prints_the_plan_and_the_body_and_sends_no_write(data_repo: GitRepo) -> None:
    github = FakeGitHub().on("GET", "/repos/owner/data/issues", body=[])

    run = run_cli(
        ["report", "--path", str(data_repo.root / "portfolio"), "--publish", "--dry-run"],
        env=PUBLISH_ENV,
        github=github,
    )

    assert run.code == 0, run.err
    assert github.writes == []
    assert run.out.startswith("# Weekly review — week of 2026-09-21\n")
    assert 'dry run: planned action: create issue "Weekly review — week of 2026-09-21"' in run.err
    assert "no write request was sent" in run.err


def test_repo_takes_precedence_over_github_repository(data_repo: GitRepo) -> None:
    github = FakeGitHub().on("GET", "/repos/other/place/issues", body=[])

    run = run_cli(
        [
            "report",
            "--path",
            str(data_repo.root / "portfolio"),
            "--publish",
            "--dry-run",
            "--repo",
            "other/place",
        ],
        env=PUBLISH_ENV,
        github=github,
    )

    assert run.code == 0, run.err
    assert all("/repos/other/place/" in r.url for r in github.requests)


def test_publish_creates_the_issue_through_the_api(data_repo: GitRepo) -> None:
    github = (
        FakeGitHub()
        .on("GET", "/repos/owner/data/issues", body=[])
        .on("POST", "/repos/owner/data/labels", status=201, body={})
        .on("POST", "/repos/owner/data/issues", status=201, body={"number": 1})
    )

    run = run_cli(
        ["report", "--path", str(data_repo.root / "portfolio"), "--publish"],
        env=PUBLISH_ENV,
        github=github,
    )

    assert run.code == 0, run.err
    assert [r.method for r in github.writes] == ["POST", "POST"]
    assert "published: created issue #1 in owner/data" in run.err


def test_a_failed_publish_exits_2_without_printing_the_token(data_repo: GitRepo) -> None:
    github = FakeGitHub().on(
        "GET", "/repos/owner/data/issues", status=401, body={"message": "Bad credentials"}
    )
    env = {"GITHUB_REPOSITORY": "owner/data", "GITHUB_TOKEN": "sentinel-that-must-not-print"}

    run = run_cli(
        ["report", "--path", str(data_repo.root / "portfolio"), "--publish"], env=env, github=github
    )

    assert run.code == 2
    assert "publishing to owner/data failed" in run.err
    assert "HTTP 401: Bad credentials" in run.err
    assert "sentinel-that-must-not-print" not in run.out + run.err
