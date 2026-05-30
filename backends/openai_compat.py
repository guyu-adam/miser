"""
backends/openai_compat.py - OpenAI-compatible API backend.
Probes common ports: 1234 (LM Studio), 8080 (llama.cpp), 8000 (vLLM), 8081 (LocalAI).

Also works as a generic catch-all for any /v1/chat/completions endpoint.
"""

import os, requests as req


# Common ports for local LLM tools
_DEFAULT_PORTS = [1234, 8080, 8000, 8081, 4891, 5000]
_PROBE_TIMEOUT = 3


class OpenAICompatBackend:
    """OpenAI-compatible API backend."""

    name = "OpenAI-compatible"

    def __init__(self, base_url: str = None, api_key: str = None):
        url = base_url or os.environ.get("MISER_BACKEND_URL", "")
        if not url:
            url = self._probe_ports()
        self._base_url = url.rstrip("/") if url else ""
        self._api_key = api_key or os.environ.get("MISER_BACKEND_KEY", "local")

    @property
    def base_url(self) -> str:
        return self._base_url

    def _probe_ports(self) -> str:
        """Scan common LLM ports for an OpenAI-compatible /v1 endpoint."""
        for port in _DEFAULT_PORTS:
            url = f"http://localhost:{port}/v1"
            try:
                r = req.get(f"{url}/models", timeout=_PROBE_TIMEOUT,
                            headers={"Authorization": f"Bearer local"})
                if r.status_code == 200:
                    return url
            except Exception:
                # Also try without /v1 prefix (some servers)
                try:
                    r = req.get(f"http://localhost:{port}/models", timeout=_PROBE_TIMEOUT)
                    if r.status_code == 200:
                        return f"http://localhost:{port}"
                except Exception:
                    continue
        return ""

    def detect(self) -> bool:
        """Return True if any OpenAI-compatible endpoint is reachable."""
        if not self._base_url:
            # Try port scan
            self._base_url = self._probe_ports()
        return bool(self._base_url) and self.health()

    def list_models(self) -> list[str]:
        if not self._base_url:
            return []
        try:
            r = req.get(f"{self._base_url}/models", timeout=5,
                        headers={"Authorization": f"Bearer {self._api_key}"})
            if r.status_code == 200:
                data = r.json()
                models = data.get("data", data.get("models", []))
                return [m.get("id", m.get("name", str(m))) for m in models]
        except Exception:
            pass
        return []

    def generate(self, model: str, system: str, user: str,
                 max_tokens: int = 600, temperature: float = 0.2) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
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
        if not self._base_url:
            return False
        try:
            r = req.get(f"{self._base_url}/models", timeout=_PROBE_TIMEOUT,
                        headers={"Authorization": f"Bearer {self._api_key}"})
            return r.status_code == 200
        except Exception:
            return False
