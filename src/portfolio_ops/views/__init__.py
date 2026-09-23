"""The views of spec §6 V1–V2: the dashboard and the context export.

"Dashboards and exports are views: they show state and contain no rules" (§1). A view
reads the validated portfolio and the values the rules already derive — the clock (N1),
a kernel's state (K1), whether an acceptance (B3) or a finding (P2) still holds — and
decides nothing itself: it has no rule id, prints no diagnostic and never changes an exit
code.
"""

from __future__ import annotations

from portfolio_ops.model import Decision, Portfolio


def newest_first(portfolio: Portfolio) -> list[Decision]:
    """The parsed decisions, the newest first; on the same day, the later heading first."""
    dated = [d for d in portfolio.parsed_decisions() if d.date is not None]
    return sorted(dated, key=lambda d: (d.date, d.line), reverse=True)


def latest_about(portfolio: Portfolio, ident: str) -> Decision | None:
    """The newest decision whose heading names ``ident``."""
    return next((d for d in newest_first(portfolio) if ident in d.ids), None)
