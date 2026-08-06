# H200 Phase 1 진행 상황 (자동 append)

- 시작: 2026-08-06 03:40:10 UTC · C=80 · r=2 · 셀당 3600s · **모델 Qwen/Qwen3-8B** · TP1
- 사전 등록: `logs/2026-08-05_H200_GATE_PREREG_yunuikang.md` §10 · 계획 rev3 §5.1 Phase 1
- goodput은 **점추정이 아니라 TTFT 순서통계 구간**이다 (드라이버가 per-turn을 저장하지 않음, PREREG §10.6)
- Waiting 축출은 시스템마다 **다른 사건**이다 — MORI: `CPU->Waiting`, TA+O: `Paused program`. 절대값 비교 불가

| 셀 | fit | 상태 | 시작 | 종료 | thr(드라이버) | thr(엔진) | TTFT p50 | TTFT p95 | goodput@5s | MORI÷TA+O | Waiting축출 | ping-pong | steady턴 | 비고 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
