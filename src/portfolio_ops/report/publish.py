"""Publishing the report (R1, spec §7.5): one rolling issue, not one issue a week.

The decision is a pure function — ``plan`` — of the open ``weekly-review`` issues and
whether the report has items. The executor only carries a plan out. A dry run makes the
plan, prints it, and stops: it may read, it never writes (ADR 0004).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from portfolio_ops.github import GitHubClient, Issue, Transport
from portfolio_ops.report.render import Rendered

LABEL = "weekly-review"
LABEL_COLOR = "5319e7"
LABEL_DESCRIPTION = "The weekly review that portfolio-ops keeps current"
MAX_BODY = 65_000  # GitHub rejects issue bodies over 65,536 characters
TRUNCATED = "\n\n*The report was truncated here; run `portfolio-ops report` for all of it.*\n"


@dataclass(frozen=True)
class Plan:
    create: bool = False
    update: int | None = None
    close: tuple[int, ...] = ()

    def describe(self, repository: str, title: str) -> str:
        steps = []
        if self.create:
            steps.append(f'create issue "{title}" in {repository}, labelled {LABEL}')
        if self.update is not None:
            steps.append(f'update issue #{self.update} in {repository} to "{title}"')
        if self.close:
            numbers = ", ".join(f"#{n}" for n in self.close)
            steps.append(f"close {numbers} in {repository}")
        if not steps:
            return f"nothing to do: no open {LABEL} issue and the report has no items"
        return "; then ".join(steps)


def plan(open_issues: Sequence[Issue], has_items: bool) -> Plan:
    """Keep exactly one open weekly-review issue while there is something to review."""
    ordered = sorted(open_issues, key=lambda issue: (issue.created_at, issue.number))
    if not has_items:
        return Plan(close=tuple(issue.number for issue in ordered))
    if not ordered:
        return Plan(create=True)
    return Plan(update=ordered[0].number, close=tuple(issue.number for issue in ordered[1:]))


def issue_body(rendered: Rendered) -> str:
    if len(rendered.markdown) <= MAX_BODY:
        return rendered.markdown
    return rendered.markdown[:MAX_BODY] + TRUNCATED


def publish(
    *,
    rendered: Rendered,
    repository: str,
    token: str | None,
    transport: Transport,
    api_url: str,
    dry_run: bool,
    say: Callable[[str], object],
) -> Plan:
    """Plan the change and, unless this is a dry run, carry it out."""
    client = GitHubClient(transport, token, api_url)
    if token:
        open_issues = client.open_issues(repository, LABEL)
    else:  # only a dry run gets here without a token
        say(f"no GITHUB_TOKEN: assuming {repository} has no open {LABEL} issue")
        open_issues = []
    the_plan = plan(open_issues, rendered.has_items)
    body = issue_body(rendered)
    if dry_run:
        label_missing = the_plan.create and token and not client.label_exists(repository, LABEL)
        note = (
            f" (the {LABEL} label is missing and would be created first)" if label_missing else ""
        )
        say(f"dry run: planned action: {the_plan.describe(repository, rendered.title)}{note}")
        say("dry run: the issue body is the report printed above; no write request was sent")
        return the_plan
    if the_plan.create:
        if not client.label_exists(repository, LABEL):
            client.create_label(repository, LABEL, LABEL_COLOR, LABEL_DESCRIPTION)
            say(f"published: created the {LABEL} label in {repository}")
        number = client.create_issue(repository, rendered.title, body, LABEL)
        say(f"published: created issue #{number} in {repository}")
    if the_plan.update is not None:
        client.update_issue(repository, the_plan.update, rendered.title, body)
        say(f"published: updated issue #{the_plan.update} in {repository}")
    for number in the_plan.close:
        client.close_issue(repository, number)
        say(f"published: closed issue #{number} in {repository}")
    if not the_plan.create and the_plan.update is None and not the_plan.close:
        say(f"published: {the_plan.describe(repository, rendered.title)}")
    return the_plan
