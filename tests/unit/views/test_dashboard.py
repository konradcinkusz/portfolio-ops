"""V1: the dashboard — every panel, the page around them, and what the page must never do."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import re
from collections.abc import Callable

from helpers import FIXTURES
from portfolio_ops.views.dashboard import PANELS, PRIVATE_NOTE, DashboardInput, render_dashboard

BuildView = Callable[..., DashboardInput]
Golden = Callable[[str, str], None]

# One of each thing the dashboard makes stand out, on 2026-09-22: alpha is stale, beta's
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


def test_a_quiet_portfolio_matches_its_golden_page(view: BuildView, golden: Golden) -> None:
    page = render_dashboard(view(clocks={"alpha": "2026-09-15"}, today=dt.date(2026, 9, 20)))

    golden("dashboard-quiet.html", page)


def test_a_busy_portfolio_matches_its_golden_page(view: BuildView, golden: Golden) -> None:
    page = render_dashboard(view(BUSY, clocks={"alpha": "2026-08-01", "epsilon": "2026-09-14"}))

    golden("dashboard-busy.html", page)


def test_what_needs_attention_stands_out(view: BuildView) -> None:
    page = render_dashboard(view(BUSY, clocks={"alpha": "2026-08-01", "epsilon": "2026-09-14"}))

    for marker in (
        '52 days <span class="badge attention">stale</span>',
        '<span class="badge attention">overdue</span><span class="sub">21 days ago</span>',
        '<span class="badge attention">acceptance ended</span>',
        '<span class="badge danger">critical</span>',
        '<time datetime="2026-09-01">2026-09-01</time> <span class="badge attention">expired',
        '<span class="badge attention">copy</span>',
        '<div class="tile attention"><dt>Focus this week</dt><dd class="value">None</dd>',
    ):
        assert marker in page, marker
    assert "2 high or critical · 1 acceptance ended" in page


def test_without_history_the_page_says_why_it_has_no_clocks(view: BuildView) -> None:
    page = render_dashboard(view(history=False))

    assert (
        '<p class="note">The clocks are not shown: the data directory is not inside a git '
        "repository.</p>"
    ) in page
    assert '<dt>Stale</dt><dd class="value">—</dd>' in page
    assert "<footer><p>The git history was not read, so the page shows no clocks.</p>" in page


def test_every_value_from_the_data_is_escaped(view: BuildView) -> None:
    page = render_dashboard(
        view(
            {
                "products.yaml": """
                    products:
                      - id: alpha
                        name: <b>Alpha</b> & "Sons"
                        status: active
                        next_action: Remove <script>alert(1)</script> from the page
                """,
                "decisions.md": """
                    ## 2026-09-15 · alpha · focus
                    <img src=x onerror=alert(1)>
                """,
                "findings.yaml": "findings: []\n",
                "risks.yaml": "risks: []\n",
                "kernels.yaml": "kernels: []\n",
            }
        )
    )

    assert "<script>" not in page
    assert "<img" not in page
    assert "<b>Alpha" not in page
    assert "&lt;b&gt;Alpha&lt;/b&gt; &amp; &quot;Sons&quot;" in page
    assert "Remove &lt;script&gt;alert(1)&lt;/script&gt; from the page" in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page


def test_the_page_fetches_nothing_and_its_policy_allows_exactly_its_stylesheet(
    view: BuildView,
) -> None:
    page = render_dashboard(view(BUSY))

    style = re.search(r"<style>(.*?)</style>", page, re.DOTALL)
    policy = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', page)
    assert style is not None
    assert policy is not None
    digest = base64.b64encode(hashlib.sha256(style.group(1).encode("utf-8")).digest()).decode()
    assert policy.group(1) == (
        f"default-src 'none'; style-src 'sha256-{digest}'; base-uri 'none'; form-action 'none'"
    )
    for fetch in ("<script", "<link", "<img", "<iframe", " src=", "url(", "@import", "://"):
        assert fetch not in page, fetch
    assert page.index("Content-Security-Policy") < page.index("<style>")


def test_the_page_says_it_is_private_and_asks_not_to_be_indexed(view: BuildView) -> None:
    page = render_dashboard(view())

    assert '<meta name="robots" content="noindex, nofollow">' in page
    assert f'<p class="private" role="note">{PRIVATE_NOTE}</p>' in page
    assert "never publish it on GitHub Pages" in PRIVATE_NOTE


def test_the_panels_are_registered_in_a_fixed_order_and_linked_from_the_top(
    view: BuildView,
) -> None:
    page = render_dashboard(view())
    anchors = [PANELS[position](view()).anchor for position in sorted(PANELS)]

    assert sorted(PANELS) == list(range(1, 11))
    assert len(set(anchors)) == len(anchors)
    assert [page.index(f'<section id="{a}"') for a in anchors] == sorted(
        page.index(f'<section id="{a}"') for a in anchors
    )
    for anchor in anchors:
        assert f'<a href="#{anchor}">' in page


def test_only_the_ten_latest_decisions_are_shown_newest_first(view: BuildView) -> None:
    notes = "".join(
        f"## 2026-10-{day:02} · alpha · external\nNote {day}.\n" for day in range(1, 13)
    )
    decisions = (FIXTURES / "valid" / "decisions.md").read_text() + notes

    page = render_dashboard(view({"decisions.md": decisions}, today=dt.date(2026, 10, 15)))

    assert "The 10 latest of 15 decisions, newest first; the others are in decisions.md." in page
    shown = re.findall(r'<p class="text">Note (\d+)\.</p>', page)
    assert shown == [str(day) for day in range(12, 2, -1)]


def test_the_same_input_renders_the_same_bytes(view: BuildView) -> None:
    data = view(BUSY, clocks={"alpha": "2026-08-01"})

    assert render_dashboard(data) == render_dashboard(data)
