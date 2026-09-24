# CLAUDE.md

Guidance for agents working in this repository. Humans: the same rules are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## The source of truth

[`docs/business-rules.md`](docs/business-rules.md) is the specification. When the code,
a prompt and that document disagree, the document wins and the disagreement is a finding
to report — never a judgement call to make in code. During implementation only the
**Status** and **Entry point** columns of its §6 change.

## Standards that apply

This repository follows the `architecture-standards` marketplace, declared in
[`.claude/settings.json`](.claude/settings.json) (plugins `architecture-core` and
`quality-and-process`). portfolio-ops is a Python CLI and a composite GitHub Action, not a
service, so only part of the constitution applies — [ADR 0001](docs/adr/0001-standards-scope.md)
records which part and why:

- **Apply:** P5 (the secrets are `GITHUB_TOKEN` and the optional, read-only
  `PORTFOLIO_ACCOUNT_TOKEN`, both from the environment, never printed — ADR 0008),
  P8 (optional capabilities degrade: without a token `report` still renders), P10 (rules
  and report sections are registered functions), P11 (YAML and Markdown become typed
  models in `loading.py`; git and GitHub sit behind small adapters), P12 (tag-driven
  releases), P13 (pure rules with unit tests, the clock with integration tests, the action
  with a CI self-test) and P14 (the spec, ADRs with rejected alternatives, the README's
  "How not to use" section).
- **Do not apply:** P1–P4, P6, P7, P9 and P15 — there is no AppHost, database, container,
  Fly.io app, `Program.cs` or runtime telemetry.
- **Guides:** REPO-BASELINE (translated to Python: `pyproject.toml` is the single place
  for versions), TESTING-STRATEGY §5, §6 and §9, OPEN-SOURCE-RELEASE §1, §3, §4 and §6,
  README-BADGES.

## Commands

```bash
python scripts/setup.py                     # one-command setup: .venv, dev tools, hook, tests
.venv/bin/python -m pytest                  # all tests (unit and integration)
.venv/bin/ruff check src tests scripts      # lint
.venv/bin/ruff format src tests scripts     # format
.venv/bin/mypy                              # types, strict for src/
.venv/bin/pre-commit run gitleaks-history --hook-stage manual   # secret scan, full history
.venv/bin/python -m pytest --update-golden  # regenerate golden reports after an intended change
```

On Windows the executables are under `.venv\Scripts\`.

## Rules for changes

- **Real data is never committed** — not in code, fixtures, examples, documentation or
  commit messages. Every name, date and number in tests and examples is invented. This
  repository is public, and a pushed commit is public forever.
- **Paths are always repository-relative** in documentation, scripts and workflows; never
  an absolute path from one machine.
- A rule is a function registered in `src/portfolio_ops/rules/`, with a violating fixture
  under `tests/fixtures/<rule-id>/` and a passing case, and its row in §6 of the spec
  updated.
- A new runtime dependency needs an ADR (the budget is two: PyYAML and jsonschema).
- Third-party actions are pinned by full commit SHA with the version in a comment.
