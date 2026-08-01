# M-SWP 1런 패스 중간 리포트

> 작성 2026-08-01 · 브랜치 `mori` · **HEAD `86ec401`** · 서버 goguma6 (RTX 5090 ×2, SGLang 0.5.10 + HiCache, YaRN 64k)
> 원시 데이터: `/home/yunuikang/yunuikang_work/scratch/mori/msw/results_msw.jsonl` (18/18 셀, 셀당 1런)
> 무효(pre-fix) 참고본: `.../results_msw_INVALID_prefix_0334.jsonl` (context/timeout 버그 시기 5셀, 폐기)
> 프로토콜: 고정 1h(`--duration-s 3600`, hard-deadline+grace) · Track M primary(117,257턴, decode152) · pin `--max-total-tokens 262144` · context-length 71680(YaRN factor 1.75) · warmup 20% · C 워커 순환셔플
> **failure-rate 게이트**: `fail% >1% AND failed_programs ≥3` → 조기중단(systematic만). 1–2건 transient는 관용 + failure_types 기록.
> **데이터 위생**: 18셀 중 **TA_r0_C50만 실패 1건**(=2.3%, `http_500` **transient**, 게이트 관용). 나머지 17셀 fail% 0%. systematic abort 없음.

---

## 1. 전 18셀 결과 (out tok/s | ttft_p50 s | steady_turns)

| 시스템 | C=20 | C=50 | C=80 |
|---|---|---|---|
| SMG (router=default, HiCache OFF) | 3.8 / 37.2 / 223 | 2.7 / 121.9 / 180 | 3.0 / 188.6 / 175 |
| TA (router=tr, HiCache OFF) | 21.8 / 2.0 / 1363 | 12.8 / 2.5 / 859¹ | 11.4 / 2.7 / 729 |
| TA+O r1 (tr, HiCache r1) | 19.7 / 1.8 / 1247 | 14.6 / 2.6 / 943 | 8.9 / 3.9 / 629 |
| **TA+O r2** (tr, HiCache r2) | 19.9 / 1.8 / 1307 | 16.1 / 2.1 / 994 | **14.3 / 3.4 / 888** |
| MORI r1 (mori, HiCache r1, EVICT=mori) | 16.2 / 2.5 / 1035 | 8.5 / 5.6 / 602 | 7.4 / 9.1 / 498 |
| **MORI r2** (mori, HiCache r2, EVICT=mori) | 22.2 / 2.1 / 1412 | 11.8 / 5.0 / 834 | **6.5 / 13.9 / 520** |

¹ TA_r0_C50: 1 transient http_500 (fail% 2.3%), 게이트 관용. 지표는 완료 43 프로그램 기준.
보조 지표(step req/s·cacheHit·load_back·evicted)는 `results_msw.jsonl` 참조.

## 2. P1~P4 판정 (초안)

- **P1 (C=80·r=2, MORI vs TA+O) — ❌ FAIL (역방향)**: throughput MORI/TA+O = **6.47/14.28 = 0.45** (MORI가 2.2× **느림**; 기대 ≥1.15). TTFT p50 **13.9 vs 3.4s = 4.1× 악화**; ttft_mean 94.9 vs 53.4s(1.8×); step req/s 0.18 vs 0.32(0.56×). 헤드라인 가설과 정반대.
- **P2 (C 단조성) — 미성립**: TA+O r2도 **단조↓**(19.9→16.1→14.3), MORI r2도 단조↓이나 **더 급격**(22.2→11.8→6.5). "TA+O 비단조를 MORI가 개선"이 관측되지 않음. (r1 TA+O는 C80서 소폭 꺾임 8.9<14.6이나, 헤드라인 r=2는 단조.)
- **P3 (C=20 동률) — ~성립**: MORI_r2(22.2) ≈ TA(21.8) ≈ TA+O_r2(19.9). 저압박에선 유사.
- **P4 (tr 무손상) — ✅**: TA/SMG baseline 정상 구동, 크래시·회귀 없음(격리 diff 0줄은 별도 검증됨).

## 3. 서브 결론 (예상 방향은 재현)

- **TA ≫ SMG**: 스케줄러 admission control 이득 뚜렷 — throughput 3–6×, TTFT 14–70× 개선. SMG는 admission control 부재로 C↑에 TTFT 37→189s 폭증.
- **TA+O r2 > TA**: HiCache 오프로딩 이득 — C80 14.3 vs 11.4, cacheHit ~88%. r2(host 2×) > r1(특히 C80: 14.3 vs 8.9).
- **MORI < TA+O**: MORI의 3-tier(ι 배치 + CPU tier) 스케줄링이 **압박에서 지연 유발** — TTFT가 C↑에 2.1→14s 급증 → throughput 붕괴(6.5 @ C80·r2).

## 4. token drift 규명 (요청 4항)

- within_1pct **96–98%** → **drift>1% 턴 ≈ 2–4%**. 시스템별: SMG 2.0–3.3%, TA 3.0–3.4%, TA+O 2.9–4.2%, MORI 1.9–3.4%.
- **전 시스템 균일**(특정 시스템/peak-압박 regime 편향 없음) → **상대 비교를 왜곡하지 않음**.
- 원인: 컨텍스트 누적 drift + ctx-cap 트림(64k 창에 맞춰 oldest turn 제거, 실행 보장 대가로 일부 세션의 컨텍스트가 트레이스와 불일치).
- 판정: <1%는 아니고 ~3%이나 **균일 적용** → **§5 fidelity 한계로 기록**. MORI 저성능을 설명하지 못함(균일하므로).

## 5. 진단 + 다음 단계

**MORI 저성능 유력 원인**: `MoriRouter`의 CPU-tier pause/promote가 엔진 HiCache와 **이중 관리** → 프로그램이 (라우터 promote 대기 + 엔진 reload) **이중 지연** → 압박에서 TTFT 폭증(2.1→14s). 스케줄러 tick(5s) 단위 promote 지연이 누적되는 것으로 추정. 저성능은 버그일 수도, 실제 결과일 수도 있어 분해 필요.

**권고 다음 단계**:
1. **결정셀 repeat≥3** (C=80·r=2): MORI<TA+O 역전이 재현되는지(non-overlap 판정).
2. **MORI-a-only ablation** (router=mori + EVICT=lru, C=80·r{1,2}): 
   - MORI-full vs MORI-a-only → **typed eviction 기여** 분리
   - MORI-a-only vs TA+O(router=tr) → **라우터 스케줄링 기여** 분리
3. (병행 CPU) 라우터-엔진 이중관리 코드 점검: promote 지연·CPU tier가 실 HiCache와 어떻게 상호작용하는지.

→ 원인(스케줄러 promote 지연 vs typed eviction)을 규명한 뒤 결론. 무료(GPU 무증분) TTFT 분해(기존 데이터의 ttft 분포)도 병행.

---

> 상태: 1런 패스 완료·정지. GPU 유휴. 다음 GPU 잡(repeat/ablation)은 별도 승인 후.
