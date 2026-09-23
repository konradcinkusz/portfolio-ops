"""The gates B1–B6 (spec §6, §8.5), as pure functions of the valid fixture.

The valid fixture: alpha (active) feeds from kernel core as a package; core carries the
high risk core-data-loss, accepted until 2026-12-31 for every context; alpha carries the
medium, open risk alpha-licence for store, and a claim used on the website until
2026-12-01. delta is an idea with the capability maps.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from helpers import FIXTURES, TODAY, load_valid
from portfolio_ops.model import Portfolio
from portfolio_ops.rules.gates import (
    GATE_CHECKS,
    IDEA_CHECKS,
    collect_risks,
    gate,
    gate_check,
    idea_check,
    idea_gate,
    overlaps,
    run_gate,
    run_idea_gate,
)

VALID = {name: (FIXTURES / "valid" / name).read_text() for name in ("products.yaml", "risks.yaml")}
VALID["findings.yaml"] = (FIXTURES / "valid" / "findings.yaml").read_text()
VALID["decisions.md"] = (FIXTURES / "valid" / "decisions.md").read_text()
VALID["config.yaml"] = (FIXTURES / "valid" / "config.yaml").read_text()


def edited(name: str, old: str, new: str) -> dict[str, str]:
    assert VALID[name].count(old) == 1, old
    return {name: VALID[name].replace(old, new)}


def run(portfolio: Portfolio, product: str, context: str, today: dt.date = TODAY) -> list[str]:
    target = portfolio.product(product)
    assert target is not None
    return [d.render() for d in run_gate(gate(portfolio, target, context, today))]


def risk_ids(portfolio: Portfolio, product: str, context: str) -> list[str | None]:
    target = portfolio.product(product)
    assert target is not None
    return [r.id for r in collect_risks(portfolio, target, context)]


PORTFOLIO_RISK = """
  - id: portfolio-wide
    scope: portfolio
    title: One maintainer for everything
    severity: low
    applies_to: [website]
    state: open
"""

ZETA = """
  - id: zeta
    name: Zeta
    status: paused
    status_reason: Later
    review_by: 2026-10-01
    feeds_from:
      - kernel: core
        mode: planned
