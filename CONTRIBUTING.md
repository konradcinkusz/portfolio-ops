# Contributing to portfolio-ops

Thank you for helping. Two rules come before everything else:

- **[docs/business-rules.md](docs/business-rules.md) is the source of truth.** If the code
  and that document disagree, the document wins; a change in behaviour starts as a change
  to the document.
- **Never commit real portfolio data.** This repository is public and a pushed commit is
  public forever. Fixtures and examples use invented names only.

## Setup — one command

You need Python 3.11 or newer and git. Then, from a clone:

```bash
python scripts/setup.py
```

It checks the prerequisites, creates `.venv`, installs portfolio-ops with its development
tools at the versions pinned in `pyproject.toml`, installs the pre-commit hook that scans
every commit for secrets, and runs the tests. Nothing to configure: `GITHUB_TOKEN` is
optional and only needed to publish a report, and `PORTFOLIO_ACCOUNT_TOKEN` only to scan an
account (see [secrets.env.example](secrets.env.example)). The tests never reach GitHub.
CI runs this same script, so if it works in CI it works for you.

## Everyday commands

With the environment activated (`source .venv/bin/activate`, or `.venv\Scripts\activate`
on Windows):

| What | Command |
|---|---|
| All tests, unit and integration | `python -m pytest` |
| Lint | `ruff check src tests scripts` |
| Format | `ruff format src tests scripts` |
| Types (strict for `src/`) | `mypy` |
| Secret scan over the whole history | `pre-commit run gitleaks-history --hook-stage manual` |
| Regenerate the golden reports and pages after an intended change | `python -m pytest --update-golden`, then review the diff |
| Run the engine | `portfolio-ops validate --path examples/starter` |
| Look at the example dashboard | `portfolio-ops dashboard --path examples/starter --output dashboard.html` |

CI runs all of these on every pull request — lint, types, the tests on Python 3.11 and
3.13, the dependency audit, the secret scan and the action's self-test — plus CodeQL.

## Where things live

| Area | Code | Tests |
|---|---|---|
| Typed model, JSON Schemas | `src/portfolio_ops/model.py`, `src/portfolio_ops/schemas/` | `tests/unit/test_loading.py` |
| Reading the data (P11), S6 | `src/portfolio_ops/loading.py` | `tests/unit/test_loading.py`, `tests/unit/test_schema_version.py` |
| Rules S1–S5, S8, P2, L1, L2 | `src/portfolio_ops/rules/` | `tests/unit/rules/`, `tests/fixtures/<rule-id>/` |
| Visibility guard (S7) | `src/portfolio_ops/guard.py`, `src/portfolio_ops/github.py` | `tests/unit/test_guard.py` |
| The clock (N1) | `src/portfolio_ops/history.py`, `src/portfolio_ops/git.py` | `tests/integration/test_clock.py` |
| Changes and their decisions (P1) | `src/portfolio_ops/rules/changes.py`, `src/portfolio_ops/history.py` | `tests/unit/rules/test_changes.py`, `tests/integration/test_changes.py` |
| The report (N2–N4, R1–R3, K2) | `src/portfolio_ops/report/` | `tests/unit/report/` |
| Gates (B1–B6) | `src/portfolio_ops/rules/gates.py`, `src/portfolio_ops/report/overlap.py` | `tests/unit/rules/test_gates.py`, `tests/unit/test_gate_commands.py`, `tests/fixtures/B*/` |
| Kernels (K1, K2) | `src/portfolio_ops/rules/kernels.py` | `tests/unit/rules/test_kernels.py` |
| Lookup (P3) | `src/portfolio_ops/rules/memory.py` | `tests/unit/rules/test_memory.py`, `tests/unit/test_lookup_command.py` |
| Views: dashboard (V1), export (V2) | `src/portfolio_ops/views/` | `tests/unit/views/`, `tests/unit/test_view_commands.py`, `tests/integration/test_views.py` |
| The account scan (A1–A3) | `src/portfolio_ops/account.py`, `src/portfolio_ops/github.py`, `src/portfolio_ops/rules/account.py` | `tests/unit/test_account.py`, `tests/unit/rules/test_account.py`, `tests/unit/report/test_account_section.py`, `tests/unit/test_account_commands.py` |
| Command line | `src/portfolio_ops/cli.py` | `tests/unit/test_cli.py` |
| Composite action | `action.yml` | the `self-test` job in `.github/workflows/ci.yml` |

