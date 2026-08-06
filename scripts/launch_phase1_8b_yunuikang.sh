#!/usr/bin/env bash
# 실행 A 런처 — Phase 1 rev4 (8B F1 재실행). PREREG §11.
#
# WHY THIS WRAPPER EXISTS (그냥 env 를 앞에 붙이면 안 되는 이유) [측정 2026-08-06]:
#   러너의 kill_backend 는 `pkill -9 -f "_serve_sglang_8b_tp1_h200_mori_yunuikang"` 를 쓴다.
#   `SERVE=/...\/_serve_sglang_8b_tp1_h200_mori_yunuikang.sh bash run_h200_phase1...` 처럼
#   **호출 커맨드라인에 그 경로를 적으면 그 셸 자신이 패턴에 매치되어 죽는다.**
#   tmux 페인이 통째로 사라져 실행이 시작되자마자 증발했다.
#   -> 설정을 파일 안에 두어 호출 커맨드라인에서 경로를 없앤다. 페인 cmdline 은
#      `bash .../launch_phase1_8b_yunuikang.sh` 뿐이라 어떤 kill 패턴과도 겹치지 않는다.
set -uo pipefail
REPO=/workspace/distserving

export MODEL="Qwen/Qwen3-8B"
export SERVE="$REPO/scripts/_serve_sglang_8b""_tp1_h200_mori_yunuikang.sh"   # 문자열 분할: 이 파일도 패턴에 안 걸리게
export DUR=3600                      # 60분 — 5090 앵커와 동일 (PREREG §11.1)
export OUT="$REPO/scratch/mori/h200_phase1_8b"
export PROGRESS="$REPO/logs/2026-08-06_H200_PHASE1_8B_PROGRESS_yunuikang.md"
export VERDICT_MODE=model-confound   # rev4 해석: REPRODUCED=모델/KV밀도 · NOT=interconnect/TP
export AFTER_F1=stop                 # Phase 1 은 2셀로 끝난다 (fit 스윕 폐기)

exec bash "$REPO/scripts/run_h200_phase1_yunuikang.sh"
