"""
config.py - Centralized configuration for Miser v1.5.3.
Single source of truth for all env vars, CLI args, and defaults.

New in v1.5: model="auto" means auto-detect from available backends.
"""

import os, argparse
from pathlib import Path

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULTS = {
    "port":         7860,
    "model":        "auto",          # v1.5: "auto" = discover from backend
    "auth_token":   "",
    "log_format":   "text",
    "embed_model":  "",              # v1.5: empty = skip embeddings if unavailable
    "max_queue":    10,
    "queue_timeout": 60,
    "rate_llm":     30,
    "rate_zero":    200,
    "max_body_mb":  5,
    "host":         "0.0.0.0",       # v1.5: listen on all interfaces by default
    "skip_wizard":  True,            # v1.5: wizard is inline, not separate script
}

# ── Load from environment ─────────────────────────────────────────────────────

def from_env() -> dict:
    return {
        "port":         int(os.environ.get("MISER_PORT", DEFAULTS["port"])),
        "host":         os.environ.get("MISER_HOST", DEFAULTS["host"]),
        "model":        os.environ.get("MISER_MODEL", DEFAULTS["model"]).strip(),
        "auth_token":   os.environ.get("MISER_AUTH_TOKEN", DEFAULTS["auth_token"]),
        "log_format":   os.environ.get("MISER_LOG_FORMAT", DEFAULTS["log_format"]),
        "embed_model":  os.environ.get("MISER_EMBED_MODEL", DEFAULTS["embed_model"]),
        "max_queue":    int(os.environ.get("MISER_MAX_QUEUE", DEFAULTS["max_queue"])),
        "queue_timeout": int(os.environ.get("MISER_QUEUE_TIMEOUT", DEFAULTS["queue_timeout"])),
        "rate_llm":     int(os.environ.get("MISER_RATE_LLM", DEFAULTS["rate_llm"])),
        "rate_zero":    int(os.environ.get("MISER_RATE_ZERO", DEFAULTS["rate_zero"])),
        "max_body_mb":  int(os.environ.get("MISER_MAX_BODY_MB", DEFAULTS["max_body_mb"])),
    }

# ── CLI argument parsing ──────────────────────────────────────────────────────

def parse_cli(argv: list = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Miser v1.5 - Zero-token local AI co-processor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  miser                          # auto-detect backend + model
  miser --port 8080              # custom port
  miser --model gemma4:latest    # use specific model
  miser --auth-token my-secret   # enable API auth
        """
    )
    parser.add_argument("--port", type=int, default=DEFAULTS["port"],
                        help=f"Listen port (default: {DEFAULTS['port']})")
    parser.add_argument("--host", type=str, default=DEFAULTS["host"],
                        help=f"Bind address (default: {DEFAULTS['host']})")
    parser.add_argument("--model", type=str, default=DEFAULTS["model"],
                        help=f"Model name, or 'auto' to detect (default: auto)")
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
    parser.add_argument("--setup", action="store_true",
                        help="Run inline setup wizard (model download guide)")
    parser.add_argument("--setup-agent", action="store_true",
                        help="Auto-configure MCP for all detected agents (zero manual config)")

    return parser.parse_args(argv)


def resolve(argv: list = None) -> dict:
    """Merge env vars + CLI args with CLI taking priority."""
    cfg = from_env()
    cli = parse_cli(argv)

    if argv is not None:
        cfg["port"] = cli.port if cli.port != DEFAULTS["port"] else cfg["port"]
        cfg["host"] = cli.host if cli.host != DEFAULTS["host"] else cfg["host"]
        cfg["model"] = cli.model if cli.model != DEFAULTS["model"] else cfg["model"]
        cfg["auth_token"] = cli.auth_token or cfg["auth_token"]
        cfg["log_format"] = cli.log_format if cli.log_format != DEFAULTS["log_format"] else cfg["log_format"]
        cfg["max_queue"] = cli.max_queue if cli.max_queue != DEFAULTS["max_queue"] else cfg["max_queue"]
        cfg["rate_llm"] = cli.rate_llm if cli.rate_llm != DEFAULTS["rate_llm"] else cfg["rate_llm"]
        cfg["rate_zero"] = cli.rate_zero if cli.rate_zero != DEFAULTS["rate_zero"] else cfg["rate_zero"]

    cfg["_cli"] = cli
    return cfg
