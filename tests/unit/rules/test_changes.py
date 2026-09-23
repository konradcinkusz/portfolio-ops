"""P1 (spec §8.4): each status and state change is named by a decision on its day, and
products move only along §5. The changes are given; finding them in git is tested in
tests/integration/test_changes.py.

The valid fixture's decisions: omega status_change on 2026-07-01, beta status_change on
2026-08-03, alpha focus on 2026-09-15. Status lines: alpha 4, beta 13, gamma 19, delta 25,
omega 30; state lines: alpha-licence 7, core-data-loss 14.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from helpers import load_valid
from portfolio_ops.model import Change, Portfolio
from portfolio_ops.rules.changes import TRANSITIONS, check_changes, decision_type


def product(ident: str, before: str, after: str, day: str) -> Change:
    return Change("product", ident, before, after, dt.date.fromisoformat(day), "0" * 40)


def risk(ident: str, before: str, after: str, day: str) -> Change:
    return Change("risk", ident, before, after, dt.date.fromisoformat(day), None)


@pytest.fixture
def portfolio(tmp_path: Path) -> Portfolio:
    return load_valid(tmp_path / "data")


def lines(portfolio: Portfolio, *changes: Change) -> list[str]:
    return [d.render() for d in check_changes(portfolio, changes)]


def test_a_change_named_by_a_decision_on_its_day_is_fine(portfolio: Portfolio) -> None:
    assert lines(portfolio, product("beta", "active", "paused", "2026-08-03")) == []


def test_a_change_without_a_decision_on_its_day_is_a_warning(portfolio: Portfolio) -> None:
    assert lines(portfolio, product("beta", "active", "paused", "2026-08-04")) == [
        (
            "warning P1 products.yaml:13: product 'beta' changed status from active to paused on "
            "2026-08-04, and no decision names it on that day — record the decision in "
            "decisions.md as '## 2026-08-04 · beta · status_change'"
        )
    ]


def test_a_decision_on_that_day_about_another_id_does_not_count(portfolio: Portfolio) -> None:
    assert len(lines(portfolio, product("gamma", "active", "dormant", "2026-08-03"))) == 1


def test_an_archived_product_comes_back_only_through_admit(portfolio: Portfolio) -> None:
    assert lines(portfolio, product("omega", "archived", "active", "2026-07-01")) == [
        (
            "warning P1 products.yaml:30: product 'omega' changed status from archived to active "
            "on 2026-07-01 without an admit decision — an archived product comes back only "
            "through admit: record '## 2026-07-01 · omega · admit'"
        )
    ]


def test_a_transition_outside_the_lifecycle_is_a_warning_even_with_a_decision(
    portfolio: Portfolio,
) -> None:
    assert lines(portfolio, product("beta", "dormant", "paused", "2026-08-03")) == [
        (
            "warning P1 products.yaml:13: product 'beta' changed status from dormant to paused on "
            "2026-08-03, a transition the product lifecycle does not have — from dormant a "
            "product moves to active or archived"
        )
    ]


def test_without_a_decision_a_bad_transition_gives_both_warnings(portfolio: Portfolio) -> None:
    found = lines(portfolio, product("delta", "idea", "paused", "2026-09-01"))

    assert [line.split(" — ")[0].rsplit(", ", 1)[-1] for line in found] == [
        "and no decision names it on that day",
        "a transition the product lifecycle does not have",
    ]


def test_a_risk_state_change_needs_a_decision_too(portfolio: Portfolio) -> None:
    assert lines(portfolio, risk("core-data-loss", "open", "accepted", "2026-09-10")) == [
        (
            "warning P1 risks.yaml:14: risk 'core-data-loss' changed state from open to accepted "
            "on 2026-09-10, and no decision names it on that day — record the decision in "
            "decisions.md as '## 2026-09-10 · core-data-loss · risk_accepted'"
        )
    ]


def test_risk_states_have_no_lifecycle_to_break(portfolio: Portfolio) -> None:
    # Reopening a closed risk is allowed; it only needs its decision.
    (line,) = lines(portfolio, risk("alpha-licence", "closed", "open", "2026-09-10"))

    assert "no decision names it on that day" in line
    assert line.endswith("'## 2026-09-10 · alpha-licence · status_change'")


def test_an_entity_that_no_longer_exists_has_no_line(portfolio: Portfolio) -> None:
    (line,) = lines(portfolio, product("ghost", "active", "paused", "2026-09-01"))

    assert line.startswith("warning P1 products.yaml: product 'ghost' changed status")


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (product("x", "idea", "active", "2026-09-01"), "admit"),
        (product("x", "archived", "active", "2026-09-01"), "admit"),
        (product("x", "active", "paused", "2026-09-01"), "status_change"),
        (product("x", "paused", "active", "2026-09-01"), "status_change"),
        (risk("x", "open", "accepted", "2026-09-01"), "risk_accepted"),
        (risk("x", "accepted", "closed", "2026-09-01"), "status_change"),
    ],
)
def test_the_suggested_decision_type(change: Change, expected: str) -> None:
    assert decision_type(change) == expected


def test_the_transitions_are_those_of_section_5() -> None:
    assert TRANSITIONS == {
        "idea": ("active", "archived"),
        "active": ("paused", "dormant", "archived"),
        "paused": ("active", "dormant", "archived"),
        "dormant": ("active", "archived"),
        "archived": ("active",),
    }
