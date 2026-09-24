# ADR 0008 — The account scan: a scheduled poll with a read-only, fine-grained token

- **Status:** proposed, 2026-09-24 — accepted when the owner merges phase 4
- **Decided by:** the owner, who asked for portfolio-ops to watch the whole GitHub account
  (business rules r3); the details are the engine's reading of §7.12, for the owner to
  confirm
- **Governs:** `src/portfolio_ops/account.py`, `src/portfolio_ops/rules/account.py`, the
  account's endpoints in `src/portfolio_ops/github.py`, rule S8, the report's Account
  activity section, the dashboard's repositories panel, the action's `account-token`
  input

## Context

Until r3, portfolio-ops saw one repository: the one that holds the data. The owner works
across more than a hundred repositories of one GitHub account, and that is where the WIP
limit leaks. Work goes into repositories that no product lists, or into products that are
paused, and the data files never hear of it. The owner asked for portfolio-ops to watch
the account itself.

The constraints:

- GitHub has no webhook for everything in a personal account. Organisations have one;
  users do not.
- The workflow's `GITHUB_TOKEN` is scoped to the repository whose workflow runs. It cannot
  list the account's other repositories.
- §2 rules out a hosted service and tokens in the data files.
- ADR 0001 applies P5 (secrets come from the environment and are never printed) and P8
  (optional capabilities degrade).
- With `allow_public: true` the weekly report may be public.

## Decision

**Poll, do not listen.** The report and dashboard jobs already run on the data repository's
weekly schedule and on demand. They scan the account when they run.

**A second, optional secret.**

- `PORTFOLIO_ACCOUNT_TOKEN` is a fine-grained personal access token of the owner, with
  repository access "All repositories" and the read-only permission `Metadata`, stored as
  an Actions secret of the data repository.
- The caller workflow passes it to the action's `account-token` input in the report and
  dashboard jobs only. The validate job, which runs on every pull request, Dependabot's
  included, never receives it.
- The action hands it to those two commands as `PORTFOLIO_ACCOUNT_TOKEN`, and the engine
  never prints it: an error names the method, the path and the status, as for
  `GITHUB_TOKEN`.
- A classic token (`ghp_…`) is refused before any request. Classic scopes cannot be
  read-only: one that can list private repositories can write to all of them.

**Three requests, then one per candidate.**

1. `GET /user` names the login the token belongs to.
2. `GET /user/repos?affiliation=owner`, page by page, lists the repositories the account
   owns. Each comes with whether it is private, a fork or archived, and when it was last
   pushed.
3. A candidate is pushed within the window, not archived, and not a fork unless `repos`
   lists it. For each one, `GET /repos/{owner}/{repo}/activity?actor={login}&per_page=1`
   returns the owner's latest activity: a push, a force push, a branch change or a merge.

The window is P1's, from the same weekday last week up to today, so weekly runs leave no
gap.

**The owner's activity, not anyone's.** A push date alone counts Dependabot's pushes, so a
paused product with Dependabot switched on would look worked on every week. The activity
list says who acted. Where it cannot be read — HTTP 403 or 404 for that repository — the
push date counts for it. The report and the dashboard say so, and name the permission
GitHub asks for when its `X-Accepted-GitHub-Permissions` header names one.

**Pure rules, a thin adapter** (P11, P13).

- `account.py` and `github.py` do the HTTP and turn the answers into a typed `Scan`.
- A1–A3 in `rules/account.py` are pure functions of the portfolio, the scan and today, with
  unit tests.
- Report section 9 and dashboard panel 11 render them.
- Section and panel are registered like the others (P10).

**Failures degrade (P8).**

- With no token, the section says the account was not scanned. That is not an item.
- A token that was given but failed — rejected, missing a permission, rate-limited or
  unreachable — is one item that names the reason and the fix, plus a warning on standard
  error.
- The exit code never changes.

**S8 checks offline.** `repos` entries must be written `OWNER/NAME` and belong to one
product or kernel. `account.ignore` entries are `OWNER/NAME` patterns in which `*` and `?`
stand for any characters. `validate` never touches the network for the account.

**Left out.**

- The data repository.
- With `allow_public: true`, the private repositories. The report may be public, and their
  names are not.

## Consequences

- There are now two secrets. ADR 0001's P5 reads "the only secret is `GITHUB_TOKEN`";
  this ADR amends it.
- The token expires. When it does, the weekly issue stays open on one item that says the
  token was rejected, until it is replaced.
- The report has eleven sections: Account activity is section 9, and Focus and Health move
  to 10 and 11. The sections belong to the v1.0.0 contract (§9.4); 0.x allows the change.
- A data repository made from the template before 0.4.0 needs the `account-token` line added
  to its report and dashboard jobs by hand. Dependabot bumps only the pin.
- A run costs two requests, one per hundred repositories and one per candidate. That is a
  few dozen requests a week for a hundred repositories, far below the 5,000 an hour a
  token may make.
- No new dependency: `urllib` for HTTP, `fnmatch` for the patterns.

## Alternatives considered

- **Webhooks through a GitHub App.** Rejected: the webhooks need a server to receive them,
  which is a hosted service (§2), with uptime, a public endpoint and a secret of its own.
- **A workflow in every repository that notifies the data repository.** Rejected: a file
  and a secret in each of a hundred repositories, and every new repository forgotten
  until someone adds them.
- **Moving the repositories into an organisation for its webhook.** Rejected: it
  reorganises the owner's account for the tool's sake, and the webhook still needs a
  server.
- **`GITHUB_TOKEN`.** Not possible: it sees only its own repository.
- **A classic personal access token.** Rejected and refused: it cannot be read-only.
- **A GitHub App installation token** (`actions/create-github-app-token`). Deferred:
  - It would avoid expiry and a personal token.
  - But it needs an app to register and a private key as a secret.
  - `/user/repos` does not answer installation tokens, so the scan would need a second way
    to list repositories.
- **`Contents: read` and the commits API.** Rejected: the token could read every
  repository's code, and commits on a branch that has not been merged yet would be
  missed.
- **The events API.** Rejected: at most 300 events from the last 90 days, delivered late,
  and which private events it shows depends on the kind of token.
- **The push date alone.** Rejected as the rule and kept as the fallback: it cannot tell
  the owner from Dependabot.
- **Scanning in `validate`.** Rejected: `validate` runs on every push and pull request,
  and must not depend on the network or a secret.
- **Writing the repositories into `products.yaml`.** Rejected: the tool records decisions
  and does not make them (§1). The scan names what to register, and the owner registers
  it.
- **Ignoring repositories by a GitHub topic.** Rejected:
  - It keeps part of the portfolio's state outside the data repository.
  - It needs a change in each ignored repository.

  A pattern in `config.yaml` also avoids writing a person's name, where a repository is
  named after someone (§2).
- **A configurable window.** Rejected for now: P1's window keeps weekly runs gapless, and
  nothing asks for another.
