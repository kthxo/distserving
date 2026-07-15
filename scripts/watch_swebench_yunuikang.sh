#!/usr/bin/env bash
# SWE-bench 녹화 실시간 상태 한 눈에. 사용:
#   bash scripts/watch_swebench_yunuikang.sh            # 1회 스냅샷
#   watch -n 10 bash scripts/watch_swebench_yunuikang.sh # 10초마다 갱신
REC=/home/yunuikang/yunuikang_work/scratch/rec_swebench
OUT=/home/yunuikang/yunuikang_work/scratch/swebench_out
CSV=$REC/step_profiles.csv

done=$(python3 -c "import json,os;p='$OUT/preds.json';print(len(json.load(open(p))) if os.path.exists(p) else 0)" 2>/dev/null)
progs=$(tail -n +2 "$CSV" 2>/dev/null | cut -d, -f1 | sort -un | wc -l)
steps=$(tail -n +2 "$CSV" 2>/dev/null | wc -l)
cons=$(sg docker -c 'docker ps --filter name=minisweagent- -q | wc -l' 2>/dev/null)
gpu=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader | head -1)
proc=$(ps -eo args 2>/dev/null | grep -q '[m]ini-extra swebench' && echo RUNNING || echo STOPPED)
px=$(curl -sf http://localhost:9000/health >/dev/null 2>&1 && echo OK || echo DOWN)
vl=$(curl -sf http://localhost:8000/health >/dev/null 2>&1 && echo OK || echo DOWN)

echo "===== SWE-bench 녹화 $(date '+%F %T') ====="
echo " 완료      : ${done:-0}/64 instances"
echo " 녹화됨    : ${progs:-0} programs, ${steps:-0} steps"
echo " 컨테이너  : ${cons:-?} running (목표 12)"
echo " GPU0      : ${gpu}"
echo " 프록시/vLLM: proxy=${px} vLLM=${vl}"
echo " 녹화상태  : ${proc}"
echo "--- 최근 로그 3줄 ---"
tail -3 "$REC/run_full.log" 2>/dev/null | sed 's/^/  /'
