"""
cache.py — Response cache for Miser v1.5.5.
- Simple TTL cache for deterministic Zero-LLM results (v1.4)
- Semantic cache: detects if a semantically similar query was answered before (v1.5.5)
"""

import threading, time, json, math, hashlib
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


# ── Semantic Cache (v1.5.5) ──────────────────────────────────────────────────────

class SemanticCache:
    """
    Caches LLM responses by query embedding similarity.
    If a new query matches a cached one (cosine > threshold), return cached result.
    Uses Jaccard + MinHash as a lightweight approximation when no embed model.
    """

    def __init__(self, threshold: float = 0.85, max_entries: int = 200, ttl: float = 300.0):
        self._entries: list[dict] = []  # [{query, tokens, result, ts, embedding}]
        self._lock = threading.Lock()
        self._threshold = threshold
        self._max_entries = max_entries
        self._ttl = ttl
        self._hits = 0
        self._misses = 0

    def _jaccard(self, tokens_a: set, tokens_b: set) -> float:
        if not tokens_a or not tokens_b:
            return 0.0
        return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

    def _tokenize(self, text: str) -> set:
        import re
        return set(re.findall(r"[a-zA-Z_]\w*", text.lower()))

    def _cosine_vec(self, a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb + 1e-9)

    def get(self, query, embedding=None):
        """Check if a semantically similar query is cached."""
        now = time.time()
        query_tokens = self._tokenize(query)
        with self._lock:
            # Evict expired
            self._entries = [e for e in self._entries if now - e["ts"] < self._ttl]

            best_sim = 0.0
            best_entry = None

            for entry in self._entries:
                # Two-tier match: embedding cosine > Jaccard
                sim = 0.0
                if embedding and entry.get("embedding"):
                    sim = self._cosine_vec(embedding, entry["embedding"])
                    sim = max(sim, self._jaccard(query_tokens, entry.get("tokens", set())) * 0.5)
                else:
                    sim = self._jaccard(query_tokens, entry.get("tokens", set()))

                if sim > best_sim and sim >= self._threshold:
                    best_sim = sim
                    best_entry = entry

            if best_entry:
                self._hits += 1
                best_entry["ts"] = now  # bump TTL
                return best_entry["result"]

            self._misses += 1
            return None

    def set(self, query, result, embedding=None):
        """Cache a query-result pair."""
        tokens = self._tokenize(query)
        with self._lock:
            if len(self._entries) >= self._max_entries:
                self._entries = sorted(self._entries, key=lambda e: e["ts"])[self._max_entries // 10:]
            self._entries.append({
                "query": query[:200],
                "tokens": tokens,
                "result": result[:2000],
                "ts": time.time(),
                "embedding": embedding,
            })

    @property
    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / max(total, 1), 3),
                "threshold": self._threshold,
            }


_cache = ResponseCache(ttl=30.0)
_semantic_cache = SemanticCache(threshold=0.65, ttl=300.0)


def cached(key_parts, fn):
    """Decorator: if cached, return cache; else compute + cache + return."""
    result = _cache.get(*key_parts)
    if result is not None:
        return result
    result = fn()
    _cache.set(result, *key_parts)
    return result


def semantic_cached(query, fn, embedding=None):
    """
    Check semantic cache before calling fn.
    Returns (result, cached) — cached=True means cache hit.
    """
    result = _semantic_cache.get(query, embedding)
    if result is not None:
        return result, True
    result = fn()
    _semantic_cache.set(query, result, embedding)
    return result, False


def cache_stats() -> dict:
    return {
        "zero": _cache.stats,
        "semantic": _semantic_cache.stats,
    }


def cache_clear():
    _cache.clear()
