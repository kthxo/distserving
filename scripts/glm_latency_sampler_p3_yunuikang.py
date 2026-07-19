#!/usr/bin/env python3
"""P3 §4-4-4 A/B/C — multi-window GLM tool-latency sampler (GPU-free, self-firing).
Fires a FIXED representative GLM prompt set at the external GLM API every ~INTERVAL
minutes for ~DURATION hours, logging per-call latency + timestamp. No orchestrator/GPU.
Windows are split post-hoc from timestamps. Respects GLM 1000 req/day via pacing + a
hard daily budget cap. Keys read from env only (never logged).

Env: GLM_API_KEY, GLM_BASE_URL (from .hle_env).
Args: --prompts <jsonl> --out <jsonl> [--interval-min 15] [--duration-h 24] [--daily-cap 800]
"""
import argparse, json, os, time
from datetime import datetime, timezone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval-min", type=float, default=15.0)
    ap.add_argument("--duration-h", type=float, default=24.0)
    ap.add_argument("--daily-cap", type=int, default=800)  # safety < 1000/day
    ap.add_argument("--start-unix", type=float, required=True)  # pass to avoid Date.now in-loop
    args = ap.parse_args()

    from openai import OpenAI
    api_key = os.environ["GLM_API_KEY"]
    base_url = os.getenv("GLM_BASE_URL", "https://api.z.ai/api/paas/v4")
    if "openai/v1" in base_url:
        base_url = "https://api.z.ai/api/paas/v4"
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=180.0)

    prompts = [json.loads(l) for l in open(args.prompts) if l.strip()]
    interval_s = args.interval_min * 60.0
    end_unix = args.start_unix + args.duration_h * 3600.0
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)

    def log(rec):
        with open(args.out, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    daily_count = 0
    day_anchor = args.start_unix
    tick = 0
    while time.time() < end_unix:
        # reset daily budget every 24h
        if time.time() - day_anchor >= 86400:
            day_anchor += 86400
            daily_count = 0
        tick += 1
        for p in prompts:
            if daily_count >= args.daily_cap:
                log({"event": "budget_pause", "tick": tick, "ts_unix": time.time(),
                     "daily_count": daily_count})
                break
            retries = 0
            while True:
                t0 = time.time()
                try:
                    r = client.chat.completions.create(
                        model=p["model"], messages=p["messages"],
                        temperature=p.get("temperature", 0.2),
                        max_tokens=p.get("max_tokens", 4000),
                        extra_body={"thinking": {"type": "disabled"}},
                    )
                    dt = time.time() - t0
                    daily_count += 1
                    out_tok = getattr(getattr(r, "usage", None), "completion_tokens", None)
                    fr = r.choices[0].finish_reason if r.choices else None
                    log({"ts_unix": round(t0, 3),
                         "ts_iso": datetime.fromtimestamp(t0, tz=timezone.utc).isoformat(),
                         "tick": tick, "pid": p.get("pid"), "kind": p.get("kind"),
                         "chars": p.get("chars"), "max_tokens": p.get("max_tokens"),
                         "latency_s": round(dt, 3), "success": True, "retries": retries,
                         "out_tokens": out_tok, "finish_reason": fr})
                    break
                except Exception as e:
                    dt = time.time() - t0
                    msg = str(e)[:200]
                    status = getattr(e, "status_code", None) or (429 if "429" in msg else None)
                    retries += 1
                    log({"ts_unix": round(t0, 3),
                         "ts_iso": datetime.fromtimestamp(t0, tz=timezone.utc).isoformat(),
                         "tick": tick, "pid": p.get("pid"), "kind": p.get("kind"),
                         "latency_s": round(dt, 3), "success": False, "retries": retries,
                         "status": status, "err": msg})
                    if retries >= 4:
                        break
                    # backoff (longer on rate-limit)
                    time.sleep(60 if status == 429 else min(10 * retries, 60))
        # pace to next tick
        nxt = args.start_unix + tick * interval_s
        sleep_for = max(5.0, nxt - time.time())
        time.sleep(sleep_for)

    log({"event": "sampler_done", "ts_unix": time.time(), "ticks": tick, "daily_count": daily_count})


if __name__ == "__main__":
    main()
