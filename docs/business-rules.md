# portfolio-ops — business rules

> **Status:** specification, revision **r3**, 2026-09-24.
> The source of truth for the engine's behaviour. Master prompts in `docs/delivery/` are
> generated from this document. When code, a prompt and this document disagree, this
> document wins and the disagreement is a finding. During implementation only the
> **Status** and **Entry point** columns in §6 may change.

## 1. Purpose

portfolio-ops helps one person run a portfolio of many side projects, where the only real
constraint is the owner's attention. It has four functions:

| Function | The question it answers |
|---|---|
| Limit | How many things may be in progress at once? |
| Pressure | Is what is in progress actually moving? |
| Gates | Is it safe to make this external move, or to start this new idea? |
| Memory | What has already been decided and verified, so that nothing is worked out twice? |

Dashboards and exports are views: they show state and contain no rules.

The account scan (§7.12) checks the limit against where the work actually goes: it reports
the repositories of the owner's GitHub account that were worked on outside the active
products.

## 2. Scope and anti-goals

portfolio-ops is a single-owner tool that runs in the owner's own repository. It is not:

- a team project-management system or an issue tracker;
- a hosted service;
- a place for credentials, tokens or personal data about other people — record "the
  investor declined", not the person's name. The data files hold no token: the account
  token (§7.12) lives in the data repository's encrypted Actions secrets and reaches the
  engine through the environment;
- a discovery tool — gates know only what has been registered (§8.5), and the account
  scan (§7.12) reports repositories for the owner to register, but registers nothing;
- meant for public data repositories — it refuses them unless the owner opts in (S7, §8.8).

## 3. Distribution model

| Layer | Repository | Visibility | Contents | Updated by |
|---|---|---|---|---|
| Engine | `konradcinkusz/portfolio-ops` (this repository) | public | CLI, composite action, JSON Schemas, documentation, fictional examples | semver tags |
| Template | `konradcinkusz/portfolio-ops-template` | public, marked as a template | data skeleton with fictional examples, `config.yaml` with defaults, a caller workflow pinned to an engine version | nothing to update: it holds no logic |
| Data | created with "Use this template" | private | the owner's real data files | bumping the pinned engine version |

- The engine is referenced by version, never copied. A repository created from a template
  has an unrelated history and receives no upstream changes — which is why the template
  holds no logic.
- Forks are for contributors to the engine. A fork used as a data repository is
  unsupported: a fork of a public repository is public, scheduled workflows are disabled in
  forks by default, and engine updates would collide with the data.
- Users pin the action to a release tag or, preferably, a full commit SHA.
- The repository name is part of the contract: GitHub Actions does not redirect renamed
  action repositories, so a rename breaks every caller.
- The template's copy of the caller workflow skips every job in the template repository
  itself: the template is public and holds only examples, and S7 would refuse it. In a
  repository created from the template that condition always holds.
- The report and dashboard jobs pass the account token (§7.12) from the secret
  `PORTFOLIO_ACCOUNT_TOKEN`. Without that secret the input is empty and the account is
  not scanned; the validate job never receives it.

