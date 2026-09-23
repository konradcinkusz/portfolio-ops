"""The command line: ``validate`` and ``report`` (spec §7.6), the gates ``gate`` and
``idea-gate`` (§6 B1–B6), and the exit codes of §7.7.

Every command runs in the order of §7.3: read config.yaml, check ``schema_version``
(S6), run the visibility guard (S7), then everything else. Every command but
``validate`` then validates the data and judges nothing that does not validate.

Output: diagnostics — one line per finding, §7.8 — go to standard output for
``validate`` and ``gate``; Markdown goes to standard output for ``report`` and
``idea-gate``. Warnings that are not the command's product, environment errors and
summaries go to standard error, so the standard output of every command can be piped as
it is.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import posixpath
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from portfolio_ops import __version__
from portfolio_ops.errors import EXIT_OK, EXIT_VIOLATIONS, EnvironmentProblem, Stop
from portfolio_ops.git import Git
from portfolio_ops.github import API_URL, REPOSITORY, GitHubError, Transport, urllib_transport
from portfolio_ops.guard import check_visibility
from portfolio_ops.history import NoPreviousCommit, clocks, read_history, recent_changes
from portfolio_ops.loading import (
    SCHEMA,
    DataDir,
    Document,
    Loaded,
    allow_public,
    check_schema_version,
    iter_unique,
    load_portfolio,
    parse_date,
    read_config,
)
from portfolio_ops.model import ALL, FILE_ORDER, PRODUCTS_FILE, Diagnostic, Portfolio, Product
from portfolio_ops.report import ReportInput
from portfolio_ops.report.overlap import render_idea_gate
from portfolio_ops.report.publish import publish
from portfolio_ops.report.render import render, render_invalid
from portfolio_ops.rules import CATALOGUE, validate
from portfolio_ops.rules.changes import check_changes
from portfolio_ops.rules.gates import gate, idea_gate, run_gate, run_idea_gate


class _Parser(argparse.ArgumentParser):
    """argparse that writes to the streams ``main`` was given."""

    def __init__(self, *args: Any, out: IO[str], err: IO[str], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._out = out
        self._err = err

    def _print_message(self, message: str, file: Any = None) -> None:
        if message:
            (self._out if file is None or file is sys.stdout else self._err).write(message)


def _date(text: str) -> dt.date:
    value = parse_date(text)
    if value is None:
        raise argparse.ArgumentTypeError(f"expected a real date written YYYY-MM-DD, got {text!r}")
    return value


def valid_repository(text: str) -> bool:
    return bool(REPOSITORY.fullmatch(text)) and text.split("/", 1)[1].strip(".") != ""


def _repository(text: str) -> str:
    if valid_repository(text):
        return text
    raise argparse.ArgumentTypeError(f"expected OWNER/NAME, got {text!r}")


def build_parser(out: IO[str], err: IO[str]) -> argparse.ArgumentParser:
    parser = _Parser(
        prog="portfolio-ops",
        description="Validate a portfolio data directory and keep one weekly-review issue current.",
        out=out,
        err=err,
    )
    parser.add_argument("--version", action="version", version=f"portfolio-ops {__version__}")
    commands = parser.add_subparsers(
        dest="command", required=True, metavar="{validate,report,gate,idea-gate}"
    )
    path_help = "the data directory (default: the root of the git repository, else '.')"
    check = commands.add_parser(
        "validate",
        help="check the data files against the rules",
        description="Check the data files against the rules; exit 1 on any error.",
        out=out,
        err=err,
    )
    check.add_argument("--path", metavar="DIR", help=path_help)
    report = commands.add_parser(
        "report",
        help="render the weekly report as Markdown",
        description="Render the weekly report as Markdown, and optionally publish it.",
        out=out,
        err=err,
    )
    report.add_argument("--path", metavar="DIR", help=path_help)
    report.add_argument(
        "--today",
        metavar="YYYY-MM-DD",
        type=_date,
        help="the date to report for (default: today, UTC)",
    )
    report.add_argument(
        "--publish", action="store_true", help="keep one open weekly-review issue current"
    )
    report.add_argument(
        "--dry-run",
        action="store_true",
        help="with --publish: print the planned action and send no write request",
    )
    report.add_argument(
        "--repo",
        metavar="OWNER/NAME",
        type=_repository,
        help="the repository to publish to (default: GITHUB_REPOSITORY)",
    )
    move = commands.add_parser(
        "gate",
        help="check an external move of a product in one context",
        description=(
            "Check the registered risks and claims that bear on moving a product in one "
            "context; exit 1 when the gate fails."
        ),
        out=out,
        err=err,
    )
    move.add_argument("product", metavar="PRODUCT", help="the id of the product")
    move.add_argument(
        "--context",
        metavar="CONTEXT",
        required=True,
        help="where the move happens: one of vocabularies.contexts in config.yaml",
    )
    move.add_argument("--path", metavar="DIR", help=path_help)
    move.add_argument(
        "--today",
        metavar="YYYY-MM-DD",
        type=_date,
        help="the date of the move (default: today, UTC)",
    )
    idea = commands.add_parser(
        "idea-gate",
        help="compare an idea with the products and kernels that exist",
        description=(
            "List the products and kernels that share capabilities with an idea; exit 1 when "
            "one product already shares half of them and no admit decision names the idea."
        ),
        out=out,
        err=err,
    )
    idea.add_argument("idea", metavar="IDEA", help="the id of a product whose status is idea")
    idea.add_argument("--path", metavar="DIR", help=path_help)
    return parser


def _utc_today() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


@dataclass
class _Context:
    env: Mapping[str, str]
    out: IO[str]
    err: IO[str]
    transport: Transport
    today: Callable[[], dt.date]
    prefix: str = ""

    def warn(self, diagnostic: Diagnostic) -> None:
        self.err.write(diagnostic.render(self.prefix) + "\n")


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
    transport: Transport | None = None,
    today: Callable[[], dt.date] | None = None,
) -> int:
    """Run the command line and return its exit code. The keyword arguments are seams for
    tests; the console script calls ``main()`` with none of them."""
    if stdout is None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if stderr is None and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")
    out, err = stdout or sys.stdout, stderr or sys.stderr
    try:
        args = build_parser(out, err).parse_args(argv)
    except SystemExit as exit_request:  # --help, --version, or a usage error (exit 2)
        return exit_request.code if isinstance(exit_request.code, int) else 2
    context = _Context(
        env=os.environ if env is None else env,
        out=out,
        err=err,
        transport=transport or urllib_transport,
        today=today or _utc_today,
    )
    commands: dict[str, Callable[[argparse.Namespace, _Context], int]] = {
        "validate": _validate,
        "report": _report,
        "gate": _gate,
        "idea-gate": _idea_gate,
    }
    try:
        return commands[args.command](args, context)
    except Stop as stop:
        err.write(stop.render(context.prefix) + "\n")
        return stop.exit_code


def data_dir(given: str | None, cwd: Path | None = None) -> DataDir:
    """``--path``, or else the root of the git repository, or else the current directory."""
    here = cwd or Path.cwd()
    if given is not None:
        shown = posixpath.normpath(Path(given).as_posix())
        return DataDir(here / given, "" if shown == "." else shown)
    top = Git(here).toplevel()
    if top is None:
        return DataDir(here, "")
    shown = Path(os.path.relpath(top, here)).as_posix()
    return DataDir(top, "" if shown == "." else shown)


def _open(args: argparse.Namespace, context: _Context) -> tuple[DataDir, Document]:
    """config.yaml, S6 and S7: everything that happens before other data files are read."""
    data = data_dir(args.path)
    context.prefix = data.display
    config = read_config(data)
    check_schema_version(config)
    check_visibility(
        allow_public=allow_public(config),
        flag_line=config.line(("allow_public",)),
        env=context.env,
        origin_url=lambda: Git(data.root).origin_url(),
        transport=context.transport,
        warn=context.warn,
    )
    return data, config


def _rank(diagnostic: Diagnostic) -> tuple[int, int, int]:
    file = FILE_ORDER.index(diagnostic.file) if diagnostic.file in FILE_ORDER else len(FILE_ORDER)
    rule = -1 if diagnostic.rule == SCHEMA else CATALOGUE.index(diagnostic.rule)
    return file, diagnostic.line or 0, rule


def diagnose(loaded: Loaded, today: dt.date) -> list[Diagnostic]:
    """Shape problems, then — unless a file could not be read at all — every rule."""
    found = list(loaded.problems)
    if not loaded.fatal:
        found += validate(loaded.portfolio, today)
    return sorted(iter_unique(found), key=_rank)


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _validate(args: argparse.Namespace, context: _Context) -> int:
    data, config = _open(args, context)
    today = context.today()
    loaded = load_portfolio(data, config)
    diagnostics = diagnose(loaded, today)
    if not loaded.fatal:
        found = _since_previous_commit(data, loaded.portfolio, today, context)
        diagnostics = sorted([*diagnostics, *found], key=_rank)
    for diagnostic in diagnostics:
        context.out.write(diagnostic.render(data.display) + "\n")
    errors = sum(1 for d in diagnostics if d.severity == "error")
    warnings = len(diagnostics) - errors
    context.err.write(
        f"portfolio-ops validate {data.describe()}: {_count(errors, 'error')}, "
        f"{_count(warnings, 'warning')}\n"
    )
    return EXIT_VIOLATIONS if errors else EXIT_OK


def _since_previous_commit(
    data: DataDir, portfolio: Portfolio, today: dt.date, context: _Context
) -> list[Diagnostic]:
    """P1 in ``validate``: the status and state changes since the previous commit. Outside
    a git repository there is nothing to compare with, and validate still works (AC6)."""
    try:
        changes = recent_changes(
            Git(data.root),
            data,
            today,
            warn=lambda file, message: context.warn(
                Diagnostic("warning", "P1", file, None, message)
            ),
        )
    except NoPreviousCommit:
        context.err.write(
            "note: P1 was not checked — this shallow clone does not have the previous commit; "
            "fetch the full history (fetch-depth: 0 on actions/checkout) to check it\n"
        )
        return []
    return list(check_changes(portfolio, changes))


def _report(args: argparse.Namespace, context: _Context) -> int:
    if args.dry_run and not args.publish:
        raise EnvironmentProblem("--dry-run previews publishing, so it needs --publish")
    today: dt.date = args.today or context.today()
    data, config = _open(args, context)
    repository, token = _publishing_target(args, context) if args.publish else (None, None)
    loaded = load_portfolio(data, config)
    diagnostics = diagnose(loaded, today)
    errors = [d for d in diagnostics if d.severity == "error"]
    for warning in (d for d in diagnostics if d.severity == "warning"):
        context.warn(warning)
    if errors:
        rendered = render_invalid(errors, data.display, today)
    else:
        history = read_history(
            Git(data.root),
            data,
            today,
            warn=lambda file, message: context.warn(
                Diagnostic("warning", "N1" if file == PRODUCTS_FILE else "P1", file, None, message)
            ),
        )
        portfolio = loaded.portfolio
        rendered = render(
            ReportInput(
                portfolio=portfolio,
                today=today,
                clocks=clocks(portfolio, history, today),
                next_action_since=history.next_action_since,
                last_data_commit=history.last_data_commit,
                changes=history.changes,
            )
        )
    context.out.write(rendered.markdown)
    if repository is not None:
        try:
            publish(
                rendered=rendered,
                repository=repository,
                token=token,
                transport=context.transport,
                api_url=context.env.get("GITHUB_API_URL") or API_URL,
                dry_run=args.dry_run,
                say=lambda line: context.err.write(line + "\n"),
            )
        except GitHubError as exc:
            raise EnvironmentProblem(f"publishing to {repository} failed: {exc}") from exc
    return EXIT_VIOLATIONS if errors else EXIT_OK


def _publishing_target(args: argparse.Namespace, context: _Context) -> tuple[str, str | None]:
    repository = args.repo or context.env.get("GITHUB_REPOSITORY") or ""
    if not repository:
        raise EnvironmentProblem(
            "--publish needs to know the repository — pass --repo OWNER/NAME or set "
            "GITHUB_REPOSITORY"
        )
    if not valid_repository(repository):
        raise EnvironmentProblem(f"GITHUB_REPOSITORY is {repository!r}, not OWNER/NAME")
    token = context.env.get("GITHUB_TOKEN") or None
    if token is None and not args.dry_run:
        raise EnvironmentProblem(
            f"--publish needs GITHUB_TOKEN — set it to a token that can write issues in "
            f"{repository}, or add --dry-run to preview without writing"
        )
    return repository, token


# --------------------------------------------------------------------------- the gates


def _validated(
    args: argparse.Namespace, context: _Context, today: dt.date
) -> tuple[DataDir, Portfolio] | None:
    """The data, validated first: a command that judges the data judges only valid data.
    On errors, print them like ``validate`` does and return None — the command exits 1."""
    data, config = _open(args, context)
    loaded = load_portfolio(data, config)
    diagnostics = diagnose(loaded, today)
    errors = [d for d in diagnostics if d.severity == "error"]
    for warning in (d for d in diagnostics if d.severity == "warning"):
        context.warn(warning)
    if not errors:
        return data, loaded.portfolio
    for error in errors:
        context.out.write(error.render(data.display) + "\n")
    context.err.write(
        f"portfolio-ops {args.command}: the data in {data.describe()} does not validate — "
        f"{_count(len(errors), 'error')}; fix them first, then run {args.command} again\n"
    )
    return None


def _product(portfolio: Portfolio, ident: str, command: str) -> Product:
    product = portfolio.product(ident)
    if product is not None:
        return product
    if portfolio.kernel(ident) is not None:
        raise EnvironmentProblem(
            f"'{ident}' is a kernel, and {command} checks a product — name a product instead"
        )
    raise EnvironmentProblem(f"there is no product '{ident}' in {PRODUCTS_FILE} — use its id")


def _context(portfolio: Portfolio, name: str) -> str:
    declared = portfolio.config.declared("contexts")
    if name in declared:
        return name
    known = ", ".join(declared) if declared else "none is declared yet"
    if name == ALL:
        raise EnvironmentProblem(f"all is not a context — gate one context at a time: {known}")
    raise EnvironmentProblem(
        f"'{name}' is not a context — use one of vocabularies.contexts in config.yaml: {known}"
    )


def _gate(args: argparse.Namespace, context: _Context) -> int:
    today: dt.date = args.today or context.today()
    checked = _validated(args, context, today)
    if checked is None:
        return EXIT_VIOLATIONS
    data, portfolio = checked
    product = _product(portfolio, args.product, "gate")
    the_gate = gate(portfolio, product, _context(portfolio, args.context), today)
    diagnostics = run_gate(the_gate)
    for diagnostic in diagnostics:
        context.out.write(diagnostic.render(data.display) + "\n")
    errors = sum(1 for d in diagnostics if d.severity == "error")
    warnings = len(diagnostics) - errors
    context.err.write(
        f"portfolio-ops gate {product.id} --context {the_gate.context}: "
        f"{'failed' if errors else 'passed'} — {_count(errors, 'error')}, "
        f"{_count(warnings, 'warning')}; {_count(len(the_gate.risks), 'risk')} and "
        f"{_count(len(the_gate.claims), 'claim')} bear on the move\n"
    )
    return EXIT_VIOLATIONS if errors else EXIT_OK


def _idea_gate(args: argparse.Namespace, context: _Context) -> int:
    today = context.today()
    checked = _validated(args, context, today)
    if checked is None:
        return EXIT_VIOLATIONS
    data, portfolio = checked
    idea = _product(portfolio, args.idea, "idea-gate")
    if idea.status != "idea":
        raise EnvironmentProblem(
            f"idea-gate checks an idea, and '{idea.id}' is {idea.status} — the idea gate is "
            "the step from idea to active"
        )
    the_gate = idea_gate(portfolio, idea, today)
    failures = run_idea_gate(the_gate)
    context.out.write(render_idea_gate(the_gate, failures, data.display))
    shared = (
        f"{_count(len(the_gate.products), 'product')} and "
        f"{_count(len(the_gate.kernels), 'kernel')} share its capabilities"
    )
    verdict = "failed" if failures else "passed"
    context.err.write(f"portfolio-ops idea-gate {idea.id}: {verdict} — {shared}\n")
    return EXIT_VIOLATIONS if failures else EXIT_OK
