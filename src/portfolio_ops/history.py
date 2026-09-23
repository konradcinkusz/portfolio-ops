"""What the engine reads from git: the clock (N1, spec §7.2) and the changes P1 judges.

The clock is derived from git, not from a hand-edited timestamp (spec §8.2, ADR 0003).
For each active product it is today minus the latest of three dates:

* when ``next_action`` changed to its current value,
* when the product last became ``active``,
* its latest ``defer`` decision.

The first two are read from the history of products.yaml. Versions are compared per
product id *after parsing*, so reordering products, reformatting the file, comments and
edits to other fields never reset a clock. The working tree is the newest version and is
dated today: an uncommitted change counts as a change made today.

The changes P1 judges (spec §8.4, ADR 0005) are read the same way, from products.yaml
and risks.yaml: every change of a product's status or a risk's state between two
consecutive versions, dated by the commit whose version made it. ``report`` reads all of
history; ``validate`` only what changed since the previous commit.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from portfolio_ops.errors import EnvironmentProblem
from portfolio_ops.git import Git
from portfolio_ops.loading import DataDir, product_values, risk_states
from portfolio_ops.model import (
    PRODUCTS_FILE,
    RISK_STATES,
    RISKS_FILE,
    STATUSES,
    Change,
    Portfolio,
)

_STATUS, _NEXT_ACTION = 0, 1

Warn = Callable[[str, str], None]  # the data file concerned, and the message
Parse = Callable[[str], dict[str, Any] | None]


@dataclass(frozen=True)
class Version:
    """One version of a data file: its values per id, and when it was made."""

    commit: str | None  # None: the working tree
    date: dt.date
    values: Mapping[str, Any]


@dataclass(frozen=True)
class _Tracked:
    """A value P1 follows through the versions of a file."""

    file: str
    kind: Literal["product", "risk"]
    vocabulary: tuple[str, ...]
    parse: Parse
    pick: Callable[[Any], Any]


_PRODUCTS = _Tracked(
    PRODUCTS_FILE, "product", STATUSES, product_values, lambda values: values[_STATUS]
)
_RISKS = _Tracked(RISKS_FILE, "risk", RISK_STATES, risk_states, lambda state: state)


@dataclass(frozen=True)
class History:
    """What the report needs from git: per product, when its values last changed, and the
    status and state changes P1 judges."""

    next_action_since: Mapping[str, dt.date]  # every product in the working tree
    active_since: Mapping[str, dt.date]  # products whose status is active now
    last_data_commit: dt.date | None  # the last commit touching the data directory
    changes: tuple[Change, ...] = ()  # every status and state change, oldest first


@dataclass(frozen=True)
class Clock:
    days: int
    since: dt.date  # the latest of the three dates
    next_action_since: dt.date
    active_since: dt.date
    last_defer: dt.date | None


class NoPreviousCommit(Exception):
    """A shallow clone without the previous commit: what changed cannot be told."""


def read_history(git: Git, data: DataDir, today: dt.date, warn: Warn) -> History:
    """Read the history of products.yaml and risks.yaml. Exits 2 without a full history."""
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
    current = product_values(data.read_text(PRODUCTS_FILE)) or {}
    products = _committed(git, _PRODUCTS, warn)
    versions = [(version.date, version.values) for version in products]
    next_action_since = {}
    active_since = {}
    for product_id, values in current.items():
        next_action_since[product_id] = _run_start(
            product_id, _NEXT_ACTION, values, versions, today
        )
        if values[_STATUS] == "active":
            active_since[product_id] = _run_start(product_id, _STATUS, values, versions, today)
    risks = _committed(git, _RISKS, warn)
    changes = [
        *_changes(_PRODUCTS, [*reversed(products), _working_tree(data, _PRODUCTS, today)]),
        *_changes(_RISKS, [*reversed(risks), _working_tree(data, _RISKS, today)]),
    ]
    return History(
        next_action_since,
        active_since,
        git.last_commit("."),
        tuple(sorted(changes, key=lambda c: (c.date, c.kind, c.id))),
    )


def recent_changes(git: Git, data: DataDir, today: dt.date, warn: Warn) -> tuple[Change, ...]:
    """The changes since the previous commit (P1 in ``validate``): those in the working tree,
    dated today, and those in the commits HEAD brings in over its first parent — one
    commit, or everything a merge brings in — each dated by its commit.

    Empty outside a git work tree and before the first commit. Raises NoPreviousCommit on
    a shallow clone that lacks the previous commit.
    """
    if not git.inside_work_tree() or git.revision("HEAD") is None:
        return ()
    base = git.revision("HEAD~1")
    if base is None and git.is_shallow():
        raise NoPreviousCommit
    found: list[Change] = []
    for tracked in (_PRODUCTS, _RISKS):
        versions: list[Version] = []
        if base is not None:
            (blob,) = git.blobs([f"{base}:{git.prefix()}{tracked.file}"])
            before = tracked.parse(blob.decode("utf-8", "replace")) if blob is not None else {}
            if before is not None:  # only the reference to compare with, so no date
                versions.append(Version(base, dt.date.min, before))
        in_range = _committed(git, tracked, warn, f"{base}..HEAD" if base else "HEAD")
        versions += [*reversed(in_range), _working_tree(data, tracked, today)]
        found += _changes(tracked, versions)
    return tuple(found)


def _committed(
    git: Git, tracked: _Tracked, warn: Warn, revisions: str | None = None
) -> list[Version]:
    """The versions of a data file in the commits that changed it, newest first. A version
    that does not parse is skipped with a warning."""
    commits = git.commits_touching(tracked.file, revisions)
    prefix = git.prefix()
    versions = []
    for commit, blob in zip(
        commits, git.blobs([f"{c.sha}:{prefix}{tracked.file}" for c in commits]), strict=True
    ):
        values = tracked.parse(blob.decode("utf-8", "replace")) if blob is not None else {}
        if values is None:
            warn(
                tracked.file,
                f"skipped the version of {tracked.file} in commit {commit.sha[:12]}: "
                "it does not parse",
            )
            continue
        versions.append(Version(commit.sha, commit.date, values))
    return versions


def _working_tree(data: DataDir, tracked: _Tracked, today: dt.date) -> Version:
    values = tracked.parse(data.read_text(tracked.file)) if data.exists(tracked.file) else {}
    return Version(None, today, values or {})


def _changes(tracked: _Tracked, versions: Sequence[Version]) -> list[Change]:
    """Each change of the tracked value per id between consecutive versions, oldest first.

    A value outside the vocabulary is a typo rather than a status and is passed over. An id
    missing from a version keeps its last value, so a product removed and added back with
    another status still shows the change; a new id is not a change.
    """
    last: dict[str, str] = {}
    found: list[Change] = []
    for version in versions:
        for ident, raw in version.values.items():
            value = tracked.pick(raw)
            if not isinstance(value, str) or value not in tracked.vocabulary:
                continue
            before = last.get(ident)
            if before is not None and before != value:
                found.append(
                    Change(tracked.kind, ident, before, value, version.date, version.commit)
                )
            last[ident] = value
    return found


def _normal(value: Any) -> Any:
    """Compare text by its words: re-wrapping a line is not a change."""
    return " ".join(value.split()) if isinstance(value, str) else value


def _run_start(
    product_id: str,
    field: int,
    current: tuple[Any, Any],
    versions: list[tuple[dt.date, Mapping[str, Any]]],
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
