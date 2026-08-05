"""MoriRouter — Relative-Idleness 3-tier offloading on top of ThunderAgent.

Subclass of :class:`MultiBackendRouter`. It adds:
  * relative-idleness (ι) measurement per program (mori_idleness),
  * a CPU tier between GPU and Waiting (mori_tier), and
  * ι-ranked demotion / promotion replacing the context-length ranking.

**Isolation (invariant I4)**: this class is only instantiated when
``--router mori``. It overrides methods only; ``router.py`` and
``backend/state.py`` keep a 0-line diff. The ``tr``/``default`` baselines run
the unmodified base class.

**Concurrency**: the whole scheduler tick runs under the inherited
``pause_resume_lock`` (reused as the "mori_lock" of the plan). Every tier move
inside the tick is synchronous, so no lock is re-acquired and there is no
re-entrancy. The data-plane only *reads* tier state lock-free and blocks on
``waiting_event``; all tier moves happen in the periodic tick — matching the
paper's periodic control loop.

Phase 1 (this file): CPU tier is bookkeeping; the CPU->GPU reload cost is a
model (``MoriConfig.reload_seconds``) paid as an ``asyncio.sleep`` on the
resuming request. Phase 2 wires the tier to SGLang HiCache (no engine code
here).
"""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from ..backend.state import BUFFER_PER_PROGRAM
from ..program import Program, ProgramStatus, ProgramState
from .router import MultiBackendRouter, PausedInfo
from .mori_config import MoriConfig
from .mori_idleness import IdlenessWindow
from .mori_tier import CpuTier

logger = logging.getLogger(__name__)


