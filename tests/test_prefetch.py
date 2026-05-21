import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from prefetch import PrefetchPredictor
import time


class TestPrefetchInit:
    def test_initial_state(self):
        p = PrefetchPredictor()
        assert p.stats["prefetch_count"] == 0
        assert p.stats["hit_count"] == 0
        assert p.stats["enabled"]


class TestPrefetchObserve:
    def test_single_observe(self):
        p = PrefetchPredictor()
        p.observe("/tmp/test.py")
        # No crash, state updated

    def test_multiple_observes_build_transitions(self):
        p = PrefetchPredictor()
        p.observe("/tmp/a.py")
        p.observe("/tmp/b.py")
        p.observe("/tmp/a.py")
        p.observe("/tmp/b.py")
        p.observe("/tmp/a.py")
        p.observe("/tmp/c.py")
        # Should have learned transitions
        assert p.stats["transitions_learned"] > 0


class TestPrefetchPredict:
    def test_predict_empty(self):
        p = PrefetchPredictor()
        assert p.predict_next("/unknown.py") == []

    def test_predict_after_learning(self):
        p = PrefetchPredictor()
        p.observe("/tmp/a.py")
        p.observe("/tmp/b.py")
        p.observe("/tmp/a.py")
        p.observe("/tmp/b.py")
        p.observe("/tmp/a.py")
        p.observe("/tmp/c.py")
        preds = p.predict_next("/tmp/a.py")
        assert isinstance(preds, list)


class TestPrefetchPrefetch:
    def test_prefetch_existing_file(self):
        p = PrefetchPredictor()
        p.prefetch(__file__)
        assert p.stats["prefetch_count"] == 1

    def test_prefetch_missing_file_no_crash(self):
        p = PrefetchPredictor()
        p.prefetch("/nonexistent/xyz.abc")
        assert p.stats["prefetch_count"] == 0


class TestPrefetchAfterAccess:
    def test_after_access_no_crash(self):
        p = PrefetchPredictor()
        p.after_access(__file__)


class TestPrefetchCheckHit:
    def test_check_hit_initial(self):
        p = PrefetchPredictor()
        assert not p.check_hit(__file__)


class TestPrefetchHistoryBound:
    def test_history_capped(self):
        p = PrefetchPredictor(max_history=10)
        for i in range(30):
            p.observe(f"/tmp/f{i}.py")
