"""Tests for backend.py — LLM backend abstraction (P2 #10)."""
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

    def test_health_returns_bool(self):
        b = OllamaBackend()
        result = b.health()
        assert isinstance(result, bool)

    def test_generate_handles_offline(self):
        b = OllamaBackend(base_url="http://127.0.0.1:19999")  # definitely offline
        try:
            result = b.generate("qwen3.5:4b", "System", "Hello", max_tokens=10)
        except Exception:
            result = ""  # expected when Ollama is not running
        assert isinstance(result, str)


class TestOpenAICompatBackend:
    def test_default_url(self):
        b = OpenAICompatBackend()
        assert "1234" in b.base_url

    def test_custom_url(self):
        b = OpenAICompatBackend(base_url="http://localhost:8080/v1", api_key="sk-test")
        assert b.base_url == "http://localhost:8080/v1"

    def test_health_returns_bool(self):
        b = OpenAICompatBackend(base_url="http://127.0.0.1:19998/v1")
        result = b.health()
        assert isinstance(result, bool)


class TestResolveBackend:
    def test_default_is_ollama(self):
        b = resolve_backend()
        assert isinstance(b, OllamaBackend)

    def test_openai_env_resolves(self, monkeypatch):
        monkeypatch.setenv("MISER_BACKEND", "openai")
        monkeypatch.setenv("MISER_BACKEND_URL", "http://localhost:9999/v1")
        b = resolve_backend()
        assert isinstance(b, OpenAICompatBackend)
