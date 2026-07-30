#!/usr/bin/env python3
"""Thin launcher: install the MORI HiCache typed-eviction patch, then run
sglang.launch_server with the given argv.

Used for ALL systems (SMG/TA/TA+O/MORI). Baselines pass
`--radix-eviction-policy lru`, so the patch stays inert; only `--radix-eviction-policy
mori` (or `priority`) activates typed eviction. Importing the patch also makes
those policy names CLI-selectable (they are not in the stock whitelist).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mori_hicache_yunuikang as mori_hicache  # noqa: E402

mori_hicache.install()

import runpy  # noqa: E402

# sglang.launch_server parses sys.argv[1:]; argv[0] (this launcher) is ignored.
runpy.run_module("sglang.launch_server", run_name="__main__")
