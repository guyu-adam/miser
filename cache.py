"""
cache.py — Response cache for Miser v1.4 (Phase 3 #22).
Caches Zero-LLM results to avoid redundant disk reads.
"""

import threading, time, json
from pathlib import Path


class ResponseCache:
    """Simple TTL-based cache for Zero-LLM deterministic results.
    Same path+params → cached result (TTL 30s default)."""

    def __init__(self, ttl: float = 30.0, max_entries: int = 500):
        self._store: dict[str, tuple[float, any]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0

    def _key(self, *parts) -> str:
        return json.dumps(parts, sort_keys=True)

    def get(self, *key_parts):
        k = self._key(*key_parts)
        with self._lock:
            entry = self._store.get(k)
            if entry:
                ts, val = entry
                if time.time() - ts < self._ttl:
                    self._hits += 1
                    return val
                del self._store[k]
            self._misses += 1
            return None

    def set(self, value, *key_parts):
        k = self._key(*key_parts)
        with self._lock:
            if len(self._store) >= self._max_entries:
                # Evict oldest 10%
                sorted_keys = sorted(self._store.items(), key=lambda x: x[1][0])
                for old_k, _ in sorted_keys[:self._max_entries // 10]:
                    del self._store[old_k]
            self._store[k] = (time.time(), value)

    def clear(self):
        with self._lock:
            self._store.clear()

    @property
    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / max(total, 1), 3),
                "ttl_s": self._ttl,
            }


_cache = ResponseCache(ttl=30.0)


def cached(key_parts, fn):
    """Decorator: if cached, return cache; else compute + cache + return."""
    result = _cache.get(*key_parts)
    if result is not None:
        return result
    result = fn()
    _cache.set(result, *key_parts)
    return result


def cache_stats() -> dict:
    return _cache.stats

def cache_clear():
    _cache.clear()
