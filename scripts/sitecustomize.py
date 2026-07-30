"""sitecustomize hook — applies the MORI HiCache typed-eviction patch in EVERY
Python process that starts with this directory on PYTHONPATH, including the
scheduler subprocesses SGLang spawns via multiprocessing.spawn (which re-import
sglang fresh and therefore do NOT inherit a monkey-patch applied only in the
parent). Guarded by the SGLANG_MORI_PATCH env var so it is inert unless the MORI
serve explicitly opts in.

Python runs `sitecustomize` automatically at interpreter startup (before argparse
in sglang.launch_server), so `--radix-eviction-policy mori|priority` is
registered in time and the custom RadixCache/evict_host patches are live in the
schedulers where the radix cache is actually constructed.
"""
import os

if os.environ.get("SGLANG_MORI_PATCH") == "1":
    try:
        import mori_hicache_yunuikang
        mori_hicache_yunuikang.install()
    except Exception as e:  # never break interpreter startup
        import sys
        print(f"[sitecustomize] MORI patch skipped: {e!r}", file=sys.stderr)
