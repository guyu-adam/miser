"""
model_adapter.py — Multi-model prompt formatting for Miser.

Detects model family from the model name and returns the correct
raw prompt format + response post-processor for each family.

Supported families (2026 updated):
  qwen3 / qwen3.5 / qwen3.6 / qwen3-coder — chatml + <think> for 3.x
  qwen2.5 / qwen2 / qwen2.5-coder — standard chatml
  llama4           — ChatML (same as llama3)
  llama3 / llama3.1 / llama3.2 / llama3.3 — ChatML
  llama2           — [INST]...[/INST] format
  mistral / mixtral / mistral-small / mistral3 — [INST]...[/INST]
  phi3 / phi4      — <|user|>...<|assistant|> format
  gemma / gemma3   — <start_of_turn> format
  deepseek / deepseek-coder / deepseek-v3 — ChatML
  deepseek-r1 / deepseek-r2 — ChatML + thinking
  default          — chat API, no raw format
"""

import re
import requests as _req
from typing import Callable

# ──────────────────────────────────────────────────────────────────────────────
#  Family detection
# ──────────────────────────────────────────────────────────────────────────────

def _ollama_family(model_name: str) -> str:
    """Ask Ollama for the actual model family (works for aliases like miser-qwen)."""
    try:
        r = _req.post("http://localhost:11434/api/show",
                      json={"name": model_name}, timeout=5)
        det = r.json().get("details", {})
        fam = (det.get("family") or "").lower()
        if fam:
            if "qwen35" in fam or "qwen3.5" in fam:
                return "qwen3"
            if "qwen3" in fam:
                return "qwen3"
            if "qwen2" in fam:
                return "qwen2"
            if "llama3" in fam or "llama-3" in fam:
                return "llama3"
            if "llama" in fam:
                return "llama2"
            if "mistral" in fam or "mixtral" in fam:
                return "mistral"
            if "phi" in fam:
                return "phi3"
            if "gemma" in fam:
                return "gemma"
            if "deepseek" in fam:
                return "deepseek-r1" if "r1" in fam else "deepseek"
    except Exception:
        pass
    return ""


def detect_family(model_name: str) -> str:
    # First try name-based detection (fast, no network)
    n = model_name.lower()
    # Qwen family (2024-2026: 2.5, 3, 3.5, 3.6, coder variants)
    if re.search(r'qwen3\.6|qwen3-6', n):
        return "qwen3"
    if re.search(r'qwen3\.5|qwen3-5', n):
        return "qwen3"
    if re.search(r'qwen3-coder|qwen3coder|qwen.*coder', n):
        return "qwen3"
    if re.search(r'qwen3|qwen-3', n):
        return "qwen3"
    if re.search(r'qwen2\.5|qwen2-5|qwen2', n):
        return "qwen2"
    # Llama family (2024-2026: 3.1, 3.2, 3.3, 4)
    if re.search(r'llama-?4|llama4', n):
        return "llama4"
    if re.search(r'llama-?3\.[23]|llama3\.[23]', n):
        return "llama3"
    if re.search(r'llama-?3|llama3', n):
        return "llama3"
    if re.search(r'llama-?2|llama2', n):
        return "llama2"
    # Mistral family (2024-2026: v0.3, Small, Large, 3)
    if re.search(r'mistral.*(?:3\b|small|large)', n):
        return "mistral"
    if re.search(r'mistral|mixtral', n):
        return "mistral"
    # Phi family (2024-2026: 3, 3.5, 4, 4-mini)
    if re.search(r'phi-?4|phi4', n):
        return "phi4"
    if re.search(r'phi-?3|phi3', n):
        return "phi3"
    # Gemma family (2024-2026: 2, 3, 4)
    if re.search(r'gemma-?4|gemma4', n):
        return "gemma4"       # v2026: uses built-in chat template via /api/chat
    if re.search(r'gemma-?3|gemma3', n):
        return "gemma"
    if re.search(r'gemma-?2|gemma2', n):
        return "gemma"
    if re.search(r'gemma', n):
        return "gemma"
    # DeepSeek family (2025-2026: V3, R1, R2, Coder V2)
    if re.search(r'deepseek-r2|deepseek_r2|deepseek-r1|deepseek_r1', n):
        return "deepseek-r1"
    if re.search(r'deepseek.*v3|deepseek.*v2', n):
        return "deepseek"
    if re.search(r'deepseek.*coder', n):
        return "deepseek"
    if re.search(r'deepseek', n):
        return "deepseek"
    # CodeLlama
    if re.search(r'codellama', n):
        return "llama3"
    # Cohere Command R (2024-2025)
    if re.search(r'command.?r', n):
        return "default"  # chat API compatible, uses default path
    # Yi family (2024-2025)
    if re.search(r'yi-?2|yi2', n):
        return "default"
    if re.search(r'yi', n):
        return "default"
    # Nomic embed (used for embeddings only, skip prompt detection)
    if re.search(r'nomic', n):
        return "default"
    # Name didn't match — ask Ollama (handles aliases like miser-qwen)
    ollama_fam = _ollama_family(model_name)
    return ollama_fam if ollama_fam else "default"


