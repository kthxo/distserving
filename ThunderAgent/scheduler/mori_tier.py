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
import time
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from ..backend.state import BUFFER_PER_PROGRAM

if TYPE_CHECKING:
    from ..program.state import Program


class CpuTier:
    """Token-capacity-bounded holding area for KV-offloaded programs."""

    def __init__(self, url: str, capacity_tokens: int) -> None:
        self.url = url
        self.capacity_tokens = int(capacity_tokens)
        self._programs: Dict[str, "Program"] = {}
        # Last-access wall-clock per resident program — the LRU tie-break source for
        # typed eviction (paper §4.3.2: "within each type, LRU breaks ties").
        # Without this the eviction sort has only ι as a key, so equal-ι programs
        # fall back to dict insertion order (FIFO), which is not LRU. Equal ι is not
        # a corner case: programs with no idleness samples all share
        # ``MoriConfig.default_iota``.
        self._last_access: Dict[str, float] = {}

    # -- capacity (GPU-tier convention) --
    def used_tokens(self) -> int:
        return sum(p.total_tokens for p in self._programs.values()) + \
            len(self._programs) * BUFFER_PER_PROGRAM

    def remaining(self) -> int:
        return self.capacity_tokens - self.used_tokens()

    def can_admit(self, state: "Program") -> bool:
        return self.remaining() >= state.total_tokens + BUFFER_PER_PROGRAM

    # -- membership --
    def admit(self, program_id: str, state: "Program", now: Optional[float] = None) -> None:
        self._programs[program_id] = state
        self.touch(program_id, now=now, state=state)

    def remove(self, program_id: str):
        self._last_access.pop(program_id, None)
        return self._programs.pop(program_id, None)

    def contains(self, program_id: str) -> bool:
        return program_id in self._programs

    def items(self) -> List[Tuple[str, "Program"]]:
        return list(self._programs.items())

    def count(self) -> int:
        return len(self._programs)

    # -- LRU bookkeeping (paper §4.3.2 tie-break) --
    def touch(
        self,
        program_id: str,
        now: Optional[float] = None,
        state: Optional["Program"] = None,
    ) -> None:
        """Stamp ``program_id``'s last-access time.

        Preference order:
          1. explicit ``now`` (caller knows the access instant),
          2. ``state.last_response_end`` — the last time this program actually used
             its KV on the GPU, which is what "least recently used" means here,
          3. wall-clock (a program that has never produced a response; treat the
             admission instant as its access time rather than leaving it unranked).
        """
        if now is None:
            st = state if state is not None else self._programs.get(program_id)
            now = getattr(st, "last_response_end", None) if st is not None else None
            if now is None:
                now = time.time()
        self._last_access[program_id] = float(now)

    def last_access(self, program_id: str) -> float:
        """Last-access time; ``-inf`` for an unknown id so it sorts as oldest."""
        return self._last_access.get(program_id, float("-inf"))
