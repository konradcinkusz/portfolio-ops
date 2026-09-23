<a name="readme-top"></a>

# portfolio-ops

[![Ask me anything](https://flat.badgen.net/static/Ask%20me/anything?icon=github&color=black&scale=1.01)](https://github.com/konradcinkusz "Ask me anything")
[![GitHub license](https://flat.badgen.net/github/license/konradcinkusz/portfolio-ops?icon=github&color=black&scale=1.01)](https://github.com/konradcinkusz/portfolio-ops/blob/main/LICENSE "GitHub license")
[![Maintained](https://flat.badgen.net/static/Maintained/yes?icon=github&color=black&scale=1.01)](https://github.com/konradcinkusz/portfolio-ops/commits/main "Maintained")
[![GitHub branches](https://flat.badgen.net/github/branches/konradcinkusz/portfolio-ops?icon=github&color=black&scale=1.01)](https://github.com/konradcinkusz/portfolio-ops/branches "GitHub branches")
[![GitHub commits](https://flat.badgen.net/github/commits/konradcinkusz/portfolio-ops?icon=github&color=black&scale=1.01)](https://github.com/konradcinkusz/portfolio-ops/commits "GitHub commits")
[![GitHub issues](https://flat.badgen.net/github/issues/konradcinkusz/portfolio-ops?icon=github&color=black&scale=1.01)](https://github.com/konradcinkusz/portfolio-ops/issues "GitHub issues")
[![GitHub pull requests](https://flat.badgen.net/github/prs/konradcinkusz/portfolio-ops?icon=github&color=black&scale=1.01)](https://github.com/konradcinkusz/portfolio-ops/pulls "GitHub pull requests")
[![CI](https://github.com/konradcinkusz/portfolio-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/konradcinkusz/portfolio-ops/actions/workflows/ci.yml "CI")
[![CodeQL](https://github.com/konradcinkusz/portfolio-ops/actions/workflows/codeql.yml/badge.svg)](https://github.com/konradcinkusz/portfolio-ops/actions/workflows/codeql.yml "CodeQL")

portfolio-ops checks the files that describe one person's portfolio of side projects, and
keeps a single weekly-review issue in that person's private repository up to date. It
exists because the only real limit on a pile of side projects is its owner's attention: it
caps how many projects are in progress, flags the ones that have stopped moving, gates
external moves and new ideas on what is already known, and remembers what was decided and
verified, so none of that depends on willpower.

It is a command line and a GitHub Action. Your data — a few YAML files and a Markdown
decision log — stays in a private repository of your own; this repository holds only the
engine and a fictional example.

## Quick start

You need Python 3.11 or newer and git.

```bash
git clone https://github.com/konradcinkusz/portfolio-ops.git
cd portfolio-ops
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install .
portfolio-ops validate --path examples/starter
portfolio-ops report --path examples/starter
portfolio-ops dashboard --path examples/starter --output dashboard.html
```

`validate` checks the fictional portfolio in [examples/starter](examples/starter) against
the rules and prints nothing when it is valid. `report` prints this week's review as
Markdown. `dashboard` writes the whole portfolio as one page to open in a browser.

To install a release without cloning:
`pipx install git+https://github.com/konradcinkusz/portfolio-ops@v0.3.0`.

## Using it for your own portfolio

portfolio-ops is meant to be **reused, not copied** ([ADR 0002](docs/adr/0002-distribution-model.md)):

| Layer | Repository | Visibility | Holds | Updated by |
|---|---|---|---|---|
| Engine | `konradcinkusz/portfolio-ops` (this one) | public | the CLI, the composite action, JSON Schemas, documentation, fictional examples | semver tags |
| Template | [`konradcinkusz/portfolio-ops-template`](https://github.com/konradcinkusz/portfolio-ops-template) | public, a template | a data skeleton and a caller workflow pinned to an engine version | nothing — it holds no logic |
| Data | yours, created from the template | **private** | your real data files | bumping the pinned engine version |

Create your data repository from the template: open
[portfolio-ops-template](https://github.com/konradcinkusz/portfolio-ops-template), choose
**Use this template → Create a new repository**, and make it **Private**. It starts with the
fictional example data, a README on replacing it, and this workflow as
`.github/workflows/portfolio.yml`, with the engine and every action pinned by commit SHA:

```yaml
name: portfolio
on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: "0 7 * * 1"   # weekly review, Mondays 07:00 UTC
  workflow_dispatch:

jobs:
  validate:
    if: github.event_name == 'push' || github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<full-commit-sha>   # vX.Y.Z
        with:
          fetch-depth: 0
      - uses: konradcinkusz/portfolio-ops@<full-commit-sha>   # vX.Y.Z
        with:
          command: validate

  report:
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: write
    steps:
      - uses: actions/checkout@<full-commit-sha>   # vX.Y.Z
        with:
          fetch-depth: 0
      - uses: konradcinkusz/portfolio-ops@<full-commit-sha>   # vX.Y.Z
        with:
          command: report
          publish: "true"

  dashboard:
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<full-commit-sha>   # vX.Y.Z
        with:
          fetch-depth: 0
      - id: portfolio
        uses: konradcinkusz/portfolio-ops@<full-commit-sha>   # vX.Y.Z
        with:
          command: dashboard
      - uses: actions/upload-artifact@<full-commit-sha>   # vX.Y.Z
        with:
          name: portfolio-dashboard
          path: ${{ steps.portfolio.outputs.dashboard }}
          retention-days: 7
```

Pin the action to a release's full commit SHA, with its tag in a comment, or at least to
the tag. The repository name is part of the contract: GitHub does not redirect renamed
action repositories.

The action runs `validate`, `report` and `dashboard`. The gates, `lookup` and `export` are
for the moment you are about to act or to ask — run them in a clone of your data
repository.

### The dashboard as a workflow artifact

The `dashboard` job renders the whole portfolio as one page and keeps it as the workflow
artifact `portfolio-dashboard` for seven days. Only people who can read the repository can
download it.

**Never publish the dashboard with GitHub Pages.** It lists your risks, rejections and
stalled projects, and a Pages site can be public even when its repository is private. The
page says so itself, asks search engines not to index it, and loads nothing from anywhere:
no script, font or image. It works offline, from the artifact or from a local file.

### Action inputs

| Input | Default | What it does |
|---|---|---|
| `command` | — (required) | `validate`, `report` or `dashboard` |
| `path` | `.` | The directory holding the data files, relative to the workspace |
| `publish` | `false` | With `report`: keep one open `weekly-review` issue current |
| `dry-run` | `false` | With `publish`: print the planned action and the issue body, send no write request |
| `github-token` | the workflow's token | Used for the visibility check and for publishing |
| `python-version` | `3.13` | The Python that runs the engine |

| Output | What it holds |
|---|---|
| `dashboard` | With `command: dashboard`: the path of the page, outside the workspace, for `actions/upload-artifact` |

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## The data

All files live in one directory — `--path`, by default the root of the repository.

| File | Required | Content | Schema |
|---|---|---|---|
| `config.yaml` | yes | settings, thresholds and vocabularies | [config.schema.json](src/portfolio_ops/schemas/config.schema.json) |
| `products.yaml` | yes | `products:` — each with a status: idea, active, paused, dormant or archived | [products.schema.json](src/portfolio_ops/schemas/products.schema.json) |
| `decisions.md` | yes | the decision log: one `## <YYYY-MM-DD> · <id>[, <id>…] · <type>` heading per decision | — |
| `kernels.yaml` | no | `kernels:` — shared code products reuse | [kernels.schema.json](src/portfolio_ops/schemas/kernels.schema.json) |
| `risks.yaml` | no | `risks:` — what could go wrong, and where it matters | [risks.schema.json](src/portfolio_ops/schemas/risks.schema.json) |
| `findings.yaml` | no | `findings:` — what was verified, and until when | [findings.schema.json](src/portfolio_ops/schemas/findings.schema.json) |

The JSON Schemas let an editor check a file as you type. With the YAML extension for
VS Code, for example, put this on the first line of `products.yaml`:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/konradcinkusz/portfolio-ops/v0.3.0/src/portfolio_ops/schemas/products.schema.json
```

## Commands

```
portfolio-ops validate [--path DIR]
portfolio-ops report [--path DIR] [--today YYYY-MM-DD] [--publish] [--dry-run] [--repo OWNER/NAME]
portfolio-ops gate PRODUCT --context CONTEXT [--path DIR] [--today YYYY-MM-DD]
portfolio-ops idea-gate IDEA [--path DIR]
portfolio-ops lookup SUBJECT TYPE [--path DIR] [--today YYYY-MM-DD]
portfolio-ops dashboard [--path DIR] [--today YYYY-MM-DD] [--output FILE]
portfolio-ops export [--path DIR] [--today YYYY-MM-DD] [--max-chars N]
portfolio-ops --version
```

- **`validate`** checks the data against the rules and prints one line per finding, such
  as `error S4 products.yaml:14: product 'alpha' is active but has no next_action — add
  next_action or change its status`. In a git repository it also warns about a product's
  status or a risk's state that changed since the previous commit without a decision
  dated that day; it needs no history otherwise, and works outside a repository.
- **`report`** prints the weekly review as Markdown: Stale, Escalations, Overdue reviews,
  Expired acceptances, Expired claims, Copy-paste debt, Changes without a decision, Focus
  and Health. It reads how long each active product has stood still, and what changed
  this week, from git history, so it needs a full clone. `--today` fixes the date, which
  makes the output reproducible.
- **`gate`** asks whether an external move — a store listing, a grant application, a
  talk — may go ahead. It collects the risks of the product, of every kernel it feeds
  from and of the portfolio that apply to the context, and fails on an open high or
  critical risk, or on an expired claim used in that context; an acceptance that still
  holds is a warning. `portfolio-ops gate tidewatch --context app-store --path
  examples/starter` fails on an open licence risk.
- **`idea-gate`** compares an idea with what exists: it lists the products and kernels that
  share its capabilities, and fails while one product has half of them — until an
  `admit` decision names the idea and says why it stands apart.
- **`lookup`** answers "was this already verified?" before a new check: reuse a finding
  that holds, check an expired one again and update it, or record a new one.
- **`dashboard`** writes the whole portfolio as one static HTML page:
  - a summary
  - every product by status, with next actions, clocks and reviews
  - the kernels and their state
  - the risks and findings
  - which products and kernels share each capability
  - the latest decisions with their text

  It shows state and decides nothing. Without git history it leaves out the clocks and
  says why. It writes to standard output unless `--output` names a file.
- **`export`** prints what an LLM session needs to know about the portfolio, as Markdown of
  at most `--max-chars` characters (12000 by default):
  - the active and paused products with their next actions
  - the open risks of severity medium or higher
  - the latest decisions
  - the capability vocabulary

  The decisions, newest first, fill whatever room the rest leaves. Paste it at the start
  of a conversation: `portfolio-ops export | pbcopy` on macOS, `| clip` on Windows.
- **`report --publish`** keeps one open issue labelled `weekly-review` current: it creates,
  updates or closes it. It needs `GITHUB_TOKEN`, and the repository from `--repo` or
  `GITHUB_REPOSITORY`. **`--dry-run`** prints the planned action instead and sends no write
  request.

| Exit code | Meaning |
|---|---|
| 0 | Success; warnings allowed |
| 1 | Rule violations, or a failed gate |
| 2 | Usage or environment problem: unsupported `schema_version`, a shallow clone, a missing token, visibility that cannot be determined in CI |
| 3 | Refused: the data repository is public and `allow_public: true` is not set |

The rules, their ids and their exact meaning are in the
[business rules](docs/business-rules.md#6-rule-catalogue). The messages you are most likely
to meet, with the fix for each, are in [CONTRIBUTING.md](CONTRIBUTING.md#troubleshooting).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## How not to use portfolio-ops

portfolio-ops is a single-owner tool that runs in the owner's own repository. It is not:

- **a team project-management system or an issue tracker.** It keeps one person honest
  about their own attention; it has no assignees, no permissions and no workflow.
- **a hosted service.** It runs in your repository's CI and on your machine, and nowhere
  else.
- **a place for credentials, tokens or personal data about other people.** Record "the
  investor declined", not the person's name.
- **a discovery tool.** Its checks know only what you have registered; a risk you never
  wrote down passes every check.
- **meant for public data repositories.** Your files list your risks, rejections and
  stalled projects. The engine refuses a public repository unless you set
  `allow_public: true` on purpose — for example because you build in public.

And do not fork this repository to hold your data: a fork of a public repository is
public, scheduled workflows are disabled in forks by default, and engine updates would
collide with your data.

## Dependencies

Two runtime dependencies: **PyYAML** and **jsonschema**. With jsonschema's own dependencies
that makes 7 installed packages on Python 3.11 and 6 on 3.13. Everything else — the command
line, the GitHub API calls, git — is the Python standard library. The budget and its
reasons are in [ADR 0001](docs/adr/0001-standards-scope.md).

## Documentation

- [Business rules](docs/business-rules.md) — the specification, and the source of truth
- [Architecture decisions](docs/adr/) — what was chosen, and what was rejected and why
- [Data format migrations](docs/migrations/README.md)
- [Contributing](CONTRIBUTING.md) — setup in one command, commands, troubleshooting
- [Changelog](CHANGELOG.md)

## License

[MIT](LICENSE)

<p align="right">(<a href="#readme-top">back to top</a>)</p>
