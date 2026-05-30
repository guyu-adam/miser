"""
backends/__init__.py — Backend registry and auto-discovery.

Usage:
    from backends import discover_backend
    backend = discover_backend()
    models = backend.list_models()
"""

import time
from typing import Optional

from backends.ollama import OllamaBackend
from backends.openai_compat import OpenAICompatBackend


# Ordered by preference: first backend that detects wins
_REGISTRY = [
    OllamaBackend,
    OpenAICompatBackend,
]


def discover_backend(timeout_per: float = 3.0) -> Optional:
    """Scan all registered backends. Return first one that responds."""
    for backend_cls in _REGISTRY:
        t0 = time.time()
        try:
            be = backend_cls()
            if be.detect():
                elapsed = time.time() - t0
                print(f"  [miser] Detected {be.name} at {be.base_url} ({elapsed:.1f}s)")
                return be
        except Exception:
            pass
    return None
