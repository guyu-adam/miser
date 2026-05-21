"""Performance benchmarks — latency, throughput, regression detection."""
import sys, os, time, tempfile, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tools
from cache import ResponseCache
from task_queue import RequestQueue, QueuedTask


class TestZeroLLMLatency:
    """All Zero-LLM ops must complete in <50ms (SLA)."""
    SLA_MS = 50
    BENCHMARK_FILE = None

    @classmethod
    def setup_class(cls):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        for i in range(200):
            f.write(f"def function_{i}():\n    return {i}\n\n")
        cls.BENCHMARK_FILE = f.name
        f.close()

    @classmethod
    def teardown_class(cls):
        if cls.BENCHMARK_FILE:
            os.unlink(cls.BENCHMARK_FILE)

    def _measure(self, fn, iterations=10):
        times = []
        for _ in range(iterations):
            t0 = time.perf_counter_ns()
            fn()
            t1 = time.perf_counter_ns()
            times.append((t1 - t0) / 1_000_000)  # ms
        return {
            "min_ms": round(min(times), 3),
            "max_ms": round(max(times), 3),
            "avg_ms": round(statistics.mean(times), 3),
            "p50_ms": round(statistics.median(times), 3),
            "p95_ms": round(sorted(times)[int(len(times) * 0.95)], 3) if len(times) >= 20 else round(max(times), 3),
        }

    def test_outline_latency(self):
        stats = self._measure(lambda: tools.outline_file(self.BENCHMARK_FILE))
        assert stats["p95_ms"] < self.SLA_MS, f"outline p95={stats['p95_ms']}ms > {self.SLA_MS}ms SLA"

    def test_read_latency(self):
        stats = self._measure(lambda: tools.read_file(self.BENCHMARK_FILE))
        assert stats["p95_ms"] < self.SLA_MS

    def test_grep_latency(self):
        stats = self._measure(lambda: tools.grep_file(self.BENCHMARK_FILE, "function_5"))
        assert stats["p95_ms"] < self.SLA_MS

    def test_tree_latency(self):
        stats = self._measure(lambda: tools.tree_view(".", depth=2))
        assert stats["p95_ms"] < self.SLA_MS

    def test_exists_latency(self):
        import pathlib
        stats = self._measure(lambda: pathlib.Path(self.BENCHMARK_FILE).exists())
        assert stats["p95_ms"] < self.SLA_MS


class TestCachePerformance:
    def test_cache_hit_faster_than_miss(self):
        c = ResponseCache(ttl=60)
        # First: miss (slow — call fn)
        def slow():
            time.sleep(0.01)
            return "result"
        t0 = time.perf_counter_ns()
        c.get("perf_key")
        miss_ns = time.perf_counter_ns() - t0

        c.set(slow(), "perf_key")

        # Second: hit (fast — from cache)
        t0 = time.perf_counter_ns()
        c.get("perf_key")
        hit_ns = time.perf_counter_ns() - t0

        assert hit_ns < miss_ns, f"Cache hit should be faster. hit={hit_ns}ns miss={miss_ns}ns"


class TestQueuePerformance:
    def test_enqueue_dequeue_throughput(self):
        q = RequestQueue(max_size=1000)
        t0 = time.perf_counter_ns()
        for i in range(500):
            q.enqueue(QueuedTask(str(i), f"t{i}", "s", "", 100, ""))
        for _ in range(500):
            q.dequeue()
        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000
        assert elapsed_ms < 200, f"1000 ops in {elapsed_ms:.1f}ms > 200ms limit"


class TestSafeEvalPerformance:
    def test_batch_throughput(self):
        t0 = time.perf_counter_ns()
        for _ in range(500):
            tools._safe_eval("(1+2)*(3+4*5-6/2)^2")
        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000
        assert elapsed_ms < 200, f"500 eval ops in {elapsed_ms:.1f}ms — too slow"


class TestTokenCounterOverhead:
    def test_counter_is_fast(self):
        t0 = time.perf_counter_ns()
        for _ in range(10000):
            tools.count_saved(40)
        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000
        assert elapsed_ms < 20  # should be near-instant


class TestPerformanceRegressionScores:
    """Record baseline numbers for future regression detection."""
    def test_record_baselines(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        for i in range(100):
            f.write(f"def fn_{i}(x): return x * {i}\nclass Cls_{i}: pass\n")
        f.close()
        n = 10
        times = []
        for _ in range(n):
            t0 = time.perf_counter_ns()
            tools.outline_file(f.name)
            times.append(time.perf_counter_ns() - t0)

        avg_us = statistics.mean(times) / 1000
        # Baseline: should be well under 5ms for 200-symbol file
        assert avg_us < 5000, f"Outline too slow: {avg_us:.0f}us"

        # Read
        times = []
        for _ in range(n):
            t0 = time.perf_counter_ns()
            tools.read_file(f.name)
            times.append(time.perf_counter_ns() - t0)
        avg_us = statistics.mean(times) / 1000
        assert avg_us < 2000, f"Read too slow: {avg_us:.0f}us"
        os.unlink(f.name)
