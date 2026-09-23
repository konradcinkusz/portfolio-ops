"""The idea gate's reuse and overlap report (B5, B6): golden files, like the weekly report."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from helpers import FIXTURES, TODAY, load_valid
from portfolio_ops.model import Portfolio
from portfolio_ops.report.overlap import render_idea_gate
from portfolio_ops.rules.gates import idea_gate, run_idea_gate

Golden = Callable[[str, str], None]
PRODUCTS = (FIXTURES / "valid" / "products.yaml").read_text()
DECISIONS = (FIXTURES / "valid" / "decisions.md").read_text()
# delta, the idea, wants sync and notes; zeta, another idea, wants notes and maps.
OVERLAPPING = PRODUCTS.replace("capabilities: [maps]", "capabilities: [sync, notes]") + (
    "\n  - id: zeta\n    name: Zeta | the other\n    status: idea\n"
    "    capabilities: [notes, maps]\n"
)


def render(portfolio: Portfolio) -> str:
    delta = portfolio.product("delta")
    assert delta is not None
    the_gate = idea_gate(portfolio, delta, TODAY)
    return render_idea_gate(the_gate, run_idea_gate(the_gate), "")


def test_a_failed_idea_gate_matches_its_golden_file(golden: Golden, tmp_path: Path) -> None:
    text = render(load_valid(tmp_path / "data", {"products.yaml": OVERLAPPING}))

    assert "**Failed.**" in text
    golden("idea-gate-failed.md", text)


def test_an_admitted_idea_passes_and_names_the_decision(golden: Golden, tmp_path: Path) -> None:
    decisions = (
        DECISIONS + "\n## 2026-09-20 · delta · admit\nDelta syncs notes; alpha never will.\n"
    )
    portfolio = load_valid(
        tmp_path / "data", {"products.yaml": OVERLAPPING, "decisions.md": decisions}
    )

    golden("idea-gate-admitted.md", render(portfolio))


def test_an_idea_that_overlaps_nothing_says_so(tmp_path: Path) -> None:
    text = render(load_valid(tmp_path / "data"))

    assert "None: no product that is not archived shares a capability with the idea." in text
    assert "None: no kernel shares a capability with the idea." in text
    assert text.endswith("**Passed.** No single product shares half of the idea's capabilities.\n")
