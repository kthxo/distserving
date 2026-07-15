#!/usr/bin/env python3
"""SWE-bench Lite에서 레포별 계층적(stratified) 비례 샘플로 N개 태스크를 뽑는다.

배경: Lite는 레포 불균형이 심함(django 38%, sympy 25.7%). 데이터셋이 instance_id
알파벳 정렬이라 head-N(`--slice 0:N`)은 astropy+django만 뽑혀 대표성이 없다.
→ 원본 300개의 레포 분포를 유지하도록 레포별 비례 배분(largest-remainder) 후
레포 내부 시드 고정 랜덤 샘플. 각 레포 최소 1개 보장(--min-per-repo).

산출물:
  <out>.txt        : 뽑힌 instance_id 한 줄씩(주석에 레포별 배분·시드 기록)
  <out>.filter.txt : mini-extra swebench --filter 에 넣을 정규식 ^(id1|id2|...)$
  <out>.meta.json  : 배분표 + 원본% vs 표본% 대조 + 시드

GPU/Docker 불필요(데이터셋 메타만 로드). 결정적(시드 고정).
"""
import argparse
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path


def proportional_alloc(counts: dict, n: int, min_per_repo: int) -> dict:
    """레포별 비례 배분(largest-remainder) + 각 레포 최소 min_per_repo 보장.

    counts: {repo: 원본 태스크 수}, n: 목표 총합.
    반환: {repo: 뽑을 수}, 합계 == n (가능한 경우).
    """
    repos = list(counts)
    total = sum(counts.values())
    if n > total:
        raise ValueError(f"n({n}) > total({total})")

    # 1) 각 레포 최소 보장(레포 수 * min <= n 이어야 함)
    base = {r: min(min_per_repo, counts[r]) for r in repos}
    used = sum(base.values())
    if used > n:
        raise ValueError(f"min_per_repo*repos({used}) > n({n}); min_per_repo를 낮춰라")

    # 2) 남은 자리를 '남은 원본 수' 비례로 largest-remainder 배분
    remaining = n - used
    rem_counts = {r: counts[r] - base[r] for r in repos}  # 이미 뽑은 만큼 뺀 잔여 풀
    rem_total = sum(rem_counts.values())
    alloc = dict(base)
    if remaining > 0 and rem_total > 0:
        quota = {r: remaining * rem_counts[r] / rem_total for r in repos}
        floor = {r: int(math.floor(quota[r])) for r in repos}
        # 잔여 원본을 넘지 않도록 상한
        floor = {r: min(floor[r], rem_counts[r]) for r in repos}
        for r in repos:
            alloc[r] += floor[r]
        left = n - sum(alloc.values())
        # 소수부 큰 순서로 1개씩(잔여 풀 남은 레포만)
        frac_order = sorted(repos, key=lambda r: (quota[r] - math.floor(quota[r])), reverse=True)
        i = 0
        while left > 0 and i < 10 * len(repos):
            r = frac_order[i % len(frac_order)]
            if alloc[r] < counts[r]:
                alloc[r] += 1
                left -= 1
            i += 1
    return alloc


def main():
    ap = argparse.ArgumentParser(description="Stratified-by-repo sampler for SWE-bench Lite")
    ap.add_argument("--dataset", default="princeton-nlp/SWE-bench_Lite")
    ap.add_argument("--split", default="test")
    ap.add_argument("--n", type=int, default=64, help="뽑을 태스크 수")
    ap.add_argument("--seed", type=int, default=20260707, help="결정적 시드")
    ap.add_argument("--min-per-repo", type=int, default=1, help="각 레포 최소 태스크 수(0=순수비례)")
    ap.add_argument("--out", default="/home/yunuikang/yunuikang_work/scratch/traces/swebench_stratified64")
    args = ap.parse_args()

    from datasets import load_dataset
    ds = load_dataset(args.dataset, split=args.split)
    by_repo = defaultdict(list)
    for row in ds:
        by_repo[row["repo"]].append(row["instance_id"])
    counts = {r: len(v) for r, v in by_repo.items()}
    total = sum(counts.values())

    alloc = proportional_alloc(counts, args.n, args.min_per_repo)

    # 레포 내부 시드 고정 랜덤 샘플(레포명으로 시드 파생 → 레포 간 독립·결정적)
    picked = {}
    for repo in sorted(by_repo):
        ids = sorted(by_repo[repo])  # 정렬로 순서 결정성 확보
        rng = random.Random(f"{args.seed}:{repo}")
        k = alloc.get(repo, 0)
        picked[repo] = sorted(rng.sample(ids, k)) if k > 0 else []

    flat = [iid for repo in sorted(picked) for iid in picked[repo]]
    assert len(flat) == sum(alloc.values())

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 1) id 리스트(+ 주석)
    with open(out.with_suffix(".txt"), "w") as f:
        f.write(f"# stratified sample n={len(flat)} seed={args.seed} min_per_repo={args.min_per_repo}\n")
        f.write(f"# dataset={args.dataset} split={args.split} total={total}\n")
        for repo in sorted(picked):
            f.write(f"# {repo}: {len(picked[repo])} (orig {counts[repo]}, "
                    f"{100*counts[repo]/total:.1f}% -> {100*len(picked[repo])/len(flat):.1f}%)\n")
        for iid in flat:
            f.write(iid + "\n")

    # 2) mini-extra --filter 정규식
    filt = "^(" + "|".join(iid.replace(".", r"\.").replace("+", r"\+") for iid in flat) + ")$"
    out.with_suffix(".filter.txt").write_text(filt + "\n")

    # 3) meta: 배분 + 원본% vs 표본% 대조
    meta = {
        "dataset": args.dataset, "split": args.split, "n": len(flat), "seed": args.seed,
        "min_per_repo": args.min_per_repo, "total_instances": total, "num_repos": len(counts),
        "allocation": {r: {"picked": len(picked[r]), "orig": counts[r],
                            "orig_pct": round(100*counts[r]/total, 1),
                            "sample_pct": round(100*len(picked[r])/len(flat), 1)}
                       for r in sorted(counts)},
    }
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))

    # 콘솔 요약
    print(f"Sampled {len(flat)}/{total} tasks across {len(counts)} repos (seed={args.seed}, min_per_repo={args.min_per_repo})")
    print(f"{'repo':30s} {'orig':>5s} {'orig%':>6s} {'pick':>5s} {'samp%':>6s}")
    for r in sorted(counts, key=lambda x: -counts[x]):
        a = meta["allocation"][r]
        print(f"{r:30s} {a['orig']:>5d} {a['orig_pct']:>5.1f}% {a['picked']:>5d} {a['sample_pct']:>5.1f}%")
    # 분포 충실도: L1 거리(원본% vs 표본%)
    l1 = sum(abs(meta["allocation"][r]['orig_pct'] - meta["allocation"][r]['sample_pct']) for r in counts)
    print(f"distribution L1 drift (sum |orig% - sample%|) = {l1:.1f} pct-points")
    print("wrote:", out.with_suffix('.txt'), out.with_suffix('.filter.txt'), out.with_suffix('.meta.json'))


if __name__ == "__main__":
    main()
