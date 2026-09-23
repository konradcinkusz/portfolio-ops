"""View inputs built from fixture data and synthetic clocks — no git needed here."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path

import pytest

from helpers import TODAY, load_valid, match_golden
from portfolio_ops.history import Clock
from portfolio_ops.rules import validate
from portfolio_ops.views.dashboard import DashboardInput

BuildView = Callable[..., DashboardInput]
Golden = Callable[[str, str], None]
GOLDEN = Path(__file__).parent / "golden"
NOT_IN_GIT = "the data directory is not inside a git repository"


@pytest.fixture
def golden(request: pytest.FixtureRequest) -> Golden:
    """``golden(name, text)``: the text equals golden/<name>, byte for byte."""

    def check(name: str, text: str) -> None:
        match_golden(GOLDEN / name, text, request.config.getoption("--update-golden"))

    return check


@pytest.fixture
def view(tmp_path: Path) -> BuildView:
    """``view(files, clocks=..., today=..., history=...)``: a DashboardInput over the valid
    fixture with ``files`` replaced.

    ``clocks`` maps each active product to the date its clock starts. Without ``history``
    there are no clocks, as outside a git repository. The data must validate: a view only
    ever shows valid data.
    """

    def make(
        files: dict[str, str] | None = None,
        *,
        clocks: dict[str, str] | None = None,
        today: dt.date = TODAY,
        last_commit: str | None = "2026-09-20",
        history: bool = True,
    ) -> DashboardInput:
        root = tmp_path / f"data-{len(list(tmp_path.iterdir()))}"
        portfolio = load_valid(root, files)
        errors = [d.render() for d in validate(portfolio, today) if d.severity == "error"]
        assert errors == []
        if not history:
            return DashboardInput(portfolio, today, None, None, NOT_IN_GIT)
        starts = {pid: dt.date.fromisoformat(start) for pid, start in (clocks or {}).items()}
        return DashboardInput(
            portfolio=portfolio,
            today=today,
            clocks={
                pid: Clock(
                    days=(today - start).days,
                    since=start,
                    next_action_since=start,
                    active_since=start,
                    last_defer=None,
                )
                for pid, start in starts.items()
            },
            last_data_commit=dt.date.fromisoformat(last_commit) if last_commit else None,
        )

    return make
