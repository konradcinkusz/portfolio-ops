"""The idea gate's reuse and overlap report (B5, B6), as Markdown.

It answers the question the idea gate asks before an idea starts: what already exists?
Markdown, so the owner can paste the tables into the ``admit`` decision that justifies an
idea the gate stopped.
"""

from __future__ import annotations

from collections.abc import Sequence

from portfolio_ops.model import Diagnostic, Kernel, Product
from portfolio_ops.report.sections import entity_label, escape
from portfolio_ops.rules.gates import IdeaGate
from portfolio_ops.rules.kernels import kernel_state


def render_idea_gate(the_gate: IdeaGate, failures: Sequence[Diagnostic], prefix: str) -> str:
    idea = the_gate.idea
    total = len(the_gate.capabilities)
    lines = [
        f"# Idea gate — {entity_label(idea.name, idea.id or '')}",
        "",
        f"Capabilities: {escape(', '.join(the_gate.capabilities))}.",
        "",
        "## Products that share capabilities",
        "",
    ]
    if the_gate.products:
        lines += ["| Product | Status | Shared | Share |", "|---|---|---|---:|"]
        for overlap in the_gate.products:
            product = overlap.entity
            status = product.status if isinstance(product, Product) else ""
            lines.append(
                f"| {entity_label(product.name, product.id or '')} | {status} | "
                f"{escape(', '.join(overlap.shared))} | {len(overlap.shared)} of {total} |"
            )
    else:
        lines.append("None: no product that is not archived shares a capability with the idea.")
    lines += ["", "## Kernels that share capabilities", ""]
    if the_gate.kernels:
        lines += ["| Kernel | Shared | State |", "|---|---|---|"]
        for overlap in the_gate.kernels:
            kernel = overlap.entity
            state = kernel_state(the_gate.portfolio, kernel) if isinstance(kernel, Kernel) else None
            lines.append(
                f"| {entity_label(kernel.name, kernel.id or '')} | "
                f"{escape(', '.join(overlap.shared))} | {state.summary if state else ''} |"
            )
        lines += ["", "Feed the idea from these kernels rather than building the same thing again."]
    else:
        lines.append("None: no kernel shares a capability with the idea.")
    lines += ["", "## Verdict", ""]
    admitted = the_gate.admitted_by
    if failures:
        lines += [
            (
                "**Failed.** A single product already has at least half of the idea's "
                "capabilities (B6):"
            ),
            "",
            "```text",
            *(failure.render(prefix) for failure in failures),
            "```",
        ]
    elif admitted is not None and the_gate.dominant():
        lines.append(
            f"**Passed** on the admit decision of {admitted.date}, which names `{idea.id}` and "
            "carries the reason it stands apart."
        )
    else:
        lines.append("**Passed.** No single product shares half of the idea's capabilities.")
    return "\n".join(lines) + "\n"
