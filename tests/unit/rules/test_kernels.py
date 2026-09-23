"""K1 and K2 (spec §8.6): a kernel is done when enough products use it as a package, and a
product that copies a kernel carries debt."""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import load_valid
from portfolio_ops.rules.kernels import copies, kernel_state

# The valid fixture's kernel `core` has one package consumer, alpha.
FEEDING = """
  - id: {pid}
    name: {name}
    status: {status}
    next_action: Keep going
    feeds_from:
      - kernel: core
        mode: {mode}
"""


def with_products(*extra: str) -> dict[str, str]:
    products = (Path(__file__).parents[2] / "fixtures" / "valid" / "products.yaml").read_text()
    decisions = (Path(__file__).parents[2] / "fixtures" / "valid" / "decisions.md").read_text()
    # Archived products need a status_change decision to be valid data.
    return {
        "products.yaml": products + "".join(extra),
        "decisions.md": decisions + "\n## 2026-09-01 · eta · status_change\nArchived eta.\n",
    }


def feeding(pid: str, mode: str, status: str = "paused") -> str:
    entry = FEEDING.format(pid=pid, name=pid.title(), status=status, mode=mode)
    if status == "paused":
        entry += "    status_reason: Later\n    review_by: 2026-10-01\n"
    return entry.replace("    next_action: Keep going\n", "") if status == "archived" else entry


def state_of(tmp_path: Path, *extra: str, minimum: int | None = None) -> tuple[str, str]:
    files = with_products(*extra)
    if minimum is not None:
        files["kernels.yaml"] = (
            f"kernels:\n  - id: core\n    name: Core\n    min_package_consumers: {minimum}\n"
        )
    portfolio = load_valid(tmp_path / "data", files)
    state = kernel_state(portfolio, portfolio.kernels[0])
    return state.state, state.summary


def test_k1_one_package_consumer_of_the_default_two_is_extracted(tmp_path: Path) -> None:
    assert state_of(tmp_path) == ("extracted", "extracted, 1 of 2 package consumers")


def test_k1_min_package_consumers_make_it_done(tmp_path: Path) -> None:
    assert state_of(tmp_path, feeding("zeta", "package")) == ("done", "done, 2 package consumers")


def test_k1_no_package_consumer_is_planned(tmp_path: Path) -> None:
    files = {"kernels.yaml": "kernels:\n  - id: spare\n    name: Spare\n"}
    portfolio = load_valid(tmp_path / "data", files | {"products.yaml": _without_feeds()})
    state = kernel_state(portfolio, portfolio.kernels[0])

    assert (state.state, state.summary) == ("planned", "planned, no package consumer")


def _without_feeds() -> str:
    products = (Path(__file__).parents[2] / "fixtures" / "valid" / "products.yaml").read_text()
    return products.replace("    feeds_from:\n      - kernel: core\n        mode: package\n", "")


def test_k1_between_one_and_the_minimum_is_extracted(tmp_path: Path) -> None:
    # The spec names "extracted (one)" and "done (at least min_package_consumers)"; with a
    # minimum of 3, two consumers fall between them and count as extracted.
    assert state_of(tmp_path, feeding("zeta", "package"), minimum=3) == (
        "extracted",
        "extracted, 2 of 3 package consumers",
    )


def test_k1_a_minimum_of_one_makes_the_first_consumer_done(tmp_path: Path) -> None:
    assert state_of(tmp_path, minimum=1) == ("done", "done, 1 package consumer")


@pytest.mark.parametrize(
    ("mode", "status"),
    [("copy", "paused"), ("planned", "paused"), ("package", "archived")],
)
def test_k1_counts_only_package_consumers_that_are_not_archived(
    tmp_path: Path, mode: str, status: str
) -> None:
    assert state_of(tmp_path, feeding("eta", mode, status))[0] == "extracted"


def test_k2_lists_every_product_that_copies_a_kernel_but_not_archived_ones(
    tmp_path: Path,
) -> None:
    portfolio = load_valid(
        tmp_path / "data",
        with_products(
            feeding("zeta", "copy"), feeding("eta", "copy", "archived"), feeding("iota", "copy")
        ),
    )

    assert [(p.id, k.id) for p, k in copies(portfolio)] == [("iota", "core"), ("zeta", "core")]
