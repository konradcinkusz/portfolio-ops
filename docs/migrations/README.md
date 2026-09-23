# Data format migrations

`config.yaml` names the version of the data format it is written in:

```yaml
schema_version: 1
```

Every portfolio-ops command reads this first (rule S6). A version the engine does not read
stops the command with exit code 2 and a pointer to this page, before any other data file
is read.

## Versions

| `schema_version` | Read by | What it is |
|---|---|---|
| 1 | portfolio-ops 0.1.0 | The initial format of [business rules r1](../business-rules.md), §4 |

## If a command sent you here

The message says which version the data has and which the engine reads:

```
error S6 config.yaml:1: schema_version 2 is not supported by portfolio-ops 0.1.0, which reads schema_version 1 — see …/docs/migrations/
```

- **The data is newer than the engine** (the first number is larger): pin a newer engine
  version in the caller workflow of your data repository, or upgrade the CLI you run
  locally.
- **The data is older than the engine** (the first number is smaller): follow the sections
  below, one version at a time, and then set `schema_version` to the version the engine
  reads.
- **`schema_version is missing`**: add `schema_version: 1` at the top of `config.yaml`.

## How migrations are made

While portfolio-ops is 0.x anything may change (business rules §9.4), but a breaking change
to the data format never arrives silently. It:

1. increments `schema_version`;
2. adds a section below saying what changed and how to move data from the previous
   version, as steps a person can follow in a pull request to their data repository;
3. is listed in the [changelog](../../CHANGELOG.md).

A change that only adds an optional field or a rule does not change the version.

There are no migrations yet: version 1 is the first format.
