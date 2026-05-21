"""
queue.py — Request queue for Miser v1.3.

Replaces the naive "return 429 when busy" with a bounded FIFO queue.
Prevents request loss under concurrent load (review: commercialization P0).
"""

import threading, time, uuid
from collections import deque
from dataclasses import dataclass, field


@dataclass
class QueuedTask:
    task_id: str
    task: str
    sender: str
    system: str
    max_tokens: int
    explicit_type: str
    enqueued_at: float = field(default_factory=time.time)


class RequestQueue:
    """
    Bounded FIFO queue for pending LLM tasks.
    When the worker is busy, new tasks are queued instead of rejected.

    Non-LLM (Zero-LLM) tasks skip the queue — they complete in <50ms.
    """

    def __init__(self, max_size: int = 10, timeout: float = 60.0):
        self._queue: deque[QueuedTask] = deque()
        self._lock = threading.Lock()
        self._max_size = max_size
        self._timeout = timeout   # seconds before a queued task expires
        self._total_queued = 0
        self._total_expired = 0

    def enqueue(self, task: QueuedTask) -> bool:
        """Add task to queue. Returns False if queue is full."""
        with self._lock:
            if len(self._queue) >= self._max_size:
                return False
            self._queue.append(task)
            self._total_queued += 1
            return True

    def dequeue(self) -> QueuedTask | None:
        """Pop the next task from the queue, skipping expired ones."""
        with self._lock:
            while self._queue:
                task = self._queue.popleft()
                if time.time() - task.enqueued_at < self._timeout:
                    return task
                self._total_expired += 1
            return None

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "queue_size": len(self._queue),
                "max_size": self._max_size,
                "total_queued": self._total_queued,
                "total_expired": self._total_expired,
                "timeout_s": self._timeout,
            }


# Global singleton
_task_queue = RequestQueue(max_size=10, timeout=60.0)

def get_queue() -> RequestQueue:
    return _task_queue
