"""
agent_setup.py — One-command agent integration for Miser.

Usage:
    python miser.py --setup-agent          # auto-detect agent, write config
    python agent_setup.py                  # standalone

Detects which AI agent is installed and writes the correct MCP configuration
so Miser tools appear automatically in the agent. Never edit JSON/YAML manually again.
"""

import os
import sys
import json
import shutil
from pathlib import Path

MISER_DIR = Path(__file__).resolve().parent
MCP_SERVER = MISER_DIR / "mcp_server.py"

# ── Agent detection ─────────────────────────────────────────────────────────

def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def _config_exists(path: str) -> bool:
    return Path(path).expanduser().exists()

def detect_agents() -> list[tuple[str, str, str]]:
    """Return list of (agent_name, config_path, config_type) for installed agents."""
    found = []
    home = Path.home()

    # Hermes Agent (always check first — config lives in ~/.hermes/)
    hermes_config = home / ".hermes" / "config.yaml"
    if hermes_config.parent.exists():
        found.append(("hermes", str(hermes_config), "yaml"))

    # Claude Desktop
    claude_macos = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if claude_macos.exists():
        found.append(("claude-desktop", str(claude_macos), "json"))

    # Continue (VS Code extension)
    continue_config = home / ".continue" / "config.json"
    if continue_config.parent.exists():
        found.append(("continue", str(continue_config), "json"))

    # Cursor
    cursor_config = home / ".cursor" / "mcp.json"
    if cursor_config.parent.exists() or _which("cursor"):
        found.append(("cursor", str(cursor_config), "json"))

    # Windsurf
    windsurf_config = home / ".windsurf" / "mcp.json"
    if windsurf_config.parent.exists():
        found.append(("windsurf", str(windsurf_config), "json"))

    return found


# ── Config writers ──────────────────────────────────────────────────────────

def _write_hermes_config(config_path: str, mcp_server_path: str) -> bool:
    """Add Miser MCP block to Hermes config.yaml."""
    import yaml  # pyyaml required for hermes

    path = Path(config_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing config
    if path.exists():
        with open(path, "r") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        cfg = {}

    # Ensure mcp_servers key
    if "mcp_servers" not in cfg:
        cfg["mcp_servers"] = {}

    # Don't overwrite existing miser config
    if "miser" in cfg["mcp_servers"]:
        print(f"  Miser MCP already configured in {path}")
        return True

    cfg["mcp_servers"]["miser"] = {
        "command": sys.executable,
        "args": [mcp_server_path],
        "timeout": 120,
    }

    with open(path, "w") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"  ✓ Added Miser MCP to {path}")
    return True


def _write_json_config(config_path: str, mcp_server_path: str) -> bool:
    """Add Miser MCP block to a JSON-based agent config."""
    path = Path(config_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        with open(path, "r") as f:
            try:
                cfg = json.load(f)
            except json.JSONDecodeError:
                cfg = {}
    else:
        cfg = {}

    if "mcpServers" not in cfg:
        cfg["mcpServers"] = {}

    if "miser" in cfg["mcpServers"]:
        print(f"  Miser MCP already configured in {path}")
        return True

    cfg["mcpServers"]["miser"] = {
        "command": sys.executable,
        "args": [mcp_server_path],
    }

    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)

    print(f"  ✓ Added Miser MCP to {path}")
    return True


def setup_agents(agents: list[tuple[str, str, str]] | None = None,
                 mcp_server_path: str | None = None) -> dict[str, bool]:
    """Configure all detected agents. Returns {agent_name: success}."""
    if agents is None:
        agents = detect_agents()

    if mcp_server_path is None:
        mcp_server_path = str(MCP_SERVER)

    results = {}
    for name, config_path, config_type in agents:
        try:
            if config_type == "yaml":
                results[name] = _write_hermes_config(config_path, mcp_server_path)
            else:
                results[name] = _write_json_config(config_path, mcp_server_path)
        except Exception as e:
            print(f"  ✗ Failed to configure {name}: {e}")
            results[name] = False

    return results


def print_summary(results: dict[str, bool]):
    """Print human-readable summary of what was configured."""
    if not results:
        print("\n  No supported agents detected on this system.")
        print("  Supported: Hermes Agent, Claude Desktop, Continue, Cursor, Windsurf")
        print(f"\n  To configure manually, point your agent's MCP config to:")
        print(f"    {MCP_SERVER}")
        return

    print()
    for name, ok in results.items():
        icon = "✓" if ok else "✗"
        print(f"  {icon} {name}")

    print(f"\n  Restart your agent(s) to load the new Miser tools.")
    print(f"  MCP server: {MCP_SERVER}")


# ── CLI entry ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    agents = detect_agents()
    if not agents:
        print("No supported agents found. Available agents: Hermes, Claude Desktop, Continue, Cursor, Windsurf")
        sys.exit(0)

    print(f"Detected {len(agents)} agent(s):")
    for name, path, _ in agents:
        print(f"  • {name} ({path})")

    results = setup_agents(agents)
    print_summary(results)
