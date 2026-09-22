"""R2 (AC7): fixed sections in a fixed order, the same bytes for the same input.

The golden files under golden/ are the expected reports, byte for byte. After an
intended change to the report, regenerate them with ``pytest --update-golden`` and review
the diff like any other change.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from helpers import FIXTURES, TODAY
from portfolio_ops.model import Diagnostic
from portfolio_ops.report import ReportInput
from portfolio_ops.report.render import render, render_invalid

Build = Callable[..., ReportInput]
GOLDEN = Path(__file__).parent / "golden"
PRODUCTS = (FIXTURES / "valid" / "products.yaml").read_text()
SECTION_ORDER = ["Stale", "Escalations", "Overdue reviews", "Focus", "Health"]

BUSY_PRODUCTS = PRODUCTS.replace(
    "    status: idea\n    capabilities: [maps]",
    "    status: active\n    next_action: Sketch the map | legend\n    capabilities: [maps]",
).replace("review_by: 2026-10-01", "review_by: 2026-09-01")
BUSY_DECISIONS = (
    "## 2026-07-01 · omega · status_change\nArchived.\n\n"
    "## 2026-08-03 · beta · status_change\nPaused.\n\n"
    "## 2026-09-05 · alpha · defer\nWaiting for a supplier.\n\n"
    "## 2026-09-08 · alpha · focus\nFocus of the week.\n\n"
    "## 2026-09-12 · alpha · defer\nStill waiting.\n"
)


def check_golden(request: pytest.FixtureRequest, name: str, text: str) -> None:
    path = GOLDEN / name
    if request.config.getoption("--update-golden"):
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    assert text == path.read_text(encoding="utf-8")


@pytest.fixture
def busy(build: Build) -> ReportInput:
    """Every section has something: stale, escalated, overdue, and no focus this week."""
    return build(
        {"products.yaml": BUSY_PRODUCTS, "decisions.md": BUSY_DECISIONS},
        clocks={"alpha": "2026-09-12", "delta": "2026-07-01"},
        changed={"alpha": "2026-08-20"},
    )


@pytest.fixture
def quiet(build: Build) -> ReportInput:
    """Nothing to act on: the report has no items."""
    decisions = (FIXTURES / "valid" / "decisions.md").read_text()
    return build(
        {"decisions.md": decisions + "\n## 2026-09-21 · alpha · focus\nShip the draft.\n"},
        clocks={"alpha": "2026-09-10"},
    )


def test_a_report_with_items_matches_its_golden_file(
    request: pytest.FixtureRequest, busy: ReportInput
) -> None:
    rendered = render(busy)

    assert rendered.has_items
    assert rendered.title == "Weekly review — week of 2026-09-21"
    check_golden(request, "busy.md", rendered.markdown)


def test_a_report_without_items_matches_its_golden_file(
    request: pytest.FixtureRequest, quiet: ReportInput
) -> None:
    rendered = render(quiet)

    assert not rendered.has_items
    check_golden(request, "quiet.md", rendered.markdown)


def test_invalid_data_renders_only_the_validation_errors(request: pytest.FixtureRequest) -> None:
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
    check_golden(request, "invalid.md", rendered.markdown)


@pytest.mark.parametrize("scenario", ["busy", "quiet"])
def test_the_sections_come_in_the_order_of_section_7_4(
    request: pytest.FixtureRequest, scenario: str
) -> None:
    markdown = render(request.getfixturevalue(scenario)).markdown

    assert re.findall(r"^## (.+)$", markdown, re.MULTILINE) == SECTION_ORDER


def test_the_same_input_renders_the_same_bytes(busy: ReportInput) -> None:
    assert render(busy).markdown == render(busy).markdown
