"""The views as commands: ``dashboard`` (V1) and ``export`` (V2) — where their output goes,
and what happens on data that does not validate or on a request they cannot meet."""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import copy_fixture, run_cli

NO_GIT = "note: the dashboard shows no clocks — the data directory is not inside a git repository\n"


@pytest.fixture
def data(tmp_path: Path) -> Path:
    return copy_fixture("valid", tmp_path / "valid")


def test_dashboard_writes_the_page_to_the_output_file(data: Path, tmp_path: Path) -> None:
    page = tmp_path / "dashboard.html"

    run = run_cli(["dashboard", "--path", str(data), "--output", str(page)])

    assert run.code == 0, run.err
    assert run.out == ""
    assert page.read_text(encoding="utf-8").startswith("<!doctype html>\n")
    assert run.err == NO_GIT + (
        f"portfolio-ops dashboard: wrote {page} — 5 products, 1 kernel, 2 risks, 2 findings "
        "and 3 decisions\n"
    )


@pytest.mark.parametrize("output", [[], ["--output", "-"]], ids=["default", "dash"])
def test_without_a_file_the_page_goes_to_standard_output(data: Path, output: list[str]) -> None:
    run = run_cli(["dashboard", "--path", str(data), *output])

    assert run.code == 0, run.err
    assert run.out.startswith("<!doctype html>\n")
    assert run.out.endswith("</html>\n")
    assert "wrote standard output" in run.err


def test_today_is_the_day_the_page_shows(data: Path) -> None:
    run = run_cli(["dashboard", "--path", str(data), "--today", "2026-10-15"])

    assert "<title>Portfolio dashboard — 2026-10-15</title>" in run.out
    assert '<span class="badge attention">overdue</span><span class="sub">14 days ago' in run.out


def test_the_dashboard_shows_only_data_that_validates(tmp_path: Path) -> None:
    root = copy_fixture("S4", tmp_path / "S4")
    page = tmp_path / "dashboard.html"

    run = run_cli(["dashboard", "--path", str(root), "--output", str(page)])

    assert run.code == 1
    assert run.out == ""
    assert not page.exists()
    assert run.err.startswith("error S4 ")
    assert "the data in" in run.err
    assert "does not validate" in run.err


def test_an_output_that_cannot_be_written_exits_2(data: Path, tmp_path: Path) -> None:
    page = tmp_path / "missing" / "dashboard.html"

    run = run_cli(["dashboard", "--path", str(data), "--output", str(page)])

    assert run.code == 2
    assert run.out == ""
    assert f"cannot write {page}: " in run.err


def test_export_prints_the_markdown_and_says_how_much_it_holds(data: Path) -> None:
    run = run_cli(["export", "--path", str(data)])

    assert run.code == 0, run.err
    assert run.out.startswith("# Portfolio context — 2026-09-22\n")
    assert run.err == (
        f"portfolio-ops export: {len(run.out)} of at most 12000 characters, with 3 of 3 decisions\n"
    )


def test_export_leaves_out_the_oldest_decisions_to_stay_within_max_chars(data: Path) -> None:
    run = run_cli(["export", "--path", str(data), "--max-chars", "1000"])

    assert run.code == 0, run.err
    assert len(run.out) <= 1000
    assert "The rest are left out to stay within 1000 characters" in run.out
    assert run.err.endswith(" of at most 1000 characters, with 1 of 3 decisions\n")


def test_a_limit_the_fixed_parts_do_not_fit_in_exits_2(data: Path) -> None:
    run = run_cli(["export", "--path", str(data), "--max-chars", "100"])

    assert run.code == 2
    assert run.out == ""
    assert "the export needs at least " in run.err
    assert "raise --max-chars to " in run.err


@pytest.mark.parametrize("value", ["0", "-5", "many", "1.5"])
def test_max_chars_is_a_whole_number_above_0(data: Path, value: str) -> None:
    run = run_cli(["export", "--path", str(data), "--max-chars", value])

    assert run.code == 2
    assert f"expected a whole number above 0, got '{value}'" in run.err


def test_export_shows_only_data_that_validates(tmp_path: Path) -> None:
    root = copy_fixture("S4", tmp_path / "S4")

    run = run_cli(["export", "--path", str(root)])

    assert run.code == 1
    assert run.out == ""
    assert run.err.startswith("error S4 ")
