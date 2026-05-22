#!/usr/bin/env python3
"""
miser adapt — One-click agent configuration tool (P2 #12).

Usage:
  python -m scripts.adapt --tool cline     # Configure Cline
  python -m scripts.adapt --tool aider     # Configure Aider
  python -m scripts.adapt --tool codex     # Configure Codex CLI
  python -m scripts.adapt --all            # Configure all detected tools
  python -m scripts.adapt --list           # List available adapters
"""

import os, sys, shutil, json, argparse
from pathlib import Path

ADAPTERS_DIR = Path(__file__).parent.parent / "adapters"
HOME = Path.home()

# Detection and installation rules for each tool
TOOLS = {
    "cline": {
        "name": "Cline",
        "adapter": "cline-mcp.json",
        "targets": [
            HOME / ".vscode" / "mcp.json",
            HOME / ".vscode" / "cline" / "mcp.json",
        ],
    },
    "codex": {
        "name": "Codex CLI",
        "adapter": "codex-miser.sh",
        "target_type": "script",
        "action": "bash {adapter}",
    },
    "aider": {
        "name": "Aider",
        "adapter": "aider-miser.yml",
        "targets": [
            Path.cwd() / ".aider.conf.yml",
            HOME / ".aider.conf.yml",
        ],
        "merge": True,  # append to existing config
    },
    "continue": {
        "name": "Continue.dev",
        "adapter": "continue-miser.json",
        "targets": [
            HOME / ".continue" / "config.json",
        ],
    },
    "roocode": {
        "name": "Roo Code",
        "adapter": "roocode-mcp.json",
        "targets": [
            HOME / ".vscode" / "mcp.json",
        ],
    },
    "zed": {
        "name": "Zed AI",
        "adapter": "zed-miser.json",
        "targets": [
            HOME / ".config" / "zed" / "settings.json",
        ],
    },
    "jetbrains": {
        "name": "JetBrains AI",
        "adapter": "jetbrains-miser.xml",
        "target_type": "xml",
        "info": "Copy the XML content into your JetBrains IDE AI Assistant settings.",
    },
}


def detect_tool(name: str) -> bool:
    """Check if a tool is installed."""
    checks = {
        "cline": lambda: (HOME / ".vscode").exists(),
        "codex": lambda: shutil.which("codex") is not None,
        "aider": lambda: shutil.which("aider") is not None,
        "continue": lambda: (HOME / ".continue").exists(),
        "roocode": lambda: (HOME / ".vscode").exists(),
        "zed": lambda: (HOME / ".config" / "zed").exists() or shutil.which("zed") is not None,
        "jetbrains": lambda: shutil.which("idea") is not None or shutil.which("pycharm") is not None,
    }
    checker = checks.get(name, lambda: False)
    try:
        return checker()
    except Exception:
        return False


def configure_tool(name: str) -> bool:
    """Configure a single tool with its miser adapter."""
    info = TOOLS.get(name)
    if not info:
        print(f"  Unknown tool: {name}")
        return False

    adapter_path = ADAPTERS_DIR / info["adapter"]
    if not adapter_path.exists():
        print(f"  Adapter not found: {adapter_path}")
        return False

    print(f"  Configuring {info['name']}...")

    # Script-type adapters
    if info.get("target_type") == "script":
        action = info["action"].format(adapter=adapter_path)
        os.system(action)
        print(f"    ✓ Ran {action}")
        return True

    # XML-type (manual)
    if info.get("target_type") == "xml":
        print(f"    → {info.get('info', 'Manual setup required.')}")
        print(f"    → Source: {adapter_path}")
        return True

    # File-copy type
    targets = info.get("targets", [])
    for target in targets:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)

        if info.get("merge"):
            # Append to existing config
            existing = ""
            if target.exists():
                existing = target.read_text()
            if "miser" not in existing:
                adapter_content = adapter_path.read_text()
                target.write_text(existing + "\n" + adapter_content)
            print(f"    ✓ Merged into {target}")
        else:
            # Copy adapter
            shutil.copy2(adapter_path, target)
            print(f"    ✓ Installed to {target}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Miser — one-click agent configuration")
    parser.add_argument("--tool", help="Configure a specific tool")
    parser.add_argument("--all", action="store_true", help="Configure all detected tools")
    parser.add_argument("--list", action="store_true", help="List available adapters")
    args = parser.parse_args()

    if args.list:
        print("Available adapters:")
        for name, info in TOOLS.items():
            installed = "✓" if detect_tool(name) else " "
            print(f"  [{installed}] {name:<12} — {info['name']}")
        return

    if args.tool:
        configure_tool(args.tool)
        return

    if args.all:
        print("Miser — configuring all detected tools...")
        configured = 0
        for name in TOOLS:
            if detect_tool(name):
                if configure_tool(name):
                    configured += 1
        print(f"\n  Configured {configured} tools.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
