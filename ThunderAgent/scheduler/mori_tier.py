"""CPU tier bookkeeping — MORI paper §4.1 (the middle tier ThunderAgent lacks).

ThunderAgent has only GPU (``BackendState._programs``) and Waiting
(``global_waiting_queue``). MORI inserts a CPU tier between them: KV is held in
host DRAM (Phase 2: SGLang HiCache host pool; Phase 1: bookkept only) so a
program can be demoted off the GPU without discarding its KV, then promoted back
by paying a reload cost instead of a full recompute.

We keep this tier in ``MoriRouter`` (one ``CpuTier`` per backend) rather than in
``BackendState`` so that ``backend/state.py`` needs **zero** diff and the
``tr`` capacity math is byte-identical — the isolation invariant I4.

Capacity accounting uses the **same convention** as the GPU tier (prefix sharing
ignored, ``BUFFER_PER_PROGRAM`` per program) so MORI and TA+O are compared on
equal footing — invariant I2.
"""
from typing import Dict, List, Tuple, TYPE_CHECKING

from ..backend.state import BUFFER_PER_PROGRAM

if TYPE_CHECKING:
    from ..program.state import Program


class CpuTier:
    """Token-capacity-bounded holding area for KV-offloaded programs."""

    def __init__(self, url: str, capacity_tokens: int) -> None:
        self.url = url
        self.capacity_tokens = int(capacity_tokens)
        self._programs: Dict[str, "Program"] = {}

    # -- capacity (GPU-tier convention) --
    def used_tokens(self) -> int:
        return sum(p.total_tokens for p in self._programs.values()) + \
            len(self._programs) * BUFFER_PER_PROGRAM

    def remaining(self) -> int:
        return self.capacity_tokens - self.used_tokens()

    def can_admit(self, state: "Program") -> bool:
        return self.remaining() >= state.total_tokens + BUFFER_PER_PROGRAM

    # -- membership --
    def admit(self, program_id: str, state: "Program") -> None:
        self._programs[program_id] = state

    def remove(self, program_id: str):
        return self._programs.pop(program_id, None)

    def contains(self, program_id: str) -> bool:
        return program_id in self._programs

    def items(self) -> List[Tuple[str, "Program"]]:
        return list(self._programs.items())

    def count(self) -> int:
        return len(self._programs)
