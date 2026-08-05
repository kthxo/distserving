"""scheduler-in-a-box: MORI 정책 결정 로직을 GPU/엔진 없이 격리 호출하는 최소 하네스.

설계 원칙 (STEP 1 symbol audit 근거):
  * mock하는 엔진 경계는 **정확히 하나** — ``BackendState.metrics_client``.
    (``healthy`` / ``cache_config`` / ``fetch_metrics()``가 전부 이 객체로 위임된다:
     ThunderAgent/backend/state.py:73-80, :244-246)
  * 그 외에는 **전부 실제 코드**: 실제 ``MoriRouter``, 실제 ``BackendState``,
    실제 ``CpuTier``, 실제 ``IdlenessWindow``, 실제 ``_scheduled_check`` 틱.
    정책은 단 한 줄도 재구현하지 않는다.
  * 네트워크 없음 (``httpx.AsyncClient``는 생성만 되고 호출되지 않음), GPU 없음.

용량 환산 (STEP 1 §7):
    GPU 회계 = Σtotal_tokens + n×BUFFER_PER_PROGRAM   (acting_token_weight=1.0, shared_tokens=0)
    CPU 회계 = 동일 규약 (mori_tier.py:34-36)
    => "T 토큰짜리 프로그램 n칸" == capacity_tokens = n × (T + BUFFER_PER_PROGRAM)
       ``slots(n, T)`` 헬퍼가 이 환산을 한다.

ι 주입 (STEP 1 §8):
    ``_iota``가 ``idle_window.value(...)``를 부르므로 ι를 직접 세팅할 수 없다.
    윈도우에 **동일 표본 k쌍**을 push한다: push_acting(x) / push_reasoning(1-x).
    k개 동일 표본에서는 ratio-of-sums(논문 식1)와 average-of-ratios가 **둘 다 정확히 x**이므로,
    이 주입은 구현의 계산식을 테스트에 역으로 베끼는 것이 아니다.
    ``acting_since=None``으로 둬서 "진행 중 tool call" 항이 주입값을 오염시키지 않게 한다.
"""
import asyncio
import time
from typing import Dict, List, Optional, Tuple

from ThunderAgent.backend.state import BUFFER_PER_PROGRAM
from ThunderAgent.program.state import Program, ProgramState, ProgramStatus
from ThunderAgent.scheduler.mori_config import MoriConfig
from ThunderAgent.scheduler.mori_idleness import IdlenessWindow
from ThunderAgent.scheduler.mori_router import MoriRouter
from ThunderAgent.scheduler.router import MultiBackendRouter, PausedInfo

DEFAULT_URL = "http://fake-backend:0"


# ---------------------------------------------------------------------------
# 유일한 mock: 엔진 metrics 경계
# ---------------------------------------------------------------------------

class FakeCacheConfig:
    def __init__(self, total_tokens_capacity: int) -> None:
        self.total_tokens_capacity = int(total_tokens_capacity)


class FakeMetricsClient:
    """BackendState가 metrics_client에게 위임하는 표면 전부를 흉내낸다.

    실제 클라이언트가 하는 일 중 여기서 필요한 것은 (a) healthy, (b) cache_config,
    (c) fetch_metrics() 뿐이다. 네트워크 호출은 없다.
    """

    def __init__(self, capacity_tokens: int, healthy: bool = True) -> None:
        self.healthy = healthy
        self.cache_config = FakeCacheConfig(capacity_tokens)
        self.latest_metrics = None
        self.metrics_history: List = []
        self.fetch_calls = 0

    async def fetch_metrics(self) -> bool:
        self.fetch_calls += 1
        return True

    async def fetch_cache_config(self) -> bool:
        return True

    def calculate_shared_tokens(self, reasoning_program_tokens: int) -> int:
        # prefix sharing 없음 — 용량 회계를 Σtokens + n×BUFFER로 고정 (불변식 I2).
        return 0


