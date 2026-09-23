"""Values the model derives rather than stores: when a finding stops holding (P2) and whether
a risk's acceptance still holds (B3)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from helpers import TODAY, load_valid

FINDINGS = """
findings:
  - id: dated
    subject: alpha
    type: name_check
    result: The name is free
    checked_on: 2026-09-01
    expires_on: 2026-09-30

  - id: by-ttl
    subject: alpha
    type: name_check
    result: The name is free
    checked_on: 2026-09-01
"""


def test_expires_on_is_the_last_day_a_finding_holds_and_wins_over_a_ttl(tmp_path: Path) -> None:
    portfolio = load_valid(tmp_path / "data", {"findings.yaml": FINDINGS})
    dated, by_ttl = portfolio.findings

    # The valid fixture configures finding_ttl_days.name_check: 90.
    assert portfolio.config.expiry(dated) == dt.date(2026, 9, 30)
    assert portfolio.config.expiry(by_ttl) == dt.date(2026, 11, 30)


def test_a_finding_without_expires_on_or_a_ttl_has_no_expiry(tmp_path: Path) -> None:
    portfolio = load_valid(
        tmp_path / "data",
        {"findings.yaml": FINDINGS.replace("type: name_check", "type: claim")},
    )

    assert portfolio.config.expiry(portfolio.findings[1]) is None


RISK = """
risks:
  - id: r
    scope: alpha
    title: Something could break
    severity: high
    applies_to: [all]
    state: {state}
    {extra}
"""


@pytest.mark.parametrize(
    ("state", "extra", "today", "holds", "counts_as_open"),
    [
        ("accepted", "accepted_until: 2026-09-22", TODAY, True, False),
        ("accepted", "accepted_until: 2026-09-21", TODAY, False, True),
        ("open", "", TODAY, False, True),
        ("closed", "", TODAY, False, False),
    ],
)
def test_an_acceptance_holds_through_accepted_until_and_then_counts_as_open(
    tmp_path: Path, state: str, extra: str, today: dt.date, holds: bool, counts_as_open: bool
) -> None:
    portfolio = load_valid(tmp_path / "data", {"risks.yaml": RISK.format(state=state, extra=extra)})
    (risk,) = portfolio.risks

    assert risk.acceptance_holds(today) is holds
    assert risk.counts_as_open(today) is counts_as_open
