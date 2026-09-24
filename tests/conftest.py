"""Fixtures shared by every test.

The autouse fixture isolates git from the developer's own configuration — a global
``commit.gpgsign`` or hooks path would otherwise leak into the repositories the tests
create — and keeps a CI runner's GitHub variables, and a developer's account token, out of
every run, so no test reaches GitHub.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from helpers import GitRepo


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-golden",
        action="store_true",
        help="rewrite the golden report files from the current output",
    )


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    for name in (
        "GITHUB_ACTIONS",
        "GITHUB_TOKEN",
        "GITHUB_REPOSITORY",
        "GITHUB_API_URL",
        "PORTFOLIO_ACCOUNT_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def git_repo(tmp_path: Path) -> GitRepo:
    return GitRepo(tmp_path / "data")
