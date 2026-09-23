"""S6: schema_version is read first, and one this engine does not read stops every command."""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import FakeGitHub, copy_fixture, run_cli, write_files
from portfolio_ops.errors import EnvironmentProblem
from portfolio_ops.loading import check_schema_version, parse_yaml
from portfolio_ops.model import MIGRATIONS_URL, SCHEMA_VERSION

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMMANDS = [
    ["validate"],
    ["report"],
    ["report", "--today", "2026-09-22"],
    ["report", "--publish", "--dry-run", "--repo", "owner/name"],
    ["gate", "alpha", "--context", "website"],
    ["idea-gate", "delta"],
    ["lookup", "delta", "name_check"],
]


@pytest.mark.parametrize("command", COMMANDS, ids=" ".join)
def test_an_unsupported_schema_version_stops_every_command_with_exit_2(
    command: list[str], tmp_path: Path
) -> None:
    root = copy_fixture("S6", tmp_path / "data")

    run = run_cli([*command, "--path", str(root)])

    assert run.code == 2
    assert run.out == ""
    assert run.err.startswith("error S6 ")
    assert f"{root.as_posix()}/config.yaml:4:" in run.err
    assert "schema_version 2 is not supported" in run.err
    assert "docs/migrations/" in run.err


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ("allow_public: true\n", "schema_version is missing"),
        ('schema_version: "1"\n', "schema_version must be a whole number, not '1'"),
        ("schema_version: true\n", "schema_version must be a whole number, not True"),
        ("schema_version: 1.0\n", "schema_version must be a whole number, not 1.0"),
        ("schema_version: [1\n", "config.yaml is not valid YAML"),
        ("- schema_version: 1\n", "config.yaml is not a mapping with schema_version"),
    ],
)
def test_a_missing_or_unreadable_schema_version_stops_with_exit_2(
    tmp_path: Path, config: str, message: str
) -> None:
    root = copy_fixture("valid", tmp_path / "data")
    (root / "config.yaml").write_text(config)

    run = run_cli(["validate", "--path", str(root)])

    assert run.code == 2
    assert run.err.startswith("error S6 ")
    assert message in run.err
    assert MIGRATIONS_URL in run.err


def test_schema_version_is_checked_before_the_visibility_guard(tmp_path: Path) -> None:
    root = copy_fixture("S6", tmp_path / "data")
    config = (root / "config.yaml").read_text().replace("allow_public: true\n", "")
    (root / "config.yaml").write_text(config)
    github = FakeGitHub().on("GET", "/repos/owner/name", body={"private": False})
    env = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "owner/name", "GITHUB_TOKEN": "t"}

    run = run_cli(["validate", "--path", str(root)], env=env, github=github)

    assert run.code == 2
    assert run.err.startswith("error S6 ")
    assert github.requests == []


def test_no_config_yaml_means_the_path_is_not_a_data_directory(tmp_path: Path) -> None:
    root = write_files(tmp_path / "data", {"products.yaml": "products: []\n"})

    run = run_cli(["validate", "--path", str(root)])

    assert run.code == 2
    assert "no config.yaml in" in run.err
    assert "point --path at a portfolio data directory" in run.err


def test_the_supported_version_passes() -> None:
    doc = parse_yaml(f"schema_version: {SCHEMA_VERSION}\n", "config.yaml")

    assert check_schema_version(doc) == SCHEMA_VERSION


def test_an_unsupported_version_raises_an_s6_diagnostic_on_its_line() -> None:
    doc = parse_yaml("# comment\nschema_version: 7\n", "config.yaml")

    with pytest.raises(EnvironmentProblem) as stopped:
        check_schema_version(doc)

    assert stopped.value.exit_code == 2
    assert stopped.value.render().startswith("error S6 config.yaml:2: schema_version 7")


def test_the_migrations_page_exists_where_the_message_points() -> None:
    assert MIGRATIONS_URL.endswith("/docs/migrations/")
    assert (REPOSITORY_ROOT / "docs" / "migrations" / "README.md").is_file()
