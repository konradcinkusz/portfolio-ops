# ADR 0007 — The views: a self-contained dashboard and a size-bounded export

- **Status:** proposed, 2026-09-23 — accepted when the owner merges phase 3
- **Decided by:** the engine's reading of business rules §1 and §6 V1–V2, for the owner to
  confirm
- **Governs:** `src/portfolio_ops/views/`, the `dashboard` and `export` commands, the
  action's `dashboard` command and output

## Context

§1 says "Dashboards and exports are views: they show state and contain no rules". §6 adds
two of them in phase 3:

- **V1**, a static HTML dashboard. For a private data repository it is never published to
  GitHub Pages; it is a workflow artifact or a local file.
- **V2**, a size-bounded Markdown export for LLM sessions. It holds the active and paused
  products with their next actions, the open risks of severity `medium` or higher, the
  latest decisions and the capability vocabulary.

§9.3's exit criterion is that the dashboard covers everything a hand-maintained overview
showed, so that overview can be deleted.

The spec leaves open:

- the interfaces
- what the dashboard shows and how the page is built
- what "size-bounded" measures, and what gives way when the data does not fit
- whether the views need git history
- how a workflow gets the page as an artifact

## Decision

**Interfaces.**

```
portfolio-ops dashboard [--path DIR] [--today YYYY-MM-DD] [--output FILE]
portfolio-ops export [--path DIR] [--today YYYY-MM-DD] [--max-chars N]
```

**Only valid data, like the gates (ADR 0006).** Both views validate first. On errors they
print them and exit 1, and render nothing, because a view of data that does not validate
would show a portfolio that does not exist. Their errors go to standard error: standard
output may be the page, and `dashboard > page.html` must not hide a validation error in
a file.

**Views decide nothing.** A view has no rule id, prints no diagnostic and never changes an
exit code. It reuses what the rules already derive:

- the clock (N1)
- stale (N2) and overdue (N4)
- this week's focus (R3)
- a kernel's state (K1) and copy-paste debt (K2)
- whether an acceptance (B3) or a finding (P2) still holds

**The dashboard shows everything, in ten registered panels** (P10, as the report's
sections):

1. summary tiles
2. active products with their next action, clock, capabilities and kernels
3. ideas
4. paused and dormant products, the soonest review first
5. archived products
6. kernels with their state and consumers by mode
7. risks, those that count as open first
8. findings, the soonest to expire first
9. the capability map
10. the ten latest decisions with their text

A tile stands out when what it counts needs the owner: an item of the weekly report, a risk
that fails a gate, or an expired finding.

**The page is one self-contained file.**

- The stylesheet is inline, shipped as package data.
- There is no script, font, image, form or outside link, so the page works offline, from
  an artifact or a local file, and fetches nothing that could leak that it was opened.
- A `Content-Security-Policy` meta tag allows exactly that stylesheet, by its SHA-256.
- Every value from the data is escaped.
- The page carries `noindex, nofollow` and a visible note: "Private … never publish it on
  GitHub Pages".
- Dates are `<time>` elements. Light and dark follow the system, tables scroll inside
  their panel on a phone, and the page prints.

**The dashboard degrades without history (P8), where `report` stops.** Outside a git
repository, or on a shallow clone, the page renders without clocks, and says why on the
page and on standard error. The clock is the heart of the weekly report, but one column of
the dashboard.

**The export follows V2's list, in V2's order.**

- Products, risks and the vocabulary are always there in full.
- The newest decisions, each with its text, fill what is left of `--max-chars`, and the
  export says how many it left out.
- A decision is whole or left out, never cut.
- "Open" includes an acceptance past its date, as B3 says.
- The limit counts characters, 12000 by default: about three thousand tokens.
- A limit the fixed parts do not fit in exits 2 and names the smallest one that fits.
- The export needs no history, so it runs on any directory, like `validate`.
- Text is written as it is, not Markdown-escaped: the reader is a model, not a renderer.

**Where they run.**

- The action gains `command: dashboard`. It writes the page to `$RUNNER_TEMP`, outside the
  workspace so it cannot be committed by accident, and sets the output `dashboard` to its
  path.
- The caller uploads the page with `actions/upload-artifact`. A private repository's
  artifacts are readable only by those who can read the repository.
- `export` stays local: it is pasted into a session, and nothing in CI consumes it.

## Consequences

- The dashboard's golden pages pin every byte, the stylesheet included. A change to the
  stylesheet changes the policy's hash, and a test recomputes it.
- The action's contract grows by one command and one output, before v1.0.0 freezes it
  (§9.4). r2 should add both views to §7.6.
- A decision's text is now part of the model: the parser keeps the lines under each
  heading.

## Alternatives considered

- **Publishing the dashboard with GitHub Pages.** Rejected by V1 and §8.8: Pages sites of
  private repositories can be public, depending on the plan and its settings.
- **Charts or a front-end library from a CDN.** Rejected: the page would fetch code every
  time it opens, tell a third party when it was opened, and break offline. Tables and a
  stylesheet show state well enough.
- **A Markdown dashboard.** Rejected: the weekly report is the Markdown view, and it shows
  only what needs attention. The dashboard shows everything, and a static page can do that
  where an issue body cannot.
- **The action uploading the artifact itself.** Rejected: the caller would lose control of
  the artifact's name and retention, and the action would pin a second third-party action
  for every command.
- **`dashboard` exiting 2 on a shallow clone, like `report`.** Rejected: a view without its
  one git-derived column is still a correct view of the files. The action fetches the
  history anyway.
- **Bounding the export in tokens.** Rejected: tokenizers differ between models and would
  add a dependency. Characters are stable, and the default leaves room in any model's
  context.
- **Cutting the decision that does not fit.** Rejected: a decision cut in the middle can
  read as a different decision. The export says what it left out instead.
- **An export in the action, or `--output` on `export`.** Deferred: nothing in CI consumes
  it, and the shell's redirection already writes a file.
