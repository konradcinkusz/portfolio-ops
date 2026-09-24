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
verified, so none of that depends on willpower. With a read-only token it also watches
the owner's GitHub account, and names the repositories worked on outside the plan.

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
`pipx install git+https://github.com/konradcinkusz/portfolio-ops@v0.4.1`.

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
          account-token: ${{ secrets.PORTFOLIO_ACCOUNT_TOKEN }}

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
          account-token: ${{ secrets.PORTFOLIO_ACCOUNT_TOKEN }}
      - uses: actions/upload-artifact@<full-commit-sha>   # vX.Y.Z
        with:
          name: portfolio-dashboard
          path: ${{ steps.portfolio.outputs.dashboard }}
          retention-days: 7

  overview:
    if: github.event_name != 'pull_request'
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
          command: overview
          account-token: ${{ secrets.PORTFOLIO_ACCOUNT_TOKEN }}
      - uses: actions/upload-artifact@<full-commit-sha>   # vX.Y.Z
        with:
          name: portfolio-overview
          path: ${{ steps.portfolio.outputs.overview }}
          retention-days: 1

  publish-overview:
    needs: overview
    runs-on: ubuntu-latest
    permissions:
      actions: read
      contents: write
    concurrency:
      group: publish-overview
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@<full-commit-sha>   # vX.Y.Z
      - name: Commit the overview when it changed
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          pages="$RUNNER_TEMP/portfolio-overview"
          gh run download "$GITHUB_RUN_ID" --repo "$GITHUB_REPOSITORY" \
            --name portfolio-overview --dir "$pages"
          rm -rf overview && mkdir overview && cp "$pages"/*.md overview/
          git add --all overview
          if git diff --cached --quiet; then echo "The overview is current."; exit 0; fi
          git -c user.name="github-actions[bot]" \
            -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
            commit --quiet -m "Update the portfolio overview"
          git push --quiet || { git pull --rebase --quiet && git push --quiet; }
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

### Scanning the account

The workflow's own token sees only the data repository. Give the report and dashboard jobs
a second, read-only token and they also scan your GitHub account: every repository you own,
and which of them **you** pushed to since the same weekday last week. The weekly issue then
names three things:

- repositories you worked on that no product or kernel lists;
- products that are not active, but were worked on;
- repositories your `repos` lists that the account does not have.

The dashboard gains a Repositories panel with every repository, public and private, the
product or kernel it belongs to, and its latest push. The weekly issue links the workflow
run whose artifacts hold that dashboard. Pushes by Dependabot or other bots do not count as your
work. The scan is optional: without the token everything works as before, and the issue
says the account was not scanned.

To set it up:

1. On GitHub, open **Settings → Developer settings → Personal access tokens → Fine-grained
   tokens → Generate new token**.
   - **Resource owner:** your account.
   - **Expiration:** a date you will remember, for example a year ahead.
   - **Repository access:** All repositories. GitHub preselects "Public repositories",
     which leaves every private repository out of the scan; the weekly issue says so when
     that happens.
   - **Permissions:** nothing to add. The read-only `Metadata` permission every token has
     is what the scan uses.
2. In your data repository, open **Settings → Secrets and variables → Actions → New
   repository secret**, name it `PORTFOLIO_ACCOUNT_TOKEN`, and paste the token. Paste it
   nowhere else: not into a file, an issue or a chat.
3. Add `repos: [OWNER/NAME, …]` to each product and kernel in your data, and list the
   repositories that are not projects under `account.ignore` in `config.yaml`:

   ```yaml
   account:
     ignore: [your-name/dotfiles, "your-name/*-notes"]   # * and ? match any characters
   ```

The template's workflow already passes the secret to the report and dashboard jobs, and
never to `validate`. A classic token (`ghp_…`) is refused: it cannot be read-only. When the
token expires or is revoked, the weekly issue says so, and everything else keeps working.

If the issue says your activity could not be told apart from other pushes, GitHub did not
show the token a repository's activity list. It names the permission it asked for: add
that permission to the token, or accept that a push by anyone counts there. The design and
its alternatives are in [ADR 0008](docs/adr/0008-account-scan.md).

### Action inputs

| Input | Default | What it does |
|---|---|---|
| `command` | — (required) | `validate`, `report` or `dashboard` |
| `path` | `.` | The directory holding the data files, relative to the workspace |
| `publish` | `false` | With `report`: keep one open `weekly-review` issue current |
| `dry-run` | `false` | With `publish`: print the planned action and the issue body, send no write request |
| `github-token` | the workflow's token | Used for the visibility check and for publishing |
| `account-token` | — (not scanned) | With `report` or `dashboard`: a fine-grained, read-only token that scans your account; pass `secrets.PORTFOLIO_ACCOUNT_TOKEN` |
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
# yaml-language-server: $schema=https://raw.githubusercontent.com/konradcinkusz/portfolio-ops/v0.4.1/src/portfolio_ops/schemas/products.schema.json
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
  Expired acceptances, Expired claims, Copy-paste debt, Changes without a decision,
  Account activity, Focus and Health. It reads how long each active product has stood
  still, and what changed this week, from git history, so it needs a full clone. With
  `PORTFOLIO_ACCOUNT_TOKEN` set it also scans your account (see
  [Scanning the account](#scanning-the-account)). `--today` fixes the date, which makes the
  output reproducible.
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
  - with `PORTFOLIO_ACCOUNT_TOKEN` set, your account's repositories and their latest pushes

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
  investor declined", not the person's name. The one token you may add lives in your
  repository's Actions secrets, read-only; never write a token into the data files, and
  never give portfolio-ops a classic token.
- **a discovery tool.** Its checks know only what you have registered; a risk you never
  wrote down passes every check. The account scan names repositories you worked on, but
  registers nothing: what is in your portfolio stays your decision.
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
