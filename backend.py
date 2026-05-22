"""
backend.py — LLM backend abstraction for Miser v1.5 (P2 #10).

Supports:
  - Ollama (default, localhost:11434)
  - OpenAI-compatible APIs (LM Studio, llama.cpp server, vLLM, TGI, etc.)

Configure via: MISER_BACKEND=openai MISER_BACKEND_URL=http://host:port/v1
"""

import os, json, requests as req
from typing import Protocol


class LLMBackend(Protocol):
    """Abstract LLM backend interface."""

    def generate(self, model: str, system: str, user: str,
                 max_tokens: int = 600, temperature: float = 0.2,
                 stream: bool = False) -> str:
        ...

    def health(self) -> bool:
        ...

    @property
    def base_url(self) -> str:
        ...


class OllamaBackend:
    """Ollama API backend (default)."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self._base_url = base_url.rstrip("/")

    @property
    def base_url(self) -> str:
        return self._base_url

    def generate(self, model: str, system: str, user: str,
                 max_tokens: int = 600, temperature: float = 0.2,
                 stream: bool = False) -> str:
        from model_adapter import ModelAdapter
        adapter = ModelAdapter(model)
        payload = adapter.generate_payload(system, user, max_tokens, temperature)
        resp = req.post(adapter.url, json=payload, timeout=240)
        raw = adapter.extract_text(resp.json())
        return adapter.clean(raw, mode="text")

    def health(self) -> bool:
        try:
            r = req.get(f"{self._base_url}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False


class OpenAICompatBackend:
    """OpenAI-compatible API backend (LM Studio, llama.cpp, vLLM, TGI, etc.)."""

    def __init__(self, base_url: str = "http://localhost:1234/v1",
                 api_key: str = "local"):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    @property
    def base_url(self) -> str:
        return self._base_url

    def generate(self, model: str, system: str, user: str,
                 max_tokens: int = 600, temperature: float = 0.2,
                 stream: bool = False) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        resp = req.post(f"{self._base_url}/chat/completions",
                        json=payload, headers=headers, timeout=240)
        data = resp.json()
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
        return ""

    def health(self) -> bool:
        try:
            r = req.get(f"{self._base_url}/models", timeout=5,
                        headers={"Authorization": f"Bearer {self._api_key}"})
            return r.status_code == 200
        except Exception:
            return False


def resolve_backend() -> LLMBackend:
    """Resolve backend from environment."""
    backend_type = os.environ.get("MISER_BACKEND", "ollama").lower()

    if backend_type == "openai":
        url = os.environ.get("MISER_BACKEND_URL", "http://localhost:1234/v1")
        key = os.environ.get("MISER_BACKEND_KEY", "local")
        return OpenAICompatBackend(base_url=url, api_key=key)

    # Default: Ollama
    url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    return OllamaBackend(base_url=url)
