"""The report sections of spec §7.4: Stale (N2), Escalations (N3), Overdue reviews (N4),
Focus (R3) and Health. Section 1, Validation errors, is rendered by render.py because it
replaces the others rather than preceding them.
"""

from __future__ import annotations

import datetime as dt
import re
import statistics
from collections.abc import Iterator

from portfolio_ops.model import Decision, Product
from portfolio_ops.report import ReportInput, Section, section

NO_FOCUS = "No focus recorded this week"
FOCUS_WINDOW_DAYS = 7  # "the seven days ending today"
EVALUATED_FOCUS_COUNT = 4

_SPECIAL = re.compile(r"([\\`*_\[\]<>|#])")


def escape(text: str) -> str:
    """Inline Markdown text: one line, with the characters that would format escaped."""
    return _SPECIAL.sub(r"\\\1", " ".join(text.split()))


def product_label(product: Product | None, product_id: str) -> str:
    if product is None or not product.name or product.name == product_id:
        return f"`{product_id}`"
    return f"{escape(product.name)} (`{product_id}`)"


def _days(count: int) -> str:
    return f"{count} day" if count == 1 else f"{count} days"


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


def _focus_decisions(data: ReportInput) -> list[Decision]:
    """Parsed focus decisions, latest first; the later heading wins on the same day."""
    focus = [
        d for d in data.portfolio.parsed_decisions() if d.type == "focus" and d.date is not None
    ]
    return sorted(focus, key=lambda d: (d.date, d.line), reverse=True)


def _window_start(today: dt.date) -> dt.date:
    return today - dt.timedelta(days=FOCUS_WINDOW_DAYS - 1)


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
    for decision in _focus_decisions(data):
        if decision.date is not None and decision.date < start:
            yield decision, evaluate_focus(data, decision)


@section(5)
def focus(data: ReportInput) -> Section:
    """R3: this week's focus, and last week's evaluated."""
    start = _window_start(data.today)
    this_week = next(
        (d for d in _focus_decisions(data) if d.date is not None and start <= d.date <= data.today),
        None,
    )
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


@section(6)
def health(data: ReportInput) -> Section:
    """The measures of spec §10. Not items: they never make the report 'have items'."""
    thresholds = data.portfolio.config.thresholds
    active = sum(1 for p in data.portfolio.products if p.status == "active")
    days = [clock.days for clock in data.clocks.values()]
    median = f"{statistics.median(days):g} days" if days else "no active products"
    stale_count = sum(1 for clock in data.clocks.values() if clock.days > thresholds.stale_days)
    evaluated = [verdict for _, verdict in _evaluated(data)][:EVALUATED_FOCUS_COUNT]
    if evaluated:
        done = evaluated.count("done")
        completion = f"{done} of the last {len(evaluated)} evaluated focus decisions done"
    else:
        completion = "no focus decision old enough to evaluate yet"
    last_commit = str(data.last_data_commit) if data.last_data_commit else "no commit yet"
    lines = (
        f"- Active products: {active} of wip_limit {thresholds.wip_limit}",
        f"- Median clock of active products: {median}",
        f"- Stale products: {stale_count}",
        f"- Focus completion: {completion}",
        f"- Last commit touching the data: {last_commit}",
    )
    return Section("Health", lines, False)
