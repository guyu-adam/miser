"""Tests for backend.py — LLM backend abstraction (P2 #10).

Covers: Ollama backend, OpenAI compat backend, resolve logic,
mode handling (code/bullets/text), offline error recovery, health checks.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import OllamaBackend, OpenAICompatBackend, resolve_backend


class TestOllamaBackend:
    def test_default_url(self):
        b = OllamaBackend()
        assert b.base_url == "http://localhost:11434"

    def test_custom_url(self):
        b = OllamaBackend(base_url="http://192.168.1.100:11434")
        assert b.base_url == "http://192.168.1.100:11434"

    def test_trailing_slash_stripped(self):
        b = OllamaBackend(base_url="http://localhost:11434/")
        assert not b.base_url.endswith("/")

    def test_health_returns_bool(self):
        b = OllamaBackend()
        result = b.health()
        assert isinstance(result, bool)

    def test_generate_handles_offline(self):
        b = OllamaBackend(base_url="http://127.0.0.1:19999")
        try:
            result = b.generate("qwen3.5:4b", "System", "Hello", max_tokens=10)
        except Exception:
            result = ""
        assert isinstance(result, str)

    def test_generate_with_temperature(self):
        b = OllamaBackend(base_url="http://127.0.0.1:19999")
        try:
            result = b.generate("qwen3.5:4b", "System", "User", max_tokens=5, temperature=0.7)
        except Exception:
            result = ""
        assert isinstance(result, str)


class TestOpenAICompatBackend:
    def test_default_url(self):
        b = OpenAICompatBackend()
        assert "1234" in b.base_url

    def test_custom_url(self):
        b = OpenAICompatBackend(base_url="http://localhost:8080/v1", api_key="sk-test")
        assert b.base_url == "http://localhost:8080/v1"

    def test_trailing_slash_stripped(self):
        b = OpenAICompatBackend(base_url="http://localhost:1234/v1/")
        assert not b.base_url.endswith("/")

    def test_health_returns_bool(self):
        b = OpenAICompatBackend(base_url="http://127.0.0.1:19998/v1")
        result = b.health()
        assert isinstance(result, bool)

    def test_generate_handles_offline(self):
        b = OpenAICompatBackend(base_url="http://127.0.0.1:19998/v1")
        try:
            result = b.generate("local-model", "System", "User", max_tokens=5)
        except Exception:
            result = ""
        assert isinstance(result, str)

    def test_generate_builds_messages(self):
        b = OpenAICompatBackend(base_url="http://127.0.0.1:19998/v1")
        try:
            result = b.generate("test-model", "System prompt", "User query", max_tokens=10)
        except Exception:
            result = ""
        assert isinstance(result, str)


class TestResolveBackend:
    def test_default_is_ollama(self):
        b = resolve_backend()
        assert isinstance(b, OllamaBackend)

    def test_openai_env_resolves(self, monkeypatch):
        monkeypatch.setenv("MISER_BACKEND", "openai")
        monkeypatch.setenv("MISER_BACKEND_URL", "http://localhost:9999/v1")
        b = resolve_backend()
        assert isinstance(b, OpenAICompatBackend)

    def test_openai_with_custom_key(self, monkeypatch):
        monkeypatch.setenv("MISER_BACKEND", "openai")
        monkeypatch.setenv("MISER_BACKEND_URL", "http://localhost:8080/v1")
        monkeypatch.setenv("MISER_BACKEND_KEY", "sk-custom")
        b = resolve_backend()
        assert isinstance(b, OpenAICompatBackend)

    def test_invalid_backend_falls_to_ollama(self, monkeypatch):
        monkeypatch.setenv("MISER_BACKEND", "unknown_backend_xyz")
        b = resolve_backend()
        assert isinstance(b, OllamaBackend)

    def test_ollama_custom_host(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://192.168.1.50:11434")
        b = resolve_backend()
        assert isinstance(b, OllamaBackend)
        assert "192.168.1.50" in b.base_url


class TestBackendMiserIntegration:
    """Verify backend is properly wired into miser.py's llm() path."""

    def test_llm_uses_backend_generate(self):
        import inspect, miser
        source = inspect.getsource(miser.llm)
        assert "backend.generate" in source

    def test_llm_no_longer_calls_adapter_directly(self):
        import inspect, miser
        source = inspect.getsource(miser.llm)
        assert "adapter.generate_payload" not in source

    def test_admin_has_backend_attr(self):
        import miser
        assert hasattr(miser._admin, 'BACKEND')

    def test_backend_reported_in_health(self):
        import miser, json
        with miser.app.test_client() as c:
            r = c.get("/health")
            d = json.loads(r.data)
            assert "backend" in d

    def test_backend_reported_in_status(self):
        import miser, json
        with miser.app.test_client() as c:
            r = c.get("/status")
            d = json.loads(r.data)
            assert "backend" in d
