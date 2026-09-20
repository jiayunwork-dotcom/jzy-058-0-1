"""Monod kinetics kernel.

This module is deliberately nothing but pure kinetics: no validation, no
persistence, no HTTP. It is the single source of truth for the Monod
specific-growth relation used everywhere else.

    mu(S) = mumax * S / (Ks + S)
"""

from __future__ import annotations


def specific_growth_rate(substrate: float, mumax: float, ks: float) -> float:
    """Monod specific growth rate ``mu`` at substrate concentration ``S``.

    For ``S == 0`` the limit of the Monod expression is zero; evaluating the
    fraction directly would also give ``0 / Ks == 0`` for ``Ks > 0``, but the
    short-circuit keeps the intent explicit and safe when ``Ks == 0``.
    """
    if substrate == 0.0:
        return 0.0
    return mumax * substrate / (ks + substrate)
