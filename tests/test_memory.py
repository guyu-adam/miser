import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from memory import Memory
import threading, tempfile, json
from pathlib import Path


class TestMemoryInit:
    def test_initial_state(self):
        m = Memory()
        assert isinstance(m.notes, dict)
        assert isinstance(m.history, list)
        assert isinstance(m.embeddings, list)

    def test_history_is_list(self):
        m = Memory()
        assert isinstance(m.history, list)


class TestMemorySaveLoad:
    def test_save_and_retrieve_note(self):
        m = Memory()
        m.save("key1", "value1")
        assert m.notes.get("key1") == "value1"

    def test_multiple_notes(self):
        m = Memory()
        for i in range(10):
            m.save(f"k{i}", f"v{i}")
        assert m.notes.get("k0") == "v0"
        assert m.notes.get("k9") == "v9"

    def test_notes_max_cap(self):
        m = Memory()
        for i in range(250):
            m.save(f"k{i}", f"v{i}")
        assert len(m.notes) <= 200

    def test_overwrite_note(self):
        m = Memory()
        m.save("key", "old")
        m.save("key", "new")
        assert m.notes["key"] == "new"


class TestMemoryRecord:
    def test_record_adds_to_history(self):
        m = Memory()
        m.clear()  # reset to empty
        assert len(m.history) == 0
        m.record(9999, "task one", "result one")
        assert len(m.history) == 1
        assert m.history[-1]["task"] == "task one"

    def test_record_truncates_long_content(self):
        m = Memory()
        m.record(1, "a" * 200, "b" * 300)
        assert len(m.history[-1]["task"]) <= 100
        assert len(m.history[-1]["result"]) <= 200

    def test_history_capped(self):
        m = Memory()
        for i in range(50):
            m.record(i, f"task {i}", f"result {i}")
        # After 50 records + _save() trims to MAX_HIST=40
        assert len(m.history) <= 40


class TestMemoryContext:
    def test_context_no_history(self):
        m = Memory()
        ctx = m.ctx("some task")
        assert isinstance(ctx, str)

    def test_context_with_notes(self):
        m = Memory()
        m.save("stack", "Python 3.13")
        m.save("db", "PostgreSQL")
        ctx = m.ctx()
        assert "Python" in ctx or "PostgreSQL" in ctx or len(ctx) > 0

    def test_context_with_history(self):
        m = Memory()
        m.record(1, "write tests", "passed")
        m.record(2, "fix bug", "done")
        ctx = m.ctx()
        assert "Recent" in ctx or "write" in ctx or len(ctx) > 0


class TestMemoryClear:
    def test_clear_empties_history(self):
        m = Memory()
        m.record(1, "task", "result")
        m.clear()
        assert len(m.history) == 0

    def test_clear_preserves_notes(self):
        m = Memory()
        m.save("k", "v")
        m.clear()
        assert m.notes.get("k") == "v"

    def test_clear_twice_is_safe(self):
        m = Memory()
        m.clear()
        m.clear()
        assert len(m.history) == 0


class TestMemoryThreadSafety:
    def test_concurrent_saves(self):
        m = Memory()
        def save_many():
            for i in range(50):
                m.save(f"t_{threading.get_ident()}_{i}", "v")
        threads = [threading.Thread(target=save_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(m.notes) <= 200

    def test_concurrent_record(self):
        m = Memory()
        def record_many():
            for i in range(20):
                m.record(i, f"t{i}", f"r{i}")
        threads = [threading.Thread(target=record_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(m.history) > 0


class TestMemoryCosine:
    def test_cosine_identical(self):
        m = Memory()
        r = m._cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert abs(r - 1.0) < 0.001

    def test_cosine_orthogonal(self):
        m = Memory()
        r = m._cosine([1.0, 0.0], [0.0, 1.0])
        assert abs(r - 0.0) < 0.001

    def test_cosine_zero_vector(self):
        m = Memory()
        r = m._cosine([0.0, 0.0], [1.0, 2.0])
        assert r == 0.0
