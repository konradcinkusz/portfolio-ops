# ADR 0005 — Changes need a decision: what validate and the report compare (P1)

- **Status:** proposed, 2026-09-23 — accepted when the owner merges phase 2
- **Decided by:** the engine's reading of business rules §6 P1 and §8.4, for the owner to
  confirm
- **Governs:** `src/portfolio_ops/history.py`, `src/portfolio_ops/rules/changes.py`, the
  report's Changes without a decision section (rule P1)

## Context

The decision log is the portfolio's memory, and it stays complete only if every change of
a product's status or a risk's state is recorded as a decision. §8.4 rejects a local hook
and asks for a check in CI that each change "is matched by a decision naming that id",
with misses surfaced in the report "as warnings rather than blocking". §6 P1 adds that a
product's status may only move along the transitions of §5, and names two places for the
check: "CI (`validate` against the previous commit)" and `report`.

It leaves open which changes each place looks at, and how a change is dated.

## Decision

**A change** is a product's `status` or a risk's `state` that differs between two
consecutive versions of `products.yaml` or `risks.yaml`. Versions are read exactly as the
clock reads them (ADR 0003): parsed and compared per id, so reordering and reformatting
change nothing. A value outside its vocabulary is a typo, not a status, and is passed
over; a new id is not a change; an id removed and added back keeps its last value.

**Its date** is the committer date, in UTC, of the commit whose version made it (§7.1),
or today when the change is only in the working tree. It is covered by any decision
whose heading names the id and carries that date. A product brought back from `archived`
needs that decision to be an `admit` (§5).

**`validate` compares with the previous commit:** the version at `HEAD~1` is the
reference, and the changes are those in the commits `HEAD~1..HEAD` — one commit, or
everything a merge brings in, each dated by its own commit — plus the working tree. On a
pull request, CI checks out GitHub's merge commit, so validate sees every commit of the
pull request. Outside a git repository there is nothing to compare with and P1 is
skipped silently (validate still works, AC6); on a shallow clone without the previous
commit it prints a note, and the composite action unshallows first.

**The report lists the misses of its week:** every change in the full history, kept when
it is dated from the same weekday last week up to today, under Changes without a
decision. The window overlaps the previous report by one day on purpose: a change made
on the day of a scheduled run, after the run, is in the next week's report instead of
in none.

Every miss is a warning and never changes an exit code.

## Consequences

- A forgotten decision shows up on the push that forgot it, in the log of the CI run,
  and in the next weekly report.
- A miss is fixed by recording the decision with the date the message names — decisions
  may be dated in the past.
- Squash and rebase merges re-date a change to the day of the merge, like every other
  commit date the clock reads. Whoever merges that way records the decision with the
  merge day, or commits the change and its decision directly.
- With history that is not linear, versions follow `git log` order, as the clock's do; a
  change merged from a branch that edited the same file concurrently can be counted
  twice. For a single owner's data repository that is rare.

## Alternatives considered

- **The whole history in the report.** Rejected: a transition outside §5 that already
  happened can never be fixed, so it would keep the weekly issue open for ever, and an
  existing data repository would meet every historical miss at once when it upgrades.
- **The seven days ending today, the focus window of §7.4.** Rejected: with a weekly
  schedule, a change made on the day of a run but after it falls between two windows.
- **Only the last commit, even on a merge.** Rejected: on a pull request GitHub's merge
  commit carries the date the pull request was last pushed, not the date of the change.
- **A tolerance of a day or two around the decision's date.** Rejected: §6 says "dated
  on the day of the change", and the message names the exact date to write.
- **A pre-commit hook.** Rejected by §8.4: it does not run for edits in the web interface
  or on another machine.
