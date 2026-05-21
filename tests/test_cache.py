"""Tests for cache.py — response cache."""
import time
from cache import ResponseCache


class TestResponseCache:
    def test_cache_hit(self):
        c = ResponseCache(ttl=10.0)
        c.set("cached_value", "key1", "arg2")
        result = c.get("key1", "arg2")
        assert result == "cached_value"

    def test_cache_miss(self):
        c = ResponseCache(ttl=10.0)
        assert c.get("nonexistent") is None

    def test_different_keys_independent(self):
        c = ResponseCache(ttl=10.0)
        c.set("val_a", "a")
        c.set("val_b", "b")
        assert c.get("a") == "val_a"
        assert c.get("b") == "val_b"

    def test_ttl_expiry(self):
        c = ResponseCache(ttl=0.01)
        c.set("ephemeral", "k")
        time.sleep(0.02)
        assert c.get("k") is None

    def test_stats(self):
        c = ResponseCache(ttl=10.0)
        c.set("v", "k")
        c.get("k")  # hit
        c.get("missing")  # miss
        s = c.stats
        assert s["hits"] == 1
        assert s["misses"] == 1
        assert s["entries"] == 1

    def test_clear(self):
        c = ResponseCache(ttl=10.0)
        c.set("v", "k")
        c.clear()
        assert c.get("k") is None

    def test_max_entries_eviction(self):
        c = ResponseCache(ttl=10.0, max_entries=10)
        for i in range(15):
            c.set(f"v{i}", f"k{i}")
        assert c.stats["entries"] <= 10

    def test_hit_rate_calculation(self):
        c = ResponseCache(ttl=10.0)
        c.set("v", "k")
        c.get("k")  # hit
        c.get("k")  # hit
        c.get("x")  # miss
        assert abs(c.stats["hit_rate"] - 0.667) < 0.01
