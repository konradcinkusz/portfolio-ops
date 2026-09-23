"""The clock (N1, spec §7.2): how long an active product has stood still.

The clock is derived from git, not from a hand-edited timestamp (spec §8.2, ADR 0003).
For each active product it is today minus the latest of three dates:

* when ``next_action`` changed to its current value,
* when the product last became ``active``,
* its latest ``defer`` decision.

The first two are read from the history of products.yaml. Versions are compared per
product id *after parsing*, so reordering products, reformatting the file, comments and
edits to other fields never reset a clock. The working tree is the newest version and is
dated today: an uncommitted change counts as a change made today.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from portfolio_ops.errors import EnvironmentProblem
from portfolio_ops.git import Git
from portfolio_ops.loading import product_values
from portfolio_ops.model import PRODUCTS_FILE, Portfolio

_STATUS, _NEXT_ACTION = 0, 1


@dataclass(frozen=True)
class History:
    """What the report needs from git: per product, when its values last changed."""

    next_action_since: Mapping[str, dt.date]  # every product in the working tree
    active_since: Mapping[str, dt.date]  # products whose status is active now
    last_data_commit: dt.date | None  # the last commit touching the data directory


@dataclass(frozen=True)
class Clock:
    days: int
    since: dt.date  # the latest of the three dates
    next_action_since: dt.date
    active_since: dt.date
    last_defer: dt.date | None


def read_history(
    git: Git, working_tree: str, today: dt.date, warn: Callable[[str], None]
) -> History:
    """Read the history of products.yaml. Exits 2 without a usable git history."""
    if not git.inside_work_tree():
        raise EnvironmentProblem(
            f"report reads the clock from git history, but {git.cwd} is not inside a git "
            "repository — run report in a clone of the data repository"
        )
    if git.is_shallow():
        raise EnvironmentProblem(
            "report needs the full git history, but this is a shallow clone — run "
            "'git fetch --unshallow', or set fetch-depth: 0 on actions/checkout"
        )
    current = product_values(working_tree) or {}
    commits = git.commits_touching(PRODUCTS_FILE)
    prefix = git.prefix()
    versions: list[tuple[dt.date, dict[str, tuple[Any, Any]]]] = []
    for commit, blob in zip(
        commits, git.blobs([f"{c.sha}:{prefix}{PRODUCTS_FILE}" for c in commits]), strict=True
    ):
        parsed = product_values(blob.decode("utf-8", "replace")) if blob is not None else {}
        if parsed is None:
            warn(
                f"skipped the version of {PRODUCTS_FILE} in commit {commit.sha[:12]}: "
                "it does not parse"
            )
            continue
        versions.append((commit.date, parsed))
    next_action_since = {}
    active_since = {}
    for product_id, values in current.items():
        next_action_since[product_id] = _run_start(
            product_id, _NEXT_ACTION, values, versions, today
        )
        if values[_STATUS] == "active":
            active_since[product_id] = _run_start(product_id, _STATUS, values, versions, today)
    return History(next_action_since, active_since, git.last_commit("."))


def _normal(value: Any) -> Any:
    """Compare text by its words: re-wrapping a line is not a change."""
    return " ".join(value.split()) if isinstance(value, str) else value


def _run_start(
    product_id: str,
    field: int,
    current: tuple[Any, Any],
    versions: list[tuple[dt.date, dict[str, tuple[Any, Any]]]],
    today: dt.date,
) -> dt.date:
    """The date of the commit that starts the most recent unbroken run of versions in
    which the field equals its current value; today if the working tree differs from
    the last commit or the product is in no commit yet."""
    wanted = _normal(current[field])
    start = today
    for date, values in versions:  # newest first
        if product_id not in values or _normal(values[product_id][field]) != wanted:
            break
        start = date
    return start


def clocks(portfolio: Portfolio, history: History, today: dt.date) -> dict[str, Clock]:
    """N1 for every active product."""
    result = {}
    for product in portfolio.products:
        if product.status != "active" or product.id is None:
            continue
        next_action = history.next_action_since.get(product.id, today)
        active = history.active_since.get(product.id, today)
        defers = [
            d.date
            for d in portfolio.parsed_decisions()
            if d.type == "defer" and d.ids == (product.id,) and d.date is not None
        ]
        last_defer = max(defers, default=None)
        since = max(next_action, active, last_defer or next_action)
        result[product.id] = Clock(
            days=max((today - since).days, 0),
            since=since,
            next_action_since=next_action,
            active_since=active,
            last_defer=last_defer,
        )
    return result
