"""Report inputs built from fixture data and synthetic clocks — no git needed here."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path

import pytest

from helpers import TODAY, copy_fixture, write_files
from portfolio_ops.history import Clock
from portfolio_ops.loading import DataDir, load_portfolio, read_config
from portfolio_ops.report import ReportInput

Build = Callable[..., ReportInput]
LONG_AGO = dt.date(2026, 1, 1)


def day(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


@pytest.fixture
def build(tmp_path: Path) -> Build:
    """``build(files, clocks=..., changed=...)``: a ReportInput over the valid fixture.

    ``clocks`` maps each active product to the date its clock starts; ``changed`` maps a
    product to the date its next action last changed (by default its clock start, or long
    ago for a product without a clock).
    """

    def make(
        files: dict[str, str] | None = None,
        *,
        clocks: dict[str, str] | None = None,
        changed: dict[str, str] | None = None,
        today: dt.date = TODAY,
        last_commit: str | None = "2026-09-20",
    ) -> ReportInput:
        root = copy_fixture("valid", tmp_path / f"data-{len(list(tmp_path.iterdir()))}")
        write_files(root, files or {})
        data = DataDir(root)
        loaded = load_portfolio(data, read_config(data))
        assert loaded.problems == ()
        portfolio = loaded.portfolio
        starts = {pid: day(start) for pid, start in (clocks or {}).items()}
        next_action_since = {p.id: starts.get(p.id, LONG_AGO) for p in portfolio.products if p.id}
        next_action_since |= {pid: day(when) for pid, when in (changed or {}).items()}
        return ReportInput(
            portfolio=portfolio,
            today=today,
            clocks={
                pid: Clock(
                    days=(today - start).days,
                    since=start,
                    next_action_since=next_action_since[pid],
                    active_since=start,
                    last_defer=None,
                )
                for pid, start in starts.items()
            },
            next_action_since=next_action_since,
            last_data_commit=day(last_commit) if last_commit else None,
        )

    return make
