"""Scheduler-policy + isolation invariant tests for MoriRouter.

Run: `python -m pytest tests/test_mori_invariants_yunuikang.py`
 or: `python tests/test_mori_invariants_yunuikang.py`
CPU-only: a fake backend (in-memory capacity) drives _scheduled_check; no engine.
"""
import asyncio

from ThunderAgent.scheduler.mori_router import MoriRouter
from ThunderAgent.scheduler.mori_config import MoriConfig
from ThunderAgent.scheduler.mori_idleness import IdlenessWindow
from ThunderAgent.program.state import Program, ProgramStatus, ProgramState


class _FakeCache:
    def __init__(self, cap): self.total_tokens_capacity = cap


class _FakeMetrics:
    def __init__(self, cap): self.healthy = True; self.cache_config = _FakeCache(cap)
    async def fetch_metrics(self): return True


def _mk(pid, tokens, iota):
    p = Program(program_id=pid, total_tokens=tokens, status=ProgramStatus.ACTING,
                state=ProgramState.ACTIVE, backend_url="u", acting_since=None)
    w = IdlenessWindow(5)
    w.push_acting(iota)
    w.push_reasoning(1.0 - iota)
    p.idle_window = w
    return p


def _tiers(r):
    gpu = {pid for pid, p in r.programs.items() if p.tier == "gpu"}
    cpu = {pid for pid, p in r.programs.items() if p.tier == "cpu"}
    wait = {pid for pid, p in r.programs.items() if p.tier == "waiting"}
    # Invariant I1: tiers are disjoint and cover every program exactly once.
    assert gpu | cpu | wait == set(r.programs)
    assert len(gpu) + len(cpu) + len(wait) == len(r.programs)
    return gpu, cpu, wait


def _router(gpu_cap, cpu_cap, ratio=2.0):
    r = MoriRouter(["u"], backend_type="sglang",
                   mori=MoriConfig(cpu_capacity_ratio=ratio, reload_bw_bytes_per_s=1e18, min_dwell_ticks=0))
    r.backends["u"].metrics_client = _FakeMetrics(gpu_cap)
    r.cpu_tiers["u"].capacity_tokens = cpu_cap
    return r


def test_demote_iota_desc_then_promote_iota_asc():
    async def run():
        r = _router(gpu_cap=1000, cpu_cap=2000)
        b = r.backends["u"]
        for pid, io in (("A", 0.9), ("B", 0.5), ("C", 0.1)):
            p = _mk(pid, 500, io); r.programs[pid] = p; b.register_program(pid, p)
        # over capacity -> demote highest ι first
        await r._scheduled_check()
        gpu, cpu, wait = _tiers(r)
        assert cpu == {"A", "B"} and gpu == {"C"}
        assert b.remaining_capacity() >= 0
        assert r.programs["A"].waiting_event is not None      # CPU tier blocks requests
        # free capacity -> promote lowest ι first, all back
        b.metrics_client = _FakeMetrics(5000)
        await r._scheduled_check()
        gpu, cpu, wait = _tiers(r)
        assert gpu == {"A", "B", "C"} and cpu == set()
        assert r.programs["A"].reload_ready_at is not None    # reload cost stamped
        assert r.programs["A"].waiting_event is None          # promotion unblocked
    asyncio.run(run())


def test_cpu_full_falls_back_to_waiting():
    async def run():
        r = _router(gpu_cap=1000, cpu_cap=0, ratio=0.0)
        b = r.backends["u"]
        for pid, io in (("A", 0.9), ("B", 0.5), ("C", 0.1)):
            p = _mk(pid, 500, io); r.programs[pid] = p; b.register_program(pid, p)
        await r._scheduled_check()
        gpu, cpu, wait = _tiers(r)
        assert wait == {"A", "B"} and set(r.global_waiting_queue) == {"A", "B"}
        assert r.cpu_tiers["u"].count() == 0
    asyncio.run(run())


def test_release_cpu_tier_program():
    async def run():
        r = _router(gpu_cap=1000, cpu_cap=2000)
        b = r.backends["u"]
        for pid, io in (("A", 0.9), ("B", 0.5), ("C", 0.1)):
            p = _mk(pid, 500, io); r.programs[pid] = p; b.register_program(pid, p)
        await r._scheduled_check()
        assert r.cpu_tiers["u"].count() == 2
        assert await r.release_program("A")
        assert "A" not in r.programs and r.cpu_tiers["u"].count() == 1
    asyncio.run(run())


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("all invariant/policy tests passed")
