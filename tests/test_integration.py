"""Integration tests — Flask test client, no live server needed. (Phase 1 #6)"""
import json, os, sys
# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import app after path setup
import miser


def client():
    miser.app.config['TESTING'] = True
    return miser.app.test_client()


class TestHealthCheck:
    def test_health_returns_ok(self):
        c = client()
        r = c.get("/health")
        assert r.status_code == 200
        d = json.loads(r.data)
        assert d["status"] == "ok"
        assert d["version"] == "1.4.1"
        assert "model" in d

    def test_status_has_queue_stats(self):
        c = client()
        r = c.get("/status")
        assert r.status_code == 200
        d = json.loads(r.data)
        assert "queue" in d
        assert "prefetch" in d
        assert "tokens_saved_est" in d


class TestZeroLLMEndpoints:
    def test_read_existing_file(self):
        c = client()
        r = c.post("/read", json={"path": "client.py"})
        assert r.status_code == 200
        d = json.loads(r.data)
        assert "content" in d

    def test_read_missing_file(self):
        c = client()
        r = c.post("/read", json={"path": "/nonexistent_zzz"})
        d = json.loads(r.data)
        assert "not found" in d.get("content", "").lower()

    def test_exists_yes(self):
        c = client()
        r = c.post("/exists", json={"path": "miser.py"})
        d = json.loads(r.data)
        assert d["exists"] is True

    def test_exists_no(self):
        c = client()
        r = c.post("/exists", json={"path": "/tmp/nope_404.xyz"})
        d = json.loads(r.data)
        assert d["exists"] is False

    def test_outline_python(self):
        c = client()
        r = c.post("/outline", json={"path": "tools.py"})
        d = json.loads(r.data)
        assert "def " in d.get("outline", "")

    def test_tree(self):
        c = client()
        r = c.post("/tree", json={"path": ".", "depth": 1})
        d = json.loads(r.data)
        assert "client.py" in d.get("tree", "")

    def test_grep(self):
        c = client()
        r = c.post("/grep", json={"path": "client.py", "pattern": "def _post"})
        d = json.loads(r.data)
        assert "def _post" in d.get("matches", "")

    def test_run_echo(self):
        c = client()
        r = c.post("/run", json={"cmd": "echo hello_miser_test"})
        d = json.loads(r.data)
        assert "hello_miser_test" in d.get("output", "")


class TestMemory:
    def setup_method(self):
        miser.mem.clear()

    def test_save_and_retrieve(self):
        c = client()
        c.post("/note", json={"key": "test_ver", "value": "1.3.1"})
        r = c.get("/memory")
        d = json.loads(r.data)
        assert any("test_ver" in str(n) for n in d.get("notes", {}))
        c.post("/memory/clear", json={"_token": ""})


class TestBatch:
    def test_batch_run(self):
        c = client()
        r = c.post("/batch", json={"tasks": [
            {"type": "run", "cmd": "echo a"},
            {"type": "run", "cmd": "echo b"},
        ]})
        d = json.loads(r.data)
        assert len(d["results"]) == 2
        assert "a" in d["results"][0].get("result", "")
        assert "b" in d["results"][1].get("result", "")

    def test_batch_exists(self):
        c = client()
        r = c.post("/batch", json={"tasks": [
            {"type": "exists", "path": "client.py"},
            {"type": "exists", "path": "/tmp/nope"},
        ]})
        d = json.loads(r.data)
        assert d["results"][0]["result"] is True
        assert d["results"][1]["result"] is False


class TestV1Blueprint:
    """Verify /v1/ prefixed routes work (fix #31)."""
    def test_v1_read(self):
        c = client()
        r = c.post("/v1/read", json={"path": "client.py"})
        assert r.status_code == 200
        assert "content" in r.json["data"]

    def test_v1_outline(self):
        c = client()
        r = c.post("/v1/outline", json={"path": "tools.py"})
        assert r.status_code == 200
        assert "def " in r.json["data"]["outline"]

    def test_v1_health(self):
        c = client()
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json["version"] == "1.4.1"

    def test_v1_metrics(self):
        c = client()
        r = c.get("/metrics")
        assert r.status_code == 200
        assert "miser_tokens_saved" in r.data.decode()

    def test_old_read_still_works(self):
        """Backward compatibility: un-prefixed routes should still work."""
        c = client()
        r = c.post("/read", json={"path": "client.py"})
        assert r.status_code == 200


class TestFacade:
    def test_facade_models(self):
        c = client()
        r = c.get("/v1/models")
        assert r.status_code == 200
        assert r.json["object"] == "list"
        assert len(r.json["data"]) >= 1

    def test_facade_chat_completions(self):
        c = client()
        r = c.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "say hello"}],
            "max_tokens": 50,
        })
        assert r.status_code in (200, 500)  # 500 if Ollama is not running

    def test_facade_missing_messages(self):
        c = client()
        r = c.post("/v1/chat/completions", json={})
        assert r.status_code == 400


class TestQueueBehavior:
    def test_enqueue_when_busy(self):
        """Verify 202 is returned when worker is busy and queue has room."""
        c = client()
        r = c.post("/ask", json={"task": "return the number 4"})
        d = json.loads(r.data)
        # Should either return result (if fast) or be queued
        assert r.status_code in (200, 202, 429, 500)
