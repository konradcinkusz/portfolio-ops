# ADR 0003 — The clock is derived from git, not written by hand

- **Status:** accepted, 2026-09-22
- **Decided by:** the repository owner — business rules §7.2 and §8.2
- **Governs:** `src/portfolio_ops/history.py`, `src/portfolio_ops/git.py` (rule N1)

## Context

Pressure (rules N1–N3) needs to know how long an active product's next action has stood
still. Someone has to record when a next action last moved, and whatever records it will
be wrong in one of two ways: it forgets a real change, or it counts a change that was not
progress.

## Decision

The clock of an active product is today minus the latest of three dates:

1. the date of the commit that starts the most recent unbroken run of versions of
   `products.yaml` in which the product's `next_action` equals its current value;
2. the same for the product's `status` being `active`;
3. its latest `defer` decision in `decisions.md`.

How it is read:

- The engine lists the commits that touched `<path>/products.yaml`, newest first, and
  reads every version in one `git cat-file --batch` call.
- Each version is **parsed** and compared **per product id**, after whitespace is
  normalised. Reordering products, reformatting the file, comments and edits to other
  fields therefore never reset a clock. A version that does not parse is skipped with a
  warning.
- The working tree is the newest version, dated today: an uncommitted change counts as a
  change made today, and so does a product that is in no commit yet.
- Commit times are committer timestamps, converted to UTC dates (§7.1).
- Only `report` needs history. On a shallow clone it exits 2 with a message that names
  `fetch-depth: 0`; the composite action unshallows the checkout itself first. `validate`
  needs no history and works outside a repository.

## Consequences

- Nothing to maintain by hand: editing the next action *is* the signal.
- A conscious postponement is a `defer` decision, which the log keeps and N3 counts,
  rather than a quietly edited date.
- Accepted risk (business rules §11): commit dates can be rewritten by a rebase, an amend
  or a forged date, and the clock then resets without progress. The owner only deceives
  themselves, and the history stays auditable.
- `report` costs a full clone. For a data repository that is small.

## Alternatives considered

- **A hand-edited `last_touched` field.** Rejected (§8.2): a forgotten update raises a
  false alarm, and a cosmetic edit resets the clock without progress.
- **File modification times.** Rejected: a fresh clone sets them all to the clone's time.
- **`git blame` on the `next_action` line.** Rejected: blame follows lines, not values, so
  reformatting or moving a product resets the clock — the failure the per-id comparison
  exists to prevent.
- **The date of the last commit touching the product at all.** Rejected: it counts edits
  to the name or to capabilities as progress.
