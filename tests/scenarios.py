"""Invented portfolios that the views' tests share, so the dashboard (V1) and the overview
(V3) are pinned against the same data. Every name, date and number here is invented.
"""

from __future__ import annotations

import datetime as dt

from helpers import FIXTURES, TODAY
from portfolio_ops.model import Account, AccountRepository, AccountScan
from portfolio_ops.rules.account import window_start

# One of each thing the views make stand out, on 2026-09-22: alpha is stale, beta's
# review is overdue, core-data-loss's acceptance has ended, alpha-crash is open and
# critical, alpha-sync-claim has expired, epsilon carries a copy of core, and no focus is
# recorded this week.
BUSY = {
    "products.yaml": """
        products:
          - id: alpha
            name: Alpha
            status: active
            next_action: Write the first draft of the sync protocol
            capabilities: [sync]
            feeds_from:
              - kernel: core
                mode: package

          - id: epsilon
            name: Epsilon
            status: active
            next_action: Measure how long a sync takes on a slow network
            capabilities: [sync, notes]
            feeds_from:
              - kernel: core
                mode: copy

          - id: beta
            name: Beta
            status: paused
            status_reason: Waiting until alpha ships
            review_by: 2026-09-01
            next_action: Sketch the sharing screen

          - id: gamma
            name: Gamma
            status: dormant
            status_reason: Released and stable
            review_by: 2026-12-01

          - id: delta
            name: Delta
            status: idea
            capabilities: [maps]

          - id: omega
            name: Omega
            status: archived
    """,
    "risks.yaml": """
        risks:
          - id: alpha-crash
            scope: alpha
            title: The first sync after an update can crash the app
            severity: critical
            applies_to: [store]
            state: open

          - id: alpha-licence
            scope: alpha
            title: A dependency's licence may forbid resale
            severity: medium
            applies_to: [store]
            state: open

          - id: core-data-loss
            scope: core
            title: Two offline edits can overwrite each other
            severity: high
            applies_to: [all]
            state: accepted
            accepted_until: 2026-09-01

          - id: portfolio-hosting
            scope: portfolio
            title: One hosting account serves every product
            severity: low
            applies_to: [all]
            state: closed
    """,
    "findings.yaml": """
        findings:
          - id: alpha-sync-claim
            subject: alpha
            type: claim
            result: Syncs a change in under a second on a phone
            evidence: Timed on two phones over the office network
            checked_on: 2026-06-01
            expires_on: 2026-09-01
            used_in: [website]

          - id: delta-name
            subject: delta
            type: name_check
            result: No product in the store uses the name
            checked_on: 2026-09-10
    """,
    "decisions.md": """
        # Decisions

        ## 2026-07-01 · omega · status_change
        Archived omega: the experiment answered its question.

        ## 2026-08-03 · beta · status_change
        Paused beta to make room for alpha.

        ## 2026-08-10 · core-data-loss · risk_accepted
        Accepted until the end of August: one user per device.

        ## 2026-09-08 · alpha · focus
        Focus of the week.
    """,
}


# BUSY with repositories: alpha's is worked on, beta (paused) was worked on this week, the
# kernel has one, and gamma lists one the account does not have.
WITH_REPOS = BUSY | {
    "products.yaml": BUSY["products.yaml"]
    .replace(
        "            name: Alpha\n",
        "            name: Alpha\n            repos: [example-owner/alpha]\n",
    )
    .replace(
        "            name: Beta\n",
        "            name: Beta\n            repos: [example-owner/beta]\n",
    )
    .replace(
        "            name: Gamma\n",
        "            name: Gamma\n            repos: [example-owner/gamma-renamed]\n",
    ),
    "config.yaml": (FIXTURES / "valid" / "config.yaml").read_text()
    + "account:\n  ignore: [example-owner/dotfiles]\n",
}


def repository(
    name: str,
    pushed: str | None,
    worked: str | None = None,
    *,
    fork: bool = False,
    archived: bool = False,
    unreadable: bool = False,
) -> AccountRepository:
    pushed_on = dt.date.fromisoformat(pushed) if pushed else None
    if unreadable:
        return AccountRepository(
            f"example-owner/{name}", True, fork, archived, pushed_on, "unreadable"
        )
    activity = "read" if pushed_on and pushed_on >= window_start(TODAY) else "unchecked"
    owner = dt.date.fromisoformat(worked) if worked else None
    return AccountRepository(
        f"example-owner/{name}", True, fork, archived, pushed_on, activity, owner
    )


SCANNED = Account(
    scan=AccountScan(
        "example-owner",
        window_start(TODAY),
        TODAY,
        (
            repository("alpha", "2026-09-21", "2026-09-21"),
            repository("beta", "2026-09-19", "2026-09-18"),
            repository("side-quest", "2026-09-20", "2026-09-20"),
            repository("weekend-jam", "2026-09-17", unreadable=True),
            repository("dotfiles", "2026-09-16", "2026-09-16"),
            repository("core", "2026-09-10"),
            repository("bot-only", "2026-09-21"),  # Dependabot pushed, the owner did not
            repository("old-fork", "2026-09-21", fork=True),
            repository("shelved", "2025-01-01", archived=True),
            repository("never-pushed", None),
        ),
        unreadable="the token cannot read the repositories' activity lists (HTTP 403)",
    )
)
