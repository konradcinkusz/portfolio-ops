"""The rule registry (P10).

A rule is a function registered under its catalogue id (spec §6) — not a subclass of a
base class. Adding one is a function and a decorator; ``validate`` runs whatever is
registered. Rules are pure: they read the typed model and today's date, and return
diagnostics. They never read files, git or the network (P11, P13).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from portfolio_ops.model import Diagnostic, Portfolio

Check = Callable[[Portfolio, dt.date], Iterable[Diagnostic]]

# The order of the catalogue in spec §6, which is also the order rules run in.
CATALOGUE = (
    *("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "L1", "L2", "N1", "N2", "N3", "N4"),
    *("P2", "R1", "R2", "R3", "B1", "B2", "B3", "B4", "B5", "B6", "K1", "K2", "P1", "P3"),
    *("A1", "A2", "A3"),
)


@dataclass(frozen=True)
class Rule:
    id: str
    summary: str
    check: Check


REGISTRY: dict[str, Rule] = {}


def rule(rule_id: str, summary: str) -> Callable[[Check], Check]:
    """Register a validation rule under its catalogue id."""

    def register(check: Check) -> Check:
        if rule_id in REGISTRY:
            raise ValueError(f"rule {rule_id} is registered twice")
        REGISTRY[rule_id] = Rule(rule_id, summary, check)
        return check

    return register


def validate(portfolio: Portfolio, today: dt.date) -> list[Diagnostic]:
    """Run every registered rule, in catalogue order."""
    found: list[Diagnostic] = []
    for rule_id in sorted(REGISTRY, key=CATALOGUE.index):
        found.extend(REGISTRY[rule_id].check(portfolio, today))
    return found


# The built-in rules register themselves when their modules are imported.
from portfolio_ops.rules import limits, structure  # noqa: E402

__all__ = ["CATALOGUE", "REGISTRY", "Check", "Rule", "limits", "rule", "structure", "validate"]
