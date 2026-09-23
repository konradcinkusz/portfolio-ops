## What changes, and why

<!-- The behaviour that changes and the reason. If a rule changes, name its id (S4, N1…)
     and the section of docs/business-rules.md that governs it. -->

## Rules touched

<!-- Rule ids and what happens to each. A new or changed rule updates the Status and Entry
     point columns of §6 in docs/business-rules.md in the same pull request. "None" is a
     fine answer. -->

## How it is tested

<!-- The tests that protect the change. A rule needs a violating fixture under
     tests/fixtures/<rule-id>/ and a passing case. -->

## Checklist

- [ ] `python scripts/setup.py` passes locally (lint and types run in CI)
- [ ] No real personal or portfolio data anywhere — fixtures and examples are invented
- [ ] Every command, option and action input the README mentions still exists and is tested
- [ ] `CHANGELOG.md` updated under the unreleased version
- [ ] A breaking change to the data format increments `schema_version` and adds a note to `docs/migrations/`
