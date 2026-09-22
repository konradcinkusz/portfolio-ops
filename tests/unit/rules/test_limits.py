"""L1 and L2 (spec §8.1): the WIP limit, and the arithmetic that makes it meaningful."""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import FIXTURES, TODAY, copy_fixture, write_files
from portfolio_ops.loading import DataDir, load_portfolio, read_config
from portfolio_ops.rules import validate

CONFIG = (FIXTURES / "valid" / "config.yaml").read_text()
# Replacing the products leaves nothing for the fixture's risks, findings and decisions to
# refer to, so they go too.
NO_REFERENCES = {"risks.yaml": "risks: []\n", "findings.yaml": "findings: []\n", "decisions.md": ""}


def check(tmp_path: Path, files: dict[str, str]) -> list[str]:
    root = copy_fixture("valid", tmp_path / "data")
    write_files(root, files)
    data = DataDir(root)
    loaded = load_portfolio(data, read_config(data))
    assert loaded.problems == ()
    return [d.render() for d in validate(loaded.portfolio, TODAY)]


def _active(count: int) -> str:
    """``count`` active products; product n's status sits on line 4n."""
    return "products:\n" + "".join(
        f"  - id: p{n}\n    name: Product {n}\n    status: active\n    next_action: Step {n}\n"
        for n in range(1, count + 1)
    )


def _thresholds(block: str) -> str:
    return CONFIG.replace(
        "thresholds:\n  stale_days: 30\n  actions_per_week: 1\n  wip_limit: 4\n",
        f"thresholds:\n{block}",
    )


def test_l1_as_many_active_products_as_the_limit_is_fine(tmp_path: Path) -> None:
    assert check(tmp_path, {"products.yaml": _active(4), **NO_REFERENCES}) == []


def test_l1_one_active_product_over_the_limit_is_an_error_listing_them_all(
    tmp_path: Path,
) -> None:
    lines = check(tmp_path, {"products.yaml": _active(5), **NO_REFERENCES})

    assert lines == [
        (
            "error L1 products.yaml:20: 5 products are active but wip_limit is 4: p1, p2, p3, "
            "p4, p5 — keep at most 4 of them active and move the rest to paused or dormant with "
            "a review_by"
        )
    ]


def test_l1_counts_only_active_products(tmp_path: Path) -> None:
    products = _active(4) + (
        "  - id: idle\n    name: Idle\n    status: paused\n    status_reason: Later\n"
        "    review_by: 2026-10-10\n"
    )

    assert check(tmp_path, {"products.yaml": products, **NO_REFERENCES}) == []


def test_l1_follows_the_configured_limit(tmp_path: Path) -> None:
    config = _thresholds("  wip_limit: 2\n")

    lines = check(tmp_path, {"config.yaml": config, "products.yaml": _active(3), **NO_REFERENCES})

    assert len(lines) == 1
    assert lines[0].startswith(
        "error L1 products.yaml:12: 3 products are active but wip_limit is 2"
    )


def test_l2_the_defaults_make_no_noise(tmp_path: Path) -> None:
    config = _thresholds("")

    assert check(tmp_path, {"config.yaml": config}) == []


def test_l2_a_limit_above_the_arithmetic_is_a_warning_worded_as_the_spec_shows(
    tmp_path: Path,
) -> None:
    config = _thresholds("  stale_days: 30\n  actions_per_week: 1\n  wip_limit: 6\n")

    assert check(tmp_path, {"config.yaml": config}) == [
        (
            "warning L2 config.yaml:9: wip_limit 6 exceeds 30 / 7 × 1 = 4.3 — the weekly report "
            "will flag most active products"
        )
    ]


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        ("  stale_days: 14\n  actions_per_week: 1.5\n", "wip_limit 4 exceeds 14 / 7 × 1.5 = 3.0"),
        ("  stale_days: 21\n  wip_limit: 4\n", "wip_limit 4 exceeds 21 / 7 × 1 = 3.0"),
        ("  stale_days: 28\n", None),  # 28 / 7 × 1 = 4, and 4 is not more than 4
        ("  actions_per_week: 2\n  wip_limit: 8\n", None),
    ],
)
def test_l2_compares_wip_limit_with_stale_days_over_7_times_actions_per_week(
    tmp_path: Path, block: str, expected: str | None
) -> None:
    lines = check(tmp_path, {"config.yaml": _thresholds(block)})

    if expected is None:
        assert lines == []
    else:
        assert len(lines) == 1
        assert lines[0].startswith("warning L2 config.yaml:")
        assert expected in lines[0]