"""


# ------------------------------------------------------------------ B1


def test_b1_collects_the_products_risks_for_the_contexts_they_apply_to(tmp_path: Path) -> None:
    portfolio = load_valid(tmp_path / "data")

    assert risk_ids(portfolio, "alpha", "store") == ["alpha-licence", "core-data-loss"]
    assert risk_ids(portfolio, "alpha", "website") == ["core-data-loss"]


def test_b1_a_kernels_risk_reaches_every_consumer_whatever_its_mode(tmp_path: Path) -> None:
    portfolio = load_valid(tmp_path / "data", {"products.yaml": VALID["products.yaml"] + ZETA})

    assert risk_ids(portfolio, "zeta", "website") == ["core-data-loss"]


def test_b1_collects_portfolio_risks_for_every_product(tmp_path: Path) -> None:
    portfolio = load_valid(tmp_path / "data", {"risks.yaml": VALID["risks.yaml"] + PORTFOLIO_RISK})

    assert risk_ids(portfolio, "beta", "website") == ["portfolio-wide"]
    assert risk_ids(portfolio, "beta", "store") == []


def test_b1_leaves_out_the_risks_of_other_products(tmp_path: Path) -> None:
    portfolio = load_valid(tmp_path / "data")

    assert risk_ids(portfolio, "beta", "store") == []


# ------------------------------------------------------------------ B2 and B3


def test_b3_an_acceptance_that_holds_is_a_warning_on_accepted_until(tmp_path: Path) -> None:
    assert run(load_valid(tmp_path / "data"), "alpha", "website") == [
        (
            "warning B3 risks.yaml:15: risk 'core-data-loss' of kernel 'core', which alpha feeds "
            "from, is accepted until 2026-12-31, with severity high, and applies to every "
            "context — the gate passes on that acceptance; make sure it still covers this move"
        )
    ]


def test_b3_an_acceptance_holds_on_its_last_day(tmp_path: Path) -> None:
    lines = run(load_valid(tmp_path / "data"), "alpha", "website", today=dt.date(2026, 12, 31))
    risk_lines = [line.split()[:2] for line in lines if " risks.yaml:" in line]

    assert risk_lines == [["warning", "B3"]]


def test_b2_an_open_high_risk_blocks_the_move(tmp_path: Path) -> None:
    files = edited(
        "risks.yaml", "    state: accepted\n    accepted_until: 2026-12-31\n", "    state: open\n"
    )

    assert run(load_valid(tmp_path / "data", files), "alpha", "website") == [
        (
            "error B2 risks.yaml:14: risk 'core-data-loss' of kernel 'core', which alpha feeds "
            "from, is open with severity high and applies to every context — mitigate it and "
            "lower its severity, or accept it until a date with a risk_accepted decision"
        )
    ]


def test_b2_an_acceptance_past_its_date_counts_as_open(tmp_path: Path) -> None:
    lines = run(load_valid(tmp_path / "data"), "alpha", "website", today=dt.date(2027, 1, 1))

    assert lines[0] == (
        "error B2 risks.yaml:15: risk 'core-data-loss' of kernel 'core', which alpha feeds from, "
        "was accepted until 2026-12-31, so it counts as open again, with severity high, and "
        "applies to every context — renew the acceptance with a later accepted_until and a "
        "risk_accepted decision, or mitigate the risk and lower its severity"
    )


@pytest.mark.parametrize(
    ("severity", "blocks"), [("low", False), ("medium", False), ("high", True), ("critical", True)]
)
def test_b2_only_high_and_critical_open_risks_block(
    tmp_path: Path, severity: str, blocks: bool
) -> None:
    files = edited("risks.yaml", "    severity: medium\n", f"    severity: {severity}\n")
    lines = run(load_valid(tmp_path / "data", files), "alpha", "store")

    assert (
        any(
            line.startswith("error B2 risks.yaml:7: risk 'alpha-licence' of alpha ")
            for line in lines
        )
        is blocks
    )


def test_b2_a_closed_risk_never_blocks(tmp_path: Path) -> None:
    files = edited(
        "risks.yaml", "    state: accepted\n    accepted_until: 2026-12-31\n", "    state: closed\n"
    )

    assert run(load_valid(tmp_path / "data", files), "alpha", "website") == []


# ------------------------------------------------------------------ B4


def test_b4_an_expired_claim_used_in_the_context_blocks(tmp_path: Path) -> None:
    files = edited("findings.yaml", "expires_on: 2026-12-01", "expires_on: 2026-09-01")
    lines = run(load_valid(tmp_path / "data", files), "alpha", "website")

    assert lines[-1] == (
        "error B4 findings.yaml:7: claim 'alpha-sync-claim' about alpha is used in website but "
        "held only until 2026-09-01 — re-verify it before use, then update checked_on and "
        "expires_on"
    )


def test_b4_a_claim_holds_on_its_last_day(tmp_path: Path) -> None:
    files = edited("findings.yaml", "expires_on: 2026-12-01", "expires_on: 2026-09-22")

    assert not any(
        " B4 " in line for line in run(load_valid(tmp_path / "data", files), "alpha", "website")
    )


def test_b4_a_claim_used_elsewhere_does_not_block_this_context(tmp_path: Path) -> None:
    files = edited("findings.yaml", "expires_on: 2026-12-01", "expires_on: 2026-09-01")

    assert not any(
        " B4 " in line for line in run(load_valid(tmp_path / "data", files), "alpha", "store")
    )


def test_b4_an_expiry_from_a_ttl_points_at_checked_on(tmp_path: Path) -> None:
    files = edited("findings.yaml", "    expires_on: 2026-12-01\n", "")
    files |= edited("config.yaml", "  name_check: 90\n", "  name_check: 90\n  claim: 14\n")
    lines = run(load_valid(tmp_path / "data", files), "alpha", "website")

    assert lines[-1] == (
        "error B4 findings.yaml:6: claim 'alpha-sync-claim' about alpha is used in website but "
        "held only until 2026-09-15 — re-verify it before use, then update checked_on"
    )


def test_b4_checks_claims_only_and_only_about_the_product(tmp_path: Path) -> None:
    files = {
        "findings.yaml": (
            "findings:\n"
            "  - id: name\n    subject: alpha\n    type: name_check\n    result: Free\n"
            "    checked_on: 2026-01-01\n    expires_on: 2026-02-01\n    used_in: [website]\n"
            "  - id: other\n    subject: beta\n    type: claim\n    result: Fast\n"
            "    checked_on: 2026-01-01\n    expires_on: 2026-02-01\n    used_in: [website]\n"
        )
    }

    assert not any(
        " B4 " in line for line in run(load_valid(tmp_path / "data", files), "alpha", "website")
    )


# ------------------------------------------------------------------ B5 and B6


IDEAS = """
  - id: zeta
    name: Zeta
    status: idea
    capabilities: [sync, maps]

  - id: theta
    name: Theta
    status: archived
