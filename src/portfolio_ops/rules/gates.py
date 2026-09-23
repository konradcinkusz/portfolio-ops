"""The gates (spec §6 B1–B6): may this external move go ahead, and may this idea start?

``gate <product> --context <ctx>`` looks at the registered risks and claims that bear on
moving a product in one context — a store listing, a grant application, a talk.
``idea-gate <idea>`` compares an idea's capabilities with the products and kernels that
already exist. Both are pure functions of the typed model and today's date, and their
checks are registered functions (P10), like the validation rules.

A gate remembers; it does not discover (§8.5). It can only block on what has been
registered, which is why claims carry the contexts they are used in and an expiry, and
risks the contexts they apply to.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import TypeVar

from portfolio_ops.model import (
    ALL,
    PORTFOLIO,
    Decision,
    Diagnostic,
    Finding,
    Kernel,
    Portfolio,
    Product,
    Risk,
    Term,
)
from portfolio_ops.rules import CATALOGUE

BLOCKING_SEVERITIES = ("high", "critical")  # B2


@dataclass(frozen=True)
class Gate:
    """One external move — a product in a context — and what bears on it (B1)."""

    portfolio: Portfolio
    product: Product
    context: str
    today: dt.date
    kernels: tuple[str, ...]  # every kernel the product feeds from, in any mode
    risks: tuple[Risk, ...]  # the risks that apply to the move: B1
    claims: tuple[Finding, ...]  # the claims about the product used in the context


@dataclass(frozen=True)
class Overlap:
    """A product or kernel that shares capabilities with an idea (B5)."""

    entity: Product | Kernel
    shared: tuple[str, ...]  # in the order of the idea's capabilities


@dataclass(frozen=True)
class IdeaGate:
    """An idea, and the products and kernels that share its capabilities (B5)."""

    portfolio: Portfolio
    idea: Product
    today: dt.date
    capabilities: tuple[str, ...]
    products: tuple[Overlap, ...]  # not archived, most shared capabilities first
    kernels: tuple[Overlap, ...]

    @property
    def admitted_by(self) -> Decision | None:
        """The latest ``admit`` decision that names the idea (B6)."""
        admits = [
            d
            for d in self.portfolio.parsed_decisions()
            if d.type == "admit" and self.idea.id in d.ids
        ]
        return max(admits, key=lambda d: (d.date or dt.date.min, d.line), default=None)

    def dominant(self) -> tuple[Overlap, ...]:
        """The products that share at least half of the idea's capabilities (B6)."""
        total = len(self.capabilities)
        return tuple(o for o in self.products if total and 2 * len(o.shared) >= total)


# --------------------------------------------------------------------------- registries

GateCheck = Callable[[Gate], Iterable[Diagnostic]]
IdeaCheck = Callable[[IdeaGate], Iterable[Diagnostic]]

GATE_CHECKS: dict[str, GateCheck] = {}
IDEA_CHECKS: dict[str, IdeaCheck] = {}

_Check = TypeVar("_Check")


def _registrar(registry: dict[str, _Check], rule_id: str) -> Callable[[_Check], _Check]:
    def register(check: _Check) -> _Check:
        if rule_id in registry:
            raise ValueError(f"gate rule {rule_id} is registered twice")
        registry[rule_id] = check
        return check

    return register


def gate_check(rule_id: str) -> Callable[[GateCheck], GateCheck]:
    """Register a check that ``gate`` runs, under its catalogue id."""
    return _registrar(GATE_CHECKS, rule_id)


def idea_check(rule_id: str) -> Callable[[IdeaCheck], IdeaCheck]:
    """Register a check that ``idea-gate`` runs, under its catalogue id."""
    return _registrar(IDEA_CHECKS, rule_id)


# --------------------------------------------------------------------------- gate: B1–B4


