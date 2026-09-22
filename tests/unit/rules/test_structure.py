"""S1–S5 and P2: each rule, one violation at a time, starting from the valid fixture."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from helpers import TODAY, copy_fixture, write_files
from portfolio_ops.loading import DataDir, load_portfolio, read_config, schema
from portfolio_ops.model import Diagnostic
from portfolio_ops.rules import REGISTRY, rule, validate

VALID_PRODUCTS = (Path(__file__).parents[2] / "fixtures" / "valid" / "products.yaml").read_text()


def check(tmp_path: Path, files: dict[str, str], today: dt.date = TODAY) -> list[str]:
    """Rule diagnostics for the valid fixture with ``files`` replaced."""
    root = copy_fixture("valid", tmp_path / "data")
    write_files(root, files)
    data = DataDir(root)
    loaded = load_portfolio(data, read_config(data))
    assert loaded.problems == (), [p.render() for p in loaded.problems]
    return [d.render() for d in validate(loaded.portfolio, today)]


def test_the_valid_fixture_breaks_no_rule(tmp_path: Path) -> None:
    assert check(tmp_path, {}) == []


def test_every_phase_1_validation_rule_is_registered() -> None:
    assert {"S1", "S2", "S3", "S4", "S5", "P2", "L1", "L2"} <= set(REGISTRY)


def test_a_rule_id_cannot_be_registered_twice() -> None:
    with pytest.raises(ValueError, match="registered twice"):
        rule("S1", "again")(lambda portfolio, today: iter(()))


def test_rules_report_in_catalogue_order(tmp_path: Path) -> None:
    lines = check(
        tmp_path,
        {
            "products.yaml": VALID_PRODUCTS.replace("id: omega", "id: Omega").replace(
                "status: paused", "status: halted"
            )
        },
    )

    # Omega is not a slug (S1), so the decision naming omega no longer resolves (S2) and
    # the archived product is named by no status_change (S4); beta's status is unknown (S3).
    assert [line.split()[1] for line in lines] == ["S1", "S2", "S3", "S4"]


# ------------------------------------------------------------------ the published schemas


def _tagged(node: object, parent_key: str | None = None) -> list[tuple[str, str | None]]:
    found = []
    if isinstance(node, dict):
        if "x-rule" in node:
            found.append((node["x-rule"], parent_key))
        for key, value in node.items():
            found += _tagged(value, key)
    elif isinstance(node, list):
        for item in node:
            found += _tagged(item, parent_key)
    return found


def test_rule_owned_constraints_name_a_registered_rule_and_sit_in_all_of() -> None:
    tags = [
        tag
        for kind in (schema(k) for k in ("config", "products", "kernels", "risks", "findings"))
        for tag in _tagged(kind)
    ]

    assert tags
    for rule_id, parent in tags:
        assert rule_id in (*REGISTRY, "S6"), rule_id
        assert parent == "allOf", (rule_id, parent)


# ------------------------------------------------------------------ S1


@pytest.mark.parametrize(
    ("bad_id", "message"),
    [
        ("Alpha", "product id 'Alpha' is not a valid id"),
        ("-alpha", "product id '-alpha' is not a valid id"),
        ("alpha_one", "product id 'alpha_one' is not a valid id"),
        ("a" * 64, f"product id '{'a' * 64}' is not a valid id"),
        ("all", "product id 'all' is reserved — choose another id"),
        ("portfolio", "product id 'portfolio' is reserved — choose another id"),
    ],
)
def test_s1_an_id_must_be_a_slug_and_not_reserved(
    tmp_path: Path, bad_id: str, message: str
) -> None:
    extra = f"  - id: '{bad_id}'\n    name: Extra\n    status: idea\n    capabilities: [notes]\n"

    lines = check(tmp_path, {"products.yaml": VALID_PRODUCTS + extra})

    assert len(lines) == 1
    assert lines[0].startswith(f"error S1 products.yaml:31: {message}")


def test_s1_an_id_is_unique_across_all_four_files(tmp_path: Path) -> None:
    findings = (Path(__file__).parents[2] / "fixtures" / "valid" / "findings.yaml").read_text()

    lines = check(tmp_path, {"findings.yaml": findings.replace("id: delta-name", "id: core")})

    assert lines == [
        (
            "error S1 findings.yaml:10: id 'core' is already used by the kernel at kernels.yaml:2 "
            "— "
            "ids are unique across products, kernels, risks and findings"
        )
    ]


# ------------------------------------------------------------------ S2


def test_s2_a_risk_scope_must_be_a_product_a_kernel_or_portfolio(tmp_path: Path) -> None:
    risks = """
        risks:
          - id: r1
            scope: ghost
            title: Unknown scope
            severity: low
            applies_to: [all]
            state: open
          - id: r2
            scope: portfolio
            title: Portfolio-wide
            severity: low
            applies_to: [all]
            state: open
    """

    assert check(tmp_path, {"risks.yaml": risks}) == [
        (
            "error S2 risks.yaml:3: risk 'r1' has scope 'ghost', which is not a product, a kernel "
            "or "
            "portfolio — use an existing id, or portfolio"
        )
    ]


def test_s2_a_finding_subject_must_resolve(tmp_path: Path) -> None:
    findings = """
        findings:
          - id: f1
            subject: ghost
            type: name_check
            result: Checked
            checked_on: 2026-09-01
    """

    lines = check(tmp_path, {"findings.yaml": findings})

    assert [line.split(":", 2)[:2] for line in lines] == [["error S2 findings.yaml", "3"]]


def test_s2_feeds_from_must_name_a_kernel(tmp_path: Path) -> None:
    products = VALID_PRODUCTS.replace("kernel: core", "kernel: alpha")

    assert check(tmp_path, {"products.yaml": products}) == [
        (
            "error S2 products.yaml:8: product 'alpha' feeds from 'alpha', which is not a kernel — "
            "use the id of a kernel in kernels.yaml"
        )
    ]


def test_s2_every_id_in_a_decision_heading_must_resolve(tmp_path: Path) -> None:
    decisions = (
        "## 2026-09-01 · omega · status_change\n\n"
        "## 2026-09-02 · beta, ghost · status_change\n\n"
        "## 2026-09-03 · alpha-licence · risk_accepted\n"
    )

    assert check(tmp_path, {"decisions.md": decisions}) == [
        (
            "error S2 decisions.md:3: the decision names 'ghost', which is not a product, kernel, "
            "risk or finding id — ids never change: restore the id, or correct the heading"
        )
    ]


def test_s2_portfolio_is_not_an_id_a_decision_can_name(tmp_path: Path) -> None:
    decisions = "## 2026-09-01 · omega · status_change\n## 2026-09-02 · portfolio · external\n"

    lines = check(tmp_path, {"decisions.md": decisions})

    assert len(lines) == 1
    assert lines[0].startswith("error S2 decisions.md:2: the decision names 'portfolio'")


def test_s2_renaming_a_referenced_id_fails_validation(tmp_path: Path) -> None:
    products = VALID_PRODUCTS.replace("id: omega", "id: omega-renamed")
    decisions = "## 2026-07-01 · omega · status_change\n## 2026-09-01 · omega-renamed · admit\n"

    lines = check(tmp_path, {"products.yaml": products, "decisions.md": decisions})

    assert any(line.startswith("error S2 decisions.md:1:") for line in lines)


# ------------------------------------------------------------------ S3


def test_s3_a_status_must_be_one_of_the_five(tmp_path: Path) -> None:
    products = VALID_PRODUCTS.replace("status: dormant", "status: sleeping")

    assert check(tmp_path, {"products.yaml": products}) == [
        (
            "error S3 products.yaml:19: product 'gamma' has status 'sleeping', which is not idea, "
            "active, paused, dormant or archived — use one of them"
        )
    ]


def test_s3_a_capability_must_be_configured(tmp_path: Path) -> None:
    products = VALID_PRODUCTS.replace("capabilities: [maps]", "capabilities: [maps, teleport]")

    assert check(tmp_path, {"products.yaml": products}) == [
        (
            "error S3 products.yaml:26: product 'delta' lists capability 'teleport', which is not "
            "in "
            "vocabularies.capabilities — add it to config.yaml or correct it"
        )
    ]


def test_s3_a_feeds_from_mode_must_be_package_copy_or_planned(tmp_path: Path) -> None:
    products = VALID_PRODUCTS.replace("mode: package", "mode: vendored")

    lines = check(tmp_path, {"products.yaml": products})

    assert lines == [
        (
            "error S3 products.yaml:9: product 'alpha' feeds from 'core' in mode 'vendored', which "
            "is not package, copy or planned — use one of them"
        )
    ]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("severity", "severe", "risk 'r1' has severity 'severe', which is not low, medium, high"),
        ("state", "mitigated", "risk 'r1' has state 'mitigated', which is not open, accepted"),
        ("applies_to", "[moon]", "risk 'r1' lists context 'moon', which is not in"),
        ("applies_to", "[all, store]", "risk 'r1' lists all among other contexts"),
    ],
)
def test_s3_risk_values_belong_to_their_vocabularies(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    risk = {"severity": "low", "state": "open", "applies_to": "[store]"} | {field: value}
    risks = f"""
        risks:
          - id: r1
            scope: alpha
            title: A risk
            severity: {risk["severity"]}
            applies_to: {risk["applies_to"]}
            state: {risk["state"]}
    """

    lines = check(tmp_path, {"risks.yaml": risks})

    assert len(lines) == 1
    assert lines[0].startswith("error S3 risks.yaml:")
    assert message in lines[0]


def test_s3_applies_to_all_on_its_own_is_allowed(tmp_path: Path) -> None:
    risks = """
        risks:
          - id: r1
            scope: portfolio
            title: Applies everywhere
            severity: medium
            applies_to: [all]
            state: open
    """

    assert check(tmp_path, {"risks.yaml": risks}) == []


@pytest.mark.parametrize(
    ("finding_type", "used_in", "message"),
    [
        ("rumour", "[website]", "finding 'f1' has type 'rumour', which is neither claim nor"),
        ("claim", "[website, print]", "finding 'f1' lists context 'print', which is not in"),
        ("claim", "[all]", "finding 'f1' lists context 'all', which is not in"),
    ],
)
def test_s3_finding_values_belong_to_their_vocabularies(
    tmp_path: Path, finding_type: str, used_in: str, message: str
) -> None:
    findings = f"""
        findings:
          - id: f1
            subject: alpha
            type: {finding_type}
            result: Checked
            checked_on: 2026-09-01
            expires_on: 2026-12-01
            used_in: {used_in}
    """

    lines = check(tmp_path, {"findings.yaml": findings})

    assert len(lines) == 1
    assert lines[0].startswith("error S3 findings.yaml:")
    assert message in lines[0]


def test_s3_a_ttl_must_name_a_finding_type(tmp_path: Path) -> None:
    config = (Path(__file__).parents[2] / "fixtures" / "valid" / "config.yaml").read_text()

    lines = check(tmp_path, {"config.yaml": config + "  rumour: 30\n"})

    assert lines == [
        (
            "error S3 config.yaml:19: finding_ttl_days names 'rumour', which is neither claim nor "
            "in "
            "vocabularies.finding_types — add the type or remove the TTL"
        )
    ]


@pytest.mark.parametrize(
    ("heading", "message"),
    [
        ("## Paused beta for now", "the heading does not follow"),
        ("## 2026-09-23 · alpha · focus", "the decision is dated 2026-09-23, after today"),
        ("## 2026-09-01 · alpha · shrug", "the decision has type 'shrug', which is neither"),
        ("## 2026-09-01 · alpha, beta · focus", "a focus decision names exactly one product"),
        ("## 2026-09-01 · core · defer", "a defer decision names a product, and 'core' is not"),
    ],
)
def test_s3_every_decision_heading_follows_the_grammar(
    tmp_path: Path, heading: str, message: str
) -> None:
    decisions = f"## 2026-07-01 · omega · status_change\n\n{heading}\nText.\n"

    lines = check(tmp_path, {"decisions.md": decisions})

    assert len(lines) == 1
    assert lines[0].startswith("error S3 decisions.md:3: ")
    assert message in lines[0]


def test_s3_a_decision_dated_today_is_not_in_the_future(tmp_path: Path) -> None:
    decisions = f"## 2026-07-01 · omega · status_change\n## {TODAY} · alpha · external\n"

    assert check(tmp_path, {"decisions.md": decisions}) == []


def test_s3_other_heading_levels_are_free_text(tmp_path: Path) -> None:
    decisions = "# Log\n### Notes on beta\n## 2026-07-01 · omega · status_change\n#### Why\n"

    assert check(tmp_path, {"decisions.md": decisions}) == []


# ------------------------------------------------------------------ S4


def test_s4_an_active_product_needs_a_next_action(tmp_path: Path) -> None:
    products = VALID_PRODUCTS.replace(
        "    next_action: Write the first draft of the sync protocol\n", ""
    )

    assert check(tmp_path, {"products.yaml": products}) == [
        (
            "error S4 products.yaml:2: product 'alpha' is active but has no next_action — add "
            "next_action or change its status"
        )
    ]


@pytest.mark.parametrize("capabilities", ["", "    capabilities: []\n"])
def test_s4_an_idea_needs_capabilities(tmp_path: Path, capabilities: str) -> None:
    products = VALID_PRODUCTS.replace("    capabilities: [maps]\n", capabilities)

    lines = check(tmp_path, {"products.yaml": products})

    assert len(lines) == 1
    assert lines[0].startswith("error S4 products.yaml:")
    assert "product 'delta' is an idea but lists no capabilities" in lines[0]


@pytest.mark.parametrize(
    ("removed", "message"),
    [
        ("    status_reason: Waiting until alpha ships\n", "is paused but has no status_reason"),
        ("    review_by: 2026-10-01\n", "is paused but has no review_by"),
    ],
)
def test_s4_a_paused_product_needs_a_reason_and_a_review_date(
    tmp_path: Path, removed: str, message: str
) -> None:
    products = VALID_PRODUCTS.replace(removed, "")

    lines = check(tmp_path, {"products.yaml": products})

    assert len(lines) == 1
    assert lines[0].startswith(f"error S4 products.yaml:11: product 'beta' {message}")


@pytest.mark.parametrize(
    ("status_line", "review_by", "broken"),
    [
        ("status: paused", "2026-11-21", False),  # today + 60
        ("status: paused", "2026-11-22", True),
        ("status: dormant", "2027-03-21", False),  # today + 180
        ("status: dormant", "2027-03-22", True),
    ],
)
def test_s4_review_by_is_no_later_than_today_plus_the_horizon(
    tmp_path: Path, status_line: str, review_by: str, broken: bool
) -> None:
    products = VALID_PRODUCTS.replace("status: paused", status_line).replace(
        "review_by: 2026-10-01", f"review_by: {review_by}"
    )

    lines = check(tmp_path, {"products.yaml": products})

    if broken:
        assert len(lines) == 1
        assert lines[0].startswith("error S4 products.yaml:15: product 'beta' is ")
        assert "choose a date no later than" in lines[0]
    else:
        assert lines == []


def test_s4_the_horizon_comes_from_the_configuration(tmp_path: Path) -> None:
    config = (Path(__file__).parents[2] / "fixtures" / "valid" / "config.yaml").read_text()
    config = config.replace(
        "  wip_limit: 4\n", "  wip_limit: 4\n  review_horizon_days:\n    paused: 5\n"
    )

    lines = check(tmp_path, {"config.yaml": config})

    assert len(lines) == 1
    assert "is paused with review_by 2026-10-01, more than 5 days ahead" in lines[0]


def test_s4_an_archived_product_is_named_by_a_status_change_decision(tmp_path: Path) -> None:
    decisions = "## 2026-08-03 · beta · status_change\n## 2026-07-01 · omega · admit\n"

    assert check(tmp_path, {"decisions.md": decisions}) == [
        (
            "error S4 products.yaml:30: product 'omega' is archived but no status_change decision "
            "names it — record the decision in decisions.md"
        )
    ]


def test_s4_a_present_value_of_the_wrong_type_is_not_also_reported_missing(
    tmp_path: Path,
) -> None:
    root = copy_fixture("valid", tmp_path / "data")
    products = VALID_PRODUCTS.replace(
        "next_action: Write the first draft of the sync protocol", "next_action: 42"
    )
    write_files(root, {"products.yaml": products})
    data = DataDir(root)
    loaded = load_portfolio(data, read_config(data))

    assert [p.rule for p in loaded.problems] == ["schema"]
    assert validate(loaded.portfolio, TODAY) == []


# ------------------------------------------------------------------ S5


CONFIG = (Path(__file__).parents[2] / "fixtures" / "valid" / "config.yaml").read_text()


@pytest.mark.parametrize(
    ("original", "replacement", "message"),
    [
        (
            "  contexts: [website, store]",
            "  contexts: [website, store]\n  statuses: [idea, doing]",
            "vocabularies.statuses is not a configurable vocabulary",
        ),
        (
            "  contexts: [website, store]",
            "  contexts: [website, store, all]",
            "'all' cannot be declared as a context",
        ),
        (
            "  finding_types: [name_check]",
            "  finding_types: [name_check, claim]",
            "'claim' is built in — vocabularies.finding_types only adds",
        ),
        (
            "  decision_types: [external]",
            "  decision_types: [external, defer]",
            "'defer' is built in — vocabularies.decision_types only adds",
        ),
    ],
)
def test_s5_config_extends_only_the_configurable_vocabularies(
    tmp_path: Path, original: str, replacement: str, message: str
) -> None:
    lines = check(tmp_path, {"config.yaml": CONFIG.replace(original, replacement)})

    assert len(lines) == 1
    assert lines[0].startswith("error S5 config.yaml:")
    assert message in lines[0]


def test_s5_the_configured_types_extend_the_built_in_ones(tmp_path: Path) -> None:
    decisions = "## 2026-07-01 · omega · status_change\n## 2026-09-01 · alpha · external\n"

    assert check(tmp_path, {"decisions.md": decisions}) == []


# ------------------------------------------------------------------ P2


def _findings(extra: str, finding_type: str = "claim") -> str:
    return f"""
        findings:
          - id: f1
            subject: alpha
            type: {finding_type}
            result: Verified something
        {extra}
    """


def test_p2_a_finding_needs_checked_on(tmp_path: Path) -> None:
    findings = _findings("    expires_on: 2026-12-01\n            used_in: [website]")

    assert check(tmp_path, {"findings.yaml": findings}) == [
        (
            "error P2 findings.yaml:2: finding 'f1' has no checked_on — add the date the result "
            "was "
            "verified"
        )
    ]


def test_p2_a_finding_needs_expires_on_when_no_ttl_is_configured(tmp_path: Path) -> None:
    findings = _findings("    checked_on: 2026-09-01\n            used_in: [website]")

    assert check(tmp_path, {"findings.yaml": findings}) == [
        (
            "error P2 findings.yaml:2: finding 'f1' has no expires_on and no TTL is configured for "
            "type 'claim' — add expires_on, or set finding_ttl_days.claim in config.yaml"
        )
    ]


def test_p2_a_configured_ttl_stands_in_for_expires_on(tmp_path: Path) -> None:
    findings = _findings("    checked_on: 2026-09-01", finding_type="name_check")

    assert check(tmp_path, {"findings.yaml": findings}) == []


@pytest.mark.parametrize("used_in", ["", "\n            used_in: []"])
def test_p2_a_claim_says_where_it_is_used(tmp_path: Path, used_in: str) -> None:
    findings = _findings(f"    checked_on: 2026-09-01\n            expires_on: 2026-12-01{used_in}")

    lines = check(tmp_path, {"findings.yaml": findings})

    assert len(lines) == 1
    assert lines[0].startswith("error P2 findings.yaml:")
    assert "finding 'f1' is a claim with no used_in" in lines[0]


def test_p2_only_a_claim_needs_used_in(tmp_path: Path) -> None:
    findings = _findings(
        "    checked_on: 2026-09-01\n            expires_on: 2026-12-01", "name_check"
    )

    assert check(tmp_path, {"findings.yaml": findings}) == []


def test_diagnostics_render_as_one_line_per_finding() -> None:
    diagnostic = Diagnostic("error", "S4", "products.yaml", 14, "the message — the fix")

    assert diagnostic.render() == "error S4 products.yaml:14: the message — the fix"
    assert diagnostic.render("data") == "error S4 data/products.yaml:14: the message — the fix"
