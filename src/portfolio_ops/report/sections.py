"""The report sections of spec §7.4: Stale (N2), Escalations (N3), Overdue reviews (N4),
the four that R2 adds in phase 2 — Expired acceptances (B3), Expired claims (P2),
Copy-paste debt (K2) and Changes without a decision (P1) — then Account activity (A1–A3,
phase 4), Focus (R3) and Health. Section 1, Validation errors, is rendered by render.py
because it replaces the others rather than preceding them.
"""

from __future__ import annotations

import datetime as dt
import re
import statistics
from collections.abc import Iterator

from portfolio_ops.model import PORTFOLIO, AccountScan, Decision, Portfolio, Product
from portfolio_ops.report import ReportInput, Section, section
from portfolio_ops.rules.account import (
    inactive_work,
    outside_portfolio,
    shown,
    unknown_repositories,
    worked_on,
)
from portfolio_ops.rules.changes import check_changes
from portfolio_ops.rules.kernels import copies, kernel_state

NO_FOCUS = "No focus recorded this week"
FOCUS_WINDOW_DAYS = 7  # "the seven days ending today"
EVALUATED_FOCUS_COUNT = 4
CHANGES_WINDOW_DAYS = 7  # P1: from the same weekday last week up to today (ADR 0005)

_SPECIAL = re.compile(r"([\\`*_\[\]<>|#])")


def escape(text: str) -> str:
    """Inline Markdown text: one line, with the characters that would format escaped."""
    return _SPECIAL.sub(r"\\\1", " ".join(text.split()))


def entity_label(name: str | None, entity_id: str) -> str:
    """``Name (`id`)``, or just the id when there is no other name."""
    if not name or name == entity_id:
        return f"`{entity_id}`"
    return f"{escape(name)} (`{entity_id}`)"


def product_label(product: Product | None, product_id: str) -> str:
    return entity_label(product.name if product else None, product_id)


def scope_label(data: ReportInput, scope: str | None) -> str:
    """A product, a kernel or the portfolio, as a risk's scope or a finding's subject."""
    if scope is None or scope == PORTFOLIO:
        return "the portfolio"
    product = data.portfolio.product(scope)
    if product is not None:
        return product_label(product, scope)
    kernel = data.portfolio.kernel(scope)
    return entity_label(kernel.name if kernel else None, scope)


def _days(count: int) -> str:
    return f"{count} day" if count == 1 else f"{count} days"


def _median_days(days: list[int]) -> str:
    """The median clock: '1 day', '12 days', or '46.5 days' between two clocks."""
    median = statistics.median(days)
    return f"{median:g} day" if median == 1 else f"{median:g} days"


@section(2)
def stale(data: ReportInput) -> Section:
    """N2: active products whose clock exceeds stale_days."""
    limit = data.portfolio.config.thresholds.stale_days
    rows = sorted(
        ((clock.days, pid) for pid, clock in data.clocks.items() if clock.days > limit),
        key=lambda row: (-row[0], row[1]),
    )
    if not rows:
        return Section(
            "Stale", (f"Nothing is stale: every active product moved within {limit} days.",), False
        )
    lines = [
        f"Active products whose clock is past stale_days ({limit}):",
        "",
        "| Product | Clock | Next action |",
        "|---|---:|---|",
    ]
    for days, pid in rows:
        product = data.portfolio.product(pid)
        action = escape(product.next_action or "") if product else ""
        lines.append(f"| {product_label(product, pid)} | {_days(days)} | {action} |")
    return Section("Stale", tuple(lines), True)


def _defers_since(data: ReportInput, product_id: str, since: dt.date) -> list[Decision]:
    return [
        d
        for d in data.portfolio.parsed_decisions()
        if d.type == "defer" and d.ids == (product_id,) and d.date is not None and d.date > since
    ]


@section(3)
def escalations(data: ReportInput) -> Section:
    """N3: defer decisions since the latest next_action change reach deferral_limit."""
    limit = data.portfolio.config.thresholds.deferral_limit
    lines = []
    for pid, clock in sorted(data.clocks.items()):
        defers = _defers_since(data, pid, clock.next_action_since)
        if len(defers) >= limit:
            product = data.portfolio.product(pid)
            lines.append(
                f"- {product_label(product, pid)}: deferred {len(defers)} times since its next "
                f"action last changed on {clock.next_action_since} (deferral_limit {limit}) — "
                "split the action, pause or archive"
            )
    if not lines:
        return Section("Escalations", ("No escalations.",), False)
    return Section("Escalations", tuple(lines), True)


