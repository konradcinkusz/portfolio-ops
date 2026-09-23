"""The gate commands (spec §6 B1–B6): exit codes, message lines and usage errors."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from helpers import copy_fixture, run_cli

LINE = re.compile(r"^(error|warning) (\S+) (\S+):(\d+): (.+ — .+)$")


@pytest.mark.parametrize(
    ("rule", "file", "line"),
    [("B2", "risks.yaml", 14), ("B4", "findings.yaml", 7)],
)
def test_each_gate_fixture_fails_with_exactly_one_error_line_naming_file_and_line(
    tmp_path: Path, rule: str, file: str, line: int
) -> None:
    root = copy_fixture(rule, tmp_path / rule)

    run = run_cli(["gate", "alpha", "--context", "website", "--path", str(root)])

    assert run.code == 1
    (only,) = [text for text in run.lines if text.startswith("error ")]
    match = LINE.match(only)
    assert match, only
    assert match.group(1, 2) == ("error", rule)
    assert match.group(3).endswith(f"/{rule}/{file}")
    assert int(match.group(4)) == line
    assert "gate alpha --context website: failed — 1 error" in run.err


def test_the_idea_gate_fixture_fails_on_b6(tmp_path: Path) -> None:
    root = copy_fixture("B6", tmp_path / "B6")

    run = run_cli(["idea-gate", "delta", "--path", str(root)])

    assert run.code == 1
    assert run.out.startswith("# Idea gate — Delta (`delta`)\n")
    (only,) = [text for text in run.lines if text.startswith("error ")]
    assert only.startswith(f"error B6 {root.as_posix()}/products.yaml:26: idea 'delta' shares ")
    assert run.err == (
        "portfolio-ops idea-gate delta: failed — 1 product and 1 kernel share its capabilities\n"
    )


def test_the_valid_fixture_passes_both_gates(tmp_path: Path) -> None:
    root = copy_fixture("valid", tmp_path / "valid")

    move = run_cli(["gate", "alpha", "--context", "website", "--path", str(root)])
    idea = run_cli(["idea-gate", "delta", "--path", str(root)])

    assert move.code == 0
    assert [text.split()[:2] for text in move.lines] == [["warning", "B3"]]
    assert move.err.endswith(
        "gate alpha --context website: passed — 0 errors, 1 warning; 1 risk and 1 claim bear "
        "on the move\n"
    )
    assert idea.code == 0
    assert "**Passed.** No single product shares half of the idea's capabilities." in idea.lines


def test_a_move_nothing_bears_on_passes_quietly(tmp_path: Path) -> None:
    root = copy_fixture("valid", tmp_path / "valid")

    run = run_cli(["gate", "beta", "--context", "website", "--path", str(root)])

    assert run.code == 0
    assert run.out == ""
    assert run.err == (
        "portfolio-ops gate beta --context website: passed — 0 errors, 0 warnings; 0 risks and "
        "0 claims bear on the move\n"
    )


def test_today_sets_the_day_of_the_move(tmp_path: Path) -> None:
    root = copy_fixture("valid", tmp_path / "valid")

    run = run_cli(
        ["gate", "alpha", "--context", "website", "--today", "2027-01-01", "--path", str(root)]
    )

    # By then the acceptance of core-data-loss and the claim alpha-sync-claim have lapsed.
    assert run.code == 1
    assert [text.split()[:2] for text in run.lines] == [["error", "B2"], ["error", "B4"]]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["gate", "ghost", "--context", "website"], "there is no product 'ghost' in products.yaml"),
        (["gate", "core", "--context", "website"], "'core' is a kernel, and gate checks a product"),
        (
            ["gate", "alpha", "--context", "print"],
            (
                "'print' is not a context — use one of vocabularies.contexts in config.yaml: "
                "website, store"
            ),
        ),
        (
            ["gate", "alpha", "--context", "all"],
            "all is not a context — gate one context at a time: website, store",
        ),
        (["gate", "alpha"], "the following arguments are required: --context"),
        (["gate", "alpha", "--context", "website", "--today", "soon"], "expected a real date"),
        (["idea-gate", "alpha"], "idea-gate checks an idea, and 'alpha' is active"),
        (["idea-gate", "core"], "'core' is a kernel, and idea-gate checks a product"),
    ],
)
def test_usage_errors_exit_2(tmp_path: Path, args: list[str], message: str) -> None:
    root = copy_fixture("valid", tmp_path / "valid")

    run = run_cli([*args, "--path", str(root)])

    assert run.code == 2
    assert run.out == ""
    assert message in run.err


@pytest.mark.parametrize(
    "args", [["gate", "alpha", "--context", "website"], ["idea-gate", "delta"]], ids=" ".join
)
def test_the_gates_judge_only_data_that_validates(tmp_path: Path, args: list[str]) -> None:
    root = copy_fixture("S4", tmp_path / "S4")

    run = run_cli([*args, "--path", str(root)])

    assert run.code == 1
    assert [text.split()[:2] for text in run.lines] == [["error", "S4"]]
    assert f"the data in {root.as_posix()} does not validate — 1 error; fix them first" in run.err
