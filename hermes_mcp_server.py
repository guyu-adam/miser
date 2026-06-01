#!/usr/bin/env python3
"""
Hermes MCP Server — Thin wrapper for Miser MCP integration with Hermes Agent.

This file exists so existing Hermes config.yaml entries continue to work.
It simply imports and runs the main mcp_server.py.
"""

import sys
from pathlib import Path

# Add parent to path so mcp_server imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_server import main

if __name__ == "__main__":
    main()
