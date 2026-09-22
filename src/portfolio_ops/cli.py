"""The command line: ``validate`` and ``report`` (spec §7.6), exit codes of §7.7.

Every command runs in the order of §7.3: read config.yaml, check ``schema_version``
(S6), run the visibility guard (S7), then everything else.

Output: diagnostics — one line per finding, §7.8 — go to standard output for
``validate``; the report's Markdown goes to standard output for ``report``. Warnings
that are not the command's product, environment errors and summaries go to standard
error, so the standard output of either command can be piped as it is.
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
from portfolio_ops.history import clocks, read_history
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
from portfolio_ops.model import FILE_ORDER, PRODUCTS_FILE, Diagnostic
from portfolio_ops.report import ReportInput
from portfolio_ops.report.publish import publish
from portfolio_ops.report.render import render, render_invalid
from portfolio_ops.rules import CATALOGUE, validate


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
    commands = parser.add_subparsers(dest="command", required=True, metavar="{validate,report}")
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
    try:
        if args.command == "validate":
            return _validate(args, context)
        return _report(args, context)
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
    diagnostics = diagnose(load_portfolio(data, config), context.today())
    for diagnostic in diagnostics:
        context.out.write(diagnostic.render(data.display) + "\n")
    errors = sum(1 for d in diagnostics if d.severity == "error")
    warnings = len(diagnostics) - errors
    context.err.write(
        f"portfolio-ops validate {data.describe()}: {_count(errors, 'error')}, "
        f"{_count(warnings, 'warning')}\n"
    )
    return EXIT_VIOLATIONS if errors else EXIT_OK


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
            data.read_text(PRODUCTS_FILE),
            today,
            warn=lambda message: context.warn(
                Diagnostic("warning", "N1", PRODUCTS_FILE, None, message)
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
