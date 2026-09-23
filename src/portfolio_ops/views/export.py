"""V2: the context export — size-bounded Markdown for an LLM session (spec §6).

The export holds what V2 lists, in its order: the active and paused products with their
next actions, the open risks of severity ``medium`` or higher, the latest decisions and
the capability vocabulary. Everything but the decisions is always there in full; the
decisions, newest first, fill what is left of ``--max-chars``, and the export says how
many it left out. It needs no git history, so it runs on any directory, like
``validate``.

Text from the data is written as it is, on one line where it is a field, because the
reader is a language model rather than a Markdown renderer: escaping would only add
noise. A decision keeps its line breaks.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

from portfolio_ops.model import DECISIONS_FILE, PORTFOLIO, SEVERITIES, Decision, Portfolio, Risk
from portfolio_ops.views import newest_first

DEFAULT_MAX_CHARS = 12_000
EXPORTED_SEVERITIES = SEVERITIES[SEVERITIES.index("medium") :]


class TooSmall(Exception):
    """The fixed parts of the export alone are longer than the limit."""

    def __init__(self, needed: int) -> None:
        super().__init__(needed)
        self.needed = needed


@dataclass(frozen=True)
class Exported:
    markdown: str
    decisions: int  # how many decisions the export holds
    of: int  # how many there are


def render_export(portfolio: Portfolio, today: dt.date, max_chars: int) -> Exported:
    """The export, at most ``max_chars`` characters long. Raises TooSmall when even the
    parts that are always there do not fit."""
    blocks = [_decision(decision) for decision in newest_first(portfolio)]
    fixed = [_active(portfolio), _paused(portfolio), _risks(portfolio, today)]
    vocabulary = _vocabulary(portfolio)

    def assemble(limit: int, count: int, shown: Sequence[str]) -> str:
        intro = _intro(count, len(blocks), limit)
        head = [_header(today, limit), *fixed, f"## Latest decisions\n\n{intro}"]
        return "\n\n".join([*head, *shown, vocabulary]) + "\n"

    # A decision adds its block and the blank line before it, so the length with the
    # ``count`` newest decisions is that of the export without them plus their blocks.
    added = [0]
    for block in blocks:
        added.append(added[-1] + len(block) + 2)
    for count in range(len(blocks), -1, -1):
        if len(assemble(max_chars, count, ())) + added[count] <= max_chars:
            return Exported(assemble(max_chars, count, blocks[:count]), count, len(blocks))
    # The export names its own limit, so the smallest limit that fits counts its digits.
    needed = 1
    while (length := len(assemble(needed, 0, ()))) > needed:
        needed = length
    raise TooSmall(needed)


def _one_line(text: str | None) -> str:
    return " ".join((text or "").split())


def _name(name: str | None, ident: str) -> str:
    """``Name (`id`)``, or the id alone when there is no other name."""
    name = _one_line(name)
    return f"`{ident}`" if not name or name == ident else f"{name} (`{ident}`)"


def _header(today: dt.date, max_chars: int) -> str:
    return (
        f"# Portfolio context — {today}\n\n"
        f"Exported by portfolio-ops on {today} (UTC) for an LLM session: the active and "
        "paused products with their next actions, the open risks of severity medium or "
        f"higher, the latest decisions and the capability vocabulary, in at most {max_chars} "
        "characters. The data files of the portfolio hold the rest."
    )


def _active(portfolio: Portfolio) -> str:
    active = [p for p in portfolio.products if p.status == "active" and p.id]
    limit = portfolio.config.thresholds.wip_limit
    lines = [
        "## Active products",
        "",
        f"{len(active)} active, of at most {limit} (wip_limit).",
    ]
    if active:
        lines.append("")
    lines += [
        f"- {_name(p.name, p.id or '')} — next action: {_one_line(p.next_action)}" for p in active
    ]
    return "\n".join(lines)


def _paused(portfolio: Portfolio) -> str:
    paused = [p for p in portfolio.products if p.status == "paused" and p.id]
    if not paused:
        return "## Paused products\n\nNo product is paused."
    lines = ["## Paused products", ""]
    for product in paused:
        name = _name(product.name, product.id or "")
        line = (
            f"- {name} — paused: {_one_line(product.status_reason)}; review by {product.review_by}"
        )
        if product.next_action:
            line += f"; next action: {_one_line(product.next_action)}"
        lines.append(line)
    return "\n".join(lines)


def _risks(portfolio: Portfolio, today: dt.date) -> str:
    """The risks that count as open (B3) with severity medium or higher, the most severe
    first."""
    risks = sorted(
        (
            risk
            for risk in portfolio.risks
            if risk.counts_as_open(today) and risk.severity in EXPORTED_SEVERITIES
        ),
        key=lambda risk: (-SEVERITIES.index(risk.severity or "low"), risk.id or ""),
    )
    title = "## Open risks of severity medium or higher"
    if not risks:
        return f"{title}\n\nNone."
    return "\n".join([title, "", *(_risk(portfolio, risk) for risk in risks)])


def _risk(portfolio: Portfolio, risk: Risk) -> str:
    applies = ", ".join(term.value for term in risk.applies_to)
    line = (
        f"- {risk.severity}: {_name(risk.title, risk.id or '')} — about "
        f"{_scope(portfolio, risk.scope)}; applies to {applies}"
    )
    if risk.state == "accepted":
        line += f"; accepted until {risk.accepted_until}, which has passed, so it counts as open"
    return line


def _scope(portfolio: Portfolio, scope: str | None) -> str:
    if scope is None or scope == PORTFOLIO:
        return "the portfolio"
    entity = portfolio.product(scope) or portfolio.kernel(scope)
    return _name(entity.name if entity else None, scope)


def _intro(count: int, total: int, max_chars: int) -> str:
    if total == 0:
        return "No decision is recorded yet."
    if count == total:
        return "The only decision." if total == 1 else f"All {total} decisions, newest first."
    if count == 0:
        return f"No decision fits within {max_chars} characters; {DECISIONS_FILE} has all {total}."
    return (
        f"The {count} latest of {total} decisions, newest first. The rest are left out to stay "
        f"within {max_chars} characters; {DECISIONS_FILE} has them all."
    )


def _decision(decision: Decision) -> str:
    return (
        f"### {decision.heading}\n\n{decision.text}" if decision.text else f"### {decision.heading}"
    )


def _vocabulary(portfolio: Portfolio) -> str:
    terms: Sequence[str] = portfolio.config.declared("capabilities")
    listed = ", ".join(terms) if terms else "none is declared"
    return f"## Capability vocabulary\n\n{listed}"
