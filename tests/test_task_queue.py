import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from task_queue import RequestQueue, QueuedTask
import time, threading


class TestQueuedTask:
    def test_task_creation(self):
        t = QueuedTask(task_id="abc", task="hello", sender="claude",
                       system="", max_tokens=600, explicit_type="ask")
        assert t.task_id == "abc"
        assert t.task == "hello"
        assert t.sender == "claude"
        assert t.max_tokens == 600

    def test_enqueued_at_is_set(self):
        t = QueuedTask(task_id="x", task="y", sender="z", system="",
                       max_tokens=100, explicit_type="")
        now = time.time()
        assert abs(t.enqueued_at - now) < 2.0


class TestRequestQueueBasic:
    def test_empty_queue(self):
        q = RequestQueue(max_size=10)
        assert q.size == 0
        assert q.dequeue() is None

    def test_enqueue_single(self):
        q = RequestQueue(max_size=10)
        t = QueuedTask("1", "task", "s", "", 100, "")
        assert q.enqueue(t)
        assert q.size == 1

    def test_dequeue_returns_task(self):
        q = RequestQueue(max_size=10)
        t = QueuedTask("1", "task", "s", "", 100, "")
        q.enqueue(t)
        result = q.dequeue()
        assert result.task_id == "1"
        assert result.task == "task"

    def test_dequeue_fifo_order(self):
        q = RequestQueue(max_size=10)
        t1 = QueuedTask("1", "first", "s", "", 100, "")
        t2 = QueuedTask("2", "second", "s", "", 100, "")
        q.enqueue(t1)
        q.enqueue(t2)
        assert q.dequeue().task == "first"
        assert q.dequeue().task == "second"


class TestRequestQueueBounds:
    def test_max_size_enforced(self):
        q = RequestQueue(max_size=3)
        for i in range(3):
            assert q.enqueue(QueuedTask(str(i), f"t{i}", "s", "", 100, ""))
        assert not q.enqueue(QueuedTask("4", "t4", "s", "", 100, ""))
        assert q.size == 3

    def test_expired_tasks_skipped(self):
        q = RequestQueue(max_size=10, timeout=0.001)
        q.enqueue(QueuedTask("1", "t1", "s", "", 100, ""))
        time.sleep(0.01)
        # Should skip the expired task
        assert q.dequeue() is None

    def test_valid_task_not_skipped(self):
        q = RequestQueue(max_size=10, timeout=60)
        q.enqueue(QueuedTask("1", "t1", "s", "", 100, ""))
        assert q.dequeue() is not None


class TestRequestQueueStats:
    def test_total_queued(self):
        q = RequestQueue(max_size=10)
        for i in range(5):
            q.enqueue(QueuedTask(str(i), f"t{i}", "s", "", 100, ""))
        assert q.stats["total_queued"] == 5

    def test_total_expired(self):
        q = RequestQueue(max_size=10, timeout=0.001)
        q.enqueue(QueuedTask("1", "t1", "s", "", 100, ""))
        time.sleep(0.01)
        q.dequeue()
        assert q.stats["total_expired"] == 1

    def test_stats_keys(self):
        q = RequestQueue()
        s = q.stats
        assert "queue_size" in s
        assert "max_size" in s
        assert "total_queued" in s
        assert "total_expired" in s
        assert "timeout_s" in s


class TestRequestQueueConcurrent:
    def test_concurrent_enqueue(self):
        q = RequestQueue(max_size=100)
        def enq(i):
            q.enqueue(QueuedTask(str(i), f"t{i}", "s", "", 100, ""))
        threads = [threading.Thread(target=enq, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert q.size == 50

    def test_concurrent_enqueue_dequeue(self):
        q = RequestQueue(max_size=100)
        for i in range(30):
            q.enqueue(QueuedTask(str(i), f"t{i}", "s", "", 100, ""))
        results = []
        def drain():
            while True:
                t = q.dequeue()
                if t is None:
                    break
                results.append(t.task_id)
        threads = [threading.Thread(target=drain) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 30