"""


def with_idea(capabilities: str, extra_products: str = "", decisions: str = "") -> dict[str, str]:
    products = VALID["products.yaml"].replace(
        "    status: idea\n    capabilities: [maps]\n",
        f"    status: idea\n    capabilities: {capabilities}\n",
    )
    return {
        "products.yaml": products + extra_products,
        "decisions.md": VALID["decisions.md"] + decisions,
    }


def check_idea(portfolio: Portfolio, idea: str = "delta") -> list[str]:
    target = portfolio.product(idea)
    assert target is not None
    return [d.render() for d in run_idea_gate(idea_gate(portfolio, target, TODAY))]


def test_b5_lists_products_that_are_not_archived_and_kernels_most_shared_first(
    tmp_path: Path,
) -> None:
    extra = IDEAS.replace("status: archived", "status: archived\n    capabilities: [maps, notes]")
    decisions = "\n## 2026-09-01 · theta · status_change\nArchived.\n"
    portfolio = load_valid(tmp_path / "data", with_idea("[maps, notes, sync]", extra, decisions))
    delta = portfolio.product("delta")
    assert delta is not None

    products, kernels = overlaps(portfolio, delta)

    assert [(o.entity.id, o.shared) for o in products] == [
        ("zeta", ("maps", "sync")),
        ("alpha", ("sync",)),
    ]
    assert [(o.entity.id, o.shared) for o in kernels] == [("core", ("sync",))]


def test_b6_half_of_the_ideas_capabilities_in_one_product_fails_the_gate(tmp_path: Path) -> None:
    portfolio = load_valid(tmp_path / "data", with_idea("[sync, notes]"))

    assert check_idea(portfolio) == [
        (
            "error B6 products.yaml:26: idea 'delta' shares 1 of its 2 capabilities with product "
            "'alpha' (sync) — merge it into 'alpha' by archiving the idea, or record an admit "
            "decision that names delta and says why it stands apart"
        )
    ]


def test_b6_less_than_half_passes(tmp_path: Path) -> None:
    assert check_idea(load_valid(tmp_path / "data", with_idea("[sync, notes, maps]"))) == []


def test_b6_an_admit_decision_that_names_the_idea_lets_it_pass(tmp_path: Path) -> None:
    decisions = "\n## 2026-09-20 · delta · admit\nDelta works offline first; alpha never will.\n"
    portfolio = load_valid(tmp_path / "data", with_idea("[sync]", decisions=decisions))
    delta = portfolio.product("delta")
    assert delta is not None

    assert check_idea(portfolio) == []
    admitted = idea_gate(portfolio, delta, TODAY).admitted_by
    assert admitted is not None
    assert admitted.date == dt.date(2026, 9, 20)


def test_b6_an_admit_decision_about_something_else_does_not_count(tmp_path: Path) -> None:
    decisions = "\n## 2026-09-20 · alpha · admit\nNot about delta.\n"

    assert (
        len(check_idea(load_valid(tmp_path / "data", with_idea("[sync]", decisions=decisions))))
        == 1
    )


def test_b6_another_idea_counts_and_an_archived_product_does_not(tmp_path: Path) -> None:
    extra = IDEAS.replace("status: archived", "status: archived\n    capabilities: [notes]")
    decisions = "\n## 2026-09-01 · theta · status_change\nArchived.\n"
    portfolio = load_valid(tmp_path / "data", with_idea("[maps, notes]", extra, decisions))

    assert [line.split("product ")[1].split()[0] for line in check_idea(portfolio)] == ["'zeta'"]


def test_b6_reports_every_product_that_holds_half_of_the_idea(tmp_path: Path) -> None:
    portfolio = load_valid(
        tmp_path / "data", with_idea("[sync, maps]", IDEAS.split("\n  - id: theta")[0] + "\n")
    )

    assert [line.split("product ")[1].split()[0] for line in check_idea(portfolio)] == [
        "'zeta'",
        "'alpha'",
    ]


# ------------------------------------------------------------------ registries


def test_the_gate_checks_are_registered_under_their_catalogue_ids() -> None:
    assert list(GATE_CHECKS) == ["B2", "B3", "B4"]
    assert list(IDEA_CHECKS) == ["B6"]


def test_a_gate_rule_cannot_be_registered_twice() -> None:
    with pytest.raises(ValueError, match="registered twice"):
        gate_check("B2")(lambda the_gate: iter(()))
    with pytest.raises(ValueError, match="registered twice"):
        idea_check("B6")(lambda the_gate: iter(()))
