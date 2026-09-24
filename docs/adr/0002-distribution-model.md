# ADR 0002 — Distribution: a pinned composite action and a template, never a copy

- **Status:** accepted, 2026-09-22
- **Decided by:** the repository owner — business rules §3 and §8.7, with decisions D2, D3,
  D6 and D7 of the phase-1 prompt
- **Governs:** `action.yml`, `pyproject.toml`, the JSON Schemas, the workflows

## Context

The engine is public and reusable; the data it reads is private — risks, rejections,
stalled projects. Each owner keeps that data in a repository of their own. The question
is how an engine update reaches those repositories without ever copying logic into them,
and without asking owners to trust code they did not pin.

## Decision

Three layers (business rules §3):

| Layer | Repository | Visibility | Holds | Updated by |
|---|---|---|---|---|
| Engine | `konradcinkusz/portfolio-ops` | public | CLI, composite action, JSON Schemas, documentation, fictional examples | semver tags |
| Template | `konradcinkusz/portfolio-ops-template` | public, a template | a data skeleton and a caller workflow pinned to an engine version | nothing: it holds no logic |
| Data | created with "Use this template" | private | the owner's real data | bumping the pinned engine version |

- **D3 — the CI surface is a composite action at the repository root.** It installs the
  engine from its own checkout (`$GITHUB_ACTION_PATH`) into a private virtual environment,
  so the version a caller pins is the version that runs (§8.7). It leaves the caller's
  `PATH` alone.
- **D2 — no PyPI yet.** v0.1 installs from its git tag:
  `pipx install git+https://github.com/konradcinkusz/portfolio-ops@v0.1.0`. No registry
  account, no package-visibility step, while the contract may still change in 0.x.
- **D6 — the JSON Schemas ship inside the package** and are linked from the README, so
  editors validate data files as they are typed. Constraints that a rule owns are tagged
  `x-rule` inside the schema; the engine leaves those to the rule so each problem is
  reported once.
- **D7 — third-party actions are pinned by full commit SHA** with the version in a
  comment, and Dependabot keeps them current: users run this code on their private data
  with a token that can write issues. Workflows start from `contents: read`.
- **The repository name is part of the contract.** GitHub does not redirect renamed
  action repositories, so a rename would break every caller.

## Consequences

- An engine update reaches a data repository only when its owner bumps the pin — by
  hand or through Dependabot in that repository.
- The template can be regenerated from `examples/starter/` without the
  `allow_public: true` flag that the example needs only because it lives here in public.
- The action needs network access to PyPI at run time for PyYAML and jsonschema (and the
  build backend). Hash-pinning those is a candidate follow-up, recorded in the phase-1
  pull request.

## Alternatives considered

- **Forking the engine as a data repository.** Rejected (§3): a fork of a public
  repository is public, scheduled workflows are disabled in forks by default, and engine
  updates would collide with the data.
- **A reusable workflow instead of a composite action.** Rejected (§8.7): the caller
  would pin the workflow and the workflow would pin the engine — two version references to
  keep in sync, where a composite action has one.
- **Copying the engine into each data repository.** Rejected: every copy drifts, and a
  repository created from a template receives no upstream changes at all — which is why
  the template holds no logic.
- **Publishing to PyPI in phase 1.** Deferred, not rejected (D2): worth it once the
  contract freezes at v1.0.0.
