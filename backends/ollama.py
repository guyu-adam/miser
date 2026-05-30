"""
backends/ollama.py - Ollama backend (localhost:11434 or OLLAMA_HOST).
"""

import os, requests as req
from backends.openai_compat import OpenAICompatBackend


class OllamaBackend:
    """Ollama API backend - auto-detects via /api/tags."""

    name = "Ollama"

    def __init__(self, base_url: str = None):
        raw = (base_url or
               os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        # OLLAMA_HOST is a server bind address.
        # "0.0.0.0" cannot be reached — convert to localhost.
        # Bare IPs without scheme/port need full URL construction.
        if raw in ("0.0.0.0", "127.0.0.1", "localhost"):
            raw = "http://localhost:11434"
        elif raw.startswith("0.0.0.0"):
            raw = raw.replace("0.0.0.0", "127.0.0.1", 1)
        elif not raw.startswith("http"):
            raw = f"http://{raw}"
        self._base_url = raw
        self._adapters: dict = {}  # cache ModelAdapter per model

    @property
    def base_url(self) -> str:
        return self._base_url

    def detect(self) -> bool:
        """Return True if Ollama is reachable."""
        return self.health()

    def list_models(self) -> list[str]:
        try:
            r = req.get(f"{self._base_url}/api/tags", timeout=5)
            if r.status_code == 200:
                models = r.json().get("models", [])
                return [m["name"] for m in models if "name" in m]
        except Exception:
            pass
        return []

    def generate(self, model: str, system: str, user: str,
                 max_tokens: int = 600, temperature: float = 0.2) -> str:
        # Reuse cached adapter — ModelAdapter.__init__ hits /api/show
        if model not in self._adapters:
            from model_adapter import ModelAdapter
            self._adapters[model] = ModelAdapter(model)
        adapter = self._adapters[model]
        payload = adapter.generate_payload(system, user, max_tokens, temperature)
        resp = req.post(adapter.url, json=payload, timeout=240)
        raw = adapter.extract_text(resp.json())
        return adapter.clean(raw, mode="text")

    def health(self) -> bool:
        try:
            r = req.get(f"{self._base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False
