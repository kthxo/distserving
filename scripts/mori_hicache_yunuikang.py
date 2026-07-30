"""MORI typed eviction for SGLang HiCache (real engine, no fork).

Grounded in the M4-T source read of installed sglang 0.5.10:
  * `PriorityStrategy.get_priority(node) = (node.priority, node.last_access_time)`
    (`mem_cache/evict_policy.py`) is exactly MORI's GPU-tier typed eviction:
    lower priority evicted first, LRU within a type. The router stamps the type
    via the OpenAI `priority` field -> `Req.priority` -> `node.priority`
    (monotonic max on insert), so busy (high rank) KV stays on GPU and idle
    (low rank) KV is evicted first. **No engine patch needed for the GPU tier.**
  * The eviction-policy dispatch (`mem_cache/radix_cache.py`) is a hardcoded
    if/elif; "priority" works out of the box once whitelisted, but "mori" would
    raise. `HiRadixCache.evict_host` (`mem_cache/hiradix_cache.py`) reuses the
    SAME `self.eviction_strategy` as the device tier, so the CPU tier cannot be
    reversed by policy choice alone.

`install()` (call BEFORE `sglang.launch_server`):
  (a) whitelists "priority" and "mori" as CLI choices
      (`server_args.add_radix_eviction_policy_choices`);
  (b) for `--radix-eviction-policy mori`, maps the device tier to the stock
      PriorityStrategy AND makes `evict_host` sort by the REVERSED key
      (-priority) so the CPU tier evicts busy -> idle -> inactive (paper §4.3.2).
      The original `evict_host` body is reused verbatim; only the strategy is
      swapped for the duration of the call (lowest-risk override).

Baselines (SMG/TA/TA+O with `--radix-eviction-policy lru`) are unaffected: the
`_mori` flag is False and both patches are inert.
"""


def install() -> None:
    from sglang.srt import server_args as SA
    SA.add_radix_eviction_policy_choices(["priority", "mori"])

    from sglang.srt.mem_cache import radix_cache as RC
    from sglang.srt.mem_cache import evict_policy as EP

    class _MoriHostStrategy(EP.EvictionStrategy):
        """Host tier: reverse the type order (busy evicted first) while keeping
        LRU as the tiebreak — the mirror of the device PriorityStrategy."""
        def get_priority(self, node):
            return (-node.priority, node.last_access_time)

    # (1) Accept "mori": translate to stock "priority" for the device tier and
    #     flag the instance so evict_host uses the reversed host strategy.
    _orig_rc_init = RC.RadixCache.__init__

    def _rc_init(self, *args, **kwargs):
        params = args[0] if args else kwargs.get("params")
        is_mori = False
        if params is not None and str(getattr(params, "eviction_policy", "")).lower() == "mori":
            is_mori = True
            params.eviction_policy = "priority"  # device -> PriorityStrategy
        _orig_rc_init(self, *args, **kwargs)
        self._mori = is_mori
        if is_mori:
            self._mori_host_strategy = _MoriHostStrategy()

    RC.RadixCache.__init__ = _rc_init

    # (2) Host-tier reverse: swap the strategy only for the evict_host call.
    try:
        from sglang.srt.mem_cache import hiradix_cache as H
    except Exception:
        return
    if not hasattr(H.HiRadixCache, "evict_host"):
        return
    _orig_evict_host = H.HiRadixCache.evict_host

    def _evict_host(self, num_tokens):
        if getattr(self, "_mori", False):
            saved = self.eviction_strategy
            self.eviction_strategy = self._mori_host_strategy
            try:
                return _orig_evict_host(self, num_tokens)
            finally:
                self.eviction_strategy = saved
        return _orig_evict_host(self, num_tokens)

    H.HiRadixCache.evict_host = _evict_host
