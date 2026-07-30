"""MORI configuration (Relative-Idleness 3-tier offloading).

Isolated module: only consumed by ``MoriRouter``. When ``--router`` is not
``mori`` this dataclass is never instantiated, so the ``tr``/``default``
baselines are completely unaffected.
"""
from dataclasses import dataclass


# B_tok for Qwen3-8B (TP-total KV bytes per token): 2(K,V) x 36 layers x 8 kv-heads
# x 128 head_dim x 2 bytes = 147,456 B = 144 KiB/tok. Used by the Phase-1 reload
# cost model. Verified against nutella C_total x B_tok = 158 GiB.
QWEN3_8B_BYTES_PER_TOKEN = 147_456


@dataclass
class MoriConfig:
    """Hyper-parameters for the MORI scheduler.

    Attributes:
        k: idleness window size (paper fixes k=5).
        cpu_capacity_ratio: r in {1, 2}; CPU tier capacity = r x GPU pool.
        reload_bw_bytes_per_s: effective host->device bandwidth for the Phase-1
            CPU->GPU reload cost model. Placeholder until calibrated by the PCIe
            microbench (M4); nutella/goguma6 both cross-NUMA SYS so this is low.
        bytes_per_token: B_tok for the served model (reload cost sizing).
        min_dwell_ticks: sticky cooldown; a program that moved tier is not moved
            again for this many scheduler ticks (anti-thrash).
        default_iota: idleness value returned when the window has no samples.
    """
    k: int = 5
    cpu_capacity_ratio: float = 1.0
    reload_bw_bytes_per_s: float = 8.0e9
    bytes_per_token: int = QWEN3_8B_BYTES_PER_TOKEN
    min_dwell_ticks: int = 1
    default_iota: float = 0.5

    def reload_seconds(self, tokens: int) -> float:
        """Phase-1 cost model: seconds to reload ``tokens`` of KV CPU->GPU."""
        if self.reload_bw_bytes_per_s <= 0:
            return 0.0
        return max(0.0, tokens) * self.bytes_per_token / self.reload_bw_bytes_per_s
