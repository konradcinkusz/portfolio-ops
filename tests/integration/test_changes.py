"""P1 in git (spec §8.4, ADR 0005): which status and state changes the engine finds, and
how it dates them — every change in history for the report, the changes since the
previous commit for validate. Real repositories with scripted commit dates, like the
clock's tests.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from helpers import TODAY, GitRepo, copy_fixture, run_cli
from portfolio_ops.git import Git
from portfolio_ops.history import NoPreviousCommit, read_history, recent_changes
from portfolio_ops.loading import DataDir
from portfolio_ops.model import Change

CONFIG = "schema_version: 1\nallow_public: true\nvocabularies:\n  capabilities: [x]\n"
Found = tuple[str, str, str, str, str, bool]


def product(pid: str, status: str, next_action: str = "Ship it") -> str:
    lines = [f"  - id: {pid}", f"    name: {pid.title()}", f"    status: {status}"]
    if status == "active":
        lines.append(f"    next_action: {next_action}")
    if status in ("paused", "dormant"):
        lines += ["    status_reason: Later", "    review_by: 2026-10-01"]
    if status == "idea":
        lines.append("    capabilities: [x]")
    return "\n".join(lines) + "\n"


def products(*entries: str) -> str:
    return "products:\n" + "".join(entries)


def risks(*states: tuple[str, str]) -> str:
    body = "".join(
        f"  - id: {rid}\n    scope: portfolio\n    title: Something\n    severity: low\n"
        f"    applies_to: [all]\n    state: {state}\n"
        + ("    accepted_until: 2026-12-31\n" if state == "accepted" else "")
        for rid, state in states
    )
    return "risks:\n" + body


def _fail(file: str, message: str) -> None:
    raise AssertionError(f"unexpected warning about {file}: {message}")


def found(changes: tuple[Change, ...]) -> list[Found]:
    return [
        (c.kind, c.id, c.before, c.after, c.date.isoformat(), c.commit is None) for c in changes
    ]


def everything(repo: GitRepo) -> list[Found]:
    """The report's view: every change in history."""
    return found(read_history(Git(repo.root), DataDir(repo.root), TODAY, _fail).changes)


def recent(repo: GitRepo) -> list[Found]:
    """validate's view: the changes since the previous commit."""
    return found(recent_changes(Git(repo.root), DataDir(repo.root), TODAY, _fail))


@pytest.fixture
def repo(git_repo: GitRepo) -> GitRepo:
    git_repo.write("config.yaml", CONFIG)
    git_repo.write("decisions.md", "# Decisions\n")
    return git_repo


def commit_products(repo: GitRepo, day: dt.date, *entries: str) -> None:
    repo.write("products.yaml", products(*entries))
    repo.commit(day)


# ------------------------------------------------------------------ what counts as a change


def test_every_status_change_is_dated_by_its_commit(repo: GitRepo) -> None:
    commit_products(repo, dt.date(2026, 8, 1), product("alpha", "active"))
    commit_products(repo, dt.date(2026, 8, 10), product("alpha", "paused"))
    commit_products(repo, dt.date(2026, 8, 20), product("alpha", "active"))

    assert everything(repo) == [
        ("product", "alpha", "active", "paused", "2026-08-10", False),
        ("product", "alpha", "paused", "active", "2026-08-20", False),
    ]


def test_reordering_and_editing_other_fields_change_no_status(repo: GitRepo) -> None:
    commit_products(repo, dt.date(2026, 8, 1), product("alpha", "active"), product("beta", "idea"))
    commit_products(
        repo,
        dt.date(2026, 8, 10),
        product("beta", "idea"),
        product("alpha", "active", next_action="Something else"),
    )

    assert everything(repo) == []


def test_a_change_only_in_the_working_tree_is_dated_today(repo: GitRepo) -> None:
    commit_products(repo, dt.date(2026, 8, 1), product("alpha", "active"))
    repo.write("products.yaml", products(product("alpha", "paused")))

    assert everything(repo) == [("product", "alpha", "active", "paused", "2026-09-22", True)]


