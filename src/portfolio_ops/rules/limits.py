"""Limit rules L1 and L2 (spec §6, §8.1): how much may be in progress at once."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

from portfolio_ops.model import CONFIG_FILE, PRODUCTS_FILE, Diagnostic, Portfolio
from portfolio_ops.rules import rule


@rule("L1", "at most wip_limit products are active")
def check_wip_limit(portfolio: Portfolio, today: dt.date) -> Iterator[Diagnostic]:
    limit = portfolio.config.thresholds.wip_limit
    active = [p for p in portfolio.products if p.status == "active"]
    if len(active) <= limit:
        return
    names = ", ".join(p.id or f"line {p.loc.line}" for p in active)
    first_over = active[limit]
    yield Diagnostic(
        "error",
        "L1",
        PRODUCTS_FILE,
        first_over.loc.at("status"),
        f"{len(active)} products are active but wip_limit is {limit}: {names} — keep at most "
        f"{limit} of them active and move the rest to paused or dormant with a review_by",
    )


@rule("L2", "wip_limit is no more than stale_days / 7 × actions_per_week")
def check_pressure_arithmetic(portfolio: Portfolio, today: dt.date) -> Iterator[Diagnostic]:
    thresholds = portfolio.config.thresholds
    capacity = thresholds.stale_days / 7 * thresholds.actions_per_week
    if thresholds.wip_limit <= capacity:
        return
    yield Diagnostic(
        "warning",
        "L2",
        CONFIG_FILE,
        portfolio.config.loc.at("thresholds", "wip_limit"),
        f"wip_limit {thresholds.wip_limit} exceeds {thresholds.stale_days} / 7 × "
        f"{thresholds.actions_per_week:g} = {capacity:.1f} — the weekly report will flag most "
        "active products",
    )
