# ADR 0006 — The gates and lookup are commands that judge only valid data

- **Status:** proposed, 2026-09-23 — accepted when the owner merges phase 2
- **Decided by:** the engine's reading of business rules §6 B1–B6 and P3, for the owner
  to confirm
- **Governs:** `src/portfolio_ops/rules/gates.py`, `src/portfolio_ops/rules/memory.py`,
  `src/portfolio_ops/report/overlap.py`, the `gate`, `idea-gate` and `lookup` commands

## Context

§6 names three new commands — `gate <product> --context <ctx>`, `idea-gate <product>`
and `lookup` — while §7.6, the interface that freezes at v1.0.0, still lists only
`validate` and `report`. The spec fixes what each gate decides and its exit code (a
failed gate exits 1, §7.7), and leaves open the arguments, the output, what happens on
data that does not validate, and where the commands run.

## Decision

**Interfaces.**

```
portfolio-ops gate PRODUCT --context CONTEXT [--path DIR] [--today YYYY-MM-DD]
portfolio-ops idea-gate IDEA [--path DIR]
portfolio-ops lookup SUBJECT TYPE [--path DIR] [--today YYYY-MM-DD]
```

Ids are positional; `--context` is required and must be a declared context — `all` is
not one, so a move is gated one context at a time. `--today` exists where the date
decides the answer: acceptances and expiries.

**Order.** Like every command: config.yaml, S6, S7. Then the data is validated, and a
command that judges data judges only data that validates: errors are printed as
`validate` prints them and the command exits 1. Then the arguments are checked against
the data — an unknown product, context, subject or finding type, a kernel where a
product is needed, or `idea-gate` on a product that is not an idea, exits 2.

**`gate`** prints §7.8 lines: `error B2` and `error B4` fail the move, `warning B3` does
not; a verdict line goes to standard error; any error exits 1.

- B1 follows `feeds_from` in every mode, `planned` included: a product that is about to
  take on a kernel is gated on the kernel's risks already.
- B2 counts an acceptance past its `accepted_until` as open, as B3 says, and points at
  the date that lapsed.
- B4 checks the claims whose subject is the product, as §6 words it. A claim about a
  kernel or about the portfolio is not checked by the gate; the report lists it when it
  expires.

**`idea-gate`** runs on a product whose status is `idea` — the idea gate is the step from
`idea` to `active` (§5). It prints a Markdown report — the products that are not
archived and the kernels that share the idea's capabilities, each kernel with its state
(K1) — so the tables can be pasted into the `admit` decision that justifies the idea.
B6 fails once per product that has at least half of the idea's capabilities, until any
`admit` decision names the idea.

**`lookup`** prints one line per finding about the subject of that type — `reuse`,
`re-check`, or `check` when nothing is recorded — and exits 0 on valid data: it informs,
it does not judge.

**Where they run.** Locally, at the moment of the move, in a clone of the data
repository. The composite action keeps the inputs of §7.6 and runs `validate` and
`report` only.

**Registered checks.** B2–B4 register with `@gate_check` and B6 with `@idea_check`, like
the validation rules (P10); a new gate check is a function and a decorator.

## Consequences

- Exit code 1 keeps one meaning per command: this data, or this move, does not pass.
  `portfolio-ops gate app --context store && ./publish.sh` works as a guard.
- A broken data file can never make a gate pass: a risk with an unreadable severity is a
  validation error, not a risk the gate skipped.
- The idea gate's report and the weekly report share their Markdown helpers, and the
  idea gate has golden files like the weekly report.

## Alternatives considered

- **Gates as warnings of `validate`.** Rejected: a gate answers a question about one move
  in one context, and `validate` judges the state of all the data.
- **Judging data that does not validate, and skipping what cannot be read.** Rejected: a
  gate that passes because it could not read a risk is worse than no gate.
- **JSON output.** Rejected for now: nothing consumes it yet, and the §7.8 lines are
  stable, searchable and what `validate` prints.
- **`idea-gate` on any product.** Rejected: it would answer a question no status change
  asks, and B6's escape hatch — an `admit` decision — is the entry into `active`.
- **Inputs for the gates in the composite action.** Deferred: it would widen the action's
  contract before v1.0.0 for a use — gating from the Actions UI — that no one has asked
  for.