The caller workflow a data repository carries (the template ships this shape):

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
```

## 4. Data model

### 4.1 Files

All data files live in one directory — `--path`, by default the repository root.

| File | Required | Content |
|---|---|---|
| `config.yaml` | yes | settings and vocabularies (§4.2) |
| `products.yaml` | yes | `products:` — a list of products |
| `decisions.md` | yes | the decision log (§4.6) |
| `kernels.yaml` | no — missing means empty | `kernels:` — a list of kernels |
| `risks.yaml` | no — missing means empty | `risks:` — a list of risks |
| `findings.yaml` | no — missing means empty | `findings:` — a list of findings |

### 4.2 `config.yaml`

| Key | Type | Default | Used by |
|---|---|---|---|
| `schema_version` | integer | none — required | S6 |
| `allow_public` | boolean | `false` | S7 |
| `thresholds.stale_days` | integer | 30 | N2, L2 |
| `thresholds.actions_per_week` | number | 1 | L2 |
| `thresholds.wip_limit` | integer | 4 | L1, L2 |
| `thresholds.review_horizon_days.paused` | integer | 60 | S4 |
| `thresholds.review_horizon_days.dormant` | integer | 180 | S4 |
| `thresholds.deferral_limit` | integer | 2 | N3 |
| `vocabularies.contexts` | list of slugs | empty | risks, findings, gates |
| `vocabularies.capabilities` | list of slugs | empty | products, kernels, idea gate |
| `vocabularies.finding_types` | list of slugs | empty | added to the built-in `claim` |
| `vocabularies.decision_types` | list of slugs | empty | added to the built-in decision types |
| `finding_ttl_days` | map from finding type to days | empty | P2 |
| `account.ignore` | list of repository patterns `OWNER/NAME`, where `*` and `?` stand for any characters | empty | S8, A1 |

The engine has no built-in TTLs: a finding with neither `expires_on` nor a configured TTL
for its type is invalid.

### 4.3 Vocabularies

Fixed by the engine — `config.yaml` cannot change them (S5):

| Vocabulary | Values |
|---|---|
| product `status` | `idea`, `active`, `paused`, `dormant`, `archived` |
| risk `severity`, ordered | `low` < `medium` < `high` < `critical` |
| risk `state` | `open`, `accepted`, `closed` — a mitigated risk gets a lower severity, not a new state |
| `feeds_from[].mode` | `package`, `copy`, `planned` |
| finding types | `claim` |
| decision types | `admit`, `status_change`, `focus`, `defer`, `risk_accepted` |

Configured in `config.yaml`: contexts, capabilities, further finding types (for example
`name_check`, `metric`) and further decision types (for example `external`, `rejection`,
`rename`, `adoption`).

### 4.4 Identifiers

- Every `id` is a slug matching `^[a-z0-9][a-z0-9-]{0,62}$`, unique across products,
  kernels, risks and findings.
- `portfolio` and `all` are reserved.
- Ids are immutable: a rename changes `name`, never `id`. This is enforced through S2 —
  decision headings pin the ids they name, so renaming a referenced id fails validation.

### 4.5 Entities

**Product** — `products.yaml`

| Field | Type | Required |
|---|---|---|
| `id` | identifier | always |
| `name` | string | always |
| `status` | product status | always |
| `next_action` | string | when `active` |
| `capabilities` | list of configured capabilities | non-empty when `idea` |
| `feeds_from` | list of `{kernel: <kernel id>, mode: <mode>}` | no |
| `status_reason` | string | when `paused` or `dormant` |
| `review_by` | date | when `paused` or `dormant` |
| `repos` | list of GitHub repositories written `OWNER/NAME` | no |

**Kernel** — `kernels.yaml`

| Field | Type | Required |
|---|---|---|
| `id` | identifier | always |
| `name` | string | always |
| `capabilities` | list of configured capabilities | no |
| `min_package_consumers` | integer | no — default 2 |
| `repos` | list of GitHub repositories written `OWNER/NAME` | no |

**Risk** — `risks.yaml`

| Field | Type | Required |
|---|---|---|
| `id` | identifier | always |
| `scope` | a product id, a kernel id or `portfolio` | always |
| `title` | string | always |
| `severity` | risk severity | always |
| `applies_to` | non-empty list of configured contexts, or `[all]` | always |
| `state` | risk state | always |
| `accepted_until` | date | when `state` is `accepted` |

**Finding** — `findings.yaml`

| Field | Type | Required |
|---|---|---|
| `id` | identifier | always |
| `subject` | a product id, a kernel id or `portfolio` | always |
| `type` | finding type | always |
| `result` | string — what was verified | always |
| `evidence` | string — a link or a note | no |
| `checked_on` | date | always |
| `expires_on` | date | unless a TTL is configured for the type |
| `used_in` | list of configured contexts — where a claim is used externally | non-empty for `claim`; optional otherwise |

`repos` names the GitHub repositories where the work on a product or a kernel happens.
Each repository belongs to one product or kernel (S8), and only the account scan (§7.12)
reads the list.

### 4.6 Decisions — `decisions.md`

Every decision starts with a level-2 heading and continues with free Markdown until the next
level-2 heading:

```markdown
## 2026-09-22 · alpha, beta · status_change
Paused beta to make room for alpha within the WIP limit.
```

- Grammar: `## <YYYY-MM-DD> <sep> <id>[, <id>…] <sep> <type>`, where `<sep>` is `·`
  (U+00B7) or `|`.
- Every level-2 heading must parse; other heading levels are free text.
- A decision may not be dated in the future.
- `focus` and `defer` headings name exactly one product.
- The text under a heading, up to the next level-2 heading, is the decision's justification;
  the views show it (V1, V2). Text before the first level-2 heading belongs to no decision.

## 5. Product lifecycle

| Status | Meaning | Required fields | Clock or review | Counts towards the WIP limit | Allowed next statuses |
|---|---|---|---|---|---|
| `idea` | registered, not yet past the idea gate | `capabilities` | — | no | `active` (after the idea gate, within the limit), `archived` |
| `active` | in progress | `next_action` | clock (N1) | yes | `paused`, `dormant`, `archived` |
| `paused` | stopped, meant to resume | `status_reason`, `review_by` at most 60 days ahead | review at `review_by` | no | `active` (within the limit), `dormant`, `archived` |
| `dormant` | published, no investment planned | `status_reason`, `review_by` at most 180 days ahead | review at `review_by` | no | `active` (within the limit), `archived` |
| `archived` | closed | a `status_change` decision | — | no | `active`, only through an `admit` decision and within the limit |

Required fields are validated from phase 1 (S4); transitions from phase 2 (P1). The horizons
come from `thresholds.review_horizon_days`.

## 6. Rule catalogue

Prefixes: S structure, L limit, N pressure, P memory, R report, B gates, K kernels, V views,
A account.