# ---------------------------------------------------------------------------
# 용량 환산
# ---------------------------------------------------------------------------

def slots(n: int, tokens_per_program: int) -> int:
    """프로그램(T 토큰) n개가 '정확히' 들어가는 tier 용량."""
    return n * (tokens_per_program + BUFFER_PER_PROGRAM)


# ---------------------------------------------------------------------------
# 프로그램 픽스처
# ---------------------------------------------------------------------------

def set_iota(prog: Program, iota: float, k: int = 5) -> Program:
    """윈도우를 비우고 ι == iota가 되도록 동일 표본 k쌍을 push."""
    w = IdlenessWindow(k)
    for _ in range(k):
        w.push_acting(iota)
        w.push_reasoning(1.0 - iota)
    prog.idle_window = w
    return prog


def make_program(
    pid: str,
    tokens: int = 400,
    iota: float = 0.5,
    status: ProgramStatus = ProgramStatus.ACTING,
    k: int = 5,
    step_count: int = 3,
    last_response_end: Optional[float] = None,
) -> Program:
    p = Program(
        program_id=pid,
        total_tokens=tokens,
        context_len=tokens * 5,
        status=status,
        state=ProgramState.ACTIVE,
        step_count=step_count,
        acting_since=None,          # 진행 중 tool call 항을 0으로 (주입 ι를 그대로 유지)
    )
    p.last_response_end = last_response_end
    p.moved_tick = None
    set_iota(p, iota, k)
    return p


# ---------------------------------------------------------------------------
# 하네스
# ---------------------------------------------------------------------------

