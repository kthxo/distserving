"""ThunderAgent configuration."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    """ThunderAgent configuration (set via command line args)."""
    # Backend configuration
    backends: List[str] = field(default_factory=lambda: ["http://localhost:8000"])
    
    # Router mode: "default" (pure proxy), "tr" (capacity scheduling), or "mori"
    # (relative-idleness 3-tier offloading).
    router_mode: str = "tr"

    # Backend type: "vllm", "sglang", or "skyrl"
    backend_type: str = "vllm"
    
    # Profile configuration
    profile_enabled: bool = False
    profile_dir: str = "/tmp/thunderagent_profiles"
    
    # Metrics monitoring configuration
    metrics_enabled: bool = False
    metrics_interval: float = 5.0  # seconds between metrics fetch
    
    # Scheduler configuration
    scheduler_interval: float = 5.0  # seconds between scheduler checks
    acting_token_weight: float = 1.0  # weight for acting tokens in capacity calculation
    use_acting_token_decay: bool = False  # use 2^(-t) decay for acting tokens in resume logic

    # MORI configuration (only used when router_mode == "mori")
    mori_k: int = 5  # idleness window size
    mori_cpu_capacity_ratio: float = 1.0  # CPU tier capacity = ratio x GPU KV pool (1x/2x)
    mori_reload_bw_bytes_per_s: float = 8.0e9  # Phase-1 CPU->GPU reload cost model bandwidth
    mori_min_dwell_ticks: int = 1  # sticky cooldown (anti-thrash)


# Global config instance (set by __main__.py before app starts)
_config: Config = Config()


def get_config() -> Config:
    """Get the global config instance."""
    return _config


def set_config(config: Config) -> None:
    """Set the global config instance."""
    global _config
    _config = config
