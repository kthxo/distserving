#!/usr/bin/env bash
# Phase 2 런처 — 12셀 무인 실행. PREREG §E.
#
# 설정을 파일 안에 두는 이유 [측정 2026-08-06]: 호출 커맨드라인에 serve 스크립트
# 경로를 적으면 러너의 kill_backend `pkill -f` 가 **자기 셸을 매치해 죽인다**
# (실행 A 에서 tmux 페인이 시작 직후 증발했다). 페인 cmdline 은 이 런처 경로뿐이라
# 어떤 kill 패턴과도 겹치지 않는다.
set -uo pipefail
REPO=/workspace/distserving

export DUR=3600                  # 60분 (PREREG §E.4 · 5090 20분 셀의 -72.9% MORI 불리 편향 회피)
export CLIST="20 80 40"          # P1 앵커 -> P2/P4 -> P3 보간 (§E.4)
export SYSLIST="SMG TA TAO MORI" # §E.5 — 오프로딩 효과와 MORI 정책 효과를 분리
export OUT="$REPO/scratch/mori/h200_phase2"
export PROGRESS="$OUT/progress.md"

exec bash "$REPO/scripts/run_h200_phase2_yunuikang.sh"
