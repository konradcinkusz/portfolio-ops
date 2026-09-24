"""The documentation's claims are true (REPO-BASELINE.md §8, AC10).

A stale README is a review finding. These tests make the checkable claims fail loudly
instead: the action inputs and options it lists exist, the workflow it shows is the one
the spec defines, the dependency count holds, and the troubleshooting table quotes text
the engine really prints.
"""

from __future__ import annotations

import ast
import io
import json
import re
import tomllib
from pathlib import Path

import yaml

from portfolio_ops.cli import build_parser

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")
CONTRIBUTING = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
SPEC = (ROOT / "docs" / "business-rules.md").read_text(encoding="utf-8")
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
ACTION = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))


def table_rows(markdown: str, header: str) -> list[list[str]]:
    """The body rows of the Markdown table whose header row starts with ``header``."""
    lines = markdown.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def test_the_readme_lists_exactly_the_inputs_of_action_yml_with_their_defaults() -> None:
    rows = table_rows(README, "| Input |")
    documented = {row[0].strip("`"): row[1] for row in rows}

    assert set(documented) == set(ACTION["inputs"])
    for name, spec in ACTION["inputs"].items():
        if "default" in spec and "${{" not in str(spec["default"]):
            assert documented[name] == f"`{spec['default']}`", name


def test_the_readme_lists_exactly_the_outputs_of_action_yml() -> None:
    rows = table_rows(README, "| Output |")

    assert {row[0].strip("`") for row in rows} == set(ACTION["outputs"])


def test_every_option_the_readme_shows_exists_on_its_command() -> None:
    parser = build_parser(io.StringIO(), io.StringIO())
    subparsers = next(a for a in parser._actions if a.dest == "command").choices
    usage = re.search(r"```\n(portfolio-ops validate.*?)```", README, re.DOTALL)
    assert usage is not None

    for line in usage.group(1).splitlines():
        words = line.split()
        options = set(re.findall(r"--[a-z-]+", line))
        known = {
            option
            for action in subparsers.get(words[1], parser)._actions
            for option in action.option_strings
        }
        assert options <= known, (line, options - known)


def test_the_readme_shows_the_caller_workflow_of_the_spec() -> None:
    spec_block = re.search(r"```yaml\n(name: portfolio\n.*?)```", SPEC, re.DOTALL)
    readme_block = re.search(r"```yaml\n(name: portfolio\n.*?)```", README, re.DOTALL)

    assert spec_block is not None
    assert readme_block is not None
    assert readme_block.group(1) == spec_block.group(1)


def test_the_readme_states_the_runtime_dependencies_pyproject_declares() -> None:
    dependencies = [
        re.split(r"[<>=!~ ]", d, maxsplit=1)[0] for d in PYPROJECT["project"]["dependencies"]
    ]

    assert dependencies == ["PyYAML", "jsonschema"]
    assert "Two runtime dependencies: **PyYAML** and **jsonschema**" in README


def test_the_action_defaults_to_the_newest_python_ci_tests() -> None:
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    tested = ci["jobs"]["test"]["strategy"]["matrix"]["python-version"]

    assert ACTION["inputs"]["python-version"]["default"] == max(
        tested, key=lambda v: tuple(map(int, v.split(".")))
    )
    assert PYPROJECT["project"]["requires-python"] == f">={min(tested)}"


def _message_texts() -> list[str]:
    """Every string the engine and the setup script can print, joined as the parser joins
    adjacent literals, so text that spans two source lines is still one piece."""
    texts = []
    for path in [*sorted((ROOT / "src").rglob("*.py")), ROOT / "scripts" / "setup.py"]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                texts.append(node.value)
    return texts


def test_every_troubleshooting_key_is_text_the_engine_prints() -> None:
    rows = table_rows(CONTRIBUTING, "| The message contains |")
    keys = [row[0].strip("`") for row in rows]
    texts = _message_texts()

    assert len(keys) >= 15
    for key in keys:
        assert any(key in text for text in texts), key