def test_a_new_product_is_not_a_change_and_a_typo_is_passed_over(repo: GitRepo) -> None:
    commit_products(repo, dt.date(2026, 8, 1), product("alpha", "active"))
    commit_products(repo, dt.date(2026, 8, 10), product("alpha", "actve"), product("beta", "idea"))
    commit_products(repo, dt.date(2026, 8, 20), product("alpha", "paused"), product("beta", "idea"))

    assert everything(repo) == [("product", "alpha", "active", "paused", "2026-08-20", False)]


def test_a_product_removed_and_added_back_with_another_status_changed(repo: GitRepo) -> None:
    commit_products(repo, dt.date(2026, 8, 1), product("alpha", "active"), product("beta", "idea"))
    commit_products(repo, dt.date(2026, 8, 10), product("beta", "idea"))
    commit_products(repo, dt.date(2026, 8, 20), product("beta", "idea"), product("alpha", "paused"))

    assert everything(repo) == [("product", "alpha", "active", "paused", "2026-08-20", False)]


def test_risk_state_changes_are_found_like_status_changes(repo: GitRepo) -> None:
    commit_products(repo, dt.date(2026, 8, 1), product("alpha", "active"))
    repo.write("risks.yaml", risks(("leak", "open")))
    repo.commit(dt.date(2026, 8, 5))
    repo.write("risks.yaml", risks(("leak", "accepted")))
    repo.commit(dt.date(2026, 8, 15))

    assert everything(repo) == [("risk", "leak", "open", "accepted", "2026-08-15", False)]


# ------------------------------------------------------------------ since the previous commit


def test_validate_looks_only_at_the_last_commit_on_a_clean_tree(repo: GitRepo) -> None:
    commit_products(repo, dt.date(2026, 8, 1), product("alpha", "active"))
    commit_products(repo, dt.date(2026, 8, 10), product("alpha", "paused"))
    commit_products(repo, dt.date(2026, 8, 20), product("alpha", "dormant"))

    assert recent(repo) == [("product", "alpha", "paused", "dormant", "2026-08-20", False)]


def test_validate_adds_what_is_not_committed_yet(repo: GitRepo) -> None:
    commit_products(repo, dt.date(2026, 8, 1), product("alpha", "active"))
    commit_products(repo, dt.date(2026, 8, 10), product("alpha", "paused"))
    repo.write("products.yaml", products(product("alpha", "active")))

    assert recent(repo) == [
        ("product", "alpha", "active", "paused", "2026-08-10", False),
        ("product", "alpha", "paused", "active", "2026-09-22", True),
    ]


def test_on_a_merge_validate_sees_every_commit_it_brings_in(repo: GitRepo) -> None:
    commit_products(
        repo, dt.date(2026, 8, 1), product("alpha", "active"), product("beta", "active")
    )
    repo.git("checkout", "--quiet", "-b", "work")
    commit_products(
        repo, dt.date(2026, 8, 5), product("alpha", "paused"), product("beta", "active")
    )
    commit_products(
        repo, dt.date(2026, 8, 6), product("alpha", "paused"), product("beta", "paused")
    )
    repo.git("checkout", "--quiet", "main")
    repo.write("decisions.md", "# Decisions\n\nMeanwhile on main.\n")
    repo.commit(dt.date(2026, 8, 7))
    repo.git("merge", "--quiet", "--no-ff", "-m", "Merge work", "work", date=dt.date(2026, 8, 9))

    assert recent(repo) == [
        ("product", "alpha", "active", "paused", "2026-08-05", False),
        ("product", "beta", "active", "paused", "2026-08-06", False),
    ]


def test_the_first_commit_changes_nothing_but_the_working_tree_can(repo: GitRepo) -> None:
    commit_products(repo, dt.date(2026, 8, 1), product("alpha", "active"))
    assert recent(repo) == []

    repo.write("products.yaml", products(product("alpha", "paused")))
    assert recent(repo) == [("product", "alpha", "active", "paused", "2026-09-22", True)]


