"""Tests for breaker.py — circuit breaker."""
from breaker import CircuitBreaker, BreakerOpenError


class TestCircuitBreaker:
    def test_closed_passes_through(self):
        cb = CircuitBreaker(failure_threshold=5, timeout=60.0)
        result = cb.call(lambda x: x * 2, 21)
        assert result == 42
        assert cb.state == "closed"

    def test_failures_open_breaker(self):
        cb = CircuitBreaker(failure_threshold=3, timeout=60.0)
        for _ in range(3):
            try:
                cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass
        assert cb.state == "open"

    def test_open_rejects_immediately(self):
        cb = CircuitBreaker(failure_threshold=2, timeout=999.0)
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass
        with __import__('pytest').raises(BreakerOpenError):
            cb.call(lambda: 42)

    def test_half_open_probe(self):
        cb = CircuitBreaker(failure_threshold=2, timeout=0.01)
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass
        import time
        time.sleep(0.02)
        # Should transition to half_open and succeed
        result = cb.call(lambda: 42)
        assert result == 42
        assert cb.state == "closed"

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=2, timeout=999.0)
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass
        cb.reset()
        assert cb.state == "closed"
        assert cb.failures == 0

    def test_failures_counter(self):
        cb = CircuitBreaker(failure_threshold=10, timeout=60.0)
        for _ in range(3):
            try:
                cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass
        assert cb.failures == 3

    def test_success_resets_failures(self):
        cb = CircuitBreaker(failure_threshold=10, timeout=60.0)
        try:
            cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass
        cb.call(lambda: 42)
        assert cb.failures == 0
