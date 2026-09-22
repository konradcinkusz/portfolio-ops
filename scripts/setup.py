"""One-command setup for working on portfolio-ops (REPO-BASELINE.md §3, ADR 0001).

    python scripts/setup.py              # everything, ending with the test suite
    python scripts/setup.py --skip-tests

Numbered steps, each failing with the fix for what went wrong:

1. check the prerequisites — Python 3.11 or newer, and git;
2. create the virtual environment ``.venv``;
3. install portfolio-ops with its development tools, at the versions pinned in
   pyproject.toml;
4. install the pre-commit hook, which scans every commit for secrets;
5. say which optional settings are missing and what they would enable;
6. run the tests.

It uses only the standard library, so it runs the same way on Linux, macOS and Windows,
and it never asks for or stores a secret: portfolio-ops has none it cannot work without.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
MINIMUM_PYTHON = (3, 11)


def step(number: int, text: str) -> None:
    print(f"\n[{number}/6] {text}", flush=True)


def fail(message: str) -> None:
    print(f"\nsetup failed: {message}", file=sys.stderr)
    print("See the troubleshooting table in CONTRIBUTING.md.", file=sys.stderr)
    raise SystemExit(1)


def shown(part: str | Path) -> str:
    """A command part as the reader would type it: paths relative to the repository."""
    if isinstance(part, Path) and part.is_relative_to(ROOT):
        return str(part.relative_to(ROOT))
    return str(part)


def run(*command: str | Path) -> None:
    printable = " ".join(shown(part) for part in command)
    print(f"      $ {printable}", flush=True)
    if subprocess.run([str(part) for part in command], cwd=ROOT, check=False).returncode:
        fail(f"'{printable}' did not succeed")


def venv_executable(name: str) -> Path:
    folder = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    return VENV / folder / f"{name}{suffix}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up a development environment.")
    parser.add_argument("--skip-tests", action="store_true", help="stop before running the tests")
    args = parser.parse_args()

    step(1, "Checking prerequisites")
    if sys.version_info < MINIMUM_PYTHON:
        fail(
            f"Python {'.'.join(map(str, MINIMUM_PYTHON))} or newer is needed, this is "
            f"{sys.version.split()[0]} — install a newer Python from https://www.python.org/downloads/"
        )
    print(f"      Python {sys.version.split()[0]}")
    if shutil.which("git") is None:
        fail("git is not on PATH — install it from https://git-scm.com/downloads")
    print("      git found")

    step(2, "Creating the virtual environment .venv")
    if venv_executable("python").exists():
        print("      .venv exists; reusing it")
    else:
        venv.create(VENV, with_pip=True)
    python = venv_executable("python")

    step(3, "Installing portfolio-ops and its development tools (versions from pyproject.toml)")
    run(python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-e", ".[dev]")

    step(4, "Installing the pre-commit hook that scans commits for secrets")
    if (ROOT / ".git").exists():
        run(venv_executable("pre-commit"), "install")
    else:
        print("      not a git clone; skipped")

    step(5, "Optional settings")
    if os.environ.get("GITHUB_TOKEN"):
        print("      GITHUB_TOKEN is set: report --publish can write the weekly-review issue")
    else:
        print(
            "      GITHUB_TOKEN is not set (optional — needed only for report --publish without "
            "--dry-run; see secrets.env.example)"
        )

    step(6, "Running the tests")
    if args.skip_tests:
        print("      skipped (--skip-tests)")
    else:
        run(python, "-m", "pytest", "-q")

    activate = r".venv\Scripts\activate" if os.name == "nt" else "source .venv/bin/activate"
    print(f"\nReady. Activate the environment with: {activate}")


if __name__ == "__main__":
    main()
