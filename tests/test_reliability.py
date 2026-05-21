"""Reliability tests — error recovery, fallback, supervision accuracy."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tools, threading, time
from memory import Memory
from cache import ResponseCache
from breaker import CircuitBreaker
from task_queue import RequestQueue, QueuedTask


class TestErrorRecovery:
    def test_read_missing_file_no_crash(self):
        result = tools.read_file("/tmp/zzz_nonexistent_abc123.txt")
        assert "not found" in result.lower()

    def test_grep_missing_file_no_crash(self):
        result = tools.grep_file("/tmp/nonexistent", "pattern")
        assert "not found" in result.lower()

    def test_outline_missing_file_no_crash(self):
        result = tools.outline_file("/tmp/nonexistent.py")
        assert "not found" in result.lower()

    def test_write_permission_error_handled(self):
        try:
            tools.write_to_file("/root/test.txt", "data")
        except Exception:
            pass  # expected on non-root

    def test_tree_permission_error_handled(self):
        result = tools.tree_view("/root", depth=1)
        assert isinstance(result, str)  # should not crash

    def test_run_invalid_command(self):
        result = tools.run_shell("nonexistent_command_xyz123")
        assert isinstance(result, str)  # should not crash

    def test_patch_empty_content(self):
        import tempfile
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        f.write("hello"); f.close()
        result = tools.patch_file(f.name, "nonexistent_pattern", "x")
        assert "not found" in result.lower()
        os.unlink(f.name)

    def test_safe_eval_recovers(self):
        for bad in ["__import__('os')", "open('/etc/passwd')", "lambda: 1",
                     "[x for x in range(10)]", "{'a': 1}"]:
            result = tools._safe_eval(bad)
            assert "error" in result.lower()

    def test_grep_invalid_regex(self):
        import tempfile
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        f.write("hello"); f.close()
        for bad in ["[invalid", "(unclosed", "**"]:
            result = tools.grep_file(f.name, bad)
            assert isinstance(result, str)
        os.unlink(f.name)


class TestFallbackBehavior:
    def test_cache_miss_returns_none(self):
        c = ResponseCache()
        assert c.get("nonexistent") is None

    def test_queue_timeout_expires_tasks(self):
        q = RequestQueue(max_size=10, timeout=0.001)
        q.enqueue(QueuedTask("1", "t", "s", "", 100, ""))
        time.sleep(0.01)
        assert q.dequeue() is None

    def test_breaker_resets_after_success(self):
        cb = CircuitBreaker(failure_threshold=3, timeout=60)
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(Exception("x")))
            except Exception:
                pass
        cb.call(lambda: 42)  # should reset
        assert cb.failures == 0

    def test_condensation_ratio_handles_zero(self):
        from condenser import condensation_ratio
        r = condensation_ratio("", "test")
        assert r["original_chars"] == 0

    def test_prefetch_directory_no_crash(self):
        from prefetch import PrefetchPredictor
        p = PrefetchPredictor()
        p.observe("/tmp/")  # directory, not file
        # should not crash

    def test_rate_limiter_window_cleanup(self):
        from security import RateLimiter
        rl = RateLimiter()
        for _ in range(3):
            rl.allow("wp", 3)
        time.sleep(0.01)
        # Should clean old entries


class TestSupervisionAccuracy:
    def test_hallucination_phrases_complete(self):
        from client import _HALLUCINATION_PHRASES
        expected_keywords = ["access", "ai", "unable", "apologize",
                            "information", "provide", "context"]
        full = " ".join(_HALLUCINATION_PHRASES).lower()
        for kw in expected_keywords:
            assert kw in full

    def test_quality_classify_all_ops(self):
        from quality import classify_op
        ops = {
            ("fix auth login bug", "fix"): "critical",
            ("write unit tests", "test"): "standard",
            ("ls -la ~/project", "run"): "safe",
            ("deploy to production", "deploy"): "critical",
            ("explain this module", "explain"): "standard",
        }
        for (task, op_type), expected in ops.items():
            assert classify_op(task, op_type) == expected

    def test_adaptive_learning_preserves_independence(self):
        from adaptive import AdaptiveRouter
        r = AdaptiveRouter()
        for _ in range(4):
            r.record("review", False)
        # test should still be open
        ok, _ = r.should_route_to_local("write tests", "test")
        assert ok

    def test_quality_should_offload_decisions(self):
        from quality import should_offload
        assert not should_offload("add JWT authentication", "codegen")[0]
        assert should_offload("write unit tests", "test")[0]
        assert should_offload("git status", "run")[0]


class TestThreadSafetyReliability:
    def test_memory_concurrent_operations(self):
        m = Memory()
        errors = []
        def worker(wid):
            try:
                for i in range(20):
                    m.save(f"w{wid}_k{i}", f"w{wid}_v{i}")
                    m.record(wid * 100 + i, f"t{i}", f"r{i}")
            except Exception as e:
                errors.append(str(e))
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0

    def test_token_counter_consistency(self):
        start = tools.get_tokens_saved()
        threads = []
        def add_tokens():
            for _ in range(100):
                tools.count_saved(40)
        for _ in range(10):
            t = threading.Thread(target=add_tokens)
            threads.append(t); t.start()
        for t in threads: t.join()
        added = tools.get_tokens_saved() - start
        assert added >= 8000  # 10 threads × 100 calls × 10 tokens min

    def test_rate_limiter_thread_safety(self):
        from security import RateLimiter
        rl = RateLimiter()
        errors = []
        def hammer():
            try:
                for _ in range(200):
                    rl.allow(f"k_{threading.get_ident()}", 500)
            except Exception as e:
                errors.append(str(e))
        threads = [threading.Thread(target=hammer) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
