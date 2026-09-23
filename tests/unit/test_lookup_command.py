"""``portfolio-ops lookup`` (P3): reuse what holds, check again what expired, record what
is missing — one line per recorded finding, and always exit 0 on valid data."""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import copy_fixture, run_cli, write_files

EXPIRED = """
findings:
  - id: delta-name
    subject: delta
    type: name_check
    result: No product in the store uses the name
    checked_on: 2026-01-10
"""


@pytest.fixture
def data(tmp_path: Path) -> Path:
    return copy_fixture("valid", tmp_path / "valid")


def test_a_finding_that_holds_is_reused(data: Path) -> None:
    run = run_cli(["lookup", "delta", "name_check", "--path", str(data)])

    assert run.code == 0
    assert run.lines == [
        (
            f"reuse {data.as_posix()}/findings.yaml:10: finding 'delta-name' holds until "
            "2026-12-09 — No product in the store uses the name"
        )
    ]
    assert run.err == "portfolio-ops lookup delta name_check: 1 finding holds\n"


def test_an_expired_finding_is_checked_again_and_updated_in_place(data: Path) -> None:
    write_files(data, {"findings.yaml": EXPIRED})

    run = run_cli(["lookup", "delta", "name_check", "--path", str(data)])

    assert run.code == 0
    assert run.lines == [
        (
            f"re-check {data.as_posix()}/findings.yaml:2: finding 'delta-name' held until "
            "2026-04-10 — check it again, then update its result and checked_on"
        )
    ]
    assert run.err.endswith(": nothing holds; 1 finding expired\n")


def test_today_asks_whether_a_finding_will_still_hold(data: Path) -> None:
    run = run_cli(["lookup", "alpha", "claim", "--today", "2026-12-02", "--path", str(data)])

    assert run.code == 0
    assert run.out.startswith("re-check ")
    assert run.out.endswith("update its result, checked_on and expires_on\n")


def test_nothing_recorded_means_check_then_record(data: Path) -> None:
    run = run_cli(["lookup", "portfolio", "claim", "--path", str(data)])

    assert run.code == 0
    assert run.lines == [
        (
            "check: no finding records a claim about the portfolio — check it, then record the "
            "result in findings.yaml"
        )
    ]
    assert run.err.endswith(": nothing is recorded yet\n")


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["lookup", "ghost", "claim"], "'ghost' is not a product, a kernel or portfolio"),
        (
            ["lookup", "alpha", "metric"],
            "'metric' is not a finding type — use one of: claim, name_check",
        ),
        (["lookup", "alpha"], "the following arguments are required: TYPE"),
    ],
)
def test_usage_errors_exit_2(data: Path, args: list[str], message: str) -> None:
    run = run_cli([*args, "--path", str(data)])

    assert run.code == 2
    assert run.out == ""
    assert message in run.err


def test_a_kernel_can_be_the_subject(data: Path) -> None:
    assert run_cli(["lookup", "core", "claim", "--path", str(data)]).code == 0


def test_lookup_judges_only_data_that_validates(tmp_path: Path) -> None:
    root = copy_fixture("S4", tmp_path / "S4")

    run = run_cli(["lookup", "delta", "name_check", "--path", str(root)])

    assert run.code == 1
    assert [line.split()[:2] for line in run.lines] == [["error", "S4"]]
