# ADR 0009 — The overview: Markdown pages committed to the private repository

- **Status:** proposed, 2026-09-24 — accepted when the owner merges phase 5
- **Decided by:** the owner, who found the weekly issue "at most a log" and asked for a
  complete summary to browse — a page or a wiki (business rules r5); the details are the
  engine's reading of §7.11, for the owner to confirm
- **Governs:** `src/portfolio_ops/views/overview.py`, the `overview` command, the action's
  `overview` command and output, the overview and publish-overview jobs of the caller
  workflow

## Context

portfolio-ops shows its state in three places:

- The **weekly issue** is a to-do list by design (ADR 0004). It shows only what needs the
  owner, and it closes when nothing does.
- The **dashboard** (V1) shows everything, but it is a zip file attached to a workflow run.
  Seeing it takes a download and an unzip.
- The **export** (V2) is text for a language model.

Nothing gives the owner a complete picture that opens where they already are: in the
repository, on the web or in GitHub's mobile app. The constraints of V1 and §8.8 still
hold:

- the data is private;
- a GitHub Pages site of a private repository can be public;
- there is no hosted service (§2).

## Decision

**Markdown pages in `overview/` of the data repository.** GitHub renders Markdown files
with tables, links between pages, collapsible sections and Mermaid charts. It shows them to
exactly the people who can read the repository. Five pages, registered like the report's
sections (P10):

| Page | Holds |
|---|---|
| `README.md` | the home page: numbers at a glance, what needs attention, this week's focus and next actions, where the week's work went (a Mermaid pie), the latest decisions |
| `products.md` | every product by status, every kernel, the review dates on a Mermaid timeline |
| `repositories.md` | the account's repositories: those worked on in the window first, then all of them, forks and archived ones folded away |
| `risks.md` | risks, findings and copy-paste debt |
| `decisions.md` | every decision, newest first, with its text |

**A view like the others.**

- `overview` validates first, reads the history for the clocks when there is one, and
  scans the account when the token is set.
- It decides nothing.
- Every value from the data is Markdown-escaped. Mermaid labels are cut down to letters,
  digits, spaces and a few safe marks.
- With `allow_public`, no private repository is named.

**Written by the workflow, with the least privilege that can write.**

1. The **overview job** runs the engine with `contents: read`. It uploads the pages as a
   one-day artifact.
2. The **publish-overview job** holds `contents: write`, but runs no portfolio-ops code and
   no action but `actions/checkout`.
   - It downloads the pages from its own run with GitHub's preinstalled `gh`, which is why
     it also needs `actions: read`.
   - It replaces `overview/` and commits only when something changed.
   - It retries the push once after a rebase, for when `main` moved meanwhile.

A push made with the workflow's token starts no new run, so the jobs cannot loop. The
overview job runs after every push to `main`, weekly and on demand, so the pages follow the
data.

**Bookkeeping follows.**

- The Health line "last commit touching the data" leaves `overview/` aside, so the bot's
  commits do not look like the owner's.
- In GitHub Actions the report's header links the overview next to the workflow run.

## Consequences

- The data repository's history gains the bot's commits in `overview/`: at most one a
  push and one a week. They touch no data file, so the clock (N1) and change coverage
  (P1), which read `products.yaml` and `risks.yaml`, never see them.
- A data repository made from an older template needs the two jobs added by hand.
  Dependabot bumps only the pin.
- Branch protection that forbids direct pushes to `main` stops the publish job. The
  overview then stays an artifact of the run, and the job's failure says why.

## Alternatives considered

- **GitHub Pages.** Rejected (V1, §8.8): the site of a private repository can be public,
  depending on the plan.
- **The repository's wiki.** Rejected:
  - A private repository's wiki needs a paid plan.
  - The workflow's token cannot push to a wiki, so it would take a second token that can
    write.
- **An interactive page with a script.** Rejected:
  - It still needs a download.
  - It gives up the dashboard's rule of loading nothing, for filtering that a browser's
    find already does.
- **Rendering and committing in one job.** Rejected: the engine and the packages it
  installs from PyPI would run with a token that can write to the data repository.
- **`actions/download-artifact`.** Not needed: `gh` is preinstalled on GitHub-hosted
  runners and adds no third-party code to pin.
- **Generating the root `README.md`.** Rejected: it belongs to the owner, and a generated
  one would overwrite their notes. The root README links the overview instead.