| ID | Rule | Enforced by | Effect | Phase | Status | Entry point |
|---|---|---|---|---|---|---|
| S1 | Every `id` is a valid slug and unique across products, kernels, risks and findings; `portfolio` and `all` are reserved (§4.4) | `validate` | error | 1 | implemented (v0.1.0) | `portfolio_ops.rules.structure.check_ids` |
| S2 | Every reference resolves: `risks[].scope`, `findings[].subject`, `products[].feeds_from[].kernel`, and every id in a decision heading | `validate` | error | 1 | implemented (v0.1.0) | `portfolio_ops.rules.structure.check_references` |
| S3 | Every enumerated value belongs to its vocabulary (§4.3); every decision heading follows §4.6 | `validate` | error | 1 | implemented (v0.1.0) | `portfolio_ops.rules.structure.check_vocabularies` |
| S4 | The fields required by a product's status are present (§5); `review_by` is no later than today plus that status's horizon; an `archived` product is named by at least one `status_change` decision | `validate` | error | 1 | implemented (v0.1.0) | `portfolio_ops.rules.structure.check_status_fields` |
| S5 | `config.yaml` may extend the configured vocabularies only: it cannot redefine an engine-fixed vocabulary, and it cannot declare `all` as a context | `validate` | error | 1 | implemented (v0.1.0) | `portfolio_ops.rules.structure.check_config_vocabularies` |
| S6 | `schema_version` is present and supported by this engine version | every command | exit 2, pointing to `docs/migrations/` | 1 | implemented (v0.1.0) | `portfolio_ops.loading.check_schema_version` |
| S7 | A public data repository without `allow_public: true` is refused before any data file other than `config.yaml` is read (§7.3) | every command | exit 3 | 1 | implemented (v0.1.0) | `portfolio_ops.guard.check_visibility` |
| S8 | Every entry of `repos` is a repository written `OWNER/NAME` and is listed by one product or kernel only, compared without regard to case; every entry of `account.ignore` is `OWNER/NAME` in which `*` and `?` may stand for any characters | `validate` | error | 4 | implemented (v0.4.0) | `portfolio_ops.rules.structure.check_repositories` |
| L1 | The number of `active` products is at most `wip_limit`. The message lists the active products and asks to keep at most `wip_limit` of them, moving the rest to `paused` or `dormant` with a `review_by` | `validate` | error | 1 | implemented (v0.1.0) | `portfolio_ops.rules.limits.check_wip_limit` |
| L2 | `wip_limit` ≤ `stale_days` / 7 × `actions_per_week` (§8.1) | `validate` | warning | 1 | implemented (v0.1.0) | `portfolio_ops.rules.limits.check_pressure_arithmetic` |
| N1 | The clock of an `active` product is today minus the latest of: `next_action` changing to its current value, the product last becoming `active`, its latest `defer` decision (§7.2) | `report` | — | 1 | implemented (v0.1.0) | `portfolio_ops.history.clocks` |
| N2 | The clock exceeds `stale_days` | `report` | item under Stale | 1 | implemented (v0.1.0) | `portfolio_ops.report.sections.stale` |
| N3 | The number of `defer` decisions dated after the latest `next_action` change reaches `deferral_limit` | `report` | item under Escalations — split the action, pause or archive | 1 | implemented (v0.1.0) | `portfolio_ops.report.sections.escalations` |
| N4 | A `paused` or `dormant` product's `review_by` is before today | `report` | item under Overdue reviews | 1 | implemented (v0.1.0) | `portfolio_ops.report.sections.overdue_reviews` |
| P2 | Every finding has `checked_on`, and `expires_on` or a TTL configured for its type (then `expires_on` = `checked_on` + TTL); a finding holds through its `expires_on`; a `claim` has a non-empty `used_in` | `validate` | error | 1 | implemented (v0.1.0) | `portfolio_ops.rules.structure.check_findings` |
| R1 | Publishing keeps exactly one open issue labelled `weekly-review` (§7.5) | `report --publish` | — | 1 | implemented (v0.1.0) | `portfolio_ops.report.publish.plan` |
| R2 | The report has fixed sections in a fixed order (§7.4); phase 2 adds Expired acceptances, Expired claims, Copy-paste debt and Changes without a decision | `report` | — | 1, 2 | implemented (v0.2.0) | `portfolio_ops.report.render.render` |
| R3 | The focus of the week is the latest `focus` decision; the report evaluates last week's focus and flags a week without one (§7.4) | `report` | item when no focus is recorded | 1 | implemented (v0.1.0) | `portfolio_ops.report.sections.focus` |
| B1 | `gate <product> --context <ctx>` collects the risks of the product, of every kernel reachable through `feeds_from` in any mode, `planned` included (a kernel's risk is inherited by all its consumers), and of scope `portfolio`, keeping those whose `applies_to` contains `ctx` or `all` (§7.10) | `gate` | — | 2 | implemented (v0.2.0) | `portfolio_ops.rules.gates.collect_risks` |
| B2 | A collected risk is `open` with severity `high` or `critical` | `gate` | fail, exit 1 | 2 | implemented (v0.2.0) | `portfolio_ops.rules.gates.check_open_risks` |
| B3 | A collected risk is `accepted` and `accepted_until` is today or later; after that date it counts as `open` | `gate` | warning | 2 | implemented (v0.2.0) | `portfolio_ops.rules.gates.check_accepted_risks` |
| B4 | A `claim` about the product has `ctx` in `used_in` and has expired | `gate` | fail, exit 1 — re-verify before use | 2 | implemented (v0.2.0) | `portfolio_ops.rules.gates.check_expired_claims` |
| B5 | `idea-gate <product>` lists the non-archived products, other ideas included, and the kernels that share capabilities with the idea (§7.10) | `idea-gate` | reuse and overlap report | 2 | implemented (v0.2.0) | `portfolio_ops.rules.gates.overlaps` |
| B6 | At least half of the idea's capabilities are shared with a single non-archived product | `idea-gate` | fail, exit 1, until an `admit` decision names the idea (its text carries the justification); a merge is recorded by archiving the idea | 2 | implemented (v0.2.0) | `portfolio_ops.rules.gates.check_idea_overlap` |
| K1 | A kernel's state is derived, never written: `planned` (no `package` consumer), `extracted` (at least one, but fewer than `min_package_consumers`), `done` (at least `min_package_consumers`); an archived product consumes nothing | `report` | — | 2 | implemented (v0.2.0) | `portfolio_ops.rules.kernels.kernel_state` |
| K2 | A product that is not archived consumes a kernel in `copy` mode | `report` | item under Copy-paste debt | 2 | implemented (v0.2.0) | `portfolio_ops.report.sections.copy_paste_debt` |
| P1 | A product's status or a risk's state changes without a decision that names the id and is dated on the day of the change; a status transition outside §5 (§7.9) | CI (`validate` against the previous commit), `report` | warning and report item — never blocking | 2 | implemented (v0.2.0) | `portfolio_ops.rules.changes.check_changes` |
| P3 | Before a new check, look up (`subject`, `type`): reuse a valid finding; re-check and update an expired one (§7.10) | `lookup`, procedure | — | 2 | implemented (v0.2.0) | `portfolio_ops.rules.memory.lookup` |
| V1 | Dashboard: static HTML generated from the data; for a private data repository never published to GitHub Pages — a workflow artifact or a local file (§7.11) | `dashboard` | — | 3 | implemented (v0.3.0) | `portfolio_ops.views.dashboard.render_dashboard` |
| V2 | Context export: size-bounded Markdown for LLM sessions — active and paused products with their next actions, open risks of severity `medium` or higher, the latest decisions, the capability vocabulary (§7.11) | `export` | — | 3 | implemented (v0.3.0) | `portfolio_ops.views.export.render_export` |
| A1 | A repository of the account with the owner's activity in the window (§7.12) is listed by no product or kernel, and `account.ignore` does not match it | `report` | item under Account activity — add it to the `repos` of its product or kernel, registering a new product as an idea, or ignore it | 4 | implemented (v0.4.0) | `portfolio_ops.rules.account.outside_portfolio` |
| A2 | A repository listed by a product that is not `active` has the owner's activity in the window | `report` | item under Account activity — make the product active within the limit, with its decision, or stop working on it | 4 | implemented (v0.4.0) | `portfolio_ops.rules.account.inactive_work` |
| A3 | A repository in `repos` whose owner is the account is not among the account's repositories | `report` | item under Account activity — correct the name, or remove it | 4 | implemented (v0.4.0) | `portfolio_ops.rules.account.unknown_repositories` |

## 7. Operational definitions

### 7.1 Time

Dates are ISO `YYYY-MM-DD` and are evaluated in UTC. "Today" is the current UTC date, or the
value of `--today`. Git commit times are the committer timestamps, converted to UTC dates.

### 7.2 The clock (N1)

- Only `report` needs git history. `validate` reads it when it is there, for P1 (§7.9), and
  so does `dashboard`, for the clocks (§7.11); both work on any directory.
- The engine reads the commits that touched `<path>/products.yaml`, newest first, and parses
  each version. A version that fails to parse is skipped with a warning.
- Values are compared per product id after parsing, so reordering products, reformatting,
  comments and edits to other fields never reset the clock.
- "`next_action` changed to its current value" is the date of the commit that starts the
  most recent unbroken run of versions in which the product's `next_action` equals its
  current value. "Last became `active`" is defined the same way for `status`.
- A product whose working-tree value differs from the last commit, or which is not in any
  commit yet, counts as changed today.
- `defer` dates come from decision headings (§4.6).
- On a shallow clone, commands that need history exit 2 with a message that names
  `fetch-depth: 0`. The composite action fetches the full history itself when it finds a
  shallow clone.

### 7.3 The visibility guard (S7)

- Every command runs in this order: read `config.yaml`, check `schema_version` (S6), run the
  guard (S7), then everything else.
- In GitHub Actions (`GITHUB_ACTIONS=true`) the engine asks the GitHub REST API for the
  repository in `GITHUB_REPOSITORY`, authenticated with `GITHUB_TOKEN`; `private: false`
  means public. If the request fails, the command exits 2 — CI fails closed.
- Locally, the engine derives the repository from the `origin` remote when it points at
  github.com and asks without a token: `private: false` means public; a 404 means not
  public. A network failure, or a remote that is not on github.com, prints a warning and the
  command continues.
- A public repository without `allow_public: true` exits 3, with a message that names the
  flag and says what would be exposed.

### 7.4 The report (R2, R3)

The report is Markdown on standard output, with these sections in this order:

1. **Validation errors** — only when validation fails. The other sections are then left out
   with a one-line note, and the command exits 1.
2. **Stale** — N2: product, clock in days, `next_action`.
3. **Escalations** — N3.
4. **Overdue reviews** — N4: product, status, `review_by`.
5. **Expired acceptances** — B3: accepted risks whose `accepted_until` has passed; they
   count as open again.
6. **Expired claims** — `claim` findings past their expiry (P2); each is verified again
   before its next use (B4).
7. **Copy-paste debt** — K2: each product that carries a copy of a kernel, with the
   kernel's state (K1).
8. **Changes without a decision** — P1: the status and state changes dated from the same
   weekday last week up to today that no decision records, and the transitions §5 does not
   have (§7.9).
9. **Account activity** — A1, A2 and A3, from the account scan (§7.12): the repositories
   worked on outside the portfolio, those of products that are not `active`, and the
   listed ones the account does not have. Without `PORTFOLIO_ACCOUNT_TOKEN` the section
   says the account was not scanned, and that is not an item; a scan that was asked for
   and failed is one item, naming the reason and the fix.
10. **Focus** — this week's focus: the latest `focus` decision dated within the seven days
    ending today, or the item "No focus recorded this week". Last week's focus: the latest
    `focus` decision dated before that window, evaluated as `done` (the product's
    `next_action` changed after the focus date), `left active` (the product is no longer
    `active`) or `not done`.
11. **Health** — not items: active products against `wip_limit`; the median clock of
    active products; the number of stale products; focus completion over the last four
    evaluated `focus` decisions; the number of kernels in each state (K1); the repositories
    with the owner's activity in the window and how many of them are outside the portfolio,
    when the account was scanned; the date of the last commit that touched the data
    directory.

The report **has items** when any of sections 1–9 is non-empty or no focus is recorded this
week.

### 7.5 Publishing (R1)

- The issue carries the label `weekly-review` (created when missing) and the title
  `Weekly review — week of <YYYY-MM-DD>`, the Monday of the report's week.
- A pure planner decides the action from the open issues carrying the label and whether the
  report has items: none open and items → create; one open and items → update; open issues
  and no items → close them; several open and items → update the oldest and close the rest;
  none open and no items → nothing.
- `--dry-run` sends no write requests. It prints the planned action and the issue body. It
  reads the open issues when a token is available; otherwise it assumes none are open and
  says so.
- `--publish` without `GITHUB_TOKEN` exits 2 and names the variable. The repository comes
  from `GITHUB_REPOSITORY` or `--repo`. The token is never printed or logged.

### 7.6 Interfaces

These are the public contract and freeze at v1.0.0 (§9.4).

- `portfolio-ops validate [--path DIR]`
- `portfolio-ops report [--path DIR] [--today YYYY-MM-DD] [--publish] [--dry-run] [--repo OWNER/NAME]`
- `portfolio-ops gate PRODUCT --context CONTEXT [--path DIR] [--today YYYY-MM-DD]`
- `portfolio-ops idea-gate IDEA [--path DIR]`
- `portfolio-ops lookup SUBJECT TYPE [--path DIR] [--today YYYY-MM-DD]`
- `portfolio-ops dashboard [--path DIR] [--today YYYY-MM-DD] [--output FILE]`
- `portfolio-ops export [--path DIR] [--today YYYY-MM-DD] [--max-chars N]`
- `portfolio-ops --version`
- Composite action (`action.yml`) inputs: `command` (`validate`, `report` or `dashboard`,
  required), `path` (default `.`), `publish` (default `false`), `dry-run` (default
  `false`), `github-token` (default: the workflow's token), `account-token` (default:
  empty — the account is not scanned), `python-version` (default: the newest supported
  version). Output: `dashboard`, with `command: dashboard` — the path of the page, outside
  the workspace.
- Environment: `GITHUB_TOKEN` and `GITHUB_REPOSITORY` for the guard (§7.3) and publishing
  (§7.5); `PORTFOLIO_ACCOUNT_TOKEN` for the account scan of `report` and `dashboard`
  (§7.12). The action passes `account-token` to those two commands only.

### 7.7 Exit codes

| Code | Meaning |
|---|---|
| 0 | success; warnings allowed |
| 1 | rule violations, or a failed gate |
| 2 | usage or environment error — unsupported `schema_version`, shallow history, missing token, visibility undeterminable in CI, an argument the data does not have (§7.10), a limit the export cannot meet (§7.11) |
| 3 | refused by the visibility guard |

### 7.8 Messages

One line per finding, stable enough to search for:

```
error S4 products.yaml:14: product 'alpha' is active but has no next_action — add next_action or change its status
warning L2 config.yaml:6: wip_limit 6 exceeds 30 / 7 × 1 = 4.3 — the weekly report will flag most active products
```

The line number is that of the offending value, or of the entity when a field is missing.
The troubleshooting table in `CONTRIBUTING.md` is keyed on these messages.

### 7.9 Change coverage (P1)

- Changes are read from git as the clock is (§7.2): the versions of `products.yaml` and
  `risks.yaml` are compared per id after parsing, and a change is dated by the committer
  date of the commit whose version makes it, or today when it is only in the working tree.
- A value outside its vocabulary is not a status (S3 reports it), and a new id is not a
  change. An id missing from a version keeps its last value.
- A change is covered by any decision that names the id and is dated on the day of the
  change. A product that leaves `archived` also needs an `admit` decision (§5).
- `validate` checks the working tree and the commits since the previous commit — one
  commit, or everything a merge brings in. Outside a git repository there is nothing to
  compare; on a shallow clone without the previous commit it says that P1 was not checked
  and names `fetch-depth: 0`. P1 never changes the exit code.
- `report` lists the changes dated from the same weekday last week up to today (§7.4).

### 7.10 Gates and lookup

- `gate`, `idea-gate` and `lookup` run in the order of §7.3 and then validate the data. Data
  that does not validate is not judged: they print its errors and exit 1.
- An argument the data does not have — an unknown product, context, subject or finding
  type, a kernel where a product is needed, `all` as a context, `idea-gate` on a product
  that is not an idea — exits 2.
- `gate` prints §7.8 lines: `error B2` and `error B4` fail the move and exit 1; `warning B3`
  does not.
- `idea-gate` prints a Markdown report: the products and kernels that share the idea's
  capabilities, each kernel with its state (K1), and the verdict; it exits 1 while B6 fails.
- `lookup` prints one line per finding about the subject of that type — reuse one that
  holds, check an expired one again — or says there is none; it exits 0.
- A finding holds through its `expires_on`, and an acceptance through its `accepted_until`.
- They run where the move is made, in a clone of the data repository; the composite action
  does not run them.

### 7.11 Views (V1, V2)

- Views show state and decide nothing: no rule id, no diagnostic, no effect on the exit
  code. Like the gates, they work only on data that validates; its errors go to standard
  error, and the command exits 1.
- **The dashboard** is one self-contained HTML page: an inline stylesheet and no script,
  font, image or outside link; a Content-Security-Policy that allows only that
  stylesheet; every value from the data escaped; `noindex`; and a visible note that the
  page is private. Its panels, in order: a summary; the active products with their next
  actions and clocks; the ideas; the paused and dormant products, the soonest review
  first; the archived products; the kernels with their state and consumers; the risks,
  those that count as open first; the findings, the soonest to expire first; which
  products and kernels share each capability; the ten latest decisions with their text;
  and the account's repositories (§7.12) — forks and archived ones only when `repos` lists
  them — each with the product or kernel that lists it, the latest push first. When the
  account was scanned, the products panels show the latest push of each product's
  repositories and the summary counts the repositories worked on outside the plan (A1,
  A2); otherwise the repositories panel says why the account was not scanned.
- It goes to standard output, or to `--output FILE`. Without git history — outside a
  repository, or on a shallow clone — it leaves out the clocks and says why. In the
  composite action it is written outside the workspace, and the output `dashboard` holds
  its path for a workflow artifact.
- **The export** is Markdown in the order of V2. The products, the risks and the vocabulary
  are always there in full; the decisions, newest first with their text, fill what is
  left of `--max-chars` (12000 characters by default), each whole or left out, and the
  export says how many it left out. A limit too small for the rest exits 2 and names the
  smallest limit that fits.
- An open risk is one that counts as open (B3): `open`, or accepted past its
  `accepted_until`. A paused product is exported with its `status_reason` and `review_by`,
  and with its `next_action` when it has one.
- The export needs no git history.

### 7.12 The account scan (A1–A3)

- **Who asks.** `report` and `dashboard` scan the account when `PORTFOLIO_ACCOUNT_TOKEN`
  is set. No other command reads the variable, and without it both work as before (P8).
  The scan reads the account as it is when the command runs; `--today` moves only the
  window.
- **The token** is a fine-grained personal access token of the owner, with access to all of
  the account's repositories and the read-only permission `Metadata`. It is kept as the
  data repository's Actions secret `PORTFOLIO_ACCOUNT_TOKEN` and passed to the report and
  dashboard jobs only (§3). It is never printed or logged. A classic token (`ghp_…`) is
  refused before it is sent anywhere: it cannot be read-only, and one that can read
  private repositories can write to all of them.
- **The account's repositories.** The engine asks the GitHub REST API whom the token
  belongs to — the login — and which repositories that account owns, each with the time
  of its latest push. Repositories of organisations are not scanned.
- **The window** runs from the same weekday last week up to today, like the changes the
  report lists for P1 (§7.4), so two weekly runs leave no gap between them.
- **The owner's activity.** A repository pushed within the window, not archived, and not a
  fork unless `repos` lists it, is a candidate. For each candidate the engine reads the
  latest entry by the login in the repository's activity list — pushes, force pushes,
  branch changes and merges. The candidate has the owner's activity on that entry's date
  when it falls within the window; a push by anyone else, Dependabot's for example, does
  not count. Where the activity list cannot be read, a push by anyone counts, and the
  report and the dashboard say so and why.
- **Left out.** The data repository itself: `GITHUB_REPOSITORY` in GitHub Actions, the
  `origin` remote locally. With `allow_public: true`, private repositories are left out of
  what the report and the dashboard name, because the report may then be public.
  `account.ignore` leaves a repository out of A1 only; a repository that `repos` lists is
  in the portfolio whatever the patterns say.
- **Names** are compared without regard to case, as GitHub compares them. A renamed
  repository is listed under its new name, so A3 reports the old one.
- **Failures.** A rejected token (expired or revoked), a missing permission, a rate limit
  or a network failure stops the scan. The report then shows one item that names the
  reason and the fix, the dashboard a note, and standard error a warning. The exit code
  never changes.

## 8. Design notes and rejected alternatives

### 8.1 Pressure arithmetic

If about *k* next actions get done per week and the stale threshold is *N* days, roughly
*N* / 7 × *k* products can move within the threshold. With more active products than that,
the report flags most of them every week, becomes noise and stops being read. Hence L1, a
hard limit on active products, and L2, a warning when the configuration makes noise
inevitable. With the defaults — 30 days, one action a week — the limit is 4.

### 8.2 A clock derived from git, not a hand-edited timestamp

Rejected: a manual `last_touched` field. It fails both ways: a forgotten update raises a
false alarm, and a cosmetic edit resets the clock without progress. Pressure concerns
progress on the next action, so the clock is derived from the history of the `next_action`
value, and a conscious postponement is a `defer` decision rather than an edited date.

### 8.3 One rolling issue

Rejected: a new issue every week, which produces overlapping lists within a month. The
report keeps a single open issue current — the same deduplication discipline the tool asks
of its owner.

### 8.4 The decision log is checked in CI, not by a local hook

Rejected: a pre-commit hook. Local hooks do not run for edits made in the web interface or on
another machine, and "decisions.md was touched" is satisfied by any line. From phase 2, P1
checks in CI that each status or state change is matched by a decision naming that id, and
surfaces misses in the report as warnings rather than blocking.

### 8.5 Gates remember; they do not discover

A gate can only block on risks and claims that have been registered. It prevents repeating
a known mistake. Protection against statements drifting out of date over time comes from
expiry dates on claims — and only if a claim is registered before it is used externally.

### 8.6 Duplicates are found by purpose, not by dependencies

Sharing a kernel is the intended reuse pattern — a kernel is done when at least two products
use it as a package — so shared dependencies cannot signal duplication. Overlapping purpose
is detected through a controlled capability vocabulary; free-form tags drift apart and defeat
the comparison.

### 8.7 Template plus a pinned composite action

Rejected: forking (§3). Chosen over a reusable workflow: a composite action installs the
engine from its own checkout, so the version a user pins is the version that runs, with no
second version reference to keep in sync.

### 8.8 Private by default

What this tool holds — risks, rejections, stalled projects — is a list of the owner's weak
spots. Publishing it by accident cannot be undone, so the engine refuses public data
repositories unless `allow_public: true` is set deliberately, for example by someone who
builds in public.

### 8.9 The account is polled, not listened to

GitHub has no webhook for everything in a personal account. Listening would need a GitHub
App whose webhooks reach a server — a hosted service, which §2 rules out — or a workflow
and a secret in every repository of the account. A weekly review needs no more than a
poll from the data repository's own schedule. The workflow's `GITHUB_TOKEN` sees only its
own repository, so the poll needs a second token. It is optional, fine-grained and
read-only; a classic token is refused because it cannot be read-only. The engine reads
the repositories' metadata and activity lists, never their code. Only the owner's own
activity counts, so Dependabot's pushes do not make a paused product look worked on.

## 9. Delivery phases and release policy

### 9.1 Phase 1 — engine v0.1.0

**Scope:** S1–S7, L1–L2, N1–N4, P2, R1–R3; the composite action; the JSON Schemas; a
fictional example dataset in `examples/starter/`; the repository baseline.

**Acceptance criteria:**

<!-- AC:BEGIN -->
- **AC1** — `portfolio-ops validate --path examples/starter` exits 0 with no errors. The
  example data is fictional and covers every product status, at least one kernel, one risk,
  one `claim` finding, and decisions of the types `admit`, `status_change`, `focus` and
  `defer`.
- **AC2** — For each of S1, S2, S3, S4, S5, P2 and L1 a fixture violates only that rule;
  `validate` on it exits 1 and prints exactly one error line that starts with the rule id and
  names the file and the line. A fixture that violates only L2 prints one `warning L2` line
  and exits 0.
- **AC3** — An unsupported `schema_version` makes every command exit 2 with a pointer to
  `docs/migrations/`.
- **AC4** — A public data repository without `allow_public: true` makes every command exit 3
  before any data file other than `config.yaml` is read; with the flag set, commands
  proceed. In GitHub Actions a visibility that cannot be determined exits 2; locally it
  warns and proceeds.
- **AC5** — In integration tests on temporary git repositories with scripted commit dates,
  the clock of an active product equals the days since the latest of: its `next_action`
  changing to the current value, its latest transition to `active`, its latest `defer`.
  Reordering products, reformatting YAML or editing other fields does not reset it; an
  uncommitted change of `next_action` counts as today.
- **AC6** — On a shallow clone `report` exits 2 with a message that names `fetch-depth: 0`;
  `validate` needs no git history and works outside a git repository.
- **AC7** — `report --today <date>` is deterministic and renders the sections of §7.4 in
  order; on invalid data it renders only the validation-errors section and exits 1.
- **AC8** — The publish planner keeps exactly one open `weekly-review` issue as §7.5
  specifies; `report --publish --dry-run` sends no write requests and prints the planned
  action and the issue body; `--publish` without `GITHUB_TOKEN` exits 2 and names the
  variable.
- **AC9** — `action.yml` installs the engine from its own checkout and runs `validate` or
  `report`; on every pull request, CI in this repository runs the action against
  `examples/starter` — `validate`, and `report` with `publish` and `dry-run` set.
- **AC10** — The repository baseline exists and CI executes everything the repository
  claims: an MIT `LICENSE`; a README written for a stranger (what and why in the first two
  sentences, a quick start, the reuse shape of §3, a "How not to use portfolio-ops" section
  built from §2, the runtime dependency count); `CONTRIBUTING.md` with one-command setup and
  a troubleshooting table keyed on literal error text; `CHANGELOG.md` with an unreleased
  0.1.0 entry; `CODEOWNERS`; dependency-update automation for Python packages and GitHub
  Actions; `.editorconfig`; a real `.gitattributes`; issue and pull-request templates;
  secret scanning in pre-commit and CI; CI running lint, type checks, tests on the minimum
  and the newest supported Python version, a dependency audit and the self-test; static
  analysis with CodeQL; a tag-driven release workflow; `.claude/settings.json` declaring the
  standards marketplace; `CLAUDE.md` stating which standards apply; `secrets.env.example`;
  ADRs for the standards scope, the distribution model, the clock from git and the single
  rolling issue.
- **AC11** — No real personal or portfolio data anywhere in the repository: code, fixtures,
  examples, documentation or commit messages.
- **AC12** — In §6 of this document every phase-1 rule shows `implemented (v0.1.0)` and an
  entry point; nothing else in this document changed.
<!-- AC:END -->

**Then, before phase 2:** create the template repository from `examples/starter/` — without
`allow_public: true` — and the owner's private data repository from the template.

**Exit criterion:** three consecutive weeks on the owner's real, private data — the report
is updated every week, active products stay within the limit, and a focus is recorded every
week.

### 9.2 Phase 2 — v0.2.0

**Scope:** B1–B6, K1–K2, P1, P3, and the report sections that R2 adds.
**Exit criterion:** the first real external move and the first new idea have passed the
gates.

### 9.3 Phase 3 — v0.3.0

**Scope:** V1, V2.
**Exit criterion:** the generated dashboard covers everything a previously hand-maintained
overview showed, and the hand-maintained overview has been deleted.

### 9.4 Release policy

- While in 0.x anything may change. A breaking change to the data format increments
  `schema_version` and adds a note to `docs/migrations/`.
- v1.0.0 comes no earlier than the phase-1 exit criterion being met on real data, and after
  phase 2, because the gates' exit codes belong to the contract.
- v1.0.0 freezes the repository name, the CLI commands and options, the exit codes, the
  report's sections, the action's inputs and output, and the supported `schema_version`. From then on a
  breaking change needs a new major version, and a floating major tag (`v1`) tracks the
  latest release.

### 9.5 Phase 4 — v0.4.0

**Scope:** S8, A1–A3, the report's Account activity section and its Health line, the
dashboard's repositories, and the action's `account-token` input.
**Exit criterion:** on the owner's real account, two consecutive weekly reports show no
item under Account activity — every repository worked on belongs to an active product or
a kernel, or is ignored.

## 10. Measures and kill criterion

- The Health section carries the measures that show whether the system works: focus
  completion, the median age of next actions among active products, and the number of stale
  products over time. With the account scanned it also counts the repositories worked on
  outside the portfolio.
- Kill criterion: if three consecutive reports lead to no change in the data, the overhead
  exceeds the value — cut the system back to validation with the WIP limit.
- portfolio-ops is itself a product in its owner's portfolio and counts towards the same WIP
  limit.

## 11. Known limitations and accepted risks

<!-- RISKS:BEGIN -->
| Risk | If it materialises | Why it is accepted | Accepted by |
|---|---|---|---|
| Commit dates can be rewritten — rebase, amend, forged dates | The clock resets without progress | A single-owner tool: the owner only deceives themselves, and the history stays auditable | the repository owner, by committing r1 |
| Visibility cannot be determined offline | A local run on a public repository only warns | CI fails closed, and a local run publishes nothing | the repository owner, by committing r1 |
| Gates know only registered risks and claims | An unregistered problem passes a gate | Stated in §2 and §8.5; discovery is out of scope | the repository owner, by committing r1 |
| Dates are evaluated in UTC | Day boundaries shift for owners far from UTC | Thresholds are measured in weeks | the repository owner, by committing r1 |
| The account token reads the metadata of every repository of the account | A leaked token lists the names of private repositories and when they were pushed | The token is read-only and fine-grained, sees no code, expires, lives in an encrypted Actions secret passed to two jobs only, and is optional | the repository owner, by adopting r3 |
| The activity list may be unreadable with the token's permissions | Pushes by others, such as Dependabot's, count as the owner's work | The report and the dashboard say so and name the reason; the owner can grant the permission GitHub names | the repository owner, by adopting r3 |
<!-- RISKS:END -->

## 12. Revision log

| Revision | Date | Change |
|---|---|---|
| r1 | 2026-09-22 | Initial specification |
| r2 | 2026-09-23 | Folds in what phases 1–3 decided where r1 was silent, with no change of behaviour: the complete command-line interface and the action's output (§7.6), the report's ten sections (§7.4), change coverage (§7.9), the gates and lookup as commands (§7.10), the views (§7.11), the dashboard job of the caller workflow (§3), decision text (§4.6), and the rule texts of B1, B5, B6, K1, K2 and P2 |
| r3 | 2026-09-24 | Adds phase 4, the account scan (§7.12, §8.9, §9.5), at the owner's request: `repos` on products and kernels (§4.5), `account.ignore` (§4.2), rules S8 and A1–A3 (§6), the report's Account activity section and Health line (§7.4), the dashboard's repositories (§7.11), the `account-token` input and `PORTFOLIO_ACCOUNT_TOKEN` (§3, §7.6), the account token in the anti-goals (§2), and two accepted risks (§11). The template repository exists (§3) |
