"""The clock (N1, AC5) and git history (AC6), on real repositories with scripted dates.

Each test builds a throwaway repository whose commits carry the committer dates the
scenario needs, then asks the engine how many days an active product has stood still.
"""

from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path

import pytest

from helpers import TODAY, GitRepo, copy_fixture, run_cli
from portfolio_ops.git import Git
from portfolio_ops.history import clocks, read_history
from portfolio_ops.loading import DataDir, load_portfolio, read_config

CONFIG = "schema_version: 1\nallow_public: true\nvocabularies:\n  capabilities: [x]\n"


def entry(
    pid: str, status: str = "active", next_action: str | None = "Ship it", name: str = ""
) -> str:
    lines = [f"  - id: {pid}", f"    name: {name or pid.title()}", f"    status: {status}"]
    if next_action is not None:
        lines.append(f"    next_action: {next_action}")
    if status in ("paused", "dormant"):
        lines += ["    status_reason: Later", "    review_by: 2026-10-01"]
    return "\n".join(lines) + "\n"


def products(*entries: str) -> str:
    return "products:\n" + "".join(entries)


@pytest.fixture
def repo(git_repo: GitRepo) -> GitRepo:
    git_repo.write("config.yaml", CONFIG)
    git_repo.write("decisions.md", "# Decisions\n")
    return git_repo


def clock(repo: GitRepo, product_id: str, today: dt.date = TODAY) -> int:
    data = DataDir(repo.root)
    loaded = load_portfolio(data, read_config(data))
    assert loaded.problems == ()
    history = read_history(Git(repo.root), data, today, _ignore)
    return clocks(loaded.portfolio, history, today)[product_id].days


def _ignore(file: str, message: str) -> None:
    raise AssertionError(f"unexpected warning about {file}: {message}")


def days_since(day: str, today: dt.date = TODAY) -> int:
    return (today - dt.date.fromisoformat(day)).days


def test_the_clock_counts_from_the_commit_that_set_the_current_next_action(repo: GitRepo) -> None:
    repo.write("products.yaml", products(entry("alpha", next_action="Draft")))
    repo.commit(dt.date(2026, 8, 1))
    repo.write("products.yaml", products(entry("alpha", next_action="Ship")))
    repo.commit(dt.date(2026, 8, 20))

    assert clock(repo, "alpha") == days_since("2026-08-20") == 33


def test_reordering_products_does_not_reset_the_clock(repo: GitRepo) -> None:
    repo.write("products.yaml", products(entry("alpha"), entry("beta")))
    repo.commit(dt.date(2026, 8, 20))
    repo.write("products.yaml", products(entry("beta"), entry("alpha")))
    repo.commit(dt.date(2026, 9, 10))

    assert clock(repo, "alpha") == days_since("2026-08-20")


def test_reformatting_the_yaml_and_adding_comments_does_not_reset_the_clock(repo: GitRepo) -> None:
    repo.write("products.yaml", products(entry("alpha", next_action="Ship the beta")))
    repo.commit(dt.date(2026, 8, 20))
    repo.write(
        "products.yaml",
        'products: [{id: alpha, name: Alpha, status: active, next_action: "Ship the beta"}]\n',
    )
    repo.commit(dt.date(2026, 9, 5))
    repo.write(
        "products.yaml",
        """
        # Reformatted: other indentation, quotes, key order and a folded scalar.
        products:
            -   status: 'active'
                next_action: >-
                    Ship the
                    beta
                name: "Alpha"
                id: alpha
        """,
    )
    repo.commit(dt.date(2026, 9, 10))

    assert clock(repo, "alpha") == days_since("2026-08-20")


def test_editing_other_fields_does_not_reset_the_clock(repo: GitRepo) -> None:
    repo.write("products.yaml", products(entry("alpha")))
    repo.commit(dt.date(2026, 8, 20))
    repo.write("products.yaml", products(entry("alpha", name="Alpha, renamed")))
    repo.commit(dt.date(2026, 9, 10))

    assert clock(repo, "alpha") == days_since("2026-08-20")


def test_changing_next_action_back_counts_from_the_change_back(repo: GitRepo) -> None:
    for day, action in (("2026-08-01", "A"), ("2026-08-10", "B"), ("2026-08-20", "A")):
        repo.write("products.yaml", products(entry("alpha", next_action=action)))
        repo.commit(dt.date.fromisoformat(day))

    assert clock(repo, "alpha") == days_since("2026-08-20")


def test_the_latest_transition_to_active_restarts_the_clock(repo: GitRepo) -> None:
    repo.write("products.yaml", products(entry("alpha")))
    repo.commit(dt.date(2026, 6, 1))
    repo.write("products.yaml", products(entry("alpha", status="paused")))
    repo.commit(dt.date(2026, 7, 1))
    repo.write("products.yaml", products(entry("alpha")))
    repo.commit(dt.date(2026, 9, 1))

    assert clock(repo, "alpha") == days_since("2026-09-01") == 21


def test_the_latest_defer_decision_restarts_the_clock(repo: GitRepo) -> None:
    repo.write("products.yaml", products(entry("alpha")))
    repo.commit(dt.date(2026, 8, 1))
    repo.write(
        "decisions.md",
        "## 2026-09-01 · alpha · defer\nWaiting on a supplier.\n\n"
        "## 2026-09-15 · alpha · defer\nStill waiting.\n",
    )

    assert clock(repo, "alpha") == days_since("2026-09-15") == 7


def test_the_clock_is_the_latest_of_the_three_dates(repo: GitRepo) -> None:
    repo.write("products.yaml", products(entry("alpha", next_action="A")))
    repo.commit(dt.date(2026, 7, 1))
    repo.write("products.yaml", products(entry("alpha", next_action="B")))
    repo.commit(dt.date(2026, 8, 10))
    repo.write("decisions.md", "## 2026-07-20 · alpha · defer\nAn older deferral.\n")

    assert clock(repo, "alpha") == days_since("2026-08-10")


