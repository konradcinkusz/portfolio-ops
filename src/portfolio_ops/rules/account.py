"""A1–A3: the account's repositories against the portfolio (spec §6, §7.12, ADR 0008).

Pure functions of the portfolio and a scan. account.py asks GitHub; these decide. A name
is compared without regard to case, as GitHub compares it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from fnmatch import fnmatchcase

from portfolio_ops.model import (
    STATUSES,
    AccountRepository,
    AccountScan,
    Kernel,
    Portfolio,
    Product,
    Term,
)

WINDOW_DAYS = 7  # from the same weekday last week up to today, like P1's changes (§7.4)


def window_start(today: dt.date) -> dt.date:
    """The first day of the window the owner's activity is judged in."""
    return today - dt.timedelta(days=WINDOW_DAYS)


@dataclass(frozen=True)
class Work:
    """A repository the owner worked on in the window, and the day of the latest work."""

    repository: AccountRepository
    on: dt.date


@dataclass(frozen=True)
class InactiveWork:
    """A2: work in a repository of a product that is not active."""

    product: Product
    repository: AccountRepository
    on: dt.date


@dataclass(frozen=True)
class Unknown:
    """A3: a listed repository of the account that the account does not have."""

    owner: Product | Kernel
    term: Term


def worked_on(repository: AccountRepository, scan: AccountScan) -> dt.date | None:
    """The day of the owner's latest work in the repository within the window, or None.

    Where the activity list was read, only the owner's own activity counts; where it could
    not be read, a push by anyone does (§7.12)."""
    if repository.activity == "read":
        day = repository.owner_active_on
    elif repository.activity == "unreadable":
        day = repository.pushed_on
    else:
        return None
    return day if day is not None and scan.since <= day <= scan.until else None


def listing(portfolio: Portfolio) -> dict[str, Product | Kernel]:
    """Each listed repository, by its name in lower case, with the product or kernel that
    lists it. S8 makes every repository appear once."""
    listed: dict[str, Product | Kernel] = {}
    owners: tuple[Product | Kernel, ...] = (*portfolio.products, *portfolio.kernels)
    for owner in owners:
        for term in owner.repos:
            listed.setdefault(term.value.lower(), owner)
    return listed


def ignored(portfolio: Portfolio, name: str) -> bool:
    """Whether an ``account.ignore`` pattern matches the repository."""
    return any(
        fnmatchcase(name.lower(), term.value.lower()) for term in portfolio.config.account_ignore
    )


def shown(scan: AccountScan) -> tuple[AccountRepository, ...]:
    """The repositories the report and the views may name: with ``allow_public``, not the
    private ones, because the report may then be public (§7.12)."""
    return tuple(r for r in scan.repositories if not (scan.hide_private and r.private))


def visibility(scan: AccountScan) -> tuple[int, int]:
    """How many of the repositories the report may name are public, and how many private."""
    private = sum(1 for repository in shown(scan) if repository.private)
    return len(shown(scan)) - private, private


def blind_spot(scan: AccountScan) -> str | None:
    """Why the scan holds no private repository, when the token sees none (§7.12)."""
    if scan.sees_private:
        return None
    return (
        f"the token does not list this private repository, {scan.left_out}, so every private "
        "repository of the account is missing from the scan — on GitHub, edit the token and "
        'set its repository access to "All repositories"'
    )


def _newest_first(work: Work | InactiveWork) -> tuple[int, str]:
    return -work.on.toordinal(), work.repository.name.lower()


def outside_portfolio(portfolio: Portfolio, scan: AccountScan) -> list[Work]:
    """A1: repositories the owner worked on in the window that no product or kernel lists
    and ``account.ignore`` does not match, the latest work first."""
    listed = listing(portfolio)
    found = []
    for repository in shown(scan):
        if repository.name.lower() in listed or ignored(portfolio, repository.name):
            continue
        day = worked_on(repository, scan)
        if day is not None:
            found.append(Work(repository, day))
    return sorted(found, key=_newest_first)


def inactive_work(portfolio: Portfolio, scan: AccountScan) -> list[InactiveWork]:
    """A2: work in the window in a repository of a product that is not active, the latest
    work first. A status outside the vocabulary is S3's to report, not A2's."""
    by_name = {r.name.lower(): r for r in scan.repositories}
    found = []
    for product in portfolio.products:
        if product.status == "active" or product.status not in STATUSES:
            continue
        for term in product.repos:
            repository = by_name.get(term.value.lower())
            day = worked_on(repository, scan) if repository is not None else None
            if repository is not None and day is not None:
                found.append(InactiveWork(product, repository, day))
    return sorted(found, key=_newest_first)


def unknown_repositories(portfolio: Portfolio, scan: AccountScan) -> list[Unknown]:
    """A3: listed repositories owned by the account's login that the account does not have
    — a typo, a rename or a deleted repository. Repositories of other owners are not
    scanned, so they are not judged."""
    names = {r.name.lower() for r in scan.repositories}
    if scan.left_out:
        names.add(scan.left_out.lower())
    login = scan.login.lower()
    found = []
    owners: tuple[Product | Kernel, ...] = (*portfolio.products, *portfolio.kernels)
    for owner in owners:
        for term in owner.repos:
            account = term.value.split("/", 1)[0].lower()
            if account == login and term.value.lower() not in names:
                found.append(Unknown(owner, term))
    return found
