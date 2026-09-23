"""The sections of §7.4: Stale (N2), Escalations (N3), Overdue reviews (N4), the four that
R2 adds in phase 2 — Expired acceptances, Expired claims, Copy-paste debt (K2), Changes
without a decision (P1) — Focus (R3) and Health."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pytest

from helpers import FIXTURES
from portfolio_ops.model import Change
from portfolio_ops.report import ReportInput, sections, title, week_start
from portfolio_ops.report.render import render

Build = Callable[..., ReportInput]
PRODUCTS = (FIXTURES / "valid" / "products.yaml").read_text()
TWO_ACTIVE = PRODUCTS.replace(
    "    status: idea\n    capabilities: [maps]",
    "    status: active\n    next_action: Sketch the map | legend\n    capabilities: [maps]",
)
BASE_DECISIONS = "## 2026-07-01 · omega · status_change\n## 2026-08-03 · beta · status_change\n"


def decisions(*headings: str) -> dict[str, str]:
    return {"decisions.md": BASE_DECISIONS + "".join(f"{h}\nWhy.\n" for h in headings)}


# ------------------------------------------------------------------ N2


def test_n2_an_active_product_past_stale_days_is_stale(build: Build) -> None:
    data = build(
        {"products.yaml": TWO_ACTIVE}, clocks={"alpha": "2026-08-01", "delta": "2026-09-10"}
    )

    stale = sections.stale(data)

    assert stale.has_items
    assert (
        "| Alpha (`alpha`) | 52 days | Write the first draft of the sync protocol |" in stale.lines
    )
    assert not any("delta" in line for line in stale.lines)


def test_n2_a_clock_of_exactly_stale_days_is_not_stale(build: Build) -> None:
    data = build(clocks={"alpha": "2026-08-23"})  # 30 days

    assert not sections.stale(data).has_items


def test_n2_stale_products_are_listed_longest_first(build: Build) -> None:
    data = build(
        {"products.yaml": TWO_ACTIVE}, clocks={"alpha": "2026-08-01", "delta": "2026-07-01"}
    )

    rows = [line for line in sections.stale(data).lines if line.startswith("| ") and "`" in line]

    assert [row.split("`")[1] for row in rows] == ["delta", "alpha"]


def test_n2_markdown_in_a_next_action_cannot_break_the_table(build: Build) -> None:
    data = build({"products.yaml": TWO_ACTIVE}, clocks={"delta": "2026-07-01"})

    assert "| Delta (`delta`) | 83 days | Sketch the map \\| legend |" in sections.stale(data).lines


# ------------------------------------------------------------------ N3


def test_n3_deferrals_since_the_next_action_changed_reaching_the_limit_escalate(
    build: Build,
) -> None:
    data = build(
        decisions("## 2026-09-05 · alpha · defer", "## 2026-09-12 · alpha · defer"),
        clocks={"alpha": "2026-08-20"},
    )

    escalations = sections.escalations(data)

    assert escalations.has_items
    assert escalations.lines == (
        (
            "- Alpha (`alpha`): deferred 2 times since its next action last changed on "
            "2026-08-20 (deferral_limit 2) — split the action, pause or archive"
        ),
    )


def test_n3_deferrals_before_or_on_the_change_do_not_count(build: Build) -> None:
    data = build(
        decisions("## 2026-08-01 · alpha · defer", "## 2026-08-20 · alpha · defer"),
        clocks={"alpha": "2026-08-20"},
    )

    assert not sections.escalations(data).has_items


def test_n3_one_deferral_below_the_limit_is_no_escalation(build: Build) -> None:
    data = build(decisions("## 2026-09-12 · alpha · defer"), clocks={"alpha": "2026-08-20"})

    assert sections.escalations(data).lines == ("No escalations.",)


# ------------------------------------------------------------------ N4


def test_n4_a_review_date_before_today_is_overdue(build: Build) -> None:
    products = PRODUCTS.replace("review_by: 2026-10-01", "review_by: 2026-09-21")

    overdue = sections.overdue_reviews(build({"products.yaml": products}))

    assert overdue.has_items
    assert "| Beta (`beta`) | paused | 2026-09-21 |" in overdue.lines


def test_n4_a_review_date_of_today_is_not_yet_overdue(build: Build) -> None:
    products = PRODUCTS.replace("review_by: 2026-10-01", "review_by: 2026-09-22")

    assert not sections.overdue_reviews(build({"products.yaml": products})).has_items


# ------------------------------------------------------------------ R3


def test_r3_a_focus_recorded_in_the_last_seven_days_is_this_weeks_focus(build: Build) -> None:
    data = build(decisions("## 2026-09-16 · alpha · focus"), clocks={"alpha": "2026-09-01"})

    focus = sections.focus(data)

    assert not focus.has_items
    assert focus.lines[0] == "- This week: Alpha (`alpha`), recorded 2026-09-16."


def test_r3_no_focus_in_the_last_seven_days_is_an_item(build: Build) -> None:
    data = build(decisions("## 2026-09-15 · alpha · focus"), clocks={"alpha": "2026-09-01"})

    focus = sections.focus(data)

    assert focus.has_items
    assert focus.lines[0].startswith("- **No focus recorded this week.**")


@pytest.mark.parametrize(
    ("changed", "status", "verdict"),
    [
        ("2026-09-10", "active", "done"),
        ("2026-09-08", "active", "not done"),  # a change on the focus day is its start
        ("2026-09-01", "paused", "left active"),
    ],
)
def test_r3_last_weeks_focus_is_evaluated(
    build: Build, changed: str, status: str, verdict: str
) -> None:
    products = PRODUCTS
    if status == "paused":
        products = PRODUCTS.replace(
            "    status: active\n    next_action: Write the first draft of the sync protocol",
            "    status: paused\n    status_reason: Blocked\n    review_by: 2026-10-10",
        )
    data = build(
        {"products.yaml": products, **decisions("## 2026-09-08 · alpha · focus")},
        changed={"alpha": changed},
    )

    focus = sections.focus(data)

    assert focus.lines[1] == f"- Last week: Alpha (`alpha`), recorded 2026-09-08 — **{verdict}**."


def test_r3_the_later_heading_wins_when_two_focus_decisions_share_a_day(build: Build) -> None:
    data = build(
        {"products.yaml": TWO_ACTIVE}
        | decisions("## 2026-09-20 · alpha · focus", "## 2026-09-20 · delta · focus"),
    )

    assert sections.focus(data).lines[0] == "- This week: Delta (`delta`), recorded 2026-09-20."


def test_r3_without_earlier_focus_there_is_nothing_to_evaluate(build: Build) -> None:
    data = build(decisions())

    assert sections.focus(data).lines[1] == "- Last week: no earlier focus decision to evaluate."


# ------------------------------------------------------------------ Health


def test_health_reports_the_measures_of_section_10(build: Build) -> None:
    data = build(
        {"products.yaml": TWO_ACTIVE}
        | decisions(
            "## 2026-08-11 · alpha · focus",  # the fifth-latest: outside the last four
            "## 2026-08-18 · delta · focus",
            "## 2026-08-25 · alpha · focus",
            "## 2026-09-01 · delta · focus",
            "## 2026-09-08 · alpha · focus",  # alpha's action last changed 09-05: not done
        ),
        clocks={"alpha": "2026-08-01", "delta": "2026-09-10"},
        changed={"alpha": "2026-09-05", "delta": "2026-09-10"},
    )

    health = sections.health(data)

    assert not health.has_items
    assert health.lines == (
        "- Active products: 2 of wip_limit 4",
        "- Median clock of active products: 32 days",
        "- Stale products: 1",
        "- Focus completion: 3 of the last 4 evaluated focus decisions done",
        "- Kernels: 0 done, 1 extracted, 0 planned",
        "- Last commit touching the data: 2026-09-20",
    )


@pytest.mark.parametrize(
    ("clocks", "median"),
    [
        ({"alpha": "2026-09-21"}, "1 day"),
        ({"alpha": "2026-09-22"}, "0 days"),
        ({"alpha": "2026-09-21", "delta": "2026-09-20"}, "1.5 days"),
    ],
)
def test_the_median_clock_reads_as_days(build: Build, clocks: dict[str, str], median: str) -> None:
    products = PRODUCTS.replace(
        "    status: idea\n    capabilities: [maps]",
        "    status: active\n    next_action: Sketch the map\n    capabilities: [maps]",
    )

    lines = sections.health(build({"products.yaml": products}, clocks=clocks)).lines

    assert f"- Median clock of active products: {median}" in lines


def test_health_without_active_products_or_commits(build: Build) -> None:
    products = PRODUCTS.replace(
        "    status: active\n    next_action: Write the first draft of the sync protocol",
        "    status: dormant\n    status_reason: Done for now\n    review_by: 2026-12-01",
    )
    data = build({"products.yaml": products, **decisions()}, last_commit=None)

    lines = sections.health(data).lines

    assert "- Median clock of active products: no active products" in lines
    assert "- Focus completion: no focus decision old enough to evaluate yet" in lines
    assert "- Last commit touching the data: no commit yet" in lines


# ------------------------------------------------------------------ phase 2: B3, P2, K2, P1

RISKS = (FIXTURES / "valid" / "risks.yaml").read_text()
FINDINGS = (FIXTURES / "valid" / "findings.yaml").read_text()


def test_an_acceptance_that_has_ended_is_listed_as_open_again(build: Build) -> None:
    data = build({"risks.yaml": RISKS.replace("2026-12-31", "2026-09-21")})

    expired = sections.expired_acceptances(data)

    assert expired.has_items
    assert (
        "| Two offline edits can overwrite each other (`core-data-loss`) | Core (`core`) | high "
        "| 2026-09-21 |"
    ) in expired.lines


def test_an_acceptance_holds_through_its_last_day(build: Build) -> None:
    data = build({"risks.yaml": RISKS.replace("2026-12-31", "2026-09-22")})

    assert sections.expired_acceptances(data).lines == ("No expired acceptances.",)


def test_a_claim_past_its_expiry_is_listed_and_other_findings_are_not(build: Build) -> None:
    # delta-name (a name_check, TTL 90) expired too, but only claims are listed here.
    findings = FINDINGS.replace("2026-12-01", "2026-09-21").replace("2026-09-10", "2026-06-01")
    claims = sections.expired_claims(build({"findings.yaml": findings}))

    assert claims.has_items
    rows = [line for line in claims.lines if line.startswith("| ") and "`" in line]
    assert rows == [
        (
            "| Syncs a change in under a second on a phone (`alpha-sync-claim`) | Alpha "
            "(`alpha`) | website | 2026-09-21 |"
        )
    ]


def test_a_claim_holds_through_its_last_day(build: Build) -> None:
    data = build({"findings.yaml": FINDINGS.replace("2026-12-01", "2026-09-22")})

    assert sections.expired_claims(data).lines == ("No expired claims.",)


def test_k2_a_product_that_copies_a_kernel_is_copy_paste_debt(build: Build) -> None:
    products = PRODUCTS.replace(
        "    review_by: 2026-10-01\n",
        "    review_by: 2026-10-01\n    feeds_from:\n      - kernel: core\n        mode: copy\n",
    )
    debt = sections.copy_paste_debt(build({"products.yaml": products}))

    assert debt.has_items
    assert "| Beta (`beta`) | Core (`core`) | extracted, 1 of 2 package consumers |" in debt.lines


def test_k2_without_copies_there_is_no_debt(build: Build) -> None:
    debt = sections.copy_paste_debt(build())

    assert debt.lines == ("No copy-paste debt: no product carries a copy of a kernel.",)
    assert not debt.has_items


def change(ident: str, before: str, after: str, day: str) -> Change:
    return Change("product", ident, before, after, dt.date.fromisoformat(day), "c" * 40)


def test_p1_lists_the_changes_since_the_same_weekday_last_week(build: Build) -> None:
    data = build(
        changes=(
            change("gamma", "active", "dormant", "2026-09-14"),  # eight days ago: left out
            change("gamma", "dormant", "active", "2026-09-15"),  # seven days ago: listed
            change("beta", "active", "paused", "2026-09-22"),  # today: listed
        )
    )

    section = sections.changes_without_decision(data)
    listed = [line.split("'")[1] for line in section.lines if line.startswith("warning P1 ")]

    assert section.has_items
    assert section.lines[0].startswith("Status and state changes since 2026-09-15 ")
    assert listed == ["gamma", "beta"]


def test_p1_a_change_with_its_decision_is_not_listed(build: Build) -> None:
    data = build(
        decisions("## 2026-09-20 · beta · status_change"),
        changes=(change("beta", "active", "paused", "2026-09-20"),),
    )

    section = sections.changes_without_decision(data)

    assert not section.has_items
    assert section.lines == ("Every status and state change since 2026-09-15 has its decision.",)


def test_health_counts_the_kernels_by_state(build: Build) -> None:
    kernels = "kernels:\n  - id: core\n    name: Core\n  - id: spare\n    name: Spare\n"

    lines = sections.health(build({"kernels.yaml": kernels})).lines

    assert "- Kernels: 0 done, 1 extracted, 1 planned" in lines


# ------------------------------------------------------------------ the whole report


def test_the_report_has_items_for_a_section_with_items_or_a_missing_focus(build: Build) -> None:
    focus = decisions("## 2026-09-20 · alpha · focus")
    quiet = build(focus, clocks={"alpha": "2026-09-10"})
    no_focus = build(decisions(), clocks={"alpha": "2026-09-10"})
    expired = build(
        focus | {"risks.yaml": RISKS.replace("2026-12-31", "2026-09-01")},
        clocks={"alpha": "2026-09-10"},
    )

    assert not render(quiet).has_items
    assert render(no_focus).has_items
    assert render(expired).has_items


def test_the_week_starts_on_monday() -> None:
    assert week_start(dt.date(2026, 9, 27)) == dt.date(2026, 9, 21)
    assert title(dt.date(2026, 9, 21)) == "Weekly review — week of 2026-09-21"
