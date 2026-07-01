#!/usr/bin/env python3
"""Smoke test for ThunderAgent + vLLM (8B).

Exercises the full ThunderAgent path:
  1. list models through the proxy
  2. single chat completion with a program_id
  3. a 2-turn "program" reusing the same program_id (KV locality path)
  4. release the program via POST /programs/release

Run against the ThunderAgent proxy port (default 9000), NOT vLLM directly.
"""
import argparse
import sys
import uuid

import requests
from openai import OpenAI


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:9000/v1")
    ap.add_argument("--router-url", default="http://localhost:9000")
    ap.add_argument("--model", default="Qwen/Qwen3-8B")
    args = ap.parse_args()

    client = OpenAI(base_url=args.base_url, api_key="unused")

    print("== [1] list models (best-effort; proxy may not expose /v1/models) ==")
    model = args.model
    try:
        models = client.models.list()
        served = [m.id for m in models.data]
        print("served models:", served)
        model = args.model if args.model in served else (served[0] if served else args.model)
    except Exception as e:
        print("model listing not available via proxy (non-fatal):", type(e).__name__)
    print("using model:", model)

    program_id = f"smoke:{uuid.uuid4().hex[:8]}"
    print(f"\n== [2] single completion (program_id={program_id}) ==")
    r1 = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "In one short sentence, what is a KV cache? /no_think"}],
        max_tokens=256,
        temperature=0,
        extra_body={"program_id": program_id},
    )
    print("assistant:", r1.choices[0].message.content)

    print("\n== [3] second turn, same program_id (multi-turn / KV locality) ==")
    r2 = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": "In one short sentence, what is a KV cache? /no_think"},
            {"role": "assistant", "content": r1.choices[0].message.content},
            {"role": "user", "content": "Now name one downside of it in two words. /no_think"},
        ],
        max_tokens=256,
        temperature=0,
        extra_body={"program_id": program_id},
    )
    print("assistant:", r2.choices[0].message.content)
    if r2.usage is not None:
        print("usage:", r2.usage)

    print("\n== [4] release program ==")
    try:
        resp = requests.post(
            f"{args.router_url}/programs/release",
            json={"program_id": program_id},
            timeout=5,
        )
        print("release status:", resp.status_code, resp.text[:200])
    except Exception as e:  # best-effort
        print("release failed (non-fatal):", e)

    print("\nSMOKE TEST OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
