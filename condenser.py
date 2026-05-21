"""
condenser.py — Semantic context distillation for Miser.

Unlike prompt compression (which shortens characters), Context Condenser
uses the local LLM to SEMANTICALLY distill large contexts into structured
summaries that preserve key facts while reducing token count by 70-90%.

What it does:
  - Takes a large code file, error log, or document
  - Local LLM extracts: signatures, dependencies, invariants, edge cases
  - Returns a structured digest that Claude can reason about efficiently
  - Claude still does the thinking — it just gets a cleaner input

This is NOT prompt compression (caveman). It's semantic distillation:
fewer tokens, but MORE information density per token.
"""

import re, threading, time
from pathlib import Path
import requests as req

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3.5:4b"

# ── Distillation templates ────────────────────────────────────────────────────

# Each template tells the local LLM WHAT to extract and HOW to format it.
# Claude gets a clean structured digest, not a wall of code.

TEMPLATES = {
    "code_file": (
        "Extract the STRUCTURAL SUMMARY of this source file. Output ONLY:\n"
        "1. Public API: one line per function/class with signature\n"
        "2. Dependencies: imports used (list)\n"
        "3. Key invariants: any constraints or assumptions (up to 3)\n"
        "4. Edge cases: any error handling or boundary conditions (up to 3)\n"
        "Be concise. No explanation."
    ),

    "error_log": (
        "Extract the KEY FACTS from this error output. Output ONLY:\n"
        "1. Error type and message (one line)\n"
        "2. Location: file + line number\n"
        "3. Root cause hypothesis (one line)\n"
        "4. Context clues: any variable values or stack details\n"
        "Be concise. No explanation."
    ),

    "git_diff": (
        "Summarize this git diff. Output ONLY:\n"
        "1. Files changed (list)\n"
        "2. What changed: one line per file\n"
        "3. Risk assessment: high/medium/low — why (one line)\n"
        "Be concise. No explanation."
    ),

    "documentation": (
        "Extract the KEY POINTS from this documentation. Output ONLY:\n"
        "1. Topic (one line)\n"
        "2. Key facts (up to 5 bullets)\n"
        "3. Gotchas or warnings (up to 3)\n"
        "Be concise. No explanation."
    ),
}


def distill(content: str, category: str = "code_file",
             model: str = MODEL, max_tokens: int = 300) -> str:
    """
    Semantically distill a large context into a structured digest.
    For long content (>8000 chars), chunks into overlapping segments,
    distills each independently, then merges. (review issue #20)

    Args:
        content: The raw text to distill
        category: One of 'code_file', 'error_log', 'git_diff', 'documentation'
        model: Ollama model name
        max_tokens: Max output tokens for the distillation

    Returns:
        Structured digest string, or original content if distillation fails.
    """
    if not content or len(content) < 200:
        return content

    template = TEMPLATES.get(category, TEMPLATES["code_file"])
    chunk_size = 6000
    overlap = 500

    if len(content) <= chunk_size:
        chunks = [content]
    else:
        chunks = []
        start = 0
        while start < len(content):
            end = min(start + chunk_size, len(content))
            chunks.append(content[start:end])
            start += chunk_size - overlap

    digests = []
    for chunk in chunks:
        prompt = f"{template}\n\n---CONTENT---\n{chunk}\n---END---\n\nDigest:"
        raw = _call_ollama(model, prompt, max_tokens=max_tokens // max(len(chunks), 2))
        if raw and len(raw) > 15:
            digests.append(raw)

    if not digests:
        return content  # All failed

    if len(digests) == 1:
        return digests[0]

    # Merge with dedup on function/signature-level lines (review #24)
    merged = []
    seen_lines = set()
    for i, d in enumerate(digests):
        for line in d.split("\n"):
            norm = line.strip().lower()[:60]
            if norm and norm not in seen_lines:
                seen_lines.add(norm)
                merged.append(f"[Part {i+1}] {line}" if len(digests) > 1 else line)
    return "\n".join(merged)


def _call_ollama(model: str, prompt: str, max_tokens: int = 300, retries: int = 1) -> str:
    """Call Ollama with retry on failure. (review issue #20)"""
    for attempt in range(retries + 1):
        try:
            resp = req.post(OLLAMA_URL, json={
                "model": model,
                "prompt": prompt,
                "options": {"num_predict": max_tokens, "temperature": 0.1},
                "stream": False,
                "keep_alive": -1,
            }, timeout=90)
            raw = resp.json().get("response", "").strip()
            if raw:
                return raw
        except Exception:
            if attempt == retries:
                return ""
    return ""


def condensation_ratio(original: str, condensed: str) -> dict:
    """Calculate how much was saved through distillation."""
    orig_chars = len(original)
    cond_chars = len(condensed)
    orig_tokens = orig_chars // 4
    cond_tokens = cond_chars // 4
    ratio = 1 - (cond_tokens / max(orig_tokens, 1))
    return {
        "original_chars": orig_chars,
        "condensed_chars": cond_chars,
        "original_tokens_est": orig_tokens,
        "condensed_tokens_est": cond_tokens,
        "tokens_saved": orig_tokens - cond_tokens,
        "reduction_pct": round(ratio * 100),
    }
