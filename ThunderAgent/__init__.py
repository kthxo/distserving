"""
ThunderAgent - VLLM proxy with program state tracking.

Module structure:
- backend: Backend state management
- program: Program state management
- scheduler: Request routing and proxying
"""

from .config import Config, get_config, set_config
from .backend import BackendState
from .program import ProgramState, ProgramStatus
from .scheduler import MultiBackendRouter

# NOTE: `.app` is imported LAZILY (PEP 562 __getattr__ below) rather than at
# package import time. Eagerly importing `.app` here ran app.py's module-level
# `router = _create_router()` using the DEFAULT config, because importing any
# submodule (e.g. `ThunderAgent.__main__`) triggers this package __init__ BEFORE
# the CLI calls set_config(). That silently made `--backends` and `--router`
# ineffective (single backend, always tr mode). Deferring the .app import lets
# __main__ set_config() first, so the router is built from the real CLI config.
def __getattr__(name):  # noqa: D401
    if name in ("get_program_id", "register_routes"):
        from . import app as _app
        return getattr(_app, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "Config",
    "get_config",
    "set_config",
    "BackendState",
    "ProgramState",
    "ProgramStatus",
    "MultiBackendRouter",
    "get_program_id",
    "register_routes",
]

__version__ = "0.2.0"
