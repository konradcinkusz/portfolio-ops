"""P3 (spec §6): the findings about a subject of one type, and whether each still holds."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from helpers import TODAY, load_valid
from portfolio_ops.rules.memory import lookup

FINDINGS = """
findings:
  - id: old-check
    subject: delta
    type: name_check
    result: The name was free
    checked_on: 2026-01-10

  - id: new-check
    subject: delta
    type: name_check
    result: The name is still free
    checked_on: 2026-09-10

  - id: other-subject
    subject: alpha
    type: name_check
    result: Not about delta
    checked_on: 2026-09-10

  - id: delta-claim
    subject: delta
    type: claim
    result: Not a name check
    checked_on: 2026-09-10
    expires_on: 2026-12-01
    used_in: [website]
"""


def test_p3_finds_the_subjects_findings_of_the_type_longest_holding_first(tmp_path: Path) -> None:
    portfolio = load_valid(tmp_path / "data", {"findings.yaml": FINDINGS})

    found = lookup(portfolio, "delta", "name_check")

    # The valid fixture's name_check TTL is 90 days.
    assert [(f.finding.id, f.until) for f in found] == [
        ("new-check", dt.date(2026, 12, 9)),
        ("old-check", dt.date(2026, 4, 10)),
    ]
    assert [f.holds(TODAY) for f in found] == [True, False]


def test_p3_a_finding_holds_through_its_last_day(tmp_path: Path) -> None:
    portfolio = load_valid(tmp_path / "data", {"findings.yaml": FINDINGS})
    (claim,) = lookup(portfolio, "delta", "claim")

    assert claim.holds(dt.date(2026, 12, 1))
    assert not claim.holds(dt.date(2026, 12, 2))


def test_p3_nothing_recorded_is_an_empty_answer(tmp_path: Path) -> None:
    portfolio = load_valid(tmp_path / "data")

    assert lookup(portfolio, "gamma", "name_check") == ()
