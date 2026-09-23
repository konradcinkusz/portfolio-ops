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

### Changed

- The README sends a new data repository to
  [portfolio-ops-template](https://github.com/konradcinkusz/portfolio-ops-template), which
  now exists, instead of a hand-made copy of `examples/starter`.

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

[Unreleased]: https://github.com/konradcinkusz/portfolio-ops/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/konradcinkusz/portfolio-ops/releases/tag/v0.3.0
[0.2.0]: https://github.com/konradcinkusz/portfolio-ops/tree/7c55fb2
[0.1.0]: https://github.com/konradcinkusz/portfolio-ops/tree/c8bd6e4
