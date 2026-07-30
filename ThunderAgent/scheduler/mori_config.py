"""MORI configuration (Relative-Idleness 3-tier offloading).

Isolated module: only consumed by ``MoriRouter``. When ``--router`` is not
``mori`` this dataclass is never instantiated, so the ``tr``/``default``
baselines are completely unaffected.
"""
from dataclasses import dataclass


@dataclass
class MoriConfig:
    """Hyper-parameters for the MORI scheduler.

    (Re-scope 2026-07-30: the Phase-1 CPU->GPU reload cost model is removed —
    the CPU tier maps to the real SGLang HiCache host pool, so reload cost is
    paid by the engine, not modeled here.)

    Attributes:
        k: idleness window size (paper fixes k=5).
        cpu_capacity_ratio: r in {1, 2}; CPU tier capacity = r x GPU pool.
        min_dwell_ticks: sticky cooldown; a program that moved tier is not moved
            again for this many scheduler ticks (anti-thrash).
        default_iota: idleness value returned when the window has no samples.
    """
    k: int = 5
    cpu_capacity_ratio: float = 1.0
    min_dwell_ticks: int = 1
    default_iota: float = 0.5