@section(4)
def overdue_reviews(data: ReportInput) -> Section:
    """N4: a paused or dormant product's review_by is before today."""
    overdue = sorted(
        (
            p
            for p in data.portfolio.products
            if p.status in ("paused", "dormant")
            and p.review_by is not None
            and p.review_by < data.today
        ),
        key=lambda p: (p.review_by, p.id or ""),
    )
    if not overdue:
        return Section("Overdue reviews", ("No overdue reviews.",), False)
    lines = ["| Product | Status | Review by |", "|---|---|---|"]
    lines += [f"| {product_label(p, p.id or '')} | {p.status} | {p.review_by} |" for p in overdue]
    return Section("Overdue reviews", tuple(lines), True)


@section(5)
def expired_acceptances(data: ReportInput) -> Section:
    """B3: an accepted risk past its accepted_until counts as open again."""
    expired = sorted(
        (
            risk
            for risk in data.portfolio.risks
            if risk.state == "accepted" and not risk.acceptance_holds(data.today)
        ),
        key=lambda risk: (risk.accepted_until or dt.date.min, risk.id or ""),
    )
    if not expired:
        return Section("Expired acceptances", ("No expired acceptances.",), False)
    lines = [
        "Accepted risks whose acceptance has ended; they count as open again:",
        "",
        "| Risk | Scope | Severity | Accepted until |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {entity_label(risk.title, risk.id or '')} | {scope_label(data, risk.scope)} | "
        f"{risk.severity} | {risk.accepted_until} |"
        for risk in expired
    ]
    lines += [
        "",
        (
            "Renew each acceptance with a later accepted_until and a risk_accepted decision, "
            "or mitigate the risk or close it."
        ),
    ]
    return Section("Expired acceptances", tuple(lines), True)


@section(6)
def expired_claims(data: ReportInput) -> Section:
    """Claims past their expiry (P2): each must be verified again before its next use (B4)."""
    config = data.portfolio.config
    expired = []
    for finding in data.portfolio.findings:
        until = config.expiry(finding)
        if finding.type == "claim" and until is not None and until < data.today:
            expired.append((until, finding))
    if not expired:
        return Section("Expired claims", ("No expired claims.",), False)
    lines = [
        "Claims that no longer hold; verify each again before it is used:",
        "",
        "| Claim | About | Used in | Held until |",
        "|---|---|---|---|",
    ]
    for until, claim in sorted(expired, key=lambda pair: (pair[0], pair[1].id or "")):
        used = ", ".join(term.value for term in claim.used_in or ())
        lines.append(
            f"| {entity_label(claim.result, claim.id or '')} | {scope_label(data, claim.subject)} "
            f"| {escape(used)} | {until} |"
        )
    lines += ["", "Once a claim is verified again, update its checked_on and expires_on."]
    return Section("Expired claims", tuple(lines), True)


@section(7)
def copy_paste_debt(data: ReportInput) -> Section:
    """K2: a product consumes a kernel in copy mode; K1 says how far that kernel is."""
    debts = copies(data.portfolio)
    if not debts:
        return Section(
            "Copy-paste debt",
            ("No copy-paste debt: no product carries a copy of a kernel.",),
            False,
        )
    lines = [
        "Products that carry a copy of a kernel instead of using it as a package:",
        "",
        "| Product | Kernel | Kernel state |",
        "|---|---|---|",
    ]
    lines += [
        f"| {product_label(product, product.id or '')} | "
        f"{entity_label(kernel.name, kernel.id or '')} | "
        f"{kernel_state(data.portfolio, kernel).summary} |"
        for product, kernel in debts
    ]
    lines += [
        "",
        "Switch each copy to the package: a kernel is done when enough products use it as one.",
    ]
    return Section("Copy-paste debt", tuple(lines), True)


