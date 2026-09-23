# ADR 0004 — One rolling weekly-review issue

- **Status:** accepted, 2026-09-22
- **Decided by:** the repository owner — business rules §7.5 and §8.3
- **Governs:** `src/portfolio_ops/report/publish.py` (rule R1)

## Context

The weekly report has to reach its owner somewhere they will look, every week, without
turning into a pile of stale copies of itself. The report runs from a scheduled workflow
in the private data repository, with a token that can write issues.

## Decision

Publishing keeps **exactly one open issue** labelled `weekly-review` while the report has
items, and none when it has nothing to act on:

| Open issues with the label | Report has items | Action |
|---|---|---|
| none | yes | create one |
| one | yes | update it |
| several | yes | update the oldest, close the rest |
| any | no | close them |
| none | no | nothing |

- The decision is a **pure planner** — a function of the open issues and whether the
  report has items — and a thin executor carries the plan out. The planner is tested
  exhaustively without a network.
- The title is `Weekly review — week of <YYYY-MM-DD>`, the Monday of the report's week, so
  the one issue's title says which week it describes. The body is the report.
- The label is created when missing, with the issue that first needs it.
- `--dry-run` reads the open issues when a token is available, prints the planned action
  and the body, and sends no write request. Without a token it assumes no open issue and
  says so. CI runs it on every pull request against the example data.
- The token is never printed or logged; errors name the method, path and HTTP status.

## Consequences

- One place to look, and a closed issue means "nothing to act on this week".
- The issue's history is the report's history: GitHub keeps every edit of the body.
- Closing an issue by hand while items remain is undone the next week — the report
  reopens the conversation with a new issue, which is the intent.

## Alternatives considered

- **A new issue every week.** Rejected (§8.3): overlapping lists within a month, and the
  owner learns to ignore them — the deduplication discipline the tool asks of its owner,
  broken by the tool itself.
- **One pinned issue that gets a comment a week.** Rejected: the current state sits at
  the bottom of a growing thread, and notifications repeat every week even when nothing
  changed.
- **A file committed to the data repository.** Rejected: nobody is notified, and every
  report becomes a commit that the clock then has to ignore.
- **GitHub Discussions or the wiki.** Rejected: both are optional features a data
  repository may not have enabled, and neither has a state that says "done".
