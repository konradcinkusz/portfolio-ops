"""The weekly report (spec §7.4): sections registered as functions, rendered in order.

A section is a function from the report's input to a titled block of Markdown, and it is
registered under its position — the same registry pattern as the rules (P10). R2 fixes
the order; phase 2 added its four sections, and phase 4 the account's, by registering more
functions, not by editing the renderer.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from portfolio_ops.history import Clock
from portfolio_ops.model import NOT_SCANNED, Account, Change, Portfolio


@dataclass(frozen=True)
class WorkflowRun:
    """The GitHub Actions run that renders the report; its artifacts hold the dashboard."""

    url: str
    number: str


@dataclass(frozen=True)
class ReportInput:
    portfolio: Portfolio
    today: dt.date
    clocks: Mapping[str, Clock]  # N1, for every active product
    next_action_since: Mapping[str, dt.date]  # every product
    last_data_commit: dt.date | None
    changes: tuple[Change, ...] = ()  # P1: every status and state change in history
    account: Account = NOT_SCANNED  # A1–A3: the account scan, or why there is none
    run: WorkflowRun | None = None  # in GitHub Actions: the run, linked from the header
    overview: str | None = None  # in GitHub Actions: the overview's home page, when there is one


@dataclass(frozen=True)
class Section:
    title: str
    lines: tuple[str, ...]  # the Markdown body
    has_items: bool  # whether the section puts the report in "has items" (§7.4, R1)


SectionFunction = Callable[[ReportInput], Section]

SECTIONS: dict[int, SectionFunction] = {}


def section(position: int) -> Callable[[SectionFunction], SectionFunction]:
    """Register a report section at its position in the report (R2)."""

    def register(function: SectionFunction) -> SectionFunction:
        if position in SECTIONS:
            raise ValueError(f"report position {position} is registered twice")
        SECTIONS[position] = function
        return function

    return register


def week_start(today: dt.date) -> dt.date:
    """The Monday of the week that contains ``today``."""
    return today - dt.timedelta(days=today.weekday())


def title(today: dt.date) -> str:
    return f"Weekly review — week of {week_start(today).isoformat()}"


# The built-in sections register themselves when their module is imported.
from portfolio_ops.report import sections  # noqa: E402

__all__ = [
    "SECTIONS",
    "ReportInput",
    "Section",
    "SectionFunction",
    "WorkflowRun",
    "section",
    "sections",
    "title",
    "week_start",
]
