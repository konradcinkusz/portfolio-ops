"""Conditions that stop a command before it can judge the data (spec §7.7).

Rule violations are not exceptions: they are diagnostics, collected and reported
together. These are the cases where there is nothing to judge yet — the environment is
wrong (exit 2) or the visibility guard refuses to go on (exit 3).
"""

from __future__ import annotations

from portfolio_ops.model import Diagnostic

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_ENVIRONMENT = 2
EXIT_REFUSED = 3


class Stop(Exception):
    """Ends the command with an exit code and one message line."""

    exit_code = EXIT_ENVIRONMENT

    def __init__(self, message: str | Diagnostic) -> None:
        super().__init__(message if isinstance(message, str) else message.message)
        self.message = message

    def render(self, prefix: str = "") -> str:
        if isinstance(self.message, Diagnostic):
            return self.message.render(prefix)
        return f"error: {self.message}"


class EnvironmentProblem(Stop):
    """Usage or environment error: exit 2."""

    exit_code = EXIT_ENVIRONMENT


class Refused(Stop):
    """Refused by the visibility guard (S7): exit 3."""

    exit_code = EXIT_REFUSED