@section(8)
def changes_without_decision(data: ReportInput) -> Section:
    """P1: the status and state changes since the same weekday last week that no decision
    records, and the ones the product lifecycle does not have (ADR 0005)."""
    start = data.today - dt.timedelta(days=CHANGES_WINDOW_DAYS)
    recent = [change for change in data.changes if start <= change.date <= data.today]
    warnings = list(check_changes(data.portfolio, recent))
    if not warnings:
        return Section(
            "Changes without a decision",
            (f"Every status and state change since {start} has its decision.",),
            False,
        )
    lines = [
        (
            f"Status and state changes since {start} that decisions.md does not record, or "
            "that the product lifecycle does not have:"
        ),
        "",
        "```text",
        *(warning.render() for warning in warnings),
        "```",
        "",
        (
            "A decision records a change when it names the id and carries the change's date; "
            "a decision may be dated in the past."
        ),
    ]
    return Section("Changes without a decision", tuple(lines), True)


@section(9)
def account_activity(data: ReportInput) -> Section:
    """A1–A3: the account's repositories against the portfolio (§7.12)."""
    title = "Account activity"
    account = data.account
    scan = account.scan
    if scan is None:
        if account.failed:
            return Section(title, (f"- **The account was not scanned.** {account.problem}.",), True)
        return Section(title, (f"The account was not scanned: {account.problem}.",), False)
    portfolio = data.portfolio
    outside = outside_portfolio(portfolio, scan)
    inactive = inactive_work(portfolio, scan)
    unknown = unknown_repositories(portfolio, scan)
    visible = shown(scan)
    active_in = sum(1 for repository in visible if worked_on(repository, scan) is not None)
    lines = [
        (
            f"{_count(len(visible), 'repository')} of {scan.login} scanned; your activity "
            f"since {scan.since} is in {active_in} of them."
        )
    ]
    if outside:
        lines += [
            "",
            "Repositories worked on outside the portfolio (A1):",
            "",
            "| Repository | Last worked on |",
            "|---|---|",
            *(f"| `{w.repository.name}` | {w.on} |" for w in outside),
            "",
            (
                "Add each to the repos of its product or kernel, registering a new product as "
                "an idea, or add it to account.ignore in config.yaml."
            ),
        ]
    if inactive:
        lines += [
            "",
            "Products that are not active, but were worked on (A2):",
            "",
            "| Product | Status | Repository | Last worked on |",
            "|---|---|---|---|",
            *(
                f"| {product_label(w.product, w.product.id or '')} | {w.product.status} | "
                f"`{w.repository.name}` | {w.on} |"
                for w in inactive
            ),
            "",
            (
                "Make each product active within wip_limit, with its decision, or stop working "
                "on it."
            ),
        ]
    if unknown:
        lines += [
            "",
            "Listed repositories the account does not have (A3):",
            "",
            "| Listed by | Repository |",
            "|---|---|",
            *(
                f"| {entity_label(u.owner.name, u.owner.id or '')} | `{u.term.value}` |"
                for u in unknown
            ),
            "",
            (
                "Correct each name — a renamed repository goes by its new name — or remove it "
                "from repos."
            ),
        ]
    if not (outside or inactive or unknown):
        lines += [
            "",
            (
                f"Nothing outside the plan: every repository you worked on since {scan.since} "
                "belongs to an active product or a kernel, or is ignored."
            ),
        ]
    lines += _scan_notes(scan)
    return Section(title, tuple(lines), bool(outside or inactive or unknown))


def _scan_notes(scan: AccountScan) -> list[str]:
    notes = []
    unreadable = sum(1 for r in shown(scan) if r.activity == "unreadable")
    if unreadable:
        notes.append(
            f"Your activity could not be told apart from other pushes in "
            f"{_count(unreadable, 'repository')}: {scan.unreadable}. There, a push by anyone "
            "counts."
        )
    if scan.hide_private:
        notes.append("allow_public is set, so private repositories are left out.")
    return [line for note in notes for line in ("", note)]


def _count(number: int, noun: str) -> str:
    plural = f"{noun[:-1]}ies" if noun.endswith("y") else f"{noun}s"
    return f"{number} {noun}" if number == 1 else f"{number} {plural}"