def has_thinking(family: str) -> bool:
    """True if this model family does chain-of-thought in a <think> block."""
    return family in ("qwen3", "deepseek-r1", "deepseek-r2")


def use_raw_generate(family: str) -> bool:
    """True if we must use /api/generate (raw prompt) rather than /api/chat."""
    return family in ("qwen3", "qwen2", "llama4", "llama3", "llama2", "mistral",
                       "phi3", "phi4", "gemma", "deepseek-r1", "deepseek")


# ──────────────────────────────────────────────────────────────────────────────
#  Prompt builders  (return raw prompt string for /api/generate)
# ──────────────────────────────────────────────────────────────────────────────

def build_prompt(family: str, system: str, user: str) -> str:
    """Build a raw prompt string appropriate for the model family."""

    if family in ("qwen3", "qwen2"):
        # ChatML format; qwen3 gets injected empty <think> to suppress verbose thinking
        think_block = "<think>\n\n</think>\n\n" if family == "qwen3" else ""
        return (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n{think_block}"
        )

    if family == "llama4":
        # Llama 4 uses same ChatML format as Llama 3
        return (
            f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n"
            f"{system}<|eot_id|>"
            f"<|start_header_id|>user<|end_header_id|>\n"
            f"{user}<|eot_id|>"
            f"<|start_header_id|>assistant<|end_header_id|>\n"
        )

    if family == "llama3":
        return (
            f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n"
            f"{system}<|eot_id|>"
            f"<|start_header_id|>user<|end_header_id|>\n"
            f"{user}<|eot_id|>"
            f"<|start_header_id|>assistant<|end_header_id|>\n"
        )

    if family == "llama2":
        sys_block = f"<<SYS>>\n{system}\n<</SYS>>\n\n" if system else ""
        return f"[INST] {sys_block}{user} [/INST]"

    if family == "mistral":
        # Mistral v3 uses chatml; older uses [INST]
        sys_block = f"[SYSTEM_PROMPT]{system}[/SYSTEM_PROMPT]\n" if system else ""
        return f"{sys_block}[INST] {user} [/INST]"

    if family in ("phi3", "phi4"):
        return (
            f"<|system|>\n{system}<|end|>\n"
            f"<|user|>\n{user}<|end|>\n"
            f"<|assistant|>\n"
        )

    if family == "gemma":
        sys_part = f"<start_of_turn>system\n{system}<end_of_turn>\n" if system else ""
        return (
            f"<bos>{sys_part}"
            f"<start_of_turn>user\n{user}<end_of_turn>\n"
            f"<start_of_turn>model\n"
        )

    if family in ("deepseek-r1", "deepseek"):
        return (
            f"<|begin▁of▁sentence|>{system}\n"
            f"<|User|>{user}\n"
            f"<|Assistant|>"
        )

    # default / unknown: just system + user in plaintext, let Ollama handle it
    return f"{system}\n\nUser: {user}\nAssistant:"


# ──────────────────────────────────────────────────────────────────────────────
#  Response post-processor
# ──────────────────────────────────────────────────────────────────────────────

def clean_response(raw: str, family: str, mode: str = "text") -> str:
    """Strip thinking tokens and clean up the raw model response."""
    if not raw:
        return ""

    # Remove thinking blocks (qwen3, deepseek-r1)
    if has_thinking(family):
        # Strip <think>...</think> blocks
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
        # If thinking leaked without closing tag, take everything after </think>
        if '</think>' in raw:
            raw = raw.split('</think>', 1)[-1].strip()

    # Strip code fences
    raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw.strip())
    raw = re.sub(r'\n?```$', '', raw).strip()

    # Strip EOS tokens
    for tok in ['<|im_end|>', '<|end|>', '<|eot_id|>', '<end_of_turn>',
                '<|endoftext|>', '</s>', '[/INST]', '<|Assistant|>']:
        raw = raw.replace(tok, '').strip()

    if mode == "code":
        m = re.search(r'^(def |class )[a-zA-Z_]', raw, re.MULTILINE)
        if m:
            block = raw[m.start():]
            lines = block.splitlines()
            result = [lines[0]]
            for ln in lines[1:]:
                if ln and not ln.startswith((' ', '\t')) and not ln.startswith(('def ', 'class ')):
                    break
                result.append(ln)
            return "\n".join(result).strip()

    if mode == "bullets":
        bullets = re.findall(r'^[ \t]*[-•*\d\.]\s+.+', raw, re.MULTILINE)
        if len(bullets) >= 2:
            seen, deduped = set(), []
            for b in bullets:
                key = b.strip().lower()[:60]
                if key not in seen:
                    seen.add(key)
                    deduped.append(b.strip())
            return "\n".join(deduped[:8])

    # Long response: find the last clean block (avoid leaked meta-commentary)
    if len(raw) > 600:
        paras = [p.strip() for p in re.split(r'\n{2,}', raw) if p.strip()]
        meta = re.compile(r'^(we|let\'s|the problem|note:|however|but|so|now|wait|actually)', re.I)
        clean = [p for p in paras if not meta.match(p)]
        if clean:
            return clean[-1]
        return paras[-1] if paras else raw[-400:]

    return raw


