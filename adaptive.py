"""
adaptive.py — Self-calibrating quality system for Miser.

Unlike static benchmarks that test a model once, Adaptive Quality learns
from EVERY interaction: which task types the local model handles well,
which it struggles with, and adjusts offloading decisions dynamically.

How it works:
  1. Each LLM operation gets scored (by the supervision layer in client.py)
  2. Scores are aggregated by task category (explain, fix, test, etc.)
  3. When confidence for a category drops below threshold, that category
     is temporarily delegated back to Claude until confidence recovers
  4. The system re-tests periodically to see if conditions improved

This creates a feedback loop: bad results → less offloading → better quality.
"""

import time, threading
from collections import defaultdict
from dataclasses import dataclass, field

@dataclass
class CategoryProfile:
    """Learned performance profile for one task type."""
    name: str
    total_ops: int = 0
    success_ops: int = 0          # passed all supervision checks
    flagged_ops: int = 0          # had at least one flag
    recent_5: list = field(default_factory=list)  # last 5 results (True=clean, False=flagged)
    blocked_until: float = 0.0    # timestamp — if in future, this category goes to Claude
    cooldown_multiplier: float = 1.0  # increases with consecutive failures

    @property
    def success_rate(self) -> float:
        if self.total_ops == 0:
            return 1.0
        return self.success_ops / self.total_ops

    @property
    def recent_success_rate(self) -> float:
        if not self.recent_5:
            return 1.0
        return sum(1 for r in self.recent_5 if r) / len(self.recent_5)

    @property
    def is_blocked(self) -> bool:
        return time.time() < self.blocked_until

    @property
    def should_offload(self) -> bool:
        """Should we offload this category to local LLM right now?"""
        if self.is_blocked:
            return False
        if self.recent_success_rate < 0.40:
            return False
        if self.success_rate < 0.60 and self.total_ops > 10:
            return False
        return True

    def record_success(self):
        self.total_ops += 1
        self.success_ops += 1
        self.recent_5.append(True)
        if len(self.recent_5) > 5:
            self.recent_5 = self.recent_5[-5:]
        self.cooldown_multiplier = max(0.5, self.cooldown_multiplier * 0.8)

    def record_failure(self):
        self.total_ops += 1
        self.flagged_ops += 1
        self.recent_5.append(False)
        if len(self.recent_5) > 5:
            self.recent_5 = self.recent_5[-5:]
        # Escalating cooldown
        if self.recent_success_rate < 0.40:
            cooldown_seconds = 120 * self.cooldown_multiplier  # 2 min base
            self.blocked_until = time.time() + cooldown_seconds
            self.cooldown_multiplier = min(8.0, self.cooldown_multiplier * 2.0)


class AdaptiveRouter:
    """
    Learns which task types the local model handles well,
    dynamically adjusts offloading decisions.

    Key insight: a 4B model might be great at test generation but
    poor at code review. The router learns this per-session and adapts.
    """

    def __init__(self):
        self._profiles: dict[str, CategoryProfile] = defaultdict(
            lambda: CategoryProfile(name="unknown")
        )
        self._lock = threading.Lock()

    def get_profile(self, category: str) -> CategoryProfile:
        with self._lock:
            p = self._profiles[category]
            p.name = category
            return p

    def record(self, category: str, success: bool):
        with self._lock:
            p = self._profiles[category]
            p.name = category
            if success:
                p.record_success()
            else:
                p.record_failure()

    def should_route_to_local(self, task: str, category: str) -> tuple[bool, str]:
        """
        Returns (should_offload, reason).
        Combines the static classifier (quality.py) with dynamic learning.
        """
        # Static check first
        from quality import should_offload as static_check
        ok, reason = static_check(task, category)
        if not ok:
            return False, reason

        # Dynamic check
        profile = self.get_profile(category)
        if profile.is_blocked:
            remaining = int(profile.blocked_until - time.time())
            return False, f"ADAPTIVE_COOLDOWN: {category} blocked for {remaining}s (recent failures)"

        if not profile.should_offload and profile.total_ops > 5:
            return False, f"ADAPTIVE_LOW_CONFIDENCE: {category} success_rate={profile.success_rate:.0%}"

        return True, "OK"

    def snapshot(self) -> dict:
        """Return current state for status endpoint."""
        with self._lock:
            return {
                name: {
                    "total": p.total_ops,
                    "success_rate": round(p.success_rate, 2) if p.total_ops else 1.0,
                    "recent_5": p.recent_5,
                    "blocked": p.is_blocked,
                    "should_offload": p.should_offload if not p.is_blocked else False,
                }
                for name, p in self._profiles.items()
            }


# Global singleton
_router = AdaptiveRouter()


def record_outcome(category: str, success: bool):
    """Called by client after each LLM operation."""
    _router.record(category, success)


def check_routing(task: str, category: str) -> tuple[bool, str]:
    """Check whether to route to local or keep with Claude."""
    return _router.should_route_to_local(task, category)


def adaptive_status() -> dict:
    return _router.snapshot()
