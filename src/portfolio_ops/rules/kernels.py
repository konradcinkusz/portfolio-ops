"""Kernel rules K1 and K2 (spec §6, §8.6): shared code is done when it is shared as a package.

K1 derives a kernel's state from the products that feed from it; the state is never written
in kernels.yaml. K2 finds the products that carry a copy of a kernel instead of using it
as a package — the report's Copy-paste debt.

An archived product is closed and consumes nothing: it counts neither towards a kernel's
state nor as copy-paste debt, so archiving a product never leaves a permanent report item.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from portfolio_ops.model import Kernel, Portfolio, Product

State = Literal["planned", "extracted", "done"]


@dataclass(frozen=True)
class KernelState:
    kernel: Kernel
    state: State
    package_consumers: tuple[str, ...]  # the ids of the products that use it as a package

    @property
    def summary(self) -> str:
        """'done', 'extracted, 1 of 2 package consumers' or 'planned, no package consumer'."""
        count = len(self.package_consumers)
        if self.state == "planned":
            return "planned, no package consumer"
        if self.state == "done":
            return f"done, {count} package consumers" if count != 1 else "done, 1 package consumer"
        return f"extracted, {count} of {self.kernel.min_package_consumers} package consumers"


def consumers(portfolio: Portfolio, kernel_id: str, mode: str) -> tuple[Product, ...]:
    """The products that are not archived and feed from the kernel in the given mode."""
    return tuple(
        product
        for product in portfolio.products
        if product.status != "archived"
        and any(feed.kernel == kernel_id and feed.mode == mode for feed in product.feeds_from)
    )


def kernel_state(portfolio: Portfolio, kernel: Kernel) -> KernelState:
    """K1: ``planned`` with no package consumer, ``done`` with at least
    ``min_package_consumers``, ``extracted`` in between."""
    ids = tuple(p.id for p in consumers(portfolio, kernel.id or "", "package") if p.id)
    if not ids:
        state: State = "planned"
    elif len(ids) >= kernel.min_package_consumers:
        state = "done"
    else:
        state = "extracted"
    return KernelState(kernel, state, ids)


def copies(portfolio: Portfolio) -> list[tuple[Product, Kernel]]:
    """K2: every product that consumes a kernel in ``copy`` mode, with that kernel."""
    found = []
    for kernel in portfolio.kernels:
        if kernel.id is not None:
            found += [(product, kernel) for product in consumers(portfolio, kernel.id, "copy")]
    return sorted(found, key=lambda pair: (pair[0].id or "", pair[1].id or ""))
