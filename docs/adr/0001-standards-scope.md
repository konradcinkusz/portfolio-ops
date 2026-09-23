# ADR 0001 — Which standards apply, and what they mean for a Python tool

- **Status:** accepted, 2026-09-22
- **Decided by:** the repository owner, with decisions D1, D4 and D5 of the phase-1 prompt
- **Governs:** the whole repository

## Context

portfolio-ops follows the `architecture-standards` marketplace: the reference architecture
(P1–P15) and its guides. That constitution was written for services — .NET, an Aspire
AppHost, a database per service, containers on Fly.io. portfolio-ops is a Python command
line and a composite GitHub Action that reads files in its user's repository. Applying
every principle literally would produce ceremony with no failure behind it; applying none
would lose the rules that were written because something broke.

## Decision

**Principles that apply**, and what each means here:

| Principle | In this repository |
|---|---|
| P5 | The only secret is `GITHUB_TOKEN`. It is read from the environment, never printed or logged. gitleaks scans every commit (pre-commit) and the full history (CI). |
| P8 | Optional capabilities degrade: without a token `report` still renders and `--dry-run` still plans; only `--publish` fails, naming the variable. |
| P10 | Rules and report sections are functions registered in a registry, not subclasses. |
| P11 | YAML and Markdown become typed models once, in `loading.py`. git and the GitHub REST API sit behind `git.py` and `github.py`. Rules never see YAML. |
| P12 | Releases are tag-driven: a `v*` tag creates the GitHub Release. There is no deploy. |
| P13 | Rules are pure functions with unit tests; the clock has integration tests on real temporary repositories; the action has a CI self-test. |
| P14 | The specification, these ADRs, and the README's "How not to use portfolio-ops". |

**Principles that do not apply:** P1–P4, P6, P7, P9 and P15. There is no AppHost, no
database, no container, no Fly.io app, no `Program.cs` and no runtime telemetry to design.

**REPO-BASELINE, translated to Python:**

| Section | Here |
|---|---|
| §1 the baseline | CODEOWNERS, Dependabot (pip, actions, pre-commit), `.editorconfig`, a real `.gitattributes`, templates, secret scanning, CodeQL and a dependency audit, CI running what the repository claims. `.dockerignore` and `Directory.*.props` do not apply; `pyproject.toml` is the single place for versions. |
| §2 secret hygiene | gitleaks in pre-commit and CI; `secrets.env.example` documents every variable with its tier; `.env` is gitignored. |
| §3 one-command onboarding | `python scripts/setup.py` (D4). There is no mandatory secret to generate; `GITHUB_TOKEN` is the one optional setting and the script says what it enables. |
| §4 operational scripts | None exist: there is nothing to build, push, deploy or destroy. |
| §4a the product's users | Their onboarding is the template repository, planned before phase 2 and out of scope here. |
| §4b dependency budget | Two runtime dependencies (D1), published with the installed count in the README. A third needs an ADR. |
| §4c research artifacts | The arithmetic behind the thresholds is written down in business rules §8.1 and pinned by tests; the rule catalogue carries status and entry point for each rule (§6). No notebook: there is no statistical model to trace. |
| §5 workflow lifecycle | Nothing retired yet; a retired workflow will move to `.github/workflows-archive/`. |
| §6 agent definitions | `CLAUDE.md` and `.claude/settings.json` are versioned here; paths are repository-relative. |
| §7 standards adoption | `.claude/settings.json` declares the marketplace and enables `architecture-core` and `quality-and-process`. |
| §8 documentation staleness | Tests check that the README's options and action inputs exist and that the troubleshooting table quotes messages the engine really prints. |

**D1 — the runtime.** Python 3.11 or newer, standard library first: `argparse` for the
command line, `urllib` for the GitHub API, `subprocess` for git. Runtime dependencies are
PyYAML and jsonschema only. Development uses pytest, ruff, mypy (strict for `src/`) and
pip-audit. CI tests on 3.11 and 3.13, the oldest and the newest supported versions.

**D5 — the procedure.** The estate's `/implementation-phase` presupposes services —
bounded contexts, persistence, an HTTP surface, an AppHost — so phase 1 followed its own
procedure (block 9 of the phase-1 prompt). This is a deliberate deviation from
GENERATE-MASTER-PROMPT.md §2, block 9.

## Consequences

- Reviews check the principles in the first table and skip the rest without a finding.
- Python and git are preinstalled on GitHub-hosted runners, so the action needs no
  container and starts in seconds.
- The dependency count is public. jsonschema brings its own dependencies (attrs,
  referencing, rpds-py, jsonschema-specifications, and typing-extensions before Python
  3.13); that is the cost of validating against the same schemas editors use.

## Alternatives considered

- **Apply the whole constitution anyway.** Rejected: an AppHost, a database abstraction
  or telemetry for a tool that runs for seconds in CI would be ceremony, and ceremony
  teaches readers to skip the rules that matter.
- **A JavaScript action.** Rejected: the natural toolchain for a JavaScript action commits
  a bundled `dist/` of third-party code into the repository — exactly the supply-chain
  surface a tool that reads private data should not carry — and would need a second
  runtime for the command line.
- **A Docker container action.** Rejected: every run pays an image build or pull, the
  image is a second thing to pin and keep current, and Docker actions do not run on macOS
  or Windows runners.
- **Hand-rolling YAML parsing or JSON Schema validation to keep dependencies at zero.**
  Rejected under REPO-BASELINE §4b: neither protocol subset is small, and the editors
  already validate against the same JSON Schemas.