# ──────────────────────────────────────────────────────────────────────────────
#  Unified LLM call spec
# ──────────────────────────────────────────────────────────────────────────────

class ModelAdapter:
    """
    Encapsulates model-family-specific behaviour.
    Usage:
        adapter = ModelAdapter("qwen3.5:4b")
        payload = adapter.generate_payload(system, user, max_tokens=600)
        raw = requests.post(adapter.url, json=payload).json().get("response","")
        answer = adapter.clean(raw, mode="code")
    """

    GENERATE_URL = "http://localhost:11434/api/generate"
    CHAT_URL     = "http://localhost:11434/api/chat"

    def __init__(self, model_name: str):
        self.model  = model_name
        self.family = detect_family(model_name)
        self._raw   = use_raw_generate(self.family)
        self._think = has_thinking(self.family)

    @property
    def url(self) -> str:
        return self.GENERATE_URL if self._raw else self.CHAT_URL

    def generate_payload(self, system: str, user: str, max_tokens: int = 600,
                         temperature: float = 0.2) -> dict:
        think_budget = 2400 if self._think else 0
        opts = {"num_predict": max_tokens + think_budget, "temperature": temperature}

        if self._raw:
            return {
                "model":    self.model,
                "prompt":   build_prompt(self.family, system, user),
                "options":  opts,
                "stream":   False,
                "raw":      True,
                "keep_alive": -1,
            }
        else:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": user})
            return {
                "model":      self.model,
                "messages":   messages,
                "options":    opts,
                "stream":     False,
                "keep_alive": -1,
            }

    def extract_text(self, response_json: dict) -> str:
        """Pull text out of the Ollama API response dict."""
        if self._raw:
            return response_json.get("response", "").strip()
        msg = response_json.get("message", {})
        return (msg.get("content") or msg.get("thinking") or "").strip()

    def clean(self, raw: str, mode: str = "text") -> str:
        return clean_response(raw, self.family, mode)

    def info(self) -> dict:
        return {"model": self.model, "family": self.family,
                "thinking": self._think, "raw_api": self._raw}


# ──────────────────────────────────────────────────────────────────────────────
#  Model suggestions  (for README / help output)
# ──────────────────────────────────────────────────────────────────────────────

RECOMMENDED_MODELS = {
    # Speed-optimized (<2s responses)
    "4b_speed_qwen35":     "qwen3.5:4b",         # Default, 3.4GB, best all-around
    "4b_speed_qwen3":      "qwen3:4b",            # Lighter, 2.5GB
    "4b_speed_llama4":     "llama4:latest",       # Latest Llama 4 Scout

    # Quality-optimized (3-10s, smarter)
    "8b_quality_qwen35":   "qwen3.5:latest",      # Qwen 3.5 8B coding focus
    "8b_quality_llama4":   "llama3.1:8b",         # Llama 3.1 8B, battle-tested
    "7b_quality_mistral":  "mistral:7b",           # Mistral 7B, strong reasoning
    "7b_quality_mistral3": "mistral-small:latest", # Mistral Small 3 (2026)

    # Code-optimized
    "code_qwen3_coder":    "qwen3-coder:latest",   # Qwen 3 Coder (2026)
    "code_deepseek_v3":    "deepseek-coder:6.7b",  # DeepSeek Coder V2
    "code_qwen25_coder":   "qwen2.5-coder:7b",     # Qwen 2.5 Coder

    # Platform-optimized
    "phi4_windows":        "phi4:latest",           # Phi-4, fast on Windows
    "gemma3_google":       "gemma3:4b",             # Gemma 3, good for summaries

    # Thinking/CoT models
    "think_deepseek_r1":   "deepseek-r1:7b",        # DeepSeek R1, chain-of-thought
    "think_deepseek_r2":   "deepseek-r2:7b",        # DeepSeek R2 (2026)
    "think_qwen3":         "qwen3:8b",              # Qwen 3 with think block
}
