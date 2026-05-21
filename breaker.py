"""
breaker.py — Circuit breaker for Ollama API calls (Phase 3 #21).
Prevents cascading failures when Ollama is down or overloaded.
"""

import threading, time


class CircuitBreaker:
    """State machine: CLOSED → OPEN → HALF_OPEN → CLOSED."""

    CLOSED = "closed"       # Normal operation
    OPEN = "open"            # Failing, reject immediately
    HALF_OPEN = "half_open"   # Testing if recovered

    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        self._threshold = failure_threshold
        self._timeout = timeout
        self._failures = 0
        self._state = self.CLOSED
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    def call(self, fn, *args, **kwargs):
        """Execute fn() with circuit breaker protection."""
        with self._lock:
            if self._state == self.OPEN:
                if time.time() - self._last_failure_time >= self._timeout:
                    self._state = self.HALF_OPEN
                else:
                    raise BreakerOpenError(
                        f"Circuit breaker OPEN for {self._timeout - (time.time() - self._last_failure_time):.0f}s"
                    )

        try:
            result = fn(*args, **kwargs)
            with self._lock:
                if self._state == self.HALF_OPEN:
                    self._state = self.CLOSED
                self._failures = 0
            return result
        except Exception as e:
            with self._lock:
                self._failures += 1
                self._last_failure_time = time.time()
                if self._failures >= self._threshold:
                    self._state = self.OPEN
            raise e

    @property
    def state(self) -> str:
        return self._state

    @property
    def failures(self) -> int:
        return self._failures

    def reset(self):
        with self._lock:
            self._state = self.CLOSED
            self._failures = 0


class BreakerOpenError(Exception):
    pass


# Global breaker for Ollama calls
ollama_breaker = CircuitBreaker(failure_threshold=5, timeout=60.0)
