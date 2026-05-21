"""Stress tests — concurrent load, rapid fire, memory pressure."""
import sys, os, time, threading, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tools
from cache import ResponseCache
from task_queue import RequestQueue, QueuedTask
from security import RateLimiter


class TestConcurrentReads:
    def test_100_concurrent_reads(self):
        errors = []
        def reader():
            try:
                for _ in range(20):
                    tools.read_file(__file__, limit=1000)
            except Exception as e:
                errors.append(str(e))
        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0, f"Concurrent reads failed: {errors}"

    def test_100_concurrent_outlines(self):
        errors = []
        def outliner():
            try:
                for _ in range(10):
                    tools.outline_file(__file__)
            except Exception as e:
                errors.append(str(e))
        threads = [threading.Thread(target=outliner) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0

    def test_100_concurrent_greps(self):
        errors = []
        def grepper():
            try:
                for _ in range(20):
                    tools.grep_file(__file__, "def test_")
            except Exception as e:
                errors.append(str(e))
        threads = [threading.Thread(target=grepper) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0

    def test_mixed_operations_concurrent(self):
        errors = []
        def worker(wid):
            try:
                for i in range(10):
                    tools.read_file(__file__, limit=500)
                    tools.outline_file(__file__)
                    tools.grep_file(__file__, "def")
            except Exception as e:
                errors.append(f"w{wid}: {e}")
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0


class TestQueueStress:
    def test_rapid_enqueue_dequeue(self):
        q = RequestQueue(max_size=500)
        for i in range(200):
            q.enqueue(QueuedTask(str(i), f"t{i}", "s", "", 100, ""))
        count = 0
        while q.dequeue() is not None:
            count += 1
        assert count == 200

    def test_full_then_drain(self):
        q = RequestQueue(max_size=50)
        for i in range(50):
            assert q.enqueue(QueuedTask(str(i), f"t{i}", "s", "", 100, ""))
        assert not q.enqueue(QueuedTask("51", "t51", "s", "", 100, ""))
        for _ in range(50):
            assert q.dequeue() is not None
        assert q.dequeue() is None

    def test_concurrent_enqueue_different_queues(self):
        errors = []
        def worker(wid):
            try:
                q = RequestQueue(max_size=100)
                for i in range(50):
                    q.enqueue(QueuedTask(f"{wid}-{i}", f"t{i}", "s", "", 100, ""))
            except Exception as e:
                errors.append(str(e))
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0


class TestRateLimiterStress:
    def test_rapid_requests_across_keys(self):
        rl = RateLimiter()
        for i in range(1000):
            key = f"user_{i % 20}"
            rl.allow(key, 200)

    def test_many_unique_keys(self):
        rl = RateLimiter()
        for i in range(500):
            assert rl.allow(f"unique_{i}", 50)


class TestCacheStress:
    def test_many_cache_entries(self):
        c = ResponseCache(max_entries=100, ttl=60)
        for i in range(200):
            c.set(f"value_{i}", f"key_{i}")
        assert c.stats["entries"] <= 100

    def test_rapid_get_set(self):
        c = ResponseCache(ttl=60)
        for i in range(500):
            c.set(f"v{i}", f"k{i}")
            c.get(f"k{i}")


class TestMemoryStress:
    def test_read_large_file_stability(self):
        """Reading progressively larger files should not crash."""
        sizes = [100, 1000, 10000, 50000]
        for size in sizes:
            path = f"/tmp/_miser_stress_{size}.txt"
            with open(path, 'w') as f:
                f.write("x" * size)
            result = tools.read_file(path)
            assert isinstance(result, str)
            os.unlink(path)

    def test_outline_deeply_nested_file(self):
        path = "/tmp/_miser_stress_nested.py"
        with open(path, 'w') as f:
            for i in range(100):
                indent = "    " * (i % 10)
                f.write(f"{indent}def fn_{i}():\n{indent}    pass\n")
        result = tools.outline_file(path)
        assert "fn_0" in result
        assert "fn_99" in result
        os.unlink(path)


class TestRapidFireEndpoints:
    def test_rapid_grep_sequence(self):
        for i in range(100):
            result = tools.grep_file(__file__, "def test_")
            assert isinstance(result, str)

    def test_rapid_outline_sequence(self):
        for i in range(50):
            result = tools.outline_file(__file__)
            assert isinstance(result, str)

    def test_rapid_read_sequence(self):
        for i in range(100):
            result = tools.read_file(__file__, limit=200)
            assert isinstance(result, str)


class TestRecoveryUnderLoad:
    def test_mixed_load_no_degradation(self):
        """Performance should not degrade under mixed load."""
        times = []
        for _ in range(30):
            t0 = time.perf_counter_ns()
            tools.outline_file(__file__)
            tools.read_file(__file__, limit=500)
            tools.grep_file(__file__, "class Test")
            elapsed_us = (time.perf_counter_ns() - t0) / 1000
            times.append(elapsed_us)
        avg = statistics.mean(times)
        p95 = sorted(times)[int(len(times) * 0.95)]
        # All should be well under 100ms
        assert p95 < 100000, f"p95={p95:.0f}us exceeds 100ms limit"
