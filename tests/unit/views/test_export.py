"""V2: the context export — what it holds, in what order, and how it stays within its size."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from helpers import FIXTURES, TODAY, load_valid
from portfolio_ops.model import Portfolio
from portfolio_ops.views.export import DEFAULT_MAX_CHARS, TooSmall, render_export

Golden = Callable[[str, str], None]
DECISIONS = (FIXTURES / "valid" / "decisions.md").read_text()

RISKS = """
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
    applies_to: [store, website]
    state: open

  - id: core-data-loss
    scope: core
    title: Two offline edits can overwrite each other
    severity: high
    applies_to: [all]
    state: accepted
    accepted_until: 2026-09-01

  - id: core-slow
    scope: core
    title: A first sync of a large library takes minutes
    severity: medium
    applies_to: [all]
    state: accepted
    accepted_until: 2026-12-31

  - id: portfolio-hosting
    scope: portfolio
    title: One hosting account serves every product
    severity: low
    applies_to: [all]
    state: open

  - id: portfolio-backup
    scope: portfolio
    title: Backups were never restored once
    severity: critical
    applies_to: [all]
    state: closed
"""


def part(text: str, heading: str) -> list[str]:
    """The lines of one part of the export, between its heading and the next."""
    body = text.split(f"\n## {heading}\n\n", 1)[1].split("\n## ", 1)[0]
    return body.splitlines()


@pytest.fixture
def portfolio(tmp_path: Path) -> Callable[..., Portfolio]:
    def make(files: dict[str, str] | None = None) -> Portfolio:
        return load_valid(tmp_path / f"data-{len(list(tmp_path.iterdir()))}", files)

    return make


def test_the_export_of_the_valid_fixture_matches_its_golden_file(
    portfolio: Callable[..., Portfolio], golden: Golden
) -> None:
    exported = render_export(portfolio(), TODAY, DEFAULT_MAX_CHARS)

    golden("export.md", exported.markdown)
    assert (exported.decisions, exported.of) == (3, 3)


def test_the_parts_come_in_the_order_v2_lists_them(portfolio: Callable[..., Portfolio]) -> None:
    text = render_export(portfolio(), TODAY, DEFAULT_MAX_CHARS).markdown

    headings = re.findall(r"^## (.+)$", text, re.MULTILINE)
    assert headings == [
        "Active products",
        "Paused products",
        "Open risks of severity medium or higher",
        "Latest decisions",
        "Capability vocabulary",
    ]


def test_only_active_and_paused_products_are_exported(portfolio: Callable[..., Portfolio]) -> None:
    text = render_export(portfolio(), TODAY, DEFAULT_MAX_CHARS).markdown

    assert "- Alpha (`alpha`) — next action: Write the first draft of the sync protocol" in text
    assert "- Beta (`beta`) — paused: Waiting until alpha ships; review by 2026-10-01" in text
    for other in ("`gamma`", "`delta`", "(`omega`)"):
        assert other not in text


def test_only_open_risks_of_severity_medium_or_higher_are_exported(
    portfolio: Callable[..., Portfolio],
) -> None:
    text = render_export(portfolio({"risks.yaml": RISKS}), TODAY, DEFAULT_MAX_CHARS).markdown

    assert part(text, "Open risks of severity medium or higher") == [
        (
            "- critical: The first sync after an update can crash the app (`alpha-crash`) — "
            "about Alpha (`alpha`); applies to store"
        ),
        (
            "- high: Two offline edits can overwrite each other (`core-data-loss`) — about "
            "Core (`core`); applies to all; accepted until 2026-09-01, which has passed, so it "
            "counts as open"
        ),
        (
            "- medium: A dependency's licence may forbid resale (`alpha-licence`) — about "
            "Alpha (`alpha`); applies to store, website"
        ),
    ]


def test_the_newest_decisions_fill_what_the_limit_leaves(
    portfolio: Callable[..., Portfolio],
) -> None:
    # The export names its limit: 5000 has as many digits as the length of the export.
    full = render_export(portfolio(), TODAY, 5_000).markdown

    at_the_limit = render_export(portfolio(), TODAY, len(full))
    one_short = render_export(portfolio(), TODAY, len(full) - 1)

    assert (at_the_limit.decisions, len(at_the_limit.markdown)) == (3, len(full))
    assert (one_short.decisions, one_short.of) == (2, 3)
    assert len(one_short.markdown) <= len(full) - 1
    assert re.findall(r"^### (.+)$", one_short.markdown, re.MULTILINE) == [
        "2026-09-15 · alpha · focus",
        "2026-08-03 · beta · status_change",
    ]
    assert (
        "The 2 latest of 3 decisions, newest first. The rest are left out to stay within "
        f"{len(full) - 1} characters; decisions.md has them all."
    ) in one_short.markdown


@pytest.mark.parametrize("extra", [0, 1, 60, 150, 400, 1_000, 5_000])
def test_the_export_never_exceeds_its_limit(
    portfolio: Callable[..., Portfolio], extra: int
) -> None:
    notes = "".join(
        f"## 2026-09-{day:02} · alpha · external\nA note long enough to count, number {day}.\n"
        for day in range(1, 21)
    )
    data = portfolio({"decisions.md": DECISIONS + notes})
    with pytest.raises(TooSmall) as small:
        render_export(data, TODAY, 1)

    exported = render_export(data, TODAY, small.value.needed + extra)

    assert len(exported.markdown) <= small.value.needed + extra
    shown = re.findall(r"^### (\S+)", exported.markdown, re.MULTILINE)
    assert shown == sorted(shown, reverse=True)
    assert len(shown) == exported.decisions


def test_a_limit_below_the_fixed_parts_is_too_small(portfolio: Callable[..., Portfolio]) -> None:
    data = portfolio()

    with pytest.raises(TooSmall) as small:
        render_export(data, TODAY, 100)

    fitting = render_export(data, TODAY, small.value.needed)
    assert (fitting.decisions, len(fitting.markdown)) == (0, small.value.needed)
    assert (
        f"No decision fits within {small.value.needed} characters; decisions.md has all 3."
    ) in fitting.markdown
    with pytest.raises(TooSmall):
        render_export(data, TODAY, small.value.needed - 1)


def test_text_is_written_as_it_is_and_a_decision_keeps_its_line_breaks(
    portfolio: Callable[..., Portfolio],
) -> None:
    decisions = DECISIONS + "## 2026-09-20 · alpha · external\nFirst line.\n\n- a *list* item\n"
    products = (
        (FIXTURES / "valid" / "products.yaml")
        .read_text()
        .replace(
            "Write the first draft of the sync protocol", "Fix the `sync_all` *race* | [again]"
        )
    )

    text = render_export(
        portfolio({"decisions.md": decisions, "products.yaml": products}), TODAY, 12_000
    ).markdown

    assert "next action: Fix the `sync_all` *race* | [again]" in text
    assert "### 2026-09-20 · alpha · external\n\nFirst line.\n\n- a *list* item\n\n### " in text


def test_an_empty_portfolio_still_has_every_part(portfolio: Callable[..., Portfolio]) -> None:
    empty = portfolio(
        {
            "products.yaml": "products: []\n",
            "decisions.md": "# Decisions\n",
            "risks.yaml": "risks: []\n",
            "findings.yaml": "findings: []\n",
        }
    )

    text = render_export(empty, dt.date(2026, 9, 22), DEFAULT_MAX_CHARS).markdown

    assert "0 active, of at most 4 (wip_limit)." in text
    assert "No product is paused." in text
    assert "## Open risks of severity medium or higher\n\nNone." in text
    assert "No decision is recorded yet." in text
    assert text.endswith("## Capability vocabulary\n\nsync, maps, notes\n")