def test_the_changelog_has_an_entry_for_the_current_version() -> None:
    version = PYPROJECT["project"]["version"]
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert re.search(rf"^## \[{re.escape(version)}\] — ", changelog, re.MULTILINE)


def test_secrets_env_example_documents_the_variables_a_user_sets() -> None:
    example = (ROOT / "secrets.env.example").read_text(encoding="utf-8")

    for name in ("GITHUB_TOKEN", "GITHUB_REPOSITORY", "PORTFOLIO_ACCOUNT_TOKEN"):
        assert re.search(rf"^{name}=$", example, re.MULTILINE), name


def test_the_standards_marketplace_is_declared() -> None:
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))

    assert settings["extraKnownMarketplaces"]["architecture-standards"]["source"] == {
        "source": "github",
        "repo": "konradcinkusz/architecture-standards",
    }
    assert settings["enabledPlugins"] == {
        "architecture-core@architecture-standards": True,
        "quality-and-process@architecture-standards": True,
    }


# ------------------------------------------------------------------ the specification (AC12)

# SHA-256 of docs/business-rules.md, revision r5, as committed. The spec changes only by a
# new revision; implementation may change nothing but the Status and Entry point columns
# of §6. A new revision updates these two constants in the same commit.
SPEC_REVISION = "r5"
SPEC_SHA256 = "e6085b8a0b963e356c2a947d40c70690d7512b12cbacc3c875aa5a3da9480ceb"
CATALOGUE_ROW = re.compile(r"^\| [A-Z][0-9] \|")


def _catalogue_rows() -> list[list[str]]:
    section = SPEC[SPEC.index("## 6. Rule catalogue") : SPEC.index("## 7. Operational definitions")]
    return [line.split(" | ") for line in section.splitlines() if CATALOGUE_ROW.match(line)]


def _with_status_columns_reset(text: str) -> str:
    start = text.index("## 6. Rule catalogue")
    end = text.index("## 7. Operational definitions")
    lines = [
        " | ".join([*line.split(" | ")[:5], "planned", "— |"])
        if CATALOGUE_ROW.match(line)
        else line
        for line in text[start:end].split("\n")
    ]
    return text[:start] + "\n".join(lines) + text[end:]


def test_implementation_changed_nothing_in_the_spec_but_status_and_entry_point() -> None:
    import hashlib

    digest = hashlib.sha256(_with_status_columns_reset(SPEC).encode("utf-8")).hexdigest()

    assert f"revision **{SPEC_REVISION}**" in SPEC
    assert digest == SPEC_SHA256


def _released_in(row: list[str]) -> str:
    """Phase n is released as v0.n.0, and a rule of several phases with the last of them."""
    return f"implemented (v0.{max(int(phase) for phase in row[4].split(', '))}.0)"


def test_every_rule_of_every_phase_is_implemented_and_its_entry_point_exists() -> None:
    import importlib

    rows = _catalogue_rows()

    structure = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]
    phase_1 = ["L1", "L2", "N1", "N2", "N3", "N4", "P2", "R1", "R2", "R3"]
    phase_2 = ["B1", "B2", "B3", "B4", "B5", "B6", "K1", "K2", "P1", "P3"]
    phase_3 = ["V1", "V2", "V3"]
    phase_4 = ["A1", "A2", "A3"]
    assert [row[0][2:] for row in rows] == [*structure, *phase_1, *phase_2, *phase_3, *phase_4]
    for row in rows:
        if row[4] == "5":  # phase 5 is being implemented: r5 adds V3 as planned
            assert row[5:] == ["planned", "— |"], row[0]
            continue
        assert row[5] == _released_in(row), row[0]
        dotted = row[6].removesuffix(" |").strip("`")
        module, _, name = dotted.rpartition(".")
        assert callable(getattr(importlib.import_module(module), name)), dotted
