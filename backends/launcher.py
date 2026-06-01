"""
backends/launcher.py — Auto-launch LLM backends and select optimal model.

Handles:
  1. Finding Ollama binary on any OS
  2. Starting Ollama if installed but not running
  3. Ranking available models to pick the best one for agent co-processing
"""

import os
import sys
import time
import subprocess
import re
import requests as req
from pathlib import Path
from typing import Optional


# ── Find Ollama binary ──────────────────────────────────────────────────────

def find_ollama_binary() -> Optional[str]:
    """Locate the ollama executable on this system. Returns path or None."""
    # 1. Check PATH
    for cmd in ("ollama", "ollama.exe"):
        try:
            result = subprocess.run(
                [cmd, "--version"], capture_output=True, text=True, timeout=5,
                **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {})
            )
            if result.returncode == 0 and "ollama" in result.stdout.lower():
                return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # 2. Check common install paths
    paths = []
    if sys.platform == "darwin":
        paths = [
            "/usr/local/bin/ollama",
            "/opt/homebrew/bin/ollama",
            "/Applications/Ollama.app/Contents/Resources/ollama",
        ]
    elif sys.platform == "win32":
        # Windows: user install and system install
        local_appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        paths = [
            os.path.join(local_appdata, "Programs", "Ollama", "ollama.exe"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Ollama", "ollama.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Ollama", "ollama.exe"),
        ]
    else:  # Linux
        paths = [
            "/usr/bin/ollama",
            "/usr/local/bin/ollama",
            os.path.expanduser("~/.local/bin/ollama"),
        ]

    for p in paths:
        if os.path.isfile(p):
            return p

    return None


# ── Start Ollama ────────────────────────────────────────────────────────────

def start_ollama(binary: Optional[str] = None, timeout: float = 30.0) -> bool:
    """Launch Ollama in the background if not already running.
    Blocks up to `timeout` seconds waiting for it to become ready.
    Returns True if Ollama is reachable afterwards.
    """
    if binary is None:
        binary = find_ollama_binary()

    if binary is None:
        return False

    # Already running?
    try:
        r = req.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code == 200:
            return True
    except Exception:
        pass

    # Launch
    try:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(
            [binary, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs,
        )
    except Exception:
        return False

    # Wait for it
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        try:
            r = req.get("http://localhost:11434/api/tags", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass

    return False


# ── Model ranking ───────────────────────────────────────────────────────────

def _model_rank_key(model_name: str, model_info: dict | None = None) -> tuple:
    """Produce a sort key for model quality. Lower = better (we negate)."""
    n = model_name.lower()

    # Family preference (higher = better)
    family_score = 0
    if "gemma4" in n:
        family_score = 100
    elif "gemma" in n:
        family_score = 90
    elif "qwen3.5" in n or "qwen3-5" in n:
        family_score = 85
    elif "qwen3" in n:
        family_score = 80
    elif "llama4" in n:
        family_score = 75
    elif "llama3" in n or "llama-3" in n:
        family_score = 70
    elif "mistral" in n:
        family_score = 65
    elif "phi4" in n:
        family_score = 60
    elif "phi3" in n or "phi-3" in n:
        family_score = 55
    elif "deepseek" in n:
        family_score = 50

    # Parameter size (rough estimate from name)
    param_score = 0
    m = re.search(r'(\d+)\.?(\d*)\s*b', n)
    if m:
        major = int(m.group(1))
        if major >= 70:
            param_score = 70  # 70B+
        elif major >= 30:
            param_score = 30  # 30B+
        elif major >= 7:
            param_score = major  # 7B-30B
        else:
            param_score = major  # <7B

    # Quantization quality
    quant_score = 0
    if model_info:
        details = model_info.get("details", {})
        qlevel = details.get("quantization_level", "")
        if "Q8" in qlevel:
            quant_score = 8
        elif "Q6" in qlevel:
            quant_score = 6
        elif "Q5" in qlevel:
            quant_score = 5
        elif "Q4" in qlevel:
            quant_score = 4
        elif "Q3" in qlevel:
            quant_score = 3
        elif "Q2" in qlevel:
            quant_score = 2
        elif "F16" in qlevel:
            quant_score = 16

    # "latest" tag preferred over dated tags
    latest_bonus = 10 if ":latest" in n else 0

    # Negate because Python sorts ascending and we want best first
    return (-family_score, -param_score, -quant_score, -latest_bonus, n)


def select_best_model(models: list[dict]) -> Optional[str]:
    """Pick the best model from Ollama's /api/tags response.
    Returns model name string, or None if empty.
    """
    if not models:
        return None

    # Build name → info map
    info_map = {m.get("name", ""): m for m in models}

    ranked = sorted(models, key=lambda m: _model_rank_key(m.get("name", ""), m))
    best = ranked[0].get("name", "")

    return best


def list_models_ranked(models: list[dict]) -> list[str]:
    """Return model names sorted best-first."""
    if not models:
        return []
    ranked = sorted(models, key=lambda m: _model_rank_key(m.get("name", ""), m))
    return [m.get("name", "") for m in ranked]