def reachable_kernels(product: Product) -> tuple[str, ...]:
    """Every kernel the product feeds from, whatever the mode — a planned consumer is
    about to inherit the kernel's risks, so it is gated on them already."""
    found: list[str] = []
    for feed in product.feeds_from:
        if feed.kernel is not None and feed.kernel not in found:
            found.append(feed.kernel)
    return tuple(found)


def _applies(terms: Iterable[Term], context: str) -> bool:
    return any(term.value in (context, ALL) for term in terms)


def collect_risks(portfolio: Portfolio, product: Product, context: str) -> tuple[Risk, ...]:
    """B1: the risks of the product, of every kernel it feeds from and of the portfolio,
    whose ``applies_to`` contains the context or ``all``."""
    scopes = {product.id, PORTFOLIO, *reachable_kernels(product)}
    return tuple(
        risk
        for risk in portfolio.risks
        if risk.scope in scopes and _applies(risk.applies_to, context)
    )


def collect_claims(portfolio: Portfolio, product: Product, context: str) -> tuple[Finding, ...]:
    """The claims about the product that are used in the context (B4)."""
    return tuple(
        finding
        for finding in portfolio.findings
        if finding.type == "claim"
        and finding.subject == product.id
        and any(term.value == context for term in finding.used_in or ())
    )


def gate(portfolio: Portfolio, product: Product, context: str, today: dt.date) -> Gate:
    return Gate(
        portfolio=portfolio,
        product=product,
        context=context,
        today=today,
        kernels=reachable_kernels(product),
        risks=collect_risks(portfolio, product, context),
        claims=collect_claims(portfolio, product, context),
    )


def run_gate(the_gate: Gate) -> list[Diagnostic]:
    """Every registered gate check, in catalogue order."""
    found: list[Diagnostic] = []
    for rule_id in sorted(GATE_CHECKS, key=CATALOGUE.index):
        found.extend(GATE_CHECKS[rule_id](the_gate))
    return found


def _owner(the_gate: Gate, risk: Risk) -> str:
    """How the risk reaches the product: its own, a kernel's it feeds from, the portfolio's."""
    if risk.scope == the_gate.product.id:
        return f"of {the_gate.product.id}"
    if risk.scope == PORTFOLIO:
        return "of the portfolio"
    return f"of kernel '{risk.scope}', which {the_gate.product.id} feeds from,"


def _where(risk: Risk, context: str) -> str:
    if any(term.value == context for term in risk.applies_to):
        return f"applies to {context}"
    return "applies to every context"


@gate_check("B2")
def check_open_risks(the_gate: Gate) -> Iterator[Diagnostic]:
    """B2: a collected risk is open — or accepted past its date — and high or critical."""
    for risk in the_gate.risks:
        if risk.severity not in BLOCKING_SEVERITIES or not risk.counts_as_open(the_gate.today):
            continue
        owner, where = _owner(the_gate, risk), _where(risk, the_gate.context)
        if risk.state == "accepted":
            yield Diagnostic(
                "error",
                "B2",
                risk.loc.file,
                risk.loc.at("accepted_until"),
                f"{risk.label} {owner} was accepted until {risk.accepted_until}, so it counts as "
                f"open again, with severity {risk.severity}, and {where} — renew the acceptance "
                "with a later accepted_until and a risk_accepted decision, or mitigate the risk "
                "and lower its severity",
            )
        else:
            yield Diagnostic(
                "error",
                "B2",
                risk.loc.file,
                risk.loc.at("state"),
                f"{risk.label} {owner} is open with severity {risk.severity} and {where} — "
                "mitigate it and lower its severity, or accept it until a date with a "
                "risk_accepted decision",
            )


@gate_check("B3")
def check_accepted_risks(the_gate: Gate) -> Iterator[Diagnostic]:
    """B3: a collected risk is accepted, and its acceptance still holds."""
    for risk in the_gate.risks:
        if risk.acceptance_holds(the_gate.today):
            owner, where = _owner(the_gate, risk), _where(risk, the_gate.context)
            yield Diagnostic(
                "warning",
                "B3",
                risk.loc.file,
                risk.loc.at("accepted_until"),
                f"{risk.label} {owner} is accepted until {risk.accepted_until}, with severity "
                f"{risk.severity}, and {where} — the gate passes on that acceptance; make sure it "
                "still covers this move",
            )


