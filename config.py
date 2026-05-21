"""
config.py — Centralized configuration for Miser (Phase 2 #12).
Single source of truth for all env vars, CLI args, and defaults.
"""

import os, argparse
from pathlib import Path

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULTS = {
    "port":         7860,
    "model":        "qwen3.5:4b",
    "auth_token":   "",
    "log_format":   "text",
    "embed_model":  "nomic-embed-text",
    "max_queue":    10,
    "queue_timeout": 60,
    "rate_llm":     30,
    "rate_zero":    200,
    "max_body_mb":  5,
}

# ── Load from environment ─────────────────────────────────────────────────────

def from_env() -> dict:
    return {
        "port":         int(os.environ.get("MISER_PORT", DEFAULTS["port"])),
        "model":        os.environ.get("MISER_MODEL", DEFAULTS["model"]),
        "auth_token":   os.environ.get("MISER_AUTH_TOKEN", DEFAULTS["auth_token"]),
        "log_format":   os.environ.get("MISER_LOG_FORMAT", DEFAULTS["log_format"]),
        "embed_model":  os.environ.get("MISER_EMBED_MODEL", DEFAULTS["embed_model"]),
        "max_queue":    int(os.environ.get("MISER_MAX_QUEUE", DEFAULTS["max_queue"])),
        "queue_timeout": int(os.environ.get("MISER_QUEUE_TIMEOUT", DEFAULTS["queue_timeout"])),
        "rate_llm":     int(os.environ.get("MISER_RATE_LLM", DEFAULTS["rate_llm"])),
        "rate_zero":    int(os.environ.get("MISER_RATE_ZERO", DEFAULTS["rate_zero"])),
        "max_body_mb":  int(os.environ.get("MISER_MAX_BODY_MB", DEFAULTS["max_body_mb"])),
    }

# ── CLI argument parsing (Phase 1 #8) ─────────────────────────────────────────

def parse_cli(argv: list = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Miser — Save 98% API tokens with your local GPU",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python miser.py
  python miser.py --port 8080 --model mistral:7b
  python miser.py --log-format json --auth-token my-secret
  miser --version
        """
    )
    parser.add_argument("--port", type=int, default=DEFAULTS["port"],
                        help=f"Listen port (default: {DEFAULTS['port']})")
    parser.add_argument("--model", type=str, default=DEFAULTS["model"],
                        help=f"Ollama model name (default: {DEFAULTS['model']})")
    parser.add_argument("--auth-token", type=str, default="",
                        help="API auth token (enables authentication)")
    parser.add_argument("--log-format", choices=["text", "json"],
                        default=DEFAULTS["log_format"],
                        help=f"Log format (default: {DEFAULTS['log_format']})")
    parser.add_argument("--max-queue", type=int, default=DEFAULTS["max_queue"],
                        help=f"Max task queue size (default: {DEFAULTS['max_queue']})")
    parser.add_argument("--rate-llm", type=int, default=DEFAULTS["rate_llm"],
                        help=f"LLM endpoint rate limit per min (default: {DEFAULTS['rate_llm']})")
    parser.add_argument("--rate-zero", type=int, default=DEFAULTS["rate_zero"],
                        help=f"Zero-LLM endpoint rate limit per min (default: {DEFAULTS['rate_zero']})")
    parser.add_argument("--version", action="store_true",
                        help="Show version and exit")
    parser.add_argument("--wizard", action="store_true",
                        help="Run first-time setup wizard")

    return parser.parse_args(argv)


def resolve(argv: list = None) -> dict:
    """Merge env vars + CLI args with CLI taking priority.
    If argv is None, only uses env vars (safe for import by test runners)."""
    cfg = from_env()
    cli = parse_cli(argv)

    # CLI overrides env (only if explicitly provided or argv was passed)
    if argv is not None:
        cfg["port"] = cli.port if cli.port != DEFAULTS["port"] else cfg["port"]
        cfg["model"] = cli.model if cli.model != DEFAULTS["model"] else cfg["model"]
        cfg["auth_token"] = cli.auth_token or cfg["auth_token"]
        cfg["log_format"] = cli.log_format if cli.log_format != DEFAULTS["log_format"] else cfg["log_format"]
        cfg["max_queue"] = cli.max_queue if cli.max_queue != DEFAULTS["max_queue"] else cfg["max_queue"]
        cfg["rate_llm"] = cli.rate_llm if cli.rate_llm != DEFAULTS["rate_llm"] else cfg["rate_llm"]
        cfg["rate_zero"] = cli.rate_zero if cli.rate_zero != DEFAULTS["rate_zero"] else cfg["rate_zero"]

    cfg["_cli"] = cli
    return cfg