def _focus_decisions(portfolio: Portfolio) -> list[Decision]:
    """Parsed focus decisions, latest first; the later heading wins on the same day."""
    focus = [d for d in portfolio.parsed_decisions() if d.type == "focus" and d.date is not None]
    return sorted(focus, key=lambda d: (d.date, d.line), reverse=True)


def _window_start(today: dt.date) -> dt.date:
    return today - dt.timedelta(days=FOCUS_WINDOW_DAYS - 1)


def this_weeks_focus(portfolio: Portfolio, today: dt.date) -> Decision | None:
    """R3: the latest focus decision dated within the seven days ending today."""
    start = _window_start(today)
    return next(
        (d for d in _focus_decisions(portfolio) if d.date is not None and start <= d.date <= today),
        None,
    )


def evaluate_focus(data: ReportInput, decision: Decision) -> str:
    """'done', 'left active' or 'not done', as §7.4 defines them."""
    pid = decision.ids[0]
    changed = data.next_action_since.get(pid)
    if changed is not None and decision.date is not None and changed > decision.date:
        return "done"
    product = data.portfolio.product(pid)
    if product is None or product.status != "active":
        return "left active"
    return "not done"


def _evaluated(data: ReportInput) -> Iterator[tuple[Decision, str]]:
    start = _window_start(data.today)
    for decision in _focus_decisions(data.portfolio):
        if decision.date is not None and decision.date < start:
            yield decision, evaluate_focus(data, decision)


@section(10)
def focus(data: ReportInput) -> Section:
    """R3: this week's focus, and last week's evaluated."""
    this_week = this_weeks_focus(data.portfolio, data.today)
    lines = []
    if this_week is None:
        lines.append(
            f"- **{NO_FOCUS}.** Record one in decisions.md as "
            f"`## {data.today} · <product> · focus`."
        )
    else:
        pid = this_week.ids[0]
        label = product_label(data.portfolio.product(pid), pid)
        lines.append(f"- This week: {label}, recorded {this_week.date}.")
    last = next(_evaluated(data), None)
    if last is None:
        lines.append("- Last week: no earlier focus decision to evaluate.")
    else:
        decision, verdict = last
        pid = decision.ids[0]
        label = product_label(data.portfolio.product(pid), pid)
        lines.append(f"- Last week: {label}, recorded {decision.date} — **{verdict}**.")
    return Section("Focus", tuple(lines), this_week is None)


@section(11)
def health(data: ReportInput) -> Section:
    """The measures of spec §10. Not items: they never make the report 'have items'."""
    thresholds = data.portfolio.config.thresholds
    active = sum(1 for p in data.portfolio.products if p.status == "active")
    days = [clock.days for clock in data.clocks.values()]
    median = _median_days(days) if days else "no active products"
    stale_count = sum(1 for clock in data.clocks.values() if clock.days > thresholds.stale_days)
    evaluated = [verdict for _, verdict in _evaluated(data)][:EVALUATED_FOCUS_COUNT]
    if evaluated:
        done = evaluated.count("done")
        completion = f"{done} of the last {len(evaluated)} evaluated focus decisions done"
    else:
        completion = "no focus decision old enough to evaluate yet"
    last_commit = str(data.last_data_commit) if data.last_data_commit else "no commit yet"
    states = [kernel_state(data.portfolio, kernel).state for kernel in data.portfolio.kernels]
    kernels = (
        ", ".join(f"{states.count(state)} {state}" for state in ("done", "extracted", "planned"))
        if states
        else "none registered"
    )
    lines = (
        f"- Active products: {active} of wip_limit {thresholds.wip_limit}",
        f"- Median clock of active products: {median}",
        f"- Stale products: {stale_count}",
        f"- Focus completion: {completion}",
        f"- Kernels: {kernels}",
        f"- Account: {_account_health(data)}",
        f"- Last commit touching the data: {last_commit}",
    )
    return Section("Health", lines, False)


def _account_health(data: ReportInput) -> str:
    """The repositories worked on in the window, and how many are outside the portfolio."""
    scan = data.account.scan
    if scan is None:
        return "not scanned"
    worked = sum(1 for repository in shown(scan) if worked_on(repository, scan) is not None)
    outside = len(outside_portfolio(data.portfolio, scan))
    return (
        f"{_count(worked, 'repository')} worked on since {scan.since}, {outside} of them "
        "outside the portfolio"
    )