class MoriRouter(MultiBackendRouter):
    """3-tier (GPU / CPU / Waiting) relative-idleness scheduler."""

    def __init__(self, *args, mori: Optional[MoriConfig] = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.mori = mori or MoriConfig()
        # One CPU tier per backend; capacities sized in start() once the GPU KV
        # pool (cache_config.total_tokens_capacity) is known.
        self.cpu_tiers: Dict[str, CpuTier] = {
            url: CpuTier(url, 0) for url in self.backends
        }
        self._tick: int = 0

    async def start(self) -> None:
        await super().start()  # fetches cache_config, then starts scheduler loop
        for url, backend in self.backends.items():
            cap_gpu = backend.cache_config.total_tokens_capacity if backend.cache_config else 0
            self.cpu_tiers[url].capacity_tokens = int(self.mori.cpu_capacity_ratio * cap_gpu)
            logger.info(
                "MORI CPU tier %s: capacity=%d tok (ratio=%.2f x GPU %d)",
                url, self.cpu_tiers[url].capacity_tokens, self.mori.cpu_capacity_ratio, cap_gpu,
            )

    # -------------------------------------------------------------------------
    # Idleness instrumentation (always-on; paper §4.2 measurement points)
    # -------------------------------------------------------------------------

    async def update_program_before_request(self, program_id: str, state: Program, payload: Dict[str, Any]) -> bool:
        now = time.time()
        if state.idle_window is None:
            state.idle_window = IdlenessWindow(self.mori.k)
        # Pure acting (tool) time since the previous response ended.
        if state.last_response_end is not None:
            state.idle_window.push_acting(now - state.last_response_end)

        rv = await super().update_program_before_request(program_id, state, payload)

        # Typed-eviction stamp (real HiCache): encode the program's relative
        # idleness as the OpenAI `priority` field. SGLang propagates it onto the
        # radix nodes this request creates (Req.priority -> node.priority), and
        # the `priority` eviction policy sorts by (node.priority, last_access) —
        # so busy (low ι, high rank) KV is kept on GPU and idle (high ι, low rank)
        # KV is evicted first. Baselines (tr/default) never call this, so they
        # keep SGLang's native LRU. No engine patch needed for the GPU tier.
        payload["priority"] = self._type_rank(state, time.time())

        state.reason_started_at = time.time()
        return rv

    def _type_rank(self, state: Program, now: float) -> int:
        """MORI type -> priority rank (higher = keep on GPU longer).
        busy (low ι) = 2, mixed = 1, idle (high ι) = 0. GPU eviction removes the
        lowest rank first (inactive/idle -> ... -> busy)."""
        iota = self._iota(state, now)
        if iota < 0.33:
            return 2
        if iota < 0.66:
            return 1
        return 0

    def update_program_after_request(
        self, program_id: str, state: Program, total_tokens: int, prompt_tokens: int = 0
    ) -> None:
        now = time.time()
        if state.idle_window is not None and state.reason_started_at is not None:
            state.idle_window.push_reasoning(now - state.reason_started_at)
        state.last_response_end = now
        # super() sets ACTING/tokens and, if marked_for_pause, calls
        # self._clear_mark_and_pause (overridden below → routes to CPU tier).
        super().update_program_after_request(program_id, state, total_tokens, prompt_tokens)

    def _iota(self, state: Program, now: float) -> float:
        if state.idle_window is None:
            return self.mori.default_iota
        return state.idle_window.value(
            now=now, acting_since=state.acting_since, default=self.mori.default_iota
        )

    def _dwell_ok(self, state: Program) -> bool:
        mt = state.moved_tick
        return mt is None or (self._tick - mt) >= self.mori.min_dwell_ticks

    # -------------------------------------------------------------------------
    # Tier transitions (all called under pause_resume_lock inside the tick,
    # except _clear_mark_and_pause which runs on the data plane after a lazily
    # marked REASONING program returns to ACTING)
    # -------------------------------------------------------------------------

    def _demote_to_cpu(self, program_id: str, state: Program, backend) -> None:
        """GPU -> CPU tier: unregister from backend, hold KV bookkeeping in CpuTier."""
        tier = self.cpu_tiers[backend.url]
        backend.unregister_program(program_id)
        tier.admit(program_id, state)
        state.origin_backend = backend.url  # reload target on promote
        state.backend_url = None
        state.state = ProgramState.PAUSED
        state.tier = "cpu"
        state.moved_tick = self._tick
        if state.waiting_event is None:
            state.waiting_event = asyncio.Event()
        else:
            state.waiting_event.clear()
        logger.info("MORI demote GPU->CPU %s (tokens=%d)", program_id, state.total_tokens)

    def _demote(self, program_id: str, state: Program, backend) -> None:
        """Demote off GPU: prefer CPU tier, fall back to Waiting when CPU is full."""
        tier = self.cpu_tiers.get(backend.url)
        if tier is not None and tier.can_admit(state):
            self._demote_to_cpu(program_id, state, backend)
        else:
            self._pause_program(program_id, state)  # base: GPU -> Waiting (KV discarded)
            state.tier = "waiting"
            state.moved_tick = self._tick

    def _clear_mark_and_pause(self, program_id: str, state: Program) -> None:
        """Override: a lazily-marked REASONING program pauses to the CPU tier
        (not directly to Waiting as the base does)."""
        backend = self.backends.get(state.backend_url)
        if not backend:
            return
        state.marked_for_pause = False
        backend.future_paused_tokens -= state.total_tokens
        if backend.future_paused_tokens < 0:
            backend.future_paused_tokens = 0
        self._demote(program_id, state, backend)

    def _promote_from_cpu(self, program_id: str, state: Program, backend, now: float) -> None:
        """CPU -> GPU: register back and stamp the reload deadline (paid on the
        resuming request in update_program_before_request)."""
        self.cpu_tiers[state.origin_backend or backend.url].remove(program_id)
        backend.register_program(program_id, state)
        state.backend_url = backend.url
        state.origin_backend = None
        state.state = ProgramState.ACTIVE
        state.tier = "gpu"
        state.moved_tick = self._tick
        # Real HiCache pays the CPU->GPU reload (host->device KV copy) itself when
        # the next request re-prefills from the host pool — no modeled delay here.
        if state.waiting_event is not None:
            state.waiting_event.set()
            state.waiting_event = None
        logger.info("MORI promote CPU->GPU %s -> %s (tokens=%d)", program_id, backend.url, state.total_tokens)

    def _evict_cpu_to_waiting(self, tier: CpuTier, program_id: str, state: Program, now: float) -> None:
        """CPU -> Waiting: KV discarded (full recompute on later resume)."""
        tier.remove(program_id)
        self.global_waiting_queue[program_id] = PausedInfo(
            program_id=program_id,
            total_tokens=state.total_tokens,
            paused_at=now,
            origin_backend=state.origin_backend,
            step_count=state.step_count,
        )
        state.tier = "waiting"
        state.moved_tick = self._tick
        logger.info("MORI evict CPU->Waiting %s (tokens=%d)", program_id, state.total_tokens)

    # -------------------------------------------------------------------------
    # Periodic scheduler (replaces base _scheduled_check policy)
    # -------------------------------------------------------------------------

    async def _scheduled_check(self) -> None:
        for backend in self.backends.values():
            await backend.fetch_metrics()

        async with self.pause_resume_lock:
            self._tick += 1
            now = time.time()

            # 1) GPU over capacity -> demote (ACTING first, then lazy REASONING),
            #    each highest-ι first, destination CPU (fallback Waiting).
            for backend in self.backends.values():
                if backend.cache_config and backend.remaining_capacity() < 0:
                    self._mori_pause_until_safe(backend, now)

            # 2) CPU tier over capacity -> evict highest-ι to Waiting.
            for tier in self.cpu_tiers.values():
                self._mori_evict_cpu(tier, now)

            # 3) GPU spare capacity -> promote (CPU-pending, Waiting-returning,
            #    Waiting-new, CPU-idle), each lowest-ι first.
            self._mori_promote(now)

    def _acting_on_backend(self, backend_url: str) -> List[Tuple[str, Program]]:
        return [
            (pid, s) for pid, s in self.programs.items()
            if s.backend_url == backend_url and s.status == ProgramStatus.ACTING
        ]

    def _reasoning_unmarked_on_backend(self, backend_url: str) -> List[Tuple[str, Program]]:
        return [
            (pid, s) for pid, s in self.programs.items()
            if s.backend_url == backend_url
            and s.status == ProgramStatus.REASONING
            and not s.marked_for_pause
        ]

    def _mori_pause_until_safe(self, backend, now: float) -> None:
        guard = 0
        while backend.remaining_capacity() < 0 and guard < 100000:
            guard += 1
            # ACTING first, highest ι first.
            acting = self._acting_on_backend(backend.url)
            acting.sort(key=lambda x: self._iota(x[1], now), reverse=True)
            moved = False
            for pid, state in acting:
                if self._dwell_ok(state):
                    self._demote(pid, state, backend)
                    moved = True
                    break
            if moved:
                continue
            # Then lazily mark REASONING, highest ι first (paused when it returns
            # to ACTING → routed to CPU by _clear_mark_and_pause).
            reasoning = self._reasoning_unmarked_on_backend(backend.url)
            if reasoning:
                reasoning.sort(key=lambda x: self._iota(x[1], now), reverse=True)
                pid, state = reasoning[0]
                self._mark_program_for_pause(pid, state)
                continue
            break

    def _mori_evict_cpu(self, tier: CpuTier, now: float) -> None:
        guard = 0
        while tier.remaining() < 0 and guard < 100000:
            guard += 1
            items = tier.items()
            if not items:
                break
            # Typed eviction (paper §4.3.2): highest-ι first (least likely to resume
            # soon on GPU), and **within the same type, LRU breaks ties** — the
            # least-recently-used program is evicted first.
            # Key is (-ι, last_access) with no `reverse`, so both terms sort ascending
            # in the intended direction: -ι ascending == ι descending, and last_access
            # ascending == oldest first. (Using reverse=True with a tuple would flip
            # the tie-break to most-recently-used.)
            items.sort(key=lambda x: (-self._iota(x[1], now), tier.last_access(x[0])))
            pid, state = items[0]
            self._evict_cpu_to_waiting(tier, pid, state, now)

    def _mori_promote(self, now: float) -> None:
        cpu_pending: List[Tuple[str, Program]] = []   # CPU tier w/ pending request
        cpu_idle: List[Tuple[str, Program]] = []       # CPU tier, no pending request
        for tier in self.cpu_tiers.values():
            for pid, state in tier.items():
                (cpu_pending if state.status == ProgramStatus.REASONING else cpu_idle).append((pid, state))

        wait_reasoning: List[Tuple[str, Program]] = []
        wait_new: List[Tuple[str, Program]] = []
        wait_acting: List[Tuple[str, Program]] = []
        for pid in list(self.global_waiting_queue.keys()):
            state = self.programs.get(pid)
            if state is None:
                continue
            if state.step_count == 1:
                wait_new.append((pid, state))
            elif state.status == ProgramStatus.REASONING:
                wait_reasoning.append((pid, state))
            else:
                wait_acting.append((pid, state))

        # Lowest ι first within each priority group (keep least-idle on GPU).
        for group in (cpu_pending, wait_reasoning, wait_new, cpu_idle, wait_acting):
            group.sort(key=lambda x: self._iota(x[1], now))

        order = cpu_pending + wait_reasoning + wait_new + cpu_idle + wait_acting
        for pid, state in order:
            if not self._dwell_ok(state):
                continue
            required = state.total_tokens + BUFFER_PER_PROGRAM
            # Best-fit: backend with the most remaining capacity that fits.
            best = None
            best_rem = -1
            for backend in self.backends.values():
                if not (backend.cache_config and backend.healthy):
                    continue
                rem = backend.remaining_capacity()
                if rem >= required and rem > best_rem:
                    best = backend
                    best_rem = rem
            if best is None:
                continue
            if state.tier == "cpu":
                self._promote_from_cpu(pid, state, best, now)
            else:
                self.global_waiting_queue.pop(pid, None)
                self._resume_program(state, target_backend=best)
                state.tier = "gpu"
                state.moved_tick = self._tick

    # -------------------------------------------------------------------------
    # Lifecycle / observability
    # -------------------------------------------------------------------------

    async def release_program(self, program_id: str) -> bool:
        state = self.programs.get(program_id)
        if state is not None and state.tier == "cpu":
            for tier in self.cpu_tiers.values():
                tier.remove(program_id)
            if state.waiting_event:
                state.waiting_event.set()
            state.state = ProgramState.TERMINATED
            del self.programs[program_id]
            logger.info("Released CPU-tier program: %s", program_id)
            return True
        return await super().release_program(program_id)

    def get_program_stats(self) -> Dict[str, Any]:
        stats = super().get_program_stats()
        cpu_total = sum(t.count() for t in self.cpu_tiers.values())
        stats["cpu_tier"] = cpu_total
        stats["cpu_tier_per_backend"] = {
            url: {"count": t.count(), "used_tokens": t.used_tokens(),
                  "capacity_tokens": t.capacity_tokens}
            for url, t in self.cpu_tiers.items()
        }
        return stats
