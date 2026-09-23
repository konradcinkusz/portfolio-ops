"""YAML and Markdown become typed models here, once (P11).

This module is the edge. It reads the data files, remembers the line of every value,
checks each file against the shape its JSON Schema describes, and hands over the typed
model of model.py. Everything after it — rules, report sections — works on that model
and never sees YAML.

Three reading decisions, each made once here so nothing downstream has to know:

* **YAML 1.2 core scalars.** PyYAML resolves YAML 1.1, where ``no`` is false,
  ``2026-09-22`` is a date object and ``1:30`` is the number 90. The data files are read
  with the core schema instead — the one JSON Schema-aware editors apply — so a date
  stays text until this module parses it, and a product called No stays a name.
* **An empty value is an absent value.** ``next_action:`` with nothing after it, or a
  blank string, counts as not written, so it is reported as missing rather than as
  having the wrong type.
* **Shape versus rules.** The JSON Schemas describe both the shape of a file and, for
  editors, the constraints owned by rules (vocabularies, id syntax, status-dependent
  fields). Each rule-owned constraint sits in an ``allOf`` entry tagged ``x-rule``; the
  engine removes those entries and leaves the rule to its own function, so every
  problem is reported once, under one id. What remains is shape, reported as
  ``schema``.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from functools import cache
from importlib import resources
from pathlib import Path as FsPath
from typing import Any, NoReturn

import yaml
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

from portfolio_ops import __version__
from portfolio_ops.errors import EnvironmentProblem
from portfolio_ops.model import (
    CONFIG_FILE,
    DECISIONS_FILE,
    FINDINGS_FILE,
    KERNELS_FILE,
    MIGRATIONS_URL,
    PRODUCTS_FILE,
    RISKS_FILE,
    SCHEMA_VERSION,
    Config,
    Decision,
    Diagnostic,
    FeedsFrom,
    Finding,
    Kernel,
    Loc,
    Path,
    Portfolio,
    Product,
    Risk,
    Term,
    Thresholds,
)

SCHEMA = "schema"  # the label of shape problems, which belong to no catalogue rule

_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

# The list files of §4.1: file, top-level key, what one entry is called, required.
_LIST_FILES = (
    (PRODUCTS_FILE, "products", "product", True),
    (KERNELS_FILE, "kernels", "kernel", False),
    (RISKS_FILE, "risks", "risk", False),
    (FINDINGS_FILE, "findings", "finding", False),
)


class DataDir:
    """The directory that holds the data files.

    Every data file is read through ``read_text``. That single door is what lets a test
    prove the visibility guard runs before anything but config.yaml is read (AC4).
    """

    def __init__(self, root: FsPath, display: str = "") -> None:
        self.root = root
        self.display = display  # how diagnostics name the directory; "" for "."

    def exists(self, name: str) -> bool:
        return (self.root / name).is_file()

    def read_text(self, name: str) -> str:
        try:
            return (self.root / name).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise _NotText(name, exc) from exc
        except OSError as exc:
            raise EnvironmentProblem(f"cannot read {self.describe(name)}: {exc.strerror}") from exc

    def describe(self, name: str | None = None) -> str:
        base = self.display or "."
        return base if name is None else (f"{self.display}/{name}" if self.display else name)


class _NotText(Exception):
    def __init__(self, name: str, exc: UnicodeDecodeError) -> None:
        super().__init__(name)
        self.name = name
        self.reason = exc.reason


# --------------------------------------------------------------------------- YAML


class _CoreLoader(yaml.SafeLoader):
    """SafeLoader resolving plain scalars with YAML 1.2's core schema."""


