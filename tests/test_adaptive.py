"""Tests for adaptive.py — self-learning quality router."""


class TestAdaptiveRouter:
    def test_initial_state_allows_all(self):
        from adaptive import AdaptiveRouter
        r = AdaptiveRouter()
        ok, reason = r.should_route_to_local("write tests", "test")
        assert ok

    def test_failures_trigger_cooldown(self):
        from adaptive import AdaptiveRouter
        r = AdaptiveRouter()
        # 4 consecutive failures should trigger block
        for _ in range(4):
            r.record("review", False)
        ok, reason = r.should_route_to_local("review this", "review")
        assert not ok
        assert "COOLDOWN" in reason or "LOW_CONFIDENCE" in reason

    def test_successes_keep_open(self):
        from adaptive import AdaptiveRouter
        r = AdaptiveRouter()
        for _ in range(8):
            r.record("test", True)
        ok, reason = r.should_route_to_local("write tests", "test")
        assert ok

    def test_mixed_categories_independent(self):
        from adaptive import AdaptiveRouter
        r = AdaptiveRouter()
        # Kill review but test remains open
        for _ in range(4):
            r.record("review", False)
        for _ in range(6):
            r.record("test", True)
        assert not r.should_route_to_local("review code", "review")[0]
        assert r.should_route_to_local("write tests", "test")[0]

    def test_cooldown_escalates(self):
        from adaptive import AdaptiveRouter
        r = AdaptiveRouter()
        mult0 = r.get_profile("explain").cooldown_multiplier
        r.record("explain", False)
        mult1 = r.get_profile("explain").cooldown_multiplier
        assert mult1 >= mult0
        r.record("explain", False)
        mult2 = r.get_profile("explain").cooldown_multiplier
        assert mult2 > mult1  # escalating after 2 failures

    def test_snapshot(self):
        from adaptive import AdaptiveRouter
        r = AdaptiveRouter()
        r.record("fix", True)
        r.record("fix", True)
        snap = r.snapshot()
        assert "fix" in snap
        assert snap["fix"]["total"] == 2