def test_an_uncommitted_change_of_next_action_counts_as_today(repo: GitRepo) -> None:
    repo.write("products.yaml", products(entry("alpha", next_action="A")))
    repo.commit(dt.date(2026, 8, 1))
    repo.write("products.yaml", products(entry("alpha", next_action="B")))

    assert clock(repo, "alpha") == 0


def test_an_uncommitted_edit_to_another_field_does_not_reset_the_clock(repo: GitRepo) -> None:
    repo.write("products.yaml", products(entry("alpha")))
    repo.commit(dt.date(2026, 8, 1))
    repo.write("products.yaml", products(entry("alpha", name="Alpha Two")))

    assert clock(repo, "alpha") == days_since("2026-08-01")


def test_a_product_that_is_in_no_commit_yet_counts_as_changed_today(repo: GitRepo) -> None:
    repo.write("products.yaml", products(entry("alpha")))
    repo.commit(dt.date(2026, 8, 1))
    repo.write("products.yaml", products(entry("alpha"), entry("beta")))

    assert clock(repo, "beta") == 0
    assert clock(repo, "alpha") == days_since("2026-08-01")


def test_a_version_that_does_not_parse_is_skipped_with_a_warning(repo: GitRepo) -> None:
    repo.write("products.yaml", products(entry("alpha")))
    repo.commit(dt.date(2026, 8, 1))
    repo.write("products.yaml", "products: [this does not parse\n")
    repo.commit(dt.date(2026, 8, 10))
    repo.write("products.yaml", products(entry("alpha")))
    repo.commit(dt.date(2026, 8, 20))
    warnings: list[str] = []

    data = DataDir(repo.root)
    history = read_history(
        Git(repo.root), data, TODAY, lambda file, message: warnings.append(f"{file}: {message}")
    )

    assert history.next_action_since["alpha"] == dt.date(2026, 8, 1)
    assert len(warnings) == 1
    assert "does not parse" in warnings[0]


def test_commit_times_are_committer_dates_converted_to_utc(repo: GitRepo) -> None:
    repo.write("products.yaml", products(entry("alpha")))
    repo.commit("2026-08-01T23:30:00-05:00")  # 04:30 UTC on 2 August

    assert clock(repo, "alpha") == days_since("2026-08-02")


def test_the_history_of_a_data_directory_inside_a_larger_repository(git_repo: GitRepo) -> None:
    git_repo.write("README.md", "Not data.\n")
    git_repo.write("data/config.yaml", CONFIG)
    git_repo.write("data/decisions.md", "")
    git_repo.write("data/products.yaml", products(entry("alpha")))
    git_repo.commit(dt.date(2026, 8, 1))
    git_repo.write("README.md", "Still not data.\n")
    git_repo.write("products.yaml", products(entry("alpha", next_action="Elsewhere")))
    git_repo.commit(dt.date(2026, 9, 1))
    data = DataDir(git_repo.root / "data")

    history = read_history(Git(data.root), data, TODAY, _ignore)

    assert history.next_action_since["alpha"] == dt.date(2026, 8, 1)
    assert history.last_data_commit == dt.date(2026, 8, 1)


def test_the_clock_never_runs_backwards_when_today_precedes_the_commit(repo: GitRepo) -> None:
    repo.write("products.yaml", products(entry("alpha")))
    repo.commit(dt.date(2026, 9, 20))

    assert clock(repo, "alpha", today=dt.date(2026, 9, 1)) == 0


# ------------------------------------------------------------------ AC6


def _shallow_clone(repo: GitRepo, dest: Path) -> Path:
    subprocess.run(
        ["git", "clone", "--quiet", "--depth", "1", repo.root.as_uri(), str(dest)],
        check=True,
        capture_output=True,
    )
    return dest


@pytest.fixture
def history_repo(repo: GitRepo) -> GitRepo:
    for day in (1, 10, 20):
        repo.write("products.yaml", products(entry("alpha", next_action=f"Step {day}")))
        repo.commit(dt.date(2026, 8, day))
    return repo


def test_report_on_a_shallow_clone_exits_2_naming_fetch_depth_0(
    history_repo: GitRepo, tmp_path: Path
) -> None:
    clone = _shallow_clone(history_repo, tmp_path / "shallow")

    run = run_cli(["report", "--path", str(clone)])

    assert run.code == 2
    assert run.out == ""
    assert "shallow clone" in run.err
    assert "fetch-depth: 0" in run.err


def test_validate_needs_no_history_even_on_a_shallow_clone(
    history_repo: GitRepo, tmp_path: Path
) -> None:
    clone = _shallow_clone(history_repo, tmp_path / "shallow")

    assert run_cli(["validate", "--path", str(clone)]).code == 0


def test_validate_works_outside_a_git_repository(tmp_path: Path) -> None:
    root = copy_fixture("valid", tmp_path / "plain")

    run = run_cli(["validate", "--path", str(root)])

    assert run.code == 0
    assert run.out == ""


def test_report_outside_a_git_repository_exits_2(tmp_path: Path) -> None:
    root = copy_fixture("valid", tmp_path / "plain")

    run = run_cli(["report", "--path", str(root)])

    assert run.code == 2
    assert "not inside a git repository" in run.err


def test_the_report_counts_stale_days_from_git(history_repo: GitRepo) -> None:
    run = run_cli(["report", "--path", str(history_repo.root), "--today", "2026-09-22"])

    assert run.code == 0, run.err
    assert "- Median clock of active products: 33 days" in run.lines
    assert "| Alpha (`alpha`) | 33 days | Step 20 |" in run.lines
