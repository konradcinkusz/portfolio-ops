# Changelog

Notable changes to portfolio-ops. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the versions follow
[Semantic Versioning](https://semver.org/). While the version is 0.x anything may change
(business rules §9.4), but a breaking change to the data format always increments
`schema_version` and adds a note to [docs/migrations/](docs/migrations/README.md).

To release, replace "Unreleased" with the date, then push the tag; the release workflow
refuses an undated entry.

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

[0.1.0]: https://github.com/konradcinkusz/portfolio-ops/releases/tag/v0.1.0
