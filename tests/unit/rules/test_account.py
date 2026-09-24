"""A1–A3 (spec §6, §7.12): pure functions of the portfolio and a scan. Names are invented."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from helpers import TODAY, load_valid
from portfolio_ops.model import AccountRepository, AccountScan, Portfolio
from portfolio_ops.rules.account import (
    inactive_work,
    outside_portfolio,
    unknown_repositories,
    window_start,
    worked_on,
)

VALID = Path(__file__).parents[2] / "fixtures" / "valid"
PRODUCTS = (VALID / "products.yaml").read_text(encoding="utf-8")
CONFIG = (VALID / "config.yaml").read_text(encoding="utf-8")
IN_WINDOW = dt.date(2026, 9, 20)
BEFORE = dt.date(2026, 9, 1)


def worked(name: str, day: dt.date = IN_WINDOW, *, private: bool = True) -> AccountRepository:
    """A repository whose owner acted on ``day``, as read from its activity list."""
    return AccountRepository(
        f"example-owner/{name}", private, False, False, day, activity="read", owner_active_on=day
    )


def the_scan(*repositories: AccountRepository, hide_private: bool = False) -> AccountScan:
    return AccountScan(
        "example-owner",
        window_start(TODAY),
        TODAY,
        repositories,
        left_out="example-owner/portfolio-data",
        hide_private=hide_private,
    )


def portfolio(tmp_path: Path, **repos: str) -> Portfolio:
    """The valid fixture, with ``repos`` added to the products named by keyword."""
    products = PRODUCTS
    for pid, listed in repos.items():
        entry = f"  - id: {pid}\n    name: {pid.title()}\n"
        assert entry in products
        products = products.replace(entry, f"{entry}    repos: {listed}\n")
    config = CONFIG + "account:\n  ignore: [example-owner/dotfiles, 'example-owner/*-notes']\n"
    return load_valid(tmp_path / "data", {"products.yaml": products, "config.yaml": config})


# ------------------------------------------------------------------ the window


def test_the_window_runs_from_the_same_weekday_last_week_up_to_today() -> None:
    assert window_start(TODAY) == dt.date(2026, 9, 15)
    assert TODAY.weekday() == window_start(TODAY).weekday()


def test_only_the_owners_activity_counts_where_the_activity_list_was_read() -> None:
    scan = the_scan()
    bot_only = AccountRepository(
        "example-owner/a", True, False, False, IN_WINDOW, activity="read", owner_active_on=None
    )
    earlier = AccountRepository(
        "example-owner/b", True, False, False, IN_WINDOW, activity="read", owner_active_on=BEFORE
    )
    unreadable = AccountRepository(
        "example-owner/c", True, False, False, IN_WINDOW, activity="unreadable"
    )
    unchecked = AccountRepository("example-owner/d", True, False, False, IN_WINDOW)

    assert worked_on(worked("x"), scan) == IN_WINDOW
    assert worked_on(bot_only, scan) is None
    assert worked_on(earlier, scan) is None
    assert worked_on(unreadable, scan) == IN_WINDOW  # a push by anyone counts
    assert worked_on(unchecked, scan) is None
    assert worked_on(worked("first", window_start(TODAY)), scan) == window_start(TODAY)
    assert worked_on(worked("today", TODAY), scan) == TODAY


# ------------------------------------------------------------------ A1


def test_a1_lists_work_outside_the_portfolio_the_latest_first(tmp_path: Path) -> None:
    data = portfolio(tmp_path, alpha="[example-owner/alpha]")
    scan = the_scan(
        worked("side-quest", dt.date(2026, 9, 16)),
        worked("alpha"),  # listed by alpha
        worked("Dotfiles"),  # ignored, whatever the case
        worked("recipe-notes"),  # ignored by a pattern
        worked("late-night", TODAY),
        worked("old", BEFORE),  # not in the window
    )

    found = outside_portfolio(data, scan)

    assert [(w.repository.name, w.on) for w in found] == [
        ("example-owner/late-night", TODAY),
        ("example-owner/side-quest", dt.date(2026, 9, 16)),
    ]


def test_a1_treats_a_kernels_repository_as_in_the_portfolio(tmp_path: Path) -> None:
    data = portfolio(tmp_path)  # the valid fixture's kernel lists example-owner/core

    assert outside_portfolio(data, the_scan(worked("CORE"))) == []


def test_a1_names_no_private_repository_when_the_data_may_be_public(tmp_path: Path) -> None:
    data = portfolio(tmp_path)
    scan = the_scan(worked("secret"), worked("open", private=False), hide_private=True)

    assert [w.repository.name for w in outside_portfolio(data, scan)] == ["example-owner/open"]


# ------------------------------------------------------------------ A2


def test_a2_lists_work_on_products_that_are_not_active(tmp_path: Path) -> None:
    data = portfolio(
        tmp_path,
        alpha="[example-owner/alpha]",  # active: not A2
        beta="[example-owner/beta]",  # paused
        delta="[example-owner/delta]",  # idea
        omega="[Example-Owner/Omega]",  # archived, listed in another case
        gamma="[example-owner/gamma]",  # dormant, but no work this week
    )
    scan = the_scan(
        worked("alpha"),
        worked("beta", dt.date(2026, 9, 18)),
        worked("delta"),
        worked("omega", TODAY),
        worked("gamma", BEFORE),
    )

    found = inactive_work(data, scan)

    assert [(w.product.id, w.product.status, w.repository.name, w.on) for w in found] == [
        ("omega", "archived", "example-owner/omega", TODAY),
        ("delta", "idea", "example-owner/delta", IN_WINDOW),
        ("beta", "paused", "example-owner/beta", dt.date(2026, 9, 18)),
    ]


def test_a2_is_not_about_kernels_or_repositories_the_scan_does_not_have(tmp_path: Path) -> None:
    data = portfolio(tmp_path, beta="[example-owner/elsewhere]")

    assert inactive_work(data, the_scan(worked("core"))) == []


# ------------------------------------------------------------------ A3


def test_a3_lists_listed_repositories_the_account_does_not_have(tmp_path: Path) -> None:
    data = portfolio(
        tmp_path,
        alpha="[example-owner/alpha, example-owner/alpha-old-name]",
        beta="[another-owner/beta]",  # another owner's repository is not scanned
        gamma="[example-owner/portfolio-data]",  # the data repository, left out on purpose
    )
    scan = the_scan(worked("ALPHA"), worked("core"))

    found = unknown_repositories(data, scan)

    assert [(u.owner.id, u.term.value, u.term.line) for u in found] == [
        ("alpha", "example-owner/alpha-old-name", 4),
    ]


def test_a3_checks_the_kernels_too(tmp_path: Path) -> None:
    data = portfolio(tmp_path)

    found = unknown_repositories(data, the_scan())

    assert [(u.owner.id, u.term.value) for u in found] == [("core", "example-owner/core")]