## Adding or changing a rule

1. Change [docs/business-rules.md](docs/business-rules.md) first, or open a
   "Rule question or proposal" issue.
2. Write the rule as a function in `src/portfolio_ops/rules/` and register it with
   `@rule("ID", "summary")` — or `@gate_check("ID")` / `@idea_check("ID")` for a check of
   `gate` or `idea-gate` — no base class to inherit (P10). Rules are pure: they read the
   typed model and today's date and return diagnostics; they never read files, git or the
   network.
3. Add a fixture under `tests/fixtures/<rule-id>/` that differs from `tests/fixtures/valid/`
   in exactly one place, and tests for both the violation and the passing case.
4. Messages follow §7.8: one line, `<severity> <rule> <file>:<line>: <what> — <fix>`, with
   the line of the offending value, or of the entity when a field is missing.
5. Update the Status and Entry point columns of §6, the CHANGELOG, and this document's
   troubleshooting table if people will meet the message.

## Troubleshooting

Find the line you saw by pasting part of it into your browser's search. Each key below is
text the engine really prints — a test keeps this table honest.

| The message contains | What it means | What to do |
|---|---|---|
| `is active but has no next_action` | S4: an active product needs one next step | Add `next_action`, or change the product's status |
| `is archived but no status_change decision names it` | S4: archiving is a decision, and decisions are logged | Add `## <date> · <id> · status_change` to decisions.md |
| `days ahead — choose a date no later than` | S4: `review_by` is past the review horizon for its status | Pick an earlier date: at most 60 days ahead when paused, 180 when dormant |
| `products are active but wip_limit is` | L1: more products are in progress than the limit allows | Move the rest to `paused` or `dormant`, each with a `review_by` |
| `the weekly report will flag most active products` | L2 (warning): the thresholds make the report noise (spec §8.1) | Lower `wip_limit`, or raise `stale_days` or `actions_per_week` |
| `which is not a product, kernel, risk or finding id` | S2: a decision names an id that no longer exists — ids never change | Restore the id and change the `name` instead, or correct the heading |
| `the heading does not follow` | S3: a level-2 heading in decisions.md is not a decision | Write it as `## 2026-09-22 · <id> · <type>`, or use `###` for other headings |
| `no TTL is configured for type` | P2: a finding needs to know when it expires | Add `expires_on`, or set `finding_ttl_days.<type>` in config.yaml |
| `is a claim with no used_in` | P2: a claim must say where it is used externally | List the contexts in `used_in` |
| `unknown key` | `schema`: a key the format does not have — usually a typo | Fix the spelling; the message lists the keys that exist |
| `is not valid YAML` | `schema`: the file does not parse | Fix the syntax at the line shown |
| `is not supported by portfolio-ops` | S6: the data format and the engine version differ | Follow [docs/migrations/](docs/migrations/README.md), or pin a matching engine version |
| `schema_version is missing` | S6: config.yaml does not say which format it uses | Add `schema_version: 1` |
| `and no decision names it on that day` | P1 (warning): a product's status or a risk's state changed with no decision dated that day | Add the heading the message shows to decisions.md — a decision may be dated in the past |
| `a transition the product lifecycle does not have` | P1 (warning): the status moved in a way §5 does not allow | Move it along §5 next time; the report shows it for a week |
| `P1 was not checked` | `validate` on a shallow clone cannot see the previous commit | Set `fetch-depth: 0` on `actions/checkout`, or run `git fetch --unshallow` |
| `is open with severity` | B2: an open high or critical risk applies to the move | Mitigate it and lower its severity, or accept it until a date with a `risk_accepted` decision |
| `so it counts as open again` | B2: the acceptance of a high or critical risk has ended | Renew it with a later `accepted_until` and a `risk_accepted` decision, or mitigate the risk |
| `held only until` | B4: a claim used in this context has expired | Verify it again before the move, then update `checked_on` (and `expires_on`) |
| `by archiving the idea` | B6: an existing product already has half of the idea's capabilities | Archive the idea to merge it into that product, or record an `admit` decision that names it and says why it stands apart |
| `is not a context` | `gate` needs one of the contexts you declared | Use a context from `vocabularies.contexts` in config.yaml, or add it there |
| `idea-gate checks an idea` | `idea-gate` compares a product whose status is `idea` | Name the idea, or give the product the status `idea` if it is one |
| `does not set allow_public: true` | S7: the data repository is public | Make the repository private, or set `allow_public: true` if you build in public |
| `cannot tell whether the data repository is public` | S7: the guard could not ask GitHub | In Actions: pass the workflow's token and check its access. Locally this is a warning only |
| `this is a shallow clone` | `report` needs the full history for the clock, and the dashboard shows no clocks without it | Set `fetch-depth: 0` on `actions/checkout`, or run `git fetch --unshallow` |
| `is not inside a git repository` | `report` reads the clock from git; the dashboard leaves the clocks out | Run it in a clone of the data repository |
| `the export needs at least` | `--max-chars` is too small for the products, risks and vocabulary, which are always exported in full | Raise `--max-chars` to the number the message names, or drop it for the default of 12000 |
| `expected a whole number above 0` | `--max-chars` is not a positive whole number | Pass a number of characters, such as `--max-chars 8000` |
| `cannot write` | `dashboard --output` names a file that cannot be written — often in a directory that does not exist | Create the directory, or choose another path |
| `--publish needs GITHUB_TOKEN` | Publishing writes an issue and needs a token | Set `GITHUB_TOKEN`, or add `--dry-run` to preview |
| `--dry-run previews publishing, so it needs --publish` | `--dry-run` only makes sense when publishing | Add `--publish`, or drop `--dry-run` |
| `git is not on PATH` | `scripts/setup.py` needs git | Install git from <https://git-scm.com/downloads> |
| `which is not written OWNER/NAME` | S8: an entry of `repos` is not a repository name | Write it as GitHub shows it, such as `your-name/tidewatch` |
| `a repository belongs to one product or kernel` | S8: two products or kernels list the same repository | Keep it in the `repos` of one of them |
| `which is not a repository pattern` | S8: an `account.ignore` entry is not `OWNER/NAME` | Write `OWNER/NAME`; `*` and `?` may stand for any characters |
| `GitHub rejected PORTFOLIO_ACCOUNT_TOKEN` | The account token has expired or been revoked | Create a new fine-grained token and replace the secret `PORTFOLIO_ACCOUNT_TOKEN` |
| `is a classic personal access token` | The account token is a classic one, which cannot be read-only | Create a fine-grained token with access to all repositories, and replace the secret |
| `the token may not list the account's repositories` | The account token cannot see the account's repositories | Give it repository access "All repositories"; the read-only Metadata permission is enough |
| `could not be told apart from other pushes` | GitHub did not show the token a repository's activity list, so any push counts there | Add the permission the message names to the token, or accept the fallback |
| `rate limit is spent` | The account token made too many requests this hour | Nothing: the next run scans again |

## Releasing

Releases are tag-driven (P12) and only the owner tags.

1. Set the version in `pyproject.toml`.
2. In CHANGELOG.md, replace "Unreleased" in that version's heading with today's date.
3. Merge, then tag the merge commit `vX.Y.Z`, in either way:
   - **In the GitHub portal:** Releases → Draft a new release → Choose a tag: type
     `vX.Y.Z` and choose "Create new tag on publish" → Target: `main` → Publish release.
     Leave the title and notes empty: the release workflow fills them in.
   - **With git:** `git tag vX.Y.Z <merge commit> && git push origin vX.Y.Z`.

The release workflow runs on the new tag. It checks that the tag, `pyproject.toml` and a
dated CHANGELOG entry agree, runs the tests on the tagged commit, and gives the release the
CHANGELOG entry as its notes. A release published in the portal exists before those checks
run: if the workflow fails, delete the release and its tag, fix the cause, and publish
again.

## Standards

This repository follows the `architecture-standards` marketplace, declared in
[.claude/settings.json](.claude/settings.json). [ADR 0001](docs/adr/0001-standards-scope.md)
says which parts apply to a Python tool, and [CLAUDE.md](CLAUDE.md) repeats the working
rules for agents.