def test_before_the_first_commit_there_is_nothing_to_compare(repo: GitRepo) -> None:
    repo.write("products.yaml", products(product("alpha", "active")))

    assert recent(repo) == []


def test_outside_a_repository_there_is_nothing_to_compare(tmp_path: Path) -> None:
    root = copy_fixture("valid", tmp_path / "plain")

    assert recent_changes(Git(root), DataDir(root), TODAY, _fail) == ()


def test_a_shallow_clone_without_the_previous_commit_cannot_tell(
    repo: GitRepo, tmp_path: Path
) -> None:
    commit_products(repo, dt.date(2026, 8, 1), product("alpha", "active"))
    commit_products(repo, dt.date(2026, 8, 10), product("alpha", "paused"))
    clone = repo.shallow_clone(tmp_path / "shallow")

    with pytest.raises(NoPreviousCommit):
        recent_changes(Git(clone), DataDir(clone), TODAY, _fail)


# ------------------------------------------------------------------ the command line


@pytest.fixture
def valid_repo(tmp_path: Path) -> GitRepo:
    """The valid fixture committed on 1 August; beta is paused."""
    repo = GitRepo(tmp_path / "data")
    copy_fixture("valid", repo.root / "portfolio")
    repo.commit(dt.date(2026, 8, 1))
    return repo


def _pause_to_dormant(repo: GitRepo, decision: str = "") -> Path:
    data = repo.root / "portfolio"
    products_file = data / "products.yaml"
    products_file.write_text(products_file.read_text().replace("status: paused", "status: dormant"))
    if decision:
        with (data / "decisions.md").open("a") as decisions:
            decisions.write(decision)
    repo.commit(dt.date(2026, 9, 20))
    return data


def test_validate_warns_about_a_change_without_a_decision_and_exits_0(valid_repo: GitRepo) -> None:
    data = _pause_to_dormant(valid_repo)

    run = run_cli(["validate", "--path", str(data)])

    assert run.code == 0
    assert run.lines == [
        (
            f"warning P1 {data.as_posix()}/products.yaml:13: product 'beta' changed status from "
            "paused to dormant on 2026-09-20, and no decision names it on that day — record the "
            "decision in decisions.md as '## 2026-09-20 · beta · status_change'"
        )
    ]
    assert run.err.endswith(": 0 errors, 1 warning\n")


def test_a_decision_on_the_day_of_the_change_satisfies_p1(valid_repo: GitRepo) -> None:
    data = _pause_to_dormant(
        valid_repo, "\n## 2026-09-20 · beta · status_change\nReleased; nothing planned.\n"
    )

    run = run_cli(["validate", "--path", str(data)])

    assert run.code == 0
    assert run.out == ""


def test_validate_on_a_shallow_clone_says_p1_was_not_checked(
    valid_repo: GitRepo, tmp_path: Path
) -> None:
    _pause_to_dormant(valid_repo)
    clone = valid_repo.shallow_clone(tmp_path / "shallow")

    run = run_cli(["validate", "--path", str(clone / "portfolio")])

    assert run.code == 0
    assert run.out == ""
    assert "note: P1 was not checked — this shallow clone does not have the previous commit" in (
        run.err
    )
    assert "fetch-depth: 0" in run.err


def test_the_report_lists_the_changes_of_its_week_without_a_decision(valid_repo: GitRepo) -> None:
    data = _pause_to_dormant(valid_repo)  # committed on 2026-09-20
    miss = (
        "warning P1 products.yaml:13: product 'beta' changed status from paused to dormant on "
        "2026-09-20, and no decision names it on that day"
    )

    this_week = run_cli(["report", "--path", str(data), "--today", "2026-09-22"])
    a_week_later = run_cli(["report", "--path", str(data), "--today", "2026-09-28"])

    assert this_week.code == 0, this_week.err
    assert miss in this_week.out
    assert a_week_later.code == 0, a_week_later.err
    assert miss not in a_week_later.out
    assert "Every status and state change since 2026-09-21 has its decision." in (
        a_week_later.lines
    )
