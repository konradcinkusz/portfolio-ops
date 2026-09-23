"""The dashboard reads the clock from git when it can, and says why when it cannot (P8)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from helpers import FIXTURES, GitRepo, run_cli


@pytest.fixture
def valid_repo(git_repo: GitRepo) -> GitRepo:
    for file in (FIXTURES / "valid").iterdir():
        git_repo.write(file.name, file.read_text(encoding="utf-8"))
    git_repo.commit(dt.date(2026, 8, 20))
    git_repo.write("products.yaml", git_repo.root.joinpath("products.yaml").read_text() + "\n")
    git_repo.commit(dt.date(2026, 9, 1), "reformat")
    return git_repo


def test_the_dashboard_reads_the_clocks_from_git(valid_repo: GitRepo) -> None:
    run = run_cli(["dashboard", "--path", str(valid_repo.root), "--today", "2026-09-22"])

    assert run.code == 0, run.err
    assert "note:" not in run.err
    # alpha's next action has stood still since the first commit; the reformat is no change.
    assert '33 days <span class="badge attention">stale</span>' in run.out
    assert 'since <time datetime="2026-08-20">2026-08-20</time>' in run.out
    assert 'The data was last committed on <time datetime="2026-09-01">' in run.out


def test_on_a_shallow_clone_the_dashboard_says_to_fetch_the_history(
    valid_repo: GitRepo, tmp_path: Path
) -> None:
    clone = valid_repo.shallow_clone(tmp_path / "shallow")

    run = run_cli(["dashboard", "--path", str(clone), "--today", "2026-09-22"])

    assert run.code == 0, run.err
    assert "note: the dashboard shows no clocks — this is a shallow clone" in run.err
    assert "fetch-depth: 0" in run.err
    assert '<p class="note">The clocks are not shown: this is a shallow clone' in run.out
