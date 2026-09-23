"""P1 (spec §6, §8.4): every status and state change is a decision, and follows §5.

A change of a product's status or of a risk's state needs a decision in decisions.md
that names the id and is dated on the day of the change; a product's status moves only
along the transitions of §5, and an archived product comes back only through ``admit``.
Misses are warnings, never errors: the decision log is kept honest by being shown what it
lacks, not by blocking the change (§8.4).

This module judges changes. Finding them in git — which changes, dated when — is
history.py's job (P11); ``validate`` passes the changes since the previous commit, the
report those of its week.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from portfolio_ops.model import (
    DECISIONS_FILE,
    PRODUCTS_FILE,
    RISKS_FILE,
    Change,
    Diagnostic,
    Portfolio,
)

# §5: the statuses each status may move to.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "idea": ("active", "archived"),
    "active": ("paused", "dormant", "archived"),
    "paused": ("active", "dormant", "archived"),
    "dormant": ("active", "archived"),
    "archived": ("active",),  # only through an admit decision
}


def _one_of(values: tuple[str, ...]) -> str:
    return values[0] if len(values) == 1 else ", ".join(values[:-1]) + f" or {values[-1]}"


def decision_type(change: Change) -> str:
    """The decision type a change is usually recorded with."""
    if change.kind == "risk":
        return "risk_accepted" if change.after == "accepted" else "status_change"
    if change.after == "active" and change.before in ("idea", "archived"):
        return "admit"
    return "status_change"


def _location(portfolio: Portfolio, change: Change) -> tuple[str, int | None]:
    """Where the entity now stands: its status or state line, if it still exists."""
    if change.kind == "product":
        product = portfolio.product(change.id)
        return PRODUCTS_FILE, product.loc.at("status") if product else None
    risk = next((r for r in portfolio.risks if r.id == change.id), None)
    return RISKS_FILE, risk.loc.at("state") if risk else None


def describe(change: Change) -> str:
    field = "status" if change.kind == "product" else "state"
    return (
        f"{change.kind} '{change.id}' changed {field} from {change.before} to {change.after} "
        f"on {change.date}"
    )


def check_changes(portfolio: Portfolio, changes: Iterable[Change]) -> Iterator[Diagnostic]:
    """P1: a warning for each change no decision names on its day, for each archived product
    brought back without ``admit``, and for each transition §5 does not allow."""
    decisions = portfolio.parsed_decisions()
    for change in changes:
        file, line = _location(portfolio, change)
        what = describe(change)
        heading = f"## {change.date} · {change.id} · {decision_type(change)}"
        covering = [d for d in decisions if change.id in d.ids and d.date == change.date]
        if not covering:
            yield Diagnostic(
                "warning",
                "P1",
                file,
                line,
                f"{what}, and no decision names it on that day — record the decision in "
                f"{DECISIONS_FILE} as '{heading}'",
            )
        elif (change.before, change.after) == ("archived", "active") and not any(
            d.type == "admit" for d in covering
        ):
            yield Diagnostic(
                "warning",
                "P1",
                file,
                line,
                f"{what} without an admit decision — an archived product comes back only "
                f"through admit: record '{heading}'",
            )
        allowed = TRANSITIONS.get(change.before, ())
        if change.kind == "product" and change.after not in allowed:
            yield Diagnostic(
                "warning",
                "P1",
                file,
                line,
                f"{what}, a transition the product lifecycle does not have — from "
                f"{change.before} a product moves to {_one_of(allowed)}",
            )
