# ADR 0009 — The overview: Markdown pages committed to the private repository

- **Status:** accepted, 2026-09-24, with the merge of phase 5
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
repository, on the web or in GitHub's mobile app. ADR 0007 rejected a Markdown dashboard
because an issue body cannot show everything; Markdown files in the repository can. The
constraints of V1 and §8.8 still hold:

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
- It decides nothing. Its "Needs attention" list repeats what the weekly report and the
  dashboard already make stand out, each item with a link to the page that has the
  details.
- Every value from the data is Markdown-escaped, including the characters GitHub gives a
  meaning beyond CommonMark: `~`, `$` and `&`. A decision's text keeps its line breaks in
  a block quote, and nothing in it formats.
- A Mermaid label keeps only letters, digits, spaces and `. - _ /`, so no name can break a
  chart or start a Mermaid keyword; a task on the timeline starts with fixed text.
- With `allow_public`, no private repository is named.

**The charts show what the data knows.**

- The pie counts the repositories with the owner's activity in the window by the product
  or kernel that lists them, and the ignored and outside ones. The scan knows where the
  work went, not how much of it there was.
- The timeline shows the review dates of the paused and dormant products, with the
  pages' own date as a milestone. Mermaid's marker for the reader's today is off: a page
  generated on Monday and read on Friday would otherwise show two different todays.

**It never overwrites what it did not write.** Each page starts with an HTML comment that
says portfolio-ops generated it. A file without that comment where a page would go — the
owner's README, with `--output` at the repository's root — stops the command with exit 2
before anything is written.

**Written by the workflow, with the least privilege that can write.**

1. The **overview job** runs the engine with `contents: read`. It uploads the pages as a
   one-day artifact.
2. The **publish-overview job** holds `contents: write`, but runs no portfolio-ops code and
   no action but `actions/checkout`.
   - It downloads the pages from its own run with GitHub's preinstalled `gh`, which is why
     it also needs `actions: read`.
   - It replaces `overview/` and commits only when something changed.
   - If `main` moved on while the pages were rendered, it pushes nothing: a newer run
     renders newer data and publishes it. Any other refusal of the push fails the job.

A push made with the workflow's token starts no new run, so the jobs cannot loop. The
overview job runs after every push to `main`, weekly and on demand, so the pages follow the
data.

**Bookkeeping follows.**

- The Health line "last commit touching the data" leaves `overview/` aside, so the bot's
  commits do not look like the owner's.
- In GitHub Actions the report's header links the overview next to the workflow run, when
  the data directory holds pages the overview wrote. The link goes to the default branch
  (`HEAD`), where the publish job commits them.

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
- **Rebasing and pushing again when `main` moved.** Rejected: pages rendered from an older
  commit would land on top of newer data, and a rebase needs a committer identity that a
  runner does not have.
- **`actions/download-artifact`.** Not needed: `gh` is preinstalled on GitHub-hosted
  runners and adds no third-party code to pin.
- **Generating the root `README.md`.** Rejected: it belongs to the owner, and a generated
  one would overwrite their notes. The root README links the overview instead.
- **Deleting the other files of the output directory.** Rejected: `--output` may name a
  directory that holds anything. The publish job replaces `overview/` as a whole, so a page
  that a later version drops disappears there.
- **Sizing the pie by commits or lines changed.** Rejected: it would read each
  repository's history, beyond the read-only `Metadata` permission the account token has,
  with many more requests on every run.