class MoriHarness:
    """단일 이벤트 루프 위에서 실제 MoriRouter 틱을 반복 실행한다.

    asyncio.Lock / Event는 **최초 사용 시점의 루프에 바인딩**되므로 (CPython
    _LoopBoundMixin), 틱마다 asyncio.run()을 새로 부르면 두 번째 틱에서
    "bound to a different event loop"로 죽는다. => 루프를 하나만 만들어 재사용.
    """

    def __init__(
        self,
        gpu_capacity: int,
        cpu_capacity: int,
        urls: Optional[List[str]] = None,
        mori: Optional[MoriConfig] = None,
        router_cls=MoriRouter,
    ) -> None:
        """router_cls=MoriRouter (기본) 또는 MultiBackendRouter (baseline 'tr' 경로 대조용).

        baseline일 때는 CPU tier가 존재하지 않으므로 ``cpu_capacity``는 무시된다.
        """
        self.urls = urls or [DEFAULT_URL]
        self.is_mori = router_cls is MoriRouter
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        if self.is_mori:
            self.router = MoriRouter(self.urls, backend_type="sglang", mori=mori or MoriConfig())
        else:
            # 'tr' 모드 = scheduling_enabled=True 인 base MultiBackendRouter.
            self.router = MultiBackendRouter(self.urls, backend_type="sglang",
                                             scheduling_enabled=True)

        # 엔진 경계 교체 + CPU tier 용량 (start()를 부르지 않으므로 직접 세팅)
        gpu_caps = gpu_capacity if isinstance(gpu_capacity, dict) else {
            u: gpu_capacity for u in self.urls
        }
        cpu_caps = cpu_capacity if isinstance(cpu_capacity, dict) else {
            u: cpu_capacity for u in self.urls
        }
        for u in self.urls:
            self.router.backends[u].metrics_client = FakeMetricsClient(gpu_caps[u])
            if self.is_mori:
                self.router.cpu_tiers[u].capacity_tokens = int(cpu_caps[u])

    # -- 배치 -------------------------------------------------------------
    def place_gpu(self, prog: Program, url: Optional[str] = None) -> Program:
        url = url or self.urls[0]
        prog.backend_url = url
        prog.origin_backend = None
        prog.state = ProgramState.ACTIVE
        prog.tier = "gpu"
        self.router.programs[prog.program_id] = prog
        self.router.backends[url].register_program(prog.program_id, prog)
        return prog

    def place_cpu(self, prog: Program, url: Optional[str] = None) -> Program:
        url = url or self.urls[0]
        prog.backend_url = None
        prog.origin_backend = url
        prog.state = ProgramState.PAUSED
        prog.tier = "cpu"
        prog.waiting_event = asyncio.Event()
        self.router.programs[prog.program_id] = prog
        self.router.cpu_tiers[url].admit(prog.program_id, prog)
        return prog

    def place_waiting(self, prog: Program, url: Optional[str] = None) -> Program:
        url = url or self.urls[0]
        prog.backend_url = None
        prog.origin_backend = url
        prog.state = ProgramState.PAUSED
        prog.tier = "waiting"
        prog.waiting_event = asyncio.Event()
        self.router.programs[prog.program_id] = prog
        self.router.global_waiting_queue[prog.program_id] = PausedInfo(
            program_id=prog.program_id,
            total_tokens=prog.total_tokens,
            paused_at=time.time(),
            origin_backend=url,
            step_count=prog.step_count,
        )
        return prog

    # -- 실행 -------------------------------------------------------------
    def tick(self) -> None:
        """실제 MoriRouter._scheduled_check() 한 틱."""
        self.loop.run_until_complete(self.router._scheduled_check())

    def call(self, coro_or_none):
        return self.loop.run_until_complete(coro_or_none)

    # -- 관측 -------------------------------------------------------------
    def tiers(self) -> Tuple[set, set, set]:
        """(gpu, cpu, waiting) 집합 + tier 분할 무결성 확인."""
        gpu, cpu, wait = set(), set(), set()
        for pid, p in self.router.programs.items():
            {"gpu": gpu, "cpu": cpu, "waiting": wait}[p.tier].add(pid)
        assert gpu | cpu | wait == set(self.router.programs), "tier 분할이 전체를 덮지 않음"
        assert len(gpu) + len(cpu) + len(wait) == len(self.router.programs), "tier 중복"
        return gpu, cpu, wait

    def iota(self, prog: Program, now: Optional[float] = None) -> float:
        """라우터가 실제로 쓰는 ι (MoriRouter._iota)."""
        return self.router._iota(prog, now if now is not None else time.time())

    def gpu_remaining(self, url: Optional[str] = None) -> int:
        return self.router.backends[url or self.urls[0]].remaining_capacity()

    def cpu_remaining(self, url: Optional[str] = None) -> int:
        return self.router.cpu_tiers[url or self.urls[0]].remaining()

    def snapshot(self) -> Dict[str, str]:
        return {pid: p.tier for pid, p in self.router.programs.items()}

    def describe(self) -> str:
        """보고서에 그대로 실을 수 있는 관측 문자열."""
        now = time.time()
        rows = []
        for pid, p in sorted(self.router.programs.items()):
            rows.append(f"{pid}(tier={p.tier}, i={self.iota(p, now):.3f}, tok={p.total_tokens}"
                        f", marked={p.marked_for_pause})")
        return ", ".join(rows)

    def close(self) -> None:
        try:
            self.loop.run_until_complete(self.router.client.aclose())
        except Exception:
            pass
        self.loop.close()


def make_harness(gpu_slots: int, cpu_slots: int, tokens: int = 400, **cfg) -> MoriHarness:
    """'GPU n칸 / CPU m칸' 초소형 하네스 (프로그램당 ``tokens`` 토큰 기준)."""
    return MoriHarness(
        gpu_capacity=slots(gpu_slots, tokens),
        cpu_capacity=slots(cpu_slots, tokens),
        mori=MoriConfig(**cfg),
    )


def make_baseline_harness(gpu_capacity: int) -> MoriHarness:
    """baseline 'tr' 경로(MultiBackendRouter) 하네스 — MORI 오버라이드 없음."""
    return MoriHarness(gpu_capacity=gpu_capacity, cpu_capacity=0,
                       router_cls=MultiBackendRouter)
