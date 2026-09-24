"""Section 9, Account activity (spec §7.4, §7.12): A1–A3 as the weekly report shows them.

Every repository name here is invented.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from helpers import TODAY
from portfolio_ops.model import Account, AccountRepository, AccountScan
from portfolio_ops.report import ReportInput, sections
from portfolio_ops.report.render import render
from portfolio_ops.rules.account import window_start

VALID = Path(__file__).parents[2] / "fixtures" / "valid"
PRODUCTS = (VALID / "products.yaml").read_text(encoding="utf-8")
CONFIG = (VALID / "config.yaml").read_text(encoding="utf-8")
IN_WINDOW = dt.date(2026, 9, 20)
Build = Callable[..., ReportInput]
Golden = Callable[[str, str], None]


def worked(
    name: str, day: dt.date | None = IN_WINDOW, *, private: bool = True
) -> AccountRepository:
    """A repository whose activity list says the owner last acted on ``day``."""
    return AccountRepository(
        f"example-owner/{name}", private, False, False, IN_WINDOW, "read", owner_active_on=day
    )


def scanned(
    *repositories: AccountRepository, hide_private: bool = False, unreadable: str = ""
) -> Account:
    scan = AccountScan(
        "example-owner",
        window_start(TODAY),
        TODAY,
        repositories,
        hide_private=hide_private,
        unreadable=unreadable,
    )
    return Account(scan=scan)


def with_repos(build: Build) -> ReportInput:
    """The valid fixture with repositories on alpha (active), beta (paused) and omega
    (archived), and one ignore pattern."""
    products = (
        PRODUCTS.replace(
            "  - id: alpha\n    name: Alpha\n",
            "  - id: alpha\n    name: Alpha\n    repos: [example-owner/alpha]\n",
        )
        .replace(
            "  - id: beta\n    name: Beta\n",
            "  - id: beta\n    name: Beta\n"
            "    repos: [example-owner/beta, example-owner/beta-old]\n",
        )
        .replace(
            "  - id: omega\n    name: Omega\n",
            "  - id: omega\n    name: Omega\n    repos: [example-owner/omega]\n",
        )
    )
    config = CONFIG + "account:\n  ignore: ['example-owner/*-notes']\n"
    return build({"products.yaml": products, "config.yaml": config})


def test_without_a_token_the_section_says_so_and_is_no_item(build: Build) -> None:
    section = sections.account_activity(build())

    assert not section.has_items
    assert section.lines == (
        (
            "The account was not scanned: PORTFOLIO_ACCOUNT_TOKEN is not set — the scan is "
            "optional; the portfolio-ops README says how to set it up."
        ),
    )


def test_a_scan_that_was_asked_for_and_failed_is_one_item(build: Build) -> None:
    data = replace(build(), account=Account(problem="GitHub rejected it — replace it", failed=True))

    section = sections.account_activity(data)

    assert section.has_items
    assert section.lines == ("- **The account was not scanned.** GitHub rejected it — replace it.",)


def test_work_that_is_all_in_the_plan_is_no_item(build: Build) -> None:
    quiet = [worked(name, None) for name in ("idle", "beta", "beta-old", "omega")]
    data = replace(
        with_repos(build),
        account=scanned(worked("alpha"), worked("core"), worked("recipe-notes"), *quiet),
    )

    section = sections.account_activity(data)

    assert not section.has_items
    assert section.lines == (
        "7 repositories of example-owner scanned; your activity since 2026-09-15 is in 3 of them.",
        "",
        (
            "Nothing outside the plan: every repository you worked on since 2026-09-15 belongs "
            "to an active product or a kernel, or is ignored."
        ),
    )


def test_a_report_with_account_items_matches_its_golden_file(build: Build, golden: Golden) -> None:
    unreadable = AccountRepository(
        "example-owner/weekend-jam", True, False, False, dt.date(2026, 9, 19), activity="unreadable"
    )
    account = scanned(
        worked("alpha"),
        worked("beta", dt.date(2026, 9, 18)),
        worked("omega", TODAY),
        worked("side-quest", dt.date(2026, 9, 16)),
        unreadable,
        worked("core"),
        worked("old-idea", dt.date(2026, 3, 1)),
        unreadable="the token cannot read the repositories' activity lists (HTTP 403; GitHub "
        "asks for contents=read)",
    )
    data = replace(with_repos(build), account=account)

    rendered = render(data)

    assert rendered.has_items
    golden("account.md", rendered.markdown)


def test_health_counts_the_work_and_what_is_outside_the_portfolio(build: Build) -> None:
    data = replace(
        with_repos(build),
        account=scanned(worked("alpha"), worked("side-quest"), worked("old", dt.date(2026, 9, 1))),
    )

    health = sections.health(data)

    assert (
        "- Account: 2 repositories worked on since 2026-09-15, 1 of them outside the portfolio"
        in health.lines
    )


def test_with_allow_public_no_private_repository_is_named_or_counted(build: Build) -> None:
    public = worked("open-tool", private=False)
    data = replace(
        with_repos(build), account=scanned(worked("hidden-work"), public, hide_private=True)
    )

    section = sections.account_activity(data)
    text = "\n".join(section.lines)

    assert "hidden-work" not in text
    assert "`example-owner/open-tool`" in text
    assert text.startswith("1 repository of example-owner scanned; your activity since ")
    assert text.endswith("allow_public is set, so private repositories are left out.")
