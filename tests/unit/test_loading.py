"""The edge (P11): YAML and Markdown become the typed model, with a line for every value."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from helpers import FIXTURES, write_files
from portfolio_ops import model
from portfolio_ops.loading import (
    DataDir,
    Loaded,
    check_shape,
    load_portfolio,
    parse_decisions,
    parse_yaml,
    read_config,
    schema,
)


def _load(root: Path) -> Loaded:
    data = DataDir(root)
    return load_portfolio(data, read_config(data))


def test_dates_and_yes_no_words_stay_text_under_yaml_1_2() -> None:
    doc = parse_yaml("a: 2026-09-22\nb: no\nc: 1:30\nd: true\ne: 0x10\nf: ~\n", "f.yaml")

    assert doc.value == {"a": "2026-09-22", "b": "no", "c": "1:30", "d": True, "e": 16}


def test_every_value_knows_the_line_that_introduces_it() -> None:
    doc = parse_yaml("products:\n  - id: alpha\n    capabilities:\n      - sync\n", "p.yaml")

    assert doc.lines[("products", 0)] == 2
    assert doc.lines[("products", 0, "id")] == 2
    assert doc.lines[("products", 0, "capabilities")] == 3
    assert doc.lines[("products", 0, "capabilities", 0)] == 4


def test_an_empty_value_counts_as_absent() -> None:
    doc = parse_yaml("next_action:\nname: '  '\nstatus: active\n", "p.yaml")

    assert doc.value == {"status": "active"}


def test_a_duplicate_key_is_reported_on_its_own_line() -> None:
    doc = parse_yaml("status: paused\nname: Beta\nstatus: active\n", "p.yaml")

    assert [d.render() for d in doc.problems] == [
        "error schema p.yaml:3: duplicate key 'status' — keep one of them"
    ]
    assert doc.value["status"] == "paused"


def test_yaml_aliases_are_refused() -> None:
    doc = parse_yaml("a: &shared [x]\nb: *shared\n", "c.yaml")

    assert [d.line for d in doc.problems] == [2]
    assert "aliases are not supported" in doc.problems[0].message


def test_invalid_yaml_is_reported_with_its_line_and_marks_the_file_unreadable() -> None:
    doc = parse_yaml("products:\n  - id: alpha\n   name: broken\n", "products.yaml")

    assert doc.fatal
    assert doc.problems[0].rule == "schema"
    assert doc.problems[0].line == 3
    assert doc.problems[0].message.startswith("products.yaml is not valid YAML:")


def test_the_valid_fixture_loads_without_problems() -> None:
    loaded = _load(FIXTURES / "valid")

    assert loaded.problems == ()
    assert not loaded.fatal
    assert [p.id for p in loaded.portfolio.products] == ["alpha", "beta", "gamma", "delta", "omega"]
    assert loaded.portfolio.kernels[0].min_package_consumers == 2
    assert loaded.portfolio.config.finding_types == ("claim", "name_check")


def test_an_unknown_key_is_a_schema_error_that_lists_the_allowed_keys(tmp_path: Path) -> None:
    root = write_files(
        tmp_path,
        {
            "config.yaml": "schema_version: 1\n",
            "products.yaml": """
                products:
                  - id: alpha
                    name: Alpha
                    status: active
                    nxt_action: Ship it
            """,
            "decisions.md": "",
        },
    )

    problems = [d.render() for d in _load(root).problems]

    assert problems == [
        (
            "error schema products.yaml:5: unknown key 'nxt_action' in product 'alpha' — check the "
            "spelling; allowed keys: id, name, status, next_action, capabilities, feeds_from, "
            "status_reason, review_by"
        )
    ]


def test_a_missing_always_required_field_is_reported_on_the_entity_line(tmp_path: Path) -> None:
    root = write_files(
        tmp_path,
        {
            "config.yaml": "schema_version: 1\n",
            "products.yaml": "products:\n  - id: alpha\n    status: idea\n    capabilities: []\n",
            "decisions.md": "",
        },
    )

    problems = [d.render() for d in _load(root).problems]

    assert problems == ["error schema products.yaml:2: product 'alpha' has no name — add it"]


@pytest.mark.parametrize(
    ("yaml_text", "message"),
    [
        (
            "  wip_limit: four\n",
            "thresholds.wip_limit in config.yaml must be a whole number, not text",
        ),
        ("  wip_limit: 0\n", "thresholds.wip_limit in config.yaml must be at least 1, not 0"),
        ("  stale_days: true\n", "thresholds.stale_days in config.yaml must be a whole number"),
    ],
)
def test_a_threshold_of_the_wrong_type_or_range_is_a_schema_error(
    tmp_path: Path, yaml_text: str, message: str
) -> None:
    root = write_files(
        tmp_path,
        {
            "config.yaml": "schema_version: 1\nthresholds:\n" + yaml_text,
            "products.yaml": "products: []\n",
            "decisions.md": "",
        },
    )

    problems = _load(root).problems

    assert len(problems) == 1
    assert problems[0].rule == "schema"
    assert problems[0].line == 3
    assert problems[0].message.startswith(message)


def test_a_date_that_does_not_exist_is_a_schema_error(tmp_path: Path) -> None:
    root = write_files(
        tmp_path,
        {
            "config.yaml": "schema_version: 1\n",
            "products.yaml": """
                products:
                  - id: beta
                    name: Beta
                    status: paused
                    status_reason: Waiting
                    review_by: 2026-02-30
            """,
            "decisions.md": "",
        },
    )

    problems = [d.render() for d in _load(root).problems]

    assert problems == [
        (
            "error schema products.yaml:6: review_by of product 'beta' must be a real date written "
            "YYYY-MM-DD, not '2026-02-30' — correct it"
        )
    ]


def test_an_accepted_risk_without_accepted_until_is_a_schema_error(tmp_path: Path) -> None:
    root = write_files(
        tmp_path,
        {
            "config.yaml": "schema_version: 1\nvocabularies:\n  contexts: [web]\n",
            "products.yaml": "products: []\n",
            "risks.yaml": """
                risks:
                  - id: risky
                    scope: portfolio
                    title: Something may break
                    severity: low
                    applies_to: [web]
                    state: accepted
            """,
            "decisions.md": "",
        },
    )

    problems = [d.render() for d in _load(root).problems]

    assert problems == [
        (
            "error schema risks.yaml:2: risk 'risky' is accepted but has no accepted_until — add "
            "the date the acceptance ends"
        )
    ]


def test_constraints_owned_by_rules_are_left_to_the_rules(tmp_path: Path) -> None:
    root = write_files(
        tmp_path,
        {
            "config.yaml": "schema_version: 1\nvocabularies:\n  contexts: [all]\n",
            "products.yaml": """
                products:
                  - id: Not-A-Slug
                    name: Bad id
                    status: activ
                  - id: beta
                    name: Beta
                    status: active
            """,
            "decisions.md": "",
        },
    )

    assert _load(root).problems == ()


def test_missing_optional_files_mean_no_entries(tmp_path: Path) -> None:
    root = write_files(
        tmp_path,
        {
            "config.yaml": "schema_version: 1\n",
            "products.yaml": "products: []\n",
            "decisions.md": "",
        },
    )

    loaded = _load(root)

    assert loaded.problems == ()
    assert loaded.portfolio.kernels == loaded.portfolio.risks == loaded.portfolio.findings == ()


def test_a_missing_required_file_is_reported_and_stops_the_rules(tmp_path: Path) -> None:
    root = write_files(tmp_path, {"config.yaml": "schema_version: 1\n", "decisions.md": ""})

    loaded = _load(root)

    assert loaded.fatal
    assert [d.render() for d in loaded.problems] == [
        "error schema products.yaml: products.yaml is missing — create it with 'products:'"
    ]


def test_only_data_files_named_by_the_spec_are_read(tmp_path: Path) -> None:
    root = write_files(
        tmp_path,
        {
            "config.yaml": "schema_version: 1\n",
            "products.yaml": "products: []\n",
            "decisions.md": "",
            "notes.yaml": "this: [is not read",
        },
    )

    assert _load(root).problems == ()


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        (
            "## 2026-09-22 · alpha, beta · status_change",
            ("2026-09-22", ("alpha", "beta"), "status_change"),
        ),
        ("## 2026-09-22 | alpha | focus", ("2026-09-22", ("alpha",), "focus")),
        ("## 2026-09-22 · alpha · focus ##", ("2026-09-22", ("alpha",), "focus")),
        ("## 2026-09-22 | alpha · defer", ("2026-09-22", ("alpha",), "defer")),
    ],
)
def test_decision_headings_that_follow_the_grammar_parse(
    heading: str, expected: tuple[str, tuple[str, ...], str]
) -> None:
    (decision,) = parse_decisions(heading + "\nWhy.\n")

    assert decision.error is None
    assert (str(decision.date), decision.ids, decision.type) == expected


@pytest.mark.parametrize(
    ("heading", "error"),
    [
        ("## Decided to pause beta", "does not follow"),
        ("## 22.09.2026 · alpha · focus", "is not a date written YYYY-MM-DD"),
        ("## 2026-02-30 · alpha · focus", "is not a real date"),
        ("## 2026-09-22 · alpha, · focus", "names an empty id"),
        ("## 2026-09-22 · alpha · focus · extra", "does not follow"),
        ("##", "does not follow"),
    ],
)
def test_decision_headings_that_break_the_grammar_carry_the_reason(
    heading: str, error: str
) -> None:
    (decision,) = parse_decisions(heading + "\n")

    assert decision.error is not None
    assert error in decision.error


def test_headings_in_code_blocks_and_other_levels_are_free_text() -> None:
    text = "# Decisions\n### A note\n```\n## not a decision\n```\n~~~~\n## nor this\n~~~~\n"

    assert parse_decisions(text) == ()


def test_decision_lines_are_counted_from_the_top_of_the_file() -> None:
    decisions = parse_decisions(
        "# Log\n\n## 2026-09-01 · a · focus\ntext\n\n## 2026-09-08 · b · focus\n"
    )

    assert [d.line for d in decisions] == [3, 6]


# ------------------------------------------------------------------ the published schemas


def _schemas() -> dict[str, dict[str, object]]:
    return {kind: schema(kind) for kind in ("config", "products", "kernels", "risks", "findings")}


@pytest.mark.parametrize("kind", ["config", "products", "kernels", "risks", "findings"])
def test_each_published_schema_is_valid_draft_07(kind: str) -> None:
    Draft7Validator.check_schema(schema(kind))


def test_the_schemas_list_exactly_the_vocabularies_the_engine_fixes() -> None:
    text = json.dumps(_schemas())

    for values in (model.STATUSES, model.SEVERITIES, model.RISK_STATES, model.FEED_MODES):
        assert json.dumps(list(values)) in text
    assert json.dumps(list(model.BUILTIN_DECISION_TYPES)) in text
    assert json.dumps(list(model.CONFIGURABLE_VOCABULARIES)) in text


def test_the_schemas_use_the_engine_id_and_vocabulary_patterns() -> None:
    text = json.dumps(_schemas())

    assert json.dumps(f"^{model.ID_PATTERN}$") in text
    assert json.dumps(f"^{model.VOCABULARY_PATTERN}$") in text


def test_every_fixture_file_matches_its_published_schema_except_where_a_rule_fails() -> None:
    doc = parse_yaml((FIXTURES / "valid" / "products.yaml").read_text(), "products.yaml")

    assert check_shape(doc, "products") == []
    full = Draft7Validator(schema("products"), format_checker=Draft7Validator.FORMAT_CHECKER)
    assert list(full.iter_errors(doc.value)) == []
