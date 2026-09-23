"""P3 (spec §6): before a new check, look up what was already verified.

``lookup <subject> <type>`` answers "has this been checked, and does it still hold?" —
the memory function of §1, so that nothing is worked out twice. A finding that holds is
reused; an expired one is checked again and updated in place, not recorded a second
time; when there is none, the check is made and its result recorded. P2 guarantees every
finding has an expiry to judge by.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from portfolio_ops.model import Finding, Portfolio


@dataclass(frozen=True)
class Found:
    """A finding about the subject, and the last day it holds (P2)."""

    finding: Finding
    until: dt.date | None

    def holds(self, today: dt.date) -> bool:
        return self.until is not None and today <= self.until


def lookup(portfolio: Portfolio, subject: str, finding_type: str) -> tuple[Found, ...]:
    """P3: the findings about ``subject`` of ``finding_type``, the longest-holding first."""
    config = portfolio.config
    found = [
        Found(finding, config.expiry(finding))
        for finding in portfolio.findings
        if finding.subject == subject and finding.type == finding_type
    ]
    return tuple(
        sorted(found, key=lambda f: (f.until or dt.date.min, f.finding.id or ""), reverse=True)
    )