@gate_check("B4")
def check_expired_claims(the_gate: Gate) -> Iterator[Diagnostic]:
    """B4: a claim about the product is used in the context and has expired."""
    config = the_gate.portfolio.config
    for claim in the_gate.claims:
        until = config.expiry(claim)
        if until is None or until >= the_gate.today:
            continue
        dated = "expires_on" in claim.present
        yield Diagnostic(
            "error",
            "B4",
            claim.loc.file,
            claim.loc.at("expires_on" if dated else "checked_on"),
            f"claim '{claim.id}' about {the_gate.product.id} is used in {the_gate.context} but "
            f"held only until {until} — re-verify it before use, then update "
            + ("checked_on and expires_on" if dated else "checked_on"),
        )


# --------------------------------------------------------------------------- idea gate: B5, B6


def _capabilities(terms: Iterable[Term] | None) -> tuple[str, ...]:
    found: list[str] = []
    for term in terms or ():
        if term.value not in found:
            found.append(term.value)
    return tuple(found)


def _overlap(wanted: tuple[str, ...], entity: Product | Kernel) -> Overlap | None:
    have = set(_capabilities(entity.capabilities))
    shared = tuple(value for value in wanted if value in have)
    return Overlap(entity, shared) if shared else None


def _ranked(found: Iterable[Overlap | None]) -> tuple[Overlap, ...]:
    kept = [o for o in found if o is not None]
    return tuple(sorted(kept, key=lambda o: (-len(o.shared), o.entity.id or "")))


def overlaps(
    portfolio: Portfolio, idea: Product
) -> tuple[tuple[Overlap, ...], tuple[Overlap, ...]]:
    """B5: the products that are not archived, and the kernels, that share capabilities
    with the idea."""
    wanted = _capabilities(idea.capabilities)
    products = _ranked(
        _overlap(wanted, product)
        for product in portfolio.products
        if product is not idea and product.id != idea.id and product.status != "archived"
    )
    kernels = _ranked(_overlap(wanted, kernel) for kernel in portfolio.kernels)
    return products, kernels


def idea_gate(portfolio: Portfolio, idea: Product, today: dt.date) -> IdeaGate:
    products, kernels = overlaps(portfolio, idea)
    return IdeaGate(
        portfolio=portfolio,
        idea=idea,
        today=today,
        capabilities=_capabilities(idea.capabilities),
        products=products,
        kernels=kernels,
    )


def run_idea_gate(the_gate: IdeaGate) -> list[Diagnostic]:
    """Every registered idea-gate check, in catalogue order."""
    found: list[Diagnostic] = []
    for rule_id in sorted(IDEA_CHECKS, key=CATALOGUE.index):
        found.extend(IDEA_CHECKS[rule_id](the_gate))
    return found


@idea_check("B6")
def check_idea_overlap(the_gate: IdeaGate) -> Iterator[Diagnostic]:
    """B6: one product shares at least half of the idea's capabilities, and no ``admit``
    decision names the idea yet."""
    if the_gate.admitted_by is not None:
        return
    idea, total = the_gate.idea, len(the_gate.capabilities)
    for overlap in the_gate.dominant():
        other = overlap.entity.id
        share = (
            "its only capability"
            if total == 1
            else f"{len(overlap.shared)} of its {total} capabilities"
        )
        yield Diagnostic(
            "error",
            "B6",
            idea.loc.file,
            idea.loc.at("capabilities"),
            f"idea '{idea.id}' shares {share} with product '{other}' "
            f"({', '.join(overlap.shared)}) — merge it into '{other}' by archiving the idea, or "
            f"record an admit decision that names {idea.id} and says why it stands apart",
        )
