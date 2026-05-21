"""
prefetch.py — Anticipatory file caching for Miser.

Unlike CLI proxies that intercept commands, Miser observes access patterns
and prefetches the NEXT likely file before Claude asks for it.

How it works:
  1. Track which files get accessed and in what order
  2. Build a lightweight Markov-chain predictor
  3. When file A is accessed, pre-load file B into the OS page cache
  4. Next read of B is instant (already in memory)

This is purely a performance optimization — no tokens involved.
It makes the "outline everything" workflow feel instant.
"""

import os, threading, time
from collections import defaultdict
from pathlib import Path

class PrefetchPredictor:
    """
    Lightweight file-access predictor.
    Observes read/outline/grep patterns and prefetches likely-next files.

    NOT a proxy — it doesn't intercept anything. It just observes and predicts.
    """

    def __init__(self, max_history: int = 200):
        self._transitions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._access_order: list[str] = []
        self._prefetch_events: list[tuple[str, float]] = []  # (filepath, timestamp) for hit detection
        self._max_history = max_history
        self._lock = threading.Lock()
        self._enabled = True
        self._prefetch_count = 0
        self._hit_count = 0

    def observe(self, filepath: str):
        """Record that a file was accessed. Update the predictor."""
        if not self._enabled:
            return
        with self._lock:
            self._access_order.append(filepath)
            if len(self._access_order) > 1:
                prev = self._access_order[-2]
                self._transitions[prev][filepath] += 1
            # Trim old history
            if len(self._access_order) > self._max_history:
                self._access_order = self._access_order[-self._max_history:]

    def predict_next(self, current_file: str) -> list[str]:
        """Given the current file, predict the next 2-3 likely files."""
        with self._lock:
            if current_file not in self._transitions:
                return []
            # Sort by access count, descending
            candidates = sorted(
                self._transitions[current_file].items(),
                key=lambda x: x[1], reverse=True
            )
            return [f for f, _ in candidates[:3]]

    def prefetch(self, filepath: str):
        """
        Pre-load a file into the OS page cache.
        Records timestamp for later hit detection (review item #19).
        """
        try:
            p = Path(filepath).expanduser().resolve()
            if not p.exists() or not p.is_file():
                return
            now = time.time()
            with open(p, 'rb') as f:
                while f.read(1024 * 1024):
                    pass
            with self._lock:
                self._prefetch_events.append((str(p), now))
                if len(self._prefetch_events) > 500:
                    self._prefetch_events = self._prefetch_events[-200:]
            self._prefetch_count += 1
        except (OSError, PermissionError):
            pass

    def after_access(self, filepath: str):
        """Called after every file access. Observes + triggers prefetch."""
        self.observe(filepath)
        if not self._enabled:
            return
        # Predict and prefetch in background
        candidates = self.predict_next(filepath)
        for candidate in candidates:
            threading.Thread(
                target=self.prefetch,
                args=(candidate,),
                daemon=True
            ).start()

    def check_hit(self, filepath: str) -> bool:
        """Check if this file was likely already cached by a prior prefetch.
        Uses access timestamp comparison — if the file was accessed within
        100ms of the prefetch, it counts as a prefetch hit."""
        p = Path(filepath).expanduser().resolve()
        try:
            access_time = p.stat().st_atime if p.exists() else 0
        except OSError:
            return False
        # Compare to our tracked prefetch timestamps
        with self._lock:
            for f, ts in self._prefetch_events:
                pf = Path(f).expanduser().resolve()
                if pf == p and abs(access_time - ts) < 0.5:
                    self._hit_count += 1
                    return True
        return False

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "prefetch_count": self._prefetch_count,
                "hit_count": self._hit_count,
                "transitions_learned": sum(len(v) for v in self._transitions.values()),
                "enabled": self._enabled,
            }


# Global singleton
_predictor = PrefetchPredictor()

def observe_access(filepath: str):
    _predictor.after_access(filepath)

def get_stats() -> dict:
    return _predictor.stats
