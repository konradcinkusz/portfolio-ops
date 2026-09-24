# Changelog

Notable changes to portfolio-ops. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the versions follow
[Semantic Versioning](https://semver.org/). While the version is 0.x anything may change
(business rules §9.4), but a breaking change to the data format always increments
`schema_version` and adds a note to [docs/migrations/](docs/migrations/README.md).

To release, replace "Unreleased" with the date, then create the tag, with git or in the
GitHub portal (CONTRIBUTING.md, Releasing); the release workflow refuses an undated entry.
0.3.0 is the first version published as a release. It includes 0.1.0 and 0.2.0, whose
links point at the commits they describe.

## [Unreleased]

## [0.5.0] — 2026-09-24

Phase 5 of the [business rules](docs/business-rules.md) (§9.6), and their revision r5: the
overview. The weekly issue lists only what needs the owner and the dashboard is a file to
download; the owner asked for a complete picture to browse. The data format is unchanged —
`schema_version` stays 1.

### Added

- **The overview** (V3, §7.11, [ADR 0009](docs/adr/0009-overview-pages.md)):
  `portfolio-ops overview` writes the whole portfolio as five linked Markdown pages, which
  GitHub renders in the private data repository, on the web and in its mobile app:
  - `README.md`: the numbers at a glance, what needs attention, this week's focus and next
    actions, where the week's work went as a Mermaid pie, and the latest decisions
  - `products.md`: every product by status and every kernel, with the review dates on a
    Mermaid timeline
  - `repositories.md`: the account's repositories, those worked on this week first
  - `risks.md`: the risks, the findings and the copy-paste debt
  - `decisions.md`: every decision, newest first, with its text

  Like the dashboard it shows state and decides nothing, reads the history and scans the
  account when it can, and works without either. Every value from the data is escaped,
  and a Mermaid label keeps only letters, digits, spaces and a few safe marks. It writes
  to `overview/` in the data directory, or to `--output DIR`, and never overwrites a file
  it did not write.
- The action's `overview` command and output: the pages go to a directory outside the
  workspace, for an artifact. The caller workflow gains the overview job, which renders
  them with read permissions after every push to `main`, weekly and on demand, and the
  publish-overview job, which commits them to `overview/` when they changed. The publish
  job runs no portfolio-ops code.
- In GitHub Actions, the report's header links the overview when the data repository has
  one.
- CI renders the example overview in the action self-test and keeps it as an artifact.

### Changed

- "Last commit touching the data" in the report's Health leaves `overview/` aside, so the
  workflow's commits of the overview do not count as the owner's.
- The account scan also runs for `overview`, and the action passes `account-token` to it.
- ADR 0007 is amended: the Markdown view it rejected is now the overview.

## [0.4.1] — 2026-09-24

The first scan of a real account read only its public repositories, and said nothing:
the token had GitHub's default repository access, "Public repositories". The
[business rules](docs/business-rules.md) are at revision r4 (§7.12, Coverage).

### Added

- The scan checks what the token sees. When the account's private data repository is not
  among the repositories the token lists, the weekly issue shows one item: the token
  sees only public repositories, and its repository access should be "All repositories".
  The dashboard shows the same as a note, and Health says "public repositories only".
- The report's Account activity section and the dashboard's Repositories panel count the
  public and the private repositories they read. The panel marks each private
  repository.
- In GitHub Actions, the report's header links the workflow run whose artifacts hold the
  dashboard, so the weekly issue leads to the page.

### Changed

- ADR 0008 is accepted with phase 4, and records the coverage check.
- The README warns that GitHub preselects "Public repositories" for a new token.

## [0.4.0] — 2026-09-24

Phase 4 of the [business rules](docs/business-rules.md) (§9.5), and their revision r3: the
account scan. The data format is unchanged — `schema_version` stays 1, and every new field
is optional.

### Added

- **The account scan** (§7.12, [ADR 0008](docs/adr/0008-account-scan.md)). With
  `PORTFOLIO_ACCOUNT_TOKEN` set, `report` and `dashboard` ask GitHub which repositories the
  owner's account has, and which of them the owner worked on since the same weekday last
  week. The token is a fine-grained, read-only token. The owner's own activity counts,
  not Dependabot's. Without the token nothing changes.
- The report's section 9, **Account activity**:
  - A1: repositories worked on outside the portfolio
  - A2: products that are not active, but were worked on
  - A3: listed repositories the account does not have

  Health counts the repositories worked on and how many are outside the portfolio. Focus
  and Health are now sections 10 and 11.
- The dashboard's **Repositories** panel, an "Outside the plan" tile, and a Last push
  column for the active, paused and dormant products.
- `repos` on products and kernels, and `account.ignore` in `config.yaml`, checked offline
  by the new rule **S8**.
- The action's `account-token` input. It is passed to `report` and `dashboard` only, and
  `validate` warns if it is given one.
- The README's "Scanning the account", with the token's setup, and troubleshooting rows
  for every new message.

### Changed

- A failed scan never changes the exit code:
  - A classic token (`ghp_…`) is refused before anything is sent.
  - A rejected token is one report item that says how to fix it.
  - An activity list GitHub will not show falls back to the push date, and the report says
    so.
- The README sends a new data repository to
  [portfolio-ops-template](https://github.com/konradcinkusz/portfolio-ops-template), which
  now exists, instead of a hand-made copy of `examples/starter`.
- ADR 0007 is accepted, with the merge of phase 3. ADR 0001 is amended for the second
  secret, and ADR 0002 names the template repository.
- The fictional starter example lists its repositories and an ignore pattern.

### Upgrading a data repository

Dependabot bumps the pinned SHA; add the account token by hand:

1. Create the token and the secret as the README's "Scanning the account" says.
2. Add `account-token: ${{ secrets.PORTFOLIO_ACCOUNT_TOKEN }}` under `with:` in the report
   and dashboard jobs of `.github/workflows/portfolio.yml`.
3. Add `repos` to your products and kernels.

## [0.3.0] — 2026-09-23

Phase 3 of the [business rules](docs/business-rules.md) (§9.3), and their revision r2.

### Added

- `portfolio-ops dashboard`: the whole portfolio as one static HTML page (V1), with:
  - summary tiles
  - every product by status, with next actions, clocks and reviews
  - kernels with their state (K1) and consumers
  - risks and findings, with what has lapsed
  - the capability map
  - the latest decisions with their text

  The page is self-contained: the stylesheet is inline, it loads nothing, and a
  Content-Security-Policy allows only that stylesheet. It says it is private and asks
  not to be indexed. Without git history it leaves out the clocks and says why.
  `--output FILE` writes it to a file.
- `portfolio-ops export`: size-bounded Markdown for an LLM session (V2), holding:
  - the active and paused products with their next actions
  - the open risks of severity medium or higher
  - the latest decisions, which fill what `--max-chars` leaves (12000 by default)
  - the capability vocabulary
- The action runs `command: dashboard` and sets the output `dashboard` to the page's path,
  for `actions/upload-artifact`. CI keeps the example dashboard as an artifact.
- ADR 0007 (the views).

### Changed

- Each decision keeps the text under its heading, which both views show.
- ADRs 0005 and 0006 are accepted, with the merge of phase 2.
- The [business rules](docs/business-rules.md) are at revision r2. It folds in what phases
  1–3 decided where r1 was silent, and changes no behaviour:
  - the whole command-line interface and the action's `dashboard` output (§7.6)
  - the report's ten sections (§7.4)
  - change coverage (§7.9), the gates and lookup (§7.10) and the views (§7.11)
  - the dashboard job of the caller workflow (§3)
  - clearer texts for B1, B5, B6, K1, K2 and P2
- The README's caller workflow is r2's, with the dashboard job and the engine pinned by
  commit SHA. Its install line and schema URL name v0.3.0.
- A release can be published from the GitHub portal: the release workflow completes a
  release that already exists instead of failing to create it again.

### Fixed

- The report's Health line read "Median clock of active products: 1 days"; it now reads
  "1 day".

## [0.2.0] — 2026-09-23

Phase 2 of the [business rules](docs/business-rules.md), revision r1 (§9.2).

### Added

- `portfolio-ops gate PRODUCT --context CONTEXT`: may an external move go ahead? It
  collects the risks of the product, of every kernel it feeds from and of the portfolio
  that apply to the context (B1), fails on an open high or critical risk (B2) or on an
  expired claim used there (B4), and warns about an acceptance that still holds (B3).
- `portfolio-ops idea-gate IDEA`: the products and kernels that share an idea's
  capabilities, as a Markdown report (B5); it fails while one product has half of them
  and no `admit` decision names the idea (B6).
- `portfolio-ops lookup SUBJECT TYPE`: reuse a finding that holds, check an expired one
  again, or record a new one (P3).
- P1: `validate` warns about a product's status or a risk's state that changed since the
  previous commit without a decision dated that day, and about a transition the product
  lifecycle (§5) does not have. It never changes the exit code.
- Four report sections (R2): Expired acceptances, Expired claims, Copy-paste debt (K2,
  with each kernel's derived state, K1) and Changes without a decision (P1). Health
  counts the kernels by state.
- ADRs 0005 (change coverage) and 0006 (the gates as commands).

### Changed

- The composite action fetches the full history for `validate` too, so P1 can compare
  with the previous commit.
- The report's note under validation errors no longer lists the other sections by name.

## [0.1.0] — 2026-09-23

Phase 1 of the [business rules](docs/business-rules.md), revision r1 (§9.1).

### Added

- `portfolio-ops validate`: the structure rules S1–S5, the limit rules L1 and L2 and the
  memory rule P2, one line per finding in the form `error S4 products.yaml:14: …`.
  Problems that no catalogue rule covers — invalid YAML, unknown keys, wrong types —
  are reported with the label `schema`.
- `schema_version` checking (S6) and the visibility guard (S7) before any other data file
  is read: exit 2 for an unsupported version, exit 3 for a public data repository without
  `allow_public: true`.
- `portfolio-ops report`: the weekly report in Markdown — Stale (N2), Escalations (N3),
  Overdue reviews (N4), Focus (R3) and Health — with the clock of each active product read
  from git history (N1). `--today` makes it deterministic.
- `report --publish`: one rolling `weekly-review` issue (R1), and `--dry-run` to preview
  it without writing.
- A composite GitHub Action (`action.yml`) that installs the engine from its own checkout.
- JSON Schemas for the data files, shipped in the package, for editors.
- A fictional example portfolio in `examples/starter/`.
- The repository baseline: MIT licence, CI (lint, types, tests on Python 3.11 and 3.13,
  dependency audit, secret scan, action self-test), CodeQL, a tag-driven release workflow,
  Dependabot, templates and ADRs 0001–0004.

[Unreleased]: https://github.com/konradcinkusz/portfolio-ops/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/konradcinkusz/portfolio-ops/releases/tag/v0.5.0
[0.4.1]: https://github.com/konradcinkusz/portfolio-ops/releases/tag/v0.4.1
[0.4.0]: https://github.com/konradcinkusz/portfolio-ops/releases/tag/v0.4.0
[0.3.0]: https://github.com/konradcinkusz/portfolio-ops/releases/tag/v0.3.0
[0.2.0]: https://github.com/konradcinkusz/portfolio-ops/tree/7c55fb2
[0.1.0]: https://github.com/konradcinkusz/portfolio-ops/tree/c8bd6e4
