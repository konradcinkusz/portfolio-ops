"""R2 (AC7): fixed sections in a fixed order, the same bytes for the same input.

The golden files under golden/ are the expected reports, byte for byte. After an
intended change to the report, regenerate them with ``pytest --update-golden`` and review
the diff like any other change.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable

import pytest

from helpers import FIXTURES, TODAY
from portfolio_ops.model import Change, Diagnostic
from portfolio_ops.report import ReportInput
from portfolio_ops.report.render import render, render_invalid

Build = Callable[..., ReportInput]
Golden = Callable[[str, str], None]
PRODUCTS = (FIXTURES / "valid" / "products.yaml").read_text()
SECTION_ORDER = [
    "Stale",
    "Escalations",
    "Overdue reviews",
    "Expired acceptances",
    "Expired claims",
    "Copy-paste debt",
    "Changes without a decision",
    "Focus",
    "Health",
]

BUSY_PRODUCTS = PRODUCTS.replace(
    "    status: idea\n    capabilities: [maps]",
    "    status: active\n    next_action: Sketch the map | legend\n    capabilities: [maps]",
).replace(
    "review_by: 2026-10-01",
    "review_by: 2026-09-01\n    feeds_from:\n      - kernel: core\n        mode: copy",
)
BUSY_RISKS = (FIXTURES / "valid" / "risks.yaml").read_text().replace("2026-12-31", "2026-09-01")
BUSY_FINDINGS = (
    (FIXTURES / "valid" / "findings.yaml").read_text().replace("2026-12-01", "2026-09-15")
)
BUSY_CHANGES = (
    Change("product", "beta", "active", "paused", dt.date(2026, 9, 20), "a" * 40),
    Change("product", "omega", "active", "archived", dt.date(2026, 7, 1), "b" * 40),
)
BUSY_DECISIONS = (
    "## 2026-07-01 · omega · status_change\nArchived.\n\n"
    "## 2026-08-03 · beta · status_change\nPaused.\n\n"
    "## 2026-09-05 · alpha · defer\nWaiting for a supplier.\n\n"
    "## 2026-09-08 · alpha · focus\nFocus of the week.\n\n"
    "## 2026-09-12 · alpha · defer\nStill waiting.\n"
)


@pytest.fixture
def busy(build: Build) -> ReportInput:
    """Every section has something: stale, escalated, overdue, an acceptance and a claim
    past their dates, a copied kernel, a change without its decision, no focus this week."""
    return build(
        {
            "products.yaml": BUSY_PRODUCTS,
            "risks.yaml": BUSY_RISKS,
            "findings.yaml": BUSY_FINDINGS,
            "decisions.md": BUSY_DECISIONS,
        },
        clocks={"alpha": "2026-09-12", "delta": "2026-07-01"},
        changed={"alpha": "2026-08-20"},
        changes=BUSY_CHANGES,
    )


@pytest.fixture
def quiet(build: Build) -> ReportInput:
    """Nothing to act on: the report has no items."""
    decisions = (FIXTURES / "valid" / "decisions.md").read_text()
    return build(
        {"decisions.md": decisions + "\n## 2026-09-21 · alpha · focus\nShip the draft.\n"},
        clocks={"alpha": "2026-09-10"},
    )


def test_a_report_with_items_matches_its_golden_file(golden: Golden, busy: ReportInput) -> None:
    rendered = render(busy)

    assert rendered.has_items
    assert rendered.title == "Weekly review — week of 2026-09-21"
    golden("busy.md", rendered.markdown)


def test_a_report_without_items_matches_its_golden_file(golden: Golden, quiet: ReportInput) -> None:
    rendered = render(quiet)

    assert not rendered.has_items
    golden("quiet.md", rendered.markdown)


def test_invalid_data_renders_only_the_validation_errors(golden: Golden) -> None:
    errors = [
        Diagnostic(
            "error",
            "S4",
            "products.yaml",
            14,
            "product 'alpha' is active but has no next_action — add next_action or change its "
            "status",
        ),
        Diagnostic("error", "S2", "risks.yaml", 3, "risk 'r1' has scope 'ghost', which is not…"),
    ]

    rendered = render_invalid(errors, "data", TODAY)

    assert rendered.has_items
    assert re.findall(r"^## (.+)$", rendered.markdown, re.MULTILINE) == ["Validation errors"]
    golden("invalid.md", rendered.markdown)


@pytest.mark.parametrize("scenario", ["busy", "quiet"])
def test_the_sections_come_in_the_order_of_section_7_4(
    request: pytest.FixtureRequest, scenario: str
) -> None:
    markdown = render(request.getfixturevalue(scenario)).markdown

    assert re.findall(r"^## (.+)$", markdown, re.MULTILINE) == SECTION_ORDER


def test_the_same_input_renders_the_same_bytes(busy: ReportInput) -> None:
    assert render(busy).markdown == render(busy).markdown
