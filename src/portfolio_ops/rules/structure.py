"""Structure rules S1–S5 and the memory rule P2 (spec §6).

Each rule is a pure function of the typed model and today's date. A value that is
present but has the wrong type was already reported by the shape check in loading.py,
so these functions look at what is *present* before calling something missing: one
problem, one line.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterator

from portfolio_ops.model import (
    ALL,
    BUILTIN_DECISION_TYPES,
    BUILTIN_FINDING_TYPES,
    CONFIG_FILE,
    CONFIGURABLE_VOCABULARIES,
    DECISIONS_FILE,
    FEED_MODES,
    ID_PATTERN,
    PORTFOLIO,
    RESERVED_IDS,
    RISK_STATES,
    SEVERITIES,
    STATUSES,
    Diagnostic,
    Portfolio,
)
from portfolio_ops.rules import rule

_SLUG = re.compile(ID_PATTERN)
_GRAMMAR = "## <YYYY-MM-DD> · <id>[, <id>…] · <type>"


def _error(rule_id: str, file: str, line: int | None, message: str) -> Diagnostic:
    return Diagnostic("error", rule_id, file, line, message)


def _one_of(values: tuple[str, ...]) -> str:
    return ", ".join(values[:-1]) + f" or {values[-1]}"


@rule("S1", "ids are valid slugs, unique across products, kernels, risks and findings")
def check_ids(portfolio: Portfolio, today: dt.date) -> Iterator[Diagnostic]:
    first: dict[str, str] = {}
    groups = (
        ("product", portfolio.products),
        ("kernel", portfolio.kernels),
        ("risk", portfolio.risks),
        ("finding", portfolio.findings),
    )
    for noun, entities in groups:
        for entity in entities:
            ident = entity.id
            if ident is None:
                continue
            file, line = entity.loc.file, entity.loc.at("id")
            if ident in RESERVED_IDS:
                yield _error(
                    "S1", file, line, f"{noun} id '{ident}' is reserved — choose another id"
                )
            elif not _SLUG.fullmatch(ident):
                yield _error(
                    "S1",
                    file,
                    line,
                    f"{noun} id '{ident}' is not a valid id — use up to 63 lowercase letters, "
                    "digits and hyphens, starting with a letter or digit",
                )
            if ident in first:
                yield _error(
                    "S1",
                    file,
                    line,
                    f"id '{ident}' is already used by the {first[ident]} — ids are unique "
                    "across products, kernels, risks and findings",
                )
            else:
                first[ident] = f"{noun} at {file}:{line}"


@rule("S2", "every reference resolves")
def check_references(portfolio: Portfolio, today: dt.date) -> Iterator[Diagnostic]:
    kernels = {k.id for k in portfolio.kernels if k.id is not None}
    products = {p.id for p in portfolio.products if p.id is not None}
    targets = products | kernels | {PORTFOLIO}
    for risk in portfolio.risks:
        if risk.scope is not None and risk.scope not in targets:
            yield _error(
                "S2",
                risk.loc.file,
                risk.loc.at("scope"),
                f"{risk.label} has scope '{risk.scope}', which is not a product, a kernel or "
                "portfolio — use an existing id, or portfolio",
            )
    for finding in portfolio.findings:
        if finding.subject is not None and finding.subject not in targets:
            yield _error(
                "S2",
                finding.loc.file,
                finding.loc.at("subject"),
                f"{finding.label} has subject '{finding.subject}', which is not a product, a "
                "kernel or portfolio — use an existing id, or portfolio",
            )
    for product in portfolio.products:
        for feed in product.feeds_from:
            if feed.kernel is not None and feed.kernel not in kernels:
                yield _error(
                    "S2",
                    product.loc.file,
                    product.loc.at("feeds_from", feed.index, "kernel"),
                    f"{product.label} feeds from '{feed.kernel}', which is not a kernel — use "
                    "the id of a kernel in kernels.yaml",
                )
    ids = portfolio.entity_ids()
    for decision in portfolio.parsed_decisions():
        for ident in decision.ids:
            if ident not in ids:
                yield _error(
                    "S2",
                    DECISIONS_FILE,
                    decision.line,
                    f"the decision names '{ident}', which is not a product, kernel, risk or "
                    "finding id — ids never change: restore the id, or correct the heading",
                )


@rule("S3", "values belong to their vocabularies; decision headings follow §4.6")
def check_vocabularies(portfolio: Portfolio, today: dt.date) -> Iterator[Diagnostic]:
    config = portfolio.config
    for product in portfolio.products:
        file = product.loc.file
        if product.status is not None and product.status not in STATUSES:
            yield _error(
                "S3",
                file,
                product.loc.at("status"),
                f"{product.label} has status '{product.status}', which is not "
                f"{_one_of(STATUSES)} — use one of them",
            )
        for term in product.capabilities or ():
            if term.value not in config.capabilities:
                yield _unknown_term("capability", term.value, product.label, file, term.line)
        for feed in product.feeds_from:
            if feed.mode is not None and feed.mode not in FEED_MODES:
                yield _error(
                    "S3",
                    file,
                    product.loc.at("feeds_from", feed.index, "mode"),
                    f"{product.label} feeds from '{feed.kernel}' in mode '{feed.mode}', which is "
                    f"not {_one_of(FEED_MODES)} — use one of them",
                )
    for kernel in portfolio.kernels:
        label = f"kernel '{kernel.id}'" if kernel.id else f"the kernel on line {kernel.loc.line}"
        for term in kernel.capabilities:
            if term.value not in config.capabilities:
                yield _unknown_term("capability", term.value, label, kernel.loc.file, term.line)
    yield from _risk_vocabularies(portfolio)
    yield from _finding_vocabularies(portfolio)
    yield from _decision_headings(portfolio, today)


def _unknown_term(kind: str, value: str, owner: str, file: str, line: int) -> Diagnostic:
    vocabulary = "contexts" if kind == "context" else "capabilities"
    return _error(
        "S3",
        file,
        line,
        f"{owner} lists {kind} '{value}', which is not in vocabularies.{vocabulary} — add it "
        f"to {CONFIG_FILE} or correct it",
    )


def _risk_vocabularies(portfolio: Portfolio) -> Iterator[Diagnostic]:
    contexts = portfolio.config.contexts
    for risk in portfolio.risks:
        file = risk.loc.file
        if risk.severity is not None and risk.severity not in SEVERITIES:
            yield _error(
                "S3",
                file,
                risk.loc.at("severity"),
                f"{risk.label} has severity '{risk.severity}', which is not "
                f"{_one_of(SEVERITIES)} — use one of them",
            )
        if risk.state is not None and risk.state not in RISK_STATES:
            yield _error(
                "S3",
                file,
                risk.loc.at("state"),
                f"{risk.label} has state '{risk.state}', which is not {_one_of(RISK_STATES)} "
                "— a mitigated risk gets a lower severity, not a new state",
            )
        several = len(risk.applies_to) > 1
        for term in risk.applies_to:
            if term.value == ALL and several:
                yield _error(
                    "S3",
                    file,
                    term.line,
                    f"{risk.label} lists all among other contexts — write applies_to: [all] on "
                    "its own, or list contexts",
                )
            elif term.value != ALL and term.value not in contexts:
                yield _unknown_term("context", term.value, risk.label, file, term.line)


def _finding_vocabularies(portfolio: Portfolio) -> Iterator[Diagnostic]:
    config = portfolio.config
    for finding in portfolio.findings:
        file = finding.loc.file
        if finding.type is not None and finding.type not in config.finding_types:
            yield _error(
                "S3",
                file,
                finding.loc.at("type"),
                f"{finding.label} has type '{finding.type}', which is neither claim nor in "
                f"vocabularies.finding_types — add it to {CONFIG_FILE} or correct it",
            )
        for term in finding.used_in or ():
            if term.value not in config.contexts:
                yield _unknown_term("context", term.value, finding.label, file, term.line)
    for name in config.finding_ttl_days:
        if name not in config.finding_types:
            yield _error(
                "S3",
                CONFIG_FILE,
                config.loc.at("finding_ttl_days", name),
                f"finding_ttl_days names '{name}', which is neither claim nor in "
                "vocabularies.finding_types — add the type or remove the TTL",
            )


def _decision_headings(portfolio: Portfolio, today: dt.date) -> Iterator[Diagnostic]:
    types = portfolio.config.decision_types
    ids = portfolio.entity_ids()
    products = {p.id for p in portfolio.products if p.id is not None}
    for decision in portfolio.decisions:
        line = decision.line
        if decision.error is not None:
            yield _error(
                "S3",
                DECISIONS_FILE,
                line,
                f"{decision.error} — every level-2 heading is a decision written "
                f"'{_GRAMMAR}'; use ### for other headings",
            )
            continue
        if decision.date is not None and decision.date > today:
            yield _error(
                "S3",
                DECISIONS_FILE,
                line,
                f"the decision is dated {decision.date}, after today ({today}) — a decision "
                "records what was decided, so date it today or earlier",
            )
        if decision.type not in types:
            yield _error(
                "S3",
                DECISIONS_FILE,
                line,
                f"the decision has type '{decision.type}', which is neither a built-in decision "
                f"type nor in vocabularies.decision_types — add it to {CONFIG_FILE} or correct it",
            )
        if decision.type in ("focus", "defer"):
            if len(decision.ids) != 1:
                yield _error(
                    "S3",
                    DECISIONS_FILE,
                    line,
                    f"a {decision.type} decision names exactly one product, this one names "
                    f"{len(decision.ids)} — write one decision per product",
                )
            elif decision.ids[0] in ids and decision.ids[0] not in products:
                yield _error(
                    "S3",
                    DECISIONS_FILE,
                    line,
                    f"a {decision.type} decision names a product, and '{decision.ids[0]}' is "
                    "not one — name the product it is about",
                )


@rule("S4", "fields required by a product's status are present and review_by is within reach")
def check_status_fields(portfolio: Portfolio, today: dt.date) -> Iterator[Diagnostic]:
    thresholds = portfolio.config.thresholds
    changed = {i for d in portfolio.parsed_decisions() if d.type == "status_change" for i in d.ids}
    for product in portfolio.products:
        file, line, status = product.loc.file, product.loc.line, product.status
        present = product.present
        if status == "idea":
            if "capabilities" not in present or product.capabilities == ():
                yield _error(
                    "S4",
                    file,
                    product.loc.at("capabilities") if "capabilities" in present else line,
                    f"{product.label} is an idea but lists no capabilities — list them, so the "
                    "idea gate can compare it with what exists",
                )
        elif status == "active":
            if "next_action" not in present:
                yield _error(
                    "S4",
                    file,
                    line,
                    f"{product.label} is active but has no next_action — add next_action or "
                    "change its status",
                )
        elif status in ("paused", "dormant"):
            horizon = thresholds.review_horizon(status) or 0
            if "status_reason" not in present:
                yield _error(
                    "S4",
                    file,
                    line,
                    f"{product.label} is {status} but has no status_reason — say why it is "
                    f"{status}",
                )
            if "review_by" not in present:
                yield _error(
                    "S4",
                    file,
                    line,
                    f"{product.label} is {status} but has no review_by — add the date to look "
                    f"at it again, at most {horizon} days ahead",
                )
            elif product.review_by is not None:
                latest = today + dt.timedelta(days=horizon)
                if product.review_by > latest:
                    yield _error(
                        "S4",
                        file,
                        product.loc.at("review_by"),
                        f"{product.label} is {status} with review_by {product.review_by}, more "
                        f"than {horizon} days ahead — choose a date no later than {latest}",
                    )
        elif status == "archived" and product.id is not None and product.id not in changed:
            yield _error(
                "S4",
                file,
                product.loc.at("status"),
                f"{product.label} is archived but no status_change decision names it — record "
                f"the decision in {DECISIONS_FILE}",
            )


@rule("S5", "config.yaml extends only the configurable vocabularies")
def check_config_vocabularies(portfolio: Portfolio, today: dt.date) -> Iterator[Diagnostic]:
    config = portfolio.config
    built_in = {
        "contexts": (ALL,),
        "finding_types": BUILTIN_FINDING_TYPES,
        "decision_types": BUILTIN_DECISION_TYPES,
    }
    for name, terms in config.vocabularies.items():
        if name not in CONFIGURABLE_VOCABULARIES:
            yield _error(
                "S5",
                CONFIG_FILE,
                config.loc.at("vocabularies", name),
                f"vocabularies.{name} is not a configurable vocabulary — {CONFIG_FILE} extends "
                "only contexts, capabilities, finding_types and decision_types; statuses, "
                "severities, states and modes are fixed by the engine",
            )
            continue
        for term in terms:
            if term.value not in built_in.get(name, ()):
                continue
            if name == "contexts":
                message = (
                    "'all' cannot be declared as a context — it is reserved for applies_to: [all]"
                )
            else:
                message = (
                    f"'{term.value}' is built in — vocabularies.{name} only adds to the "
                    "built-in values, so remove it"
                )
            yield _error("S5", CONFIG_FILE, term.line, message)


@rule("P2", "findings carry checked_on and an expiry; claims say where they are used")
def check_findings(portfolio: Portfolio, today: dt.date) -> Iterator[Diagnostic]:
    ttl = portfolio.config.finding_ttl_days
    for finding in portfolio.findings:
        file, line, present = finding.loc.file, finding.loc.line, finding.present
        if "checked_on" not in present:
            yield _error(
                "P2",
                file,
                line,
                f"{finding.label} has no checked_on — add the date the result was verified",
            )
        if "expires_on" not in present and finding.type not in ttl:
            if finding.type is None:
                message = f"{finding.label} has no expires_on — add expires_on"
            else:
                message = (
                    f"{finding.label} has no expires_on and no TTL is configured for type "
                    f"'{finding.type}' — add expires_on, or set finding_ttl_days.{finding.type} "
                    f"in {CONFIG_FILE}"
                )
            yield _error("P2", file, line, message)
        if finding.type == "claim" and ("used_in" not in present or finding.used_in == ()):
            yield _error(
                "P2",
                file,
                finding.loc.at("used_in") if "used_in" in present else line,
                f"{finding.label} is a claim with no used_in — list the contexts where the "
                "claim is used externally",
            )