_CoreLoader.yaml_implicit_resolvers = {}
for _tag, _pattern, _first in (
    ("bool", r"^(?:true|True|TRUE|false|False|FALSE)$", "tTfF"),
    ("int", r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$", "-+0123456789"),
    (
        "float",
        (
            r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
            r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"
        ),
        "-+.0123456789",
    ),
    ("null", r"^(?:~|null|Null|NULL|)$", ["~", "n", "N", ""]),
):
    _CoreLoader.add_implicit_resolver(
        f"tag:yaml.org,2002:{_tag}", re.compile(_pattern), list(_first)
    )

_ABSENT = object()


@dataclass
class Document:
    """One parsed YAML file: its value, the line of every value in it, its problems."""

    file: str
    value: Any
    lines: dict[Path, int] = field(default_factory=dict)
    problems: list[Diagnostic] = field(default_factory=list)
    fatal: bool = False  # the file could not be read as data at all

    def line(self, path: Path) -> int | None:
        while path:
            if path in self.lines:
                return self.lines[path]
            path = path[:-1]
        return self.lines.get(())

    def mapping(self) -> dict[str, Any]:
        return self.value if isinstance(self.value, dict) else {}


def parse_yaml(text: str, file: str) -> Document:
    """Parse one YAML file into plain values plus the line of each value."""
    try:
        root = yaml.compose(text, Loader=_CoreLoader)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        return _unreadable(file, mark.line + 1 if mark else None, exc.problem or str(exc))
    except yaml.YAMLError as exc:
        return _unreadable(file, None, str(exc))
    doc = Document(file, None)
    if root is not None:
        doc.value = _Converter(doc).convert(root, (), root.start_mark.line + 1)
        if doc.value is _ABSENT:
            doc.value = None
    return doc


def _unreadable(file: str, line: int | None, problem: str) -> Document:
    problem = " ".join(problem.split())
    message = f"{file} is not valid YAML: {problem} — fix the syntax"
    return Document(file, None, problems=[_error(file, line, message)], fatal=True)


class _Converter:
    def __init__(self, doc: Document) -> None:
        self.doc = doc
        self.seen: set[int] = set()

    def convert(self, node: yaml.Node, path: Path, line: int) -> Any:
        if id(node) in self.seen:
            # compose() hands back the anchored node itself for every *alias.
            self.problem(line, "YAML aliases are not supported — write the value out in full")
            return _ABSENT
        self.seen.add(id(node))
        self.doc.lines[path] = line
        if isinstance(node, yaml.MappingNode):
            return self.mapping(node, path)
        if isinstance(node, yaml.SequenceNode):
            items = []
            for index, item in enumerate(node.value):
                value = self.convert(item, (*path, index), item.start_mark.line + 1)
                items.append(None if value is _ABSENT else value)
            return items
        return self.scalar(node, line)

    def mapping(self, node: yaml.MappingNode, path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {}
        keys: set[str] = set()
        for key_node, value_node in node.value:
            key_line = key_node.start_mark.line + 1
            key = self.key(key_node, key_line)
            if key is None:
                continue
            if key in keys:
                self.problem(key_line, f"duplicate key '{key}' — keep one of them")
                continue
            keys.add(key)
            value = self.convert(value_node, (*path, key), key_line)
            if value is _ABSENT or value is None or (isinstance(value, str) and not value.strip()):
                continue  # an empty value counts as absent
            result[key] = value
        return result

    def key(self, node: yaml.Node, line: int) -> str | None:
        if isinstance(node, yaml.ScalarNode) and node.tag == "tag:yaml.org,2002:str":
            return str(node.value)
        shown = node.value if isinstance(node, yaml.ScalarNode) else "a collection"
        self.problem(line, f"the key {shown!r} is not text — write keys as plain words")
        return None

    def scalar(self, node: yaml.Node, line: int) -> Any:
        text = str(node.value)
        value = _construct(node.tag, text)
        if value is _ABSENT:
            self.problem(
                line,
                f"the YAML tag {node.tag} on {text!r} is not supported — write the value plainly",
            )
        return value

    def problem(self, line: int, message: str) -> None:
        self.doc.problems.append(_error(self.doc.file, line, message))


def _construct(tag: str, text: str) -> Any:
    """The value of a scalar under the core schema, or _ABSENT for a tag it cannot take."""
    try:
        if tag == "tag:yaml.org,2002:str":
            return text
        if tag == "tag:yaml.org,2002:null":
            return None
        if tag == "tag:yaml.org,2002:bool" and text.lower() in ("true", "false"):
            return text.lower() == "true"
        if tag == "tag:yaml.org,2002:int":
            if text.startswith("0o"):
                return int(text[2:], 8)
            if text.startswith("0x"):
                return int(text[2:], 16)
            return int(text, 10)
        if tag == "tag:yaml.org,2002:float":
            return _float(text)
    except ValueError:
        return _ABSENT  # an explicit tag the text cannot satisfy, such as !!int ten
    return _ABSENT


def _float(text: str) -> float:
    lowered = text.lower()
    if lowered.endswith(".inf"):
        return float(lowered.replace(".inf", "inf"))
    if lowered == ".nan":
        return float("nan")
    return float(text)


def _error(file: str, line: int | None, message: str, rule: str = SCHEMA) -> Diagnostic:
    return Diagnostic("error", rule, file, line, message)


# --------------------------------------------------------------------------- S6


def read_config(data: DataDir) -> Document:
    """Read and parse config.yaml — the one file read before the visibility guard."""
    if not data.exists(CONFIG_FILE):
        raise EnvironmentProblem(
            f"no {CONFIG_FILE} in {data.describe()} — point --path at a portfolio data directory"
        )
    try:
        return parse_yaml(data.read_text(CONFIG_FILE), CONFIG_FILE)
    except _NotText as exc:
        return _unreadable(CONFIG_FILE, None, f"not UTF-8 text ({exc.reason})")


def check_schema_version(config: Document) -> int:
    """S6: ``schema_version`` is present and supported, or the command exits 2."""
    pointer = f"see {MIGRATIONS_URL}"
    if config.fatal:
        reason = config.problems[0].message.split(" — ")[0]
        _stop_s6(config.problems[0].line, f"{reason}, so schema_version cannot be read — {pointer}")
    if not isinstance(config.value, dict):
        _stop_s6(config.line(()), f"{CONFIG_FILE} is not a mapping with schema_version — {pointer}")
    version = config.mapping().get("schema_version")
    line = config.line(("schema_version",))
    if version is None:
        _stop_s6(
            line, f"schema_version is missing — add 'schema_version: {SCHEMA_VERSION}'; {pointer}"
        )
    if not isinstance(version, int) or isinstance(version, bool):
        _stop_s6(line, f"schema_version must be a whole number, not {version!r} — {pointer}")
    if version != SCHEMA_VERSION:
        _stop_s6(
            line,
            f"schema_version {version} is not supported by portfolio-ops {__version__}, "
            f"which reads schema_version {SCHEMA_VERSION} — {pointer}",
        )
    return SCHEMA_VERSION


def _stop_s6(line: int | None, message: str) -> NoReturn:
    raise EnvironmentProblem(_error(CONFIG_FILE, line, message, rule="S6"))


def allow_public(config: Document) -> bool:
    """``allow_public`` as the guard reads it: only a literal true opts in."""
    return config.mapping().get("allow_public") is True


# --------------------------------------------------------------------------- shape


@cache
def schema(kind: str) -> dict[str, Any]:
    """The published JSON Schema of one data file, as editors use it."""
    source = resources.files("portfolio_ops").joinpath("schemas").joinpath(f"{kind}.schema.json")
    loaded: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
    return loaded


@cache
def _shape_validator(kind: str) -> Draft7Validator:
    return Draft7Validator(
        _without_rules(schema(kind)), format_checker=Draft7Validator.FORMAT_CHECKER
    )


def _without_rules(node: Any) -> Any:
    """Replace every rule-owned subschema (tagged x-rule) with ``true``."""
    if isinstance(node, dict):
        return True if "x-rule" in node else {k: _without_rules(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_without_rules(item) for item in node]
    return node


def check_shape(doc: Document, kind: str) -> list[Diagnostic]:
    """Validate a parsed file against its shape and describe each problem in one line."""
    found: list[Diagnostic] = []
    for error in _shape_validator(kind).iter_errors(doc.value):
        found.extend(_describe_error(doc, kind, error))
    return found


_TYPE_NAMES = {
    "string": "text",
    "integer": "a whole number",
    "number": "a number",
    "boolean": "true or false",
    "array": "a list",
    "object": "a mapping",
    "null": "empty",
}


def _kind_of(value: Any) -> str:
    if isinstance(value, bool):
        return "true or false"
    if isinstance(value, int | float):
        return "a number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "a mapping"
    return "empty"


def _describe_error(doc: Document, kind: str, error: ValidationError) -> Iterator[Diagnostic]:
    path: Path = tuple(error.absolute_path)
    subject = _subject(doc, kind, path)
    line = doc.line(path)
    validator = error.validator
    expected: Any = error.validator_value
    subschema = error.schema if isinstance(error.schema, Mapping) else {}
    if validator == "required" and isinstance(error.instance, dict):
        for key in expected:
            if key not in error.instance:
                yield _error(doc.file, line, _missing(doc, kind, path, key))
    elif validator == "additionalProperties" and isinstance(error.instance, dict):
        allowed = list(subschema.get("properties", {}))
        for key in error.instance:
            if key not in allowed:
                where = f"in {subject}" if path else f"in {doc.file}"
                hint = f"; allowed keys: {', '.join(allowed)}" if allowed else ""
                message = f"unknown key '{key}' {where} — check the spelling{hint}"
                yield _error(doc.file, doc.line((*path, key)), message)
    elif validator == "type":
        names = [expected] if isinstance(expected, str) else list(expected)
        wanted = " or ".join(_TYPE_NAMES.get(n, n) for n in names if n != "null")
        yield _error(
            doc.file,
            line,
            f"{subject} must be {wanted}, not {_kind_of(error.instance)} — correct it",
        )
    elif validator in ("pattern", "format") and expected in (
        "date",
        "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
    ):
        yield _error(
            doc.file,
            line,
            f"{subject} must be a real date written YYYY-MM-DD, not '{error.instance}' "
            "— correct it",
        )
    elif validator == "pattern":
        yield _error(
            doc.file,
            line,
            f"'{error.instance}' in {subject} is not a valid vocabulary value — use "
            "lowercase letters, digits, hyphens and underscores",
        )
    elif validator in ("minimum", "exclusiveMinimum"):
        bound = "at least" if validator == "minimum" else "more than"
        yield _error(
            doc.file,
            line,
            f"{subject} must be {bound} {expected}, not {error.instance} — raise it",
        )
    elif validator == "minItems":
        yield _error(doc.file, line, f"{subject} is empty — list at least one value")
    elif validator == "uniqueItems":
        yield _error(doc.file, line, f"{subject} lists the same value twice — keep one")
    else:
        yield _error(doc.file, line, f"{subject}: {error.message}")


def _subject(doc: Document, kind: str, path: Path) -> str:
    """Name the value at ``path`` in words: 'next_action of product 'alpha''."""
    if not path:
        return doc.file
    if kind == "config":
        return ".".join(str(p) for p in path if isinstance(p, str)) + f" in {doc.file}"
    owner = _owner(doc, kind, path)
    field_name = ".".join(str(p) for p in path[2:] if isinstance(p, str))
    if len(path) < 2:
        return f"'{path[0]}' in {doc.file}"
    return f"{field_name} of {owner}" if field_name else owner


def _owner(doc: Document, kind: str, path: Path) -> str:
    noun = next((n for _, key, n, _ in _LIST_FILES if key == kind), kind)
    if len(path) < 2 or not isinstance(path[1], int):
        return doc.file
    entries = doc.mapping().get(kind)
    entry = entries[path[1]] if isinstance(entries, list) and len(entries) > path[1] else None
    ident = entry.get("id") if isinstance(entry, dict) else None
    if isinstance(ident, str):
        return f"{noun} '{ident}'"
    return f"the {noun} on line {doc.line(path[:2])}"


def _missing(doc: Document, kind: str, path: Path, key: str) -> str:
    if not path:
        return f"{doc.file} has no '{key}' — add it"
    owner = _subject(doc, kind, path)
    if key == "accepted_until":
        return f"{owner} is accepted but has no accepted_until — add the date the acceptance ends"
    return f"{owner} has no {key} — add it"


# --------------------------------------------------------------------------- the model


@dataclass(frozen=True)
class Loaded:
    """The typed portfolio, the shape problems found on the way, and whether any file was
    unreadable enough that rules would only report its consequences."""

    portfolio: Portfolio
    problems: tuple[Diagnostic, ...]
    fatal: bool


def load_portfolio(data: DataDir, config: Document) -> Loaded:
    """Read every data file after config.yaml and build the typed model."""
    problems = list(config.problems)
    problems += check_shape(config, "config")
    fatal = config.fatal
    documents: dict[str, Document | None] = {}
    for name, key, _, required in _LIST_FILES:
        doc = _read_list_file(data, name, key, required, problems)
        if doc is None or doc.fatal:
            fatal = fatal or required or (doc is not None and doc.fatal)
        documents[key] = doc
    decisions: tuple[Decision, ...] = ()
    if not data.exists(DECISIONS_FILE):
        problems.append(
            _error(DECISIONS_FILE, None, f"{DECISIONS_FILE} is missing — create it, even if empty")
        )
        fatal = True
    else:
        try:
            decisions = parse_decisions(data.read_text(DECISIONS_FILE))
        except _NotText as exc:
            problems.append(_error(DECISIONS_FILE, None, f"not UTF-8 text ({exc.reason})"))
            fatal = True
    portfolio = Portfolio(
        config=build_config(config),
        products=tuple(build_products(documents["products"])),
        kernels=tuple(build_kernels(documents["kernels"])),
        risks=tuple(build_risks(documents["risks"])),
        findings=tuple(build_findings(documents["findings"])),
        decisions=decisions,
    )
    return Loaded(portfolio, tuple(problems), fatal)


def _read_list_file(
    data: DataDir, name: str, key: str, required: bool, problems: list[Diagnostic]
) -> Document | None:
    if not data.exists(name):
        if required:
            problems.append(_error(name, None, f"{name} is missing — create it with '{key}:'"))
        return None
    try:
        doc = parse_yaml(data.read_text(name), name)
    except _NotText as exc:
        doc = _unreadable(name, None, f"not UTF-8 text ({exc.reason})")
    problems.extend(doc.problems)
    if doc.fatal:
        return doc
    if doc.value is None and not required:
        doc.value = {}  # an empty optional file means no entries
    problems.extend(check_shape(doc, key))
    entries = doc.mapping().get(key)
    unusable = not isinstance(doc.value, dict) or (entries is None and required)
    if unusable or (entries is not None and not isinstance(entries, list)):
        doc.fatal = True  # without the list itself, rules would only report consequences
    return doc


def _entries(doc: Document | None, key: str) -> Iterator[tuple[dict[str, Any], Loc]]:
    """Each mapping in the file's list, with its location."""
    if doc is None:
        return
    entries = doc.mapping().get(key)
    if not isinstance(entries, list):
        return
    grouped: dict[int, dict[Path, int]] = {}
    for path, line in doc.lines.items():
        if len(path) > 2 and path[0] == key and isinstance(path[1], int):
            grouped.setdefault(path[1], {})[path[2:]] = line
    for index, entry in enumerate(entries):
        if isinstance(entry, dict):
            line = doc.lines.get((key, index), 1)
            yield entry, Loc(doc.file, line, grouped.get(index, {}))


def _str(entry: Mapping[str, Any], key: str) -> str | None:
    value = entry.get(key)
    return value if isinstance(value, str) else None


def _text(entry: Mapping[str, Any], key: str) -> str | None:
    value = _str(entry, key)
    return value.strip() if value is not None else None


def _date(entry: Mapping[str, Any], key: str) -> dt.date | None:
    return parse_date(entry.get(key))


def parse_date(value: object) -> dt.date | None:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _terms(entry: Mapping[str, Any], key: str, loc: Loc) -> tuple[Term, ...] | None:
    values = entry.get(key)
    if not isinstance(values, list):
        return None
    return tuple(
        Term(value, loc.at(key, index))
        for index, value in enumerate(values)
        if isinstance(value, str)
    )


def _whole(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return value
    return default


def build_config(doc: Document) -> Config:
    values = doc.mapping()
    raw_thresholds = values.get("thresholds")
    thresholds = raw_thresholds if isinstance(raw_thresholds, dict) else {}
    raw_horizons = thresholds.get("review_horizon_days")
    horizons = raw_horizons if isinstance(raw_horizons, dict) else {}
    per_week = thresholds.get("actions_per_week")
    defaults = Thresholds()
    loc = Loc(doc.file, 1, dict(doc.lines))
    raw_vocabularies = values.get("vocabularies")
    vocabularies: dict[str, tuple[Term, ...]] = {}
    if isinstance(raw_vocabularies, dict):
        vocabulary_loc = Loc(doc.file, 1, _sub(doc, ("vocabularies",)))
        for name in raw_vocabularies:
            vocabularies[name] = _terms(raw_vocabularies, name, vocabulary_loc) or ()
    raw_ttl = values.get("finding_ttl_days")
    ttl = {
        name: days
        for name, days in (raw_ttl.items() if isinstance(raw_ttl, dict) else ())
        if isinstance(days, int) and not isinstance(days, bool) and days >= 1
    }
    return Config(
        loc=loc,
        schema_version=SCHEMA_VERSION,
        allow_public=values.get("allow_public") is True,
        thresholds=Thresholds(
            stale_days=_whole(thresholds.get("stale_days"), defaults.stale_days),
            actions_per_week=(
                per_week
                if isinstance(per_week, int | float)
                and not isinstance(per_week, bool)
                and per_week > 0
                else defaults.actions_per_week
            ),
            wip_limit=_whole(thresholds.get("wip_limit"), defaults.wip_limit),
            review_horizon_paused=_whole(horizons.get("paused"), defaults.review_horizon_paused),
            review_horizon_dormant=_whole(horizons.get("dormant"), defaults.review_horizon_dormant),
            deferral_limit=_whole(thresholds.get("deferral_limit"), defaults.deferral_limit),
        ),
        vocabularies=vocabularies,
        finding_ttl_days=ttl,
    )


def _sub(doc: Document, base: Path) -> dict[Path, int]:
    size = len(base)
    return {p[size:]: line for p, line in doc.lines.items() if p[:size] == base and len(p) > size}


def build_products(doc: Document | None) -> Iterator[Product]:
    for entry, loc in _entries(doc, "products"):
        feeds = entry.get("feeds_from")
        yield Product(
            loc=loc,
            id=_str(entry, "id"),
            name=_text(entry, "name"),
            status=_str(entry, "status"),
            next_action=_text(entry, "next_action"),
            capabilities=_terms(entry, "capabilities", loc),
            feeds_from=tuple(
                FeedsFrom(_str(feed, "kernel"), _str(feed, "mode"), index)
                for index, feed in enumerate(feeds if isinstance(feeds, list) else ())
                if isinstance(feed, dict)
            ),
            status_reason=_text(entry, "status_reason"),
            review_by=_date(entry, "review_by"),
            present=frozenset(entry),
        )


def build_kernels(doc: Document | None) -> Iterator[Kernel]:
    for entry, loc in _entries(doc, "kernels"):
        yield Kernel(
            loc=loc,
            id=_str(entry, "id"),
            name=_text(entry, "name"),
            capabilities=_terms(entry, "capabilities", loc) or (),
            min_package_consumers=_whole(entry.get("min_package_consumers"), 2),
        )


def build_risks(doc: Document | None) -> Iterator[Risk]:
    for entry, loc in _entries(doc, "risks"):
        yield Risk(
            loc=loc,
            id=_str(entry, "id"),
            scope=_str(entry, "scope"),
            title=_text(entry, "title"),
            severity=_str(entry, "severity"),
            applies_to=_terms(entry, "applies_to", loc) or (),
            state=_str(entry, "state"),
            accepted_until=_date(entry, "accepted_until"),
        )


def build_findings(doc: Document | None) -> Iterator[Finding]:
    for entry, loc in _entries(doc, "findings"):
        yield Finding(
            loc=loc,
            id=_str(entry, "id"),
            subject=_str(entry, "subject"),
            type=_str(entry, "type"),
            result=_text(entry, "result"),
            evidence=_text(entry, "evidence"),
            checked_on=_date(entry, "checked_on"),
            expires_on=_date(entry, "expires_on"),
            used_in=_terms(entry, "used_in", loc),
            present=frozenset(entry),
        )


# --------------------------------------------------------------------------- decisions.md

# An ATX heading opens with 1-6 '#' followed by a space, a tab or the end of the line.
_ATX = re.compile(r"^ {0,3}(#{1,6})(?=[ \t]|$)")
_CLOSING = re.compile(r"(?:^|[ \t]+)#+[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r"^(?P<date>[^\s·|]+)\s*[·|]\s*(?P<ids>[^·|]*?)\s*[·|]\s*(?P<type>[^·|\s]+)$")
GRAMMAR = "## <YYYY-MM-DD> · <id>[, <id>…] · <type>"


def parse_decisions(text: str) -> tuple[Decision, ...]:
    """Every level-2 heading of decisions.md, parsed against the grammar of §4.6, with the
    text under it.

    Headings inside fenced code blocks are text, as Markdown renders them; other heading
    levels are free text too. The text before the first level-2 heading belongs to no
    decision.
    """
    headings: list[Decision] = []
    bodies: list[list[str]] = []
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        opening = _FENCE.match(line)
        if fence is not None:
            if opening and opening.group(1)[0] == fence[0] and len(opening.group(1)) >= len(fence):
                fence = None
        elif opening:
            fence = opening.group(1)
        elif (match := _ATX.match(line)) and len(match.group(1)) == 2:
            heading = _CLOSING.sub("", line[match.end() :]).strip()
            headings.append(parse_heading(number, heading))
            bodies.append([])
            continue
        if bodies:
            bodies[-1].append(line)
    return tuple(
        replace(decision, text=_trimmed(body))
        for decision, body in zip(headings, bodies, strict=True)
    )


def _trimmed(lines: list[str]) -> str:
    """The lines, without the blank ones before and after them."""
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return "\n".join(lines[start:end])


def parse_heading(line: int, heading: str) -> Decision:
    match = _HEADING.match(heading)
    if not match:
        return Decision(line, heading, error=f"the heading does not follow '{GRAMMAR}'")
    raw_date = match.group("date")
    if not _DATE.fullmatch(raw_date):
        return Decision(line, heading, error=f"'{raw_date}' is not a date written YYYY-MM-DD")
    date = parse_date(raw_date)
    if date is None:
        return Decision(line, heading, error=f"'{raw_date}' is not a real date")
    ids = tuple(part.strip() for part in match.group("ids").split(","))
    if not all(ids):
        return Decision(line, heading, error="the heading names an empty id")
    return Decision(line, heading, date=date, ids=ids, type=match.group("type"))


# --------------------------------------------------------------------------- history


def product_values(text: str) -> dict[str, tuple[Any, Any]] | None:
    """``(status, next_action)`` per product id in one version of products.yaml.

    Used by the clock to compare versions by value rather than by text (§7.2): order,
    formatting and other fields never enter the comparison. Returns None for a version
    that does not parse, which the clock skips.
    """
    doc = parse_yaml(text, PRODUCTS_FILE)
    entries = doc.mapping().get("products") if not doc.fatal else None
    if not isinstance(entries, list):
        return None
    values: dict[str, tuple[Any, Any]] = {}
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            values.setdefault(entry["id"], (entry.get("status"), entry.get("next_action")))
    return values


def risk_states(text: str) -> dict[str, Any] | None:
    """``state`` per risk id in one version of risks.yaml, for P1 to compare versions by
    value. risks.yaml is optional, so an empty file or list means no risks; None for a
    version that does not parse."""
    doc = parse_yaml(text, RISKS_FILE)
    if doc.fatal or not isinstance(doc.value, dict | None):
        return None
    entries = doc.mapping().get("risks")
    if entries is None:
        return {}
    if not isinstance(entries, list):
        return None
    values: dict[str, Any] = {}
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            values.setdefault(entry["id"], entry.get("state"))
    return values


def iter_unique(items: Iterable[Diagnostic]) -> Iterator[Diagnostic]:
    seen: set[tuple[str, str, int | None, str]] = set()
    for item in items:
        key = (item.rule, item.file, item.line, item.message)
        if key not in seen:
            seen.add(key)
            yield item
