"""The typed model that rules and report sections work on (P11).

loading.py turns YAML and Markdown into these values at the edge; nothing downstream sees
a YAML node or a Markdown line. Vocabulary fields stay plain strings on purpose: a status
outside its vocabulary is exactly what S3 has to be able to see and report, so the model
holds it rather than refusing it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

SCHEMA_VERSION = 1
MIGRATIONS_URL = "https://github.com/konradcinkusz/portfolio-ops/tree/main/docs/migrations/"

# The data files of spec §4.1, in the order their diagnostics are reported.
CONFIG_FILE = "config.yaml"
PRODUCTS_FILE = "products.yaml"
KERNELS_FILE = "kernels.yaml"
RISKS_FILE = "risks.yaml"
FINDINGS_FILE = "findings.yaml"
DECISIONS_FILE = "decisions.md"
FILE_ORDER = (CONFIG_FILE, PRODUCTS_FILE, KERNELS_FILE, RISKS_FILE, FINDINGS_FILE, DECISIONS_FILE)

# §4.4
ID_PATTERN = r"[a-z0-9][a-z0-9-]{0,62}"
# Vocabulary values (§4.2) are called slugs too, but the spec's own examples and built-in
# types (name_check, status_change) carry underscores, so they may; ids may not.
VOCABULARY_PATTERN = r"[a-z0-9][a-z0-9_-]{0,62}"
PORTFOLIO = "portfolio"
ALL = "all"
RESERVED_IDS = (PORTFOLIO, ALL)

# §4.3 — fixed by the engine; config.yaml cannot change them (S5).
STATUSES = ("idea", "active", "paused", "dormant", "archived")
SEVERITIES = ("low", "medium", "high", "critical")
RISK_STATES = ("open", "accepted", "closed")
FEED_MODES = ("package", "copy", "planned")
BUILTIN_FINDING_TYPES = ("claim",)
BUILTIN_DECISION_TYPES = ("admit", "status_change", "focus", "defer", "risk_accepted")
# The only vocabularies config.yaml may declare (§4.2, S5).
CONFIGURABLE_VOCABULARIES = ("contexts", "capabilities", "finding_types", "decision_types")

Severity = Literal["error", "warning"]
Path = tuple[str | int, ...]


@dataclass(frozen=True)
class Diagnostic:
    """One finding line of spec §7.8: ``<severity> <rule> <file>:<line>: <message>``.

    ``file`` is relative to the data directory; ``render`` puts the directory in front,
    so the same diagnostic reads ``products.yaml:14`` in the data repository's root and
    ``examples/starter/products.yaml:14`` elsewhere.
    """

    severity: Severity
    rule: str
    file: str
    line: int | None
    message: str

    def render(self, prefix: str = "") -> str:
        path = f"{prefix}/{self.file}" if prefix else self.file
        where = path if self.line is None else f"{path}:{self.line}"
        return f"{self.severity} {self.rule} {where}: {self.message}"


@dataclass(frozen=True)
class Loc:
    """Where something sits in its file: its own line, and the line of each value in it.

    ``lines`` maps a path relative to the entity — ``("status",)`` or
    ``("capabilities", 2)`` — to the line that introduces that value. A value that is
    missing falls back to the nearest enclosing one, which is how "the line of the
    entity when a field is missing" (§7.8) comes about.
    """

    file: str
    line: int
    lines: Mapping[Path, int] = field(default_factory=dict)

    def at(self, *path: str | int) -> int:
        while path:
            if path in self.lines:
                return self.lines[path]
            path = path[:-1]
        return self.line


@dataclass(frozen=True)
class Term:
    """One value of a vocabulary list, with the line it was written on."""

    value: str
    line: int


@dataclass(frozen=True)
class FeedsFrom:
    kernel: str | None
    mode: str | None
    index: int  # position in the product's feeds_from list, for its lines


@dataclass(frozen=True)
class Product:
    loc: Loc
    id: str | None
    name: str | None
    status: str | None
    next_action: str | None = None
    capabilities: tuple[Term, ...] | None = None  # None: the key is absent
    feeds_from: tuple[FeedsFrom, ...] = ()
    status_reason: str | None = None
    review_by: dt.date | None = None
    present: frozenset[str] = frozenset()

    @property
    def label(self) -> str:
        return f"product '{self.id}'" if self.id else f"the product on line {self.loc.line}"


@dataclass(frozen=True)
class Kernel:
    loc: Loc
    id: str | None
    name: str | None
    capabilities: tuple[Term, ...] = ()
    min_package_consumers: int = 2


@dataclass(frozen=True)
class Risk:
    loc: Loc
    id: str | None
    scope: str | None
    title: str | None
    severity: str | None
    applies_to: tuple[Term, ...]
    state: str | None
    accepted_until: dt.date | None = None

    @property
    def label(self) -> str:
        return f"risk '{self.id}'" if self.id else f"the risk on line {self.loc.line}"

    def acceptance_holds(self, today: dt.date) -> bool:
        """Accepted, and ``accepted_until`` is today or later (B3)."""
        return (
            self.state == "accepted"
            and self.accepted_until is not None
            and self.accepted_until >= today
        )

    def counts_as_open(self, today: dt.date) -> bool:
        """Open, or accepted past ``accepted_until`` — "after that date it counts as open" (B3)."""
        expired = self.state == "accepted" and not self.acceptance_holds(today)
        return self.state == "open" or expired


@dataclass(frozen=True)
class Finding:
    loc: Loc
    id: str | None
    subject: str | None
    type: str | None
    result: str | None
    evidence: str | None = None
    checked_on: dt.date | None = None
    expires_on: dt.date | None = None
    used_in: tuple[Term, ...] | None = None  # None: the key is absent
    present: frozenset[str] = frozenset()

    @property
    def label(self) -> str:
        return f"finding '{self.id}'" if self.id else f"the finding on line {self.loc.line}"


@dataclass(frozen=True)
class Decision:
    """A level-2 heading of decisions.md (§4.6).

    ``error`` says why the heading does not follow the grammar; S3 reports it. A
    heading that parses has ``error`` set to None and every other field filled in.
    """

    line: int
    heading: str
    date: dt.date | None = None
    ids: tuple[str, ...] = ()
    type: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class Change:
    """A product's status or a risk's state changing between two versions of its file (P1).

    ``date`` is the committer date, in UTC, of the commit whose version made the change,
    or today for a change that is only in the working tree (``commit`` None) — the same
    reading of history as the clock's (§7.2).
    """

    kind: Literal["product", "risk"]
    id: str
    before: str
    after: str
    date: dt.date
    commit: str | None


@dataclass(frozen=True)
class Thresholds:
    stale_days: int = 30
    actions_per_week: float = 1
    wip_limit: int = 4
    review_horizon_paused: int = 60
    review_horizon_dormant: int = 180
    deferral_limit: int = 2

    def review_horizon(self, status: str) -> int | None:
        return {"paused": self.review_horizon_paused, "dormant": self.review_horizon_dormant}.get(
            status
        )


@dataclass(frozen=True)
class Config:
    loc: Loc
    schema_version: int
    allow_public: bool = False
    thresholds: Thresholds = field(default_factory=Thresholds)
    # Every key under ``vocabularies`` as written, including ones S5 rejects.
    vocabularies: Mapping[str, tuple[Term, ...]] = field(default_factory=dict)
    finding_ttl_days: Mapping[str, int] = field(default_factory=dict)

    def declared(self, vocabulary: str) -> tuple[str, ...]:
        return tuple(term.value for term in self.vocabularies.get(vocabulary, ()))

    @property
    def contexts(self) -> frozenset[str]:
        return frozenset(self.declared("contexts"))

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset(self.declared("capabilities"))

    @property
    def finding_types(self) -> tuple[str, ...]:
        return _merge(BUILTIN_FINDING_TYPES, self.declared("finding_types"))

    @property
    def decision_types(self) -> tuple[str, ...]:
        return _merge(BUILTIN_DECISION_TYPES, self.declared("decision_types"))

    def expiry(self, finding: Finding) -> dt.date | None:
        """The last day a finding holds (P2): its ``expires_on``, or else ``checked_on`` plus
        the TTL configured for its type. A finding holds while today is no later than this."""
        if finding.expires_on is not None:
            return finding.expires_on
        ttl = self.finding_ttl_days.get(finding.type or "")
        if finding.checked_on is None or ttl is None:
            return None
        return finding.checked_on + dt.timedelta(days=ttl)


def _merge(builtin: tuple[str, ...], configured: tuple[str, ...]) -> tuple[str, ...]:
    return builtin + tuple(value for value in configured if value not in builtin)


@dataclass(frozen=True)
class Portfolio:
    config: Config
    products: tuple[Product, ...] = ()
    kernels: tuple[Kernel, ...] = ()
    risks: tuple[Risk, ...] = ()
    findings: tuple[Finding, ...] = ()
    decisions: tuple[Decision, ...] = ()

    def product(self, product_id: str) -> Product | None:
        return next((p for p in self.products if p.id == product_id), None)

    def entity_ids(self) -> frozenset[str]:
        """Every id declared in products, kernels, risks and findings (§4.4)."""
        groups: tuple[tuple[Product | Kernel | Risk | Finding, ...], ...] = (
            self.products,
            self.kernels,
            self.risks,
            self.findings,
        )
        return frozenset(e.id for group in groups for e in group if e.id is not None)

    def parsed_decisions(self) -> tuple[Decision, ...]:
        return tuple(d for d in self.decisions if d.error is None)

    def kernel(self, kernel_id: str) -> Kernel | None:
        return next((k for k in self.kernels if k.id == kernel_id), None)
