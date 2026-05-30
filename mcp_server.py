#!/usr/bin/env python3
"""
Miser MCP Server v2.0 - Agent-agnostic MCP stdio protocol bridge.

Exposes Miser's zero-token file ops and local-LLM tasks to ANY MCP-compatible agent:
  - Claude Desktop
  - Hermes Agent
  - Continue.dev
  - Cursor
  - Windsurf
  - Any tool that speaks MCP

Usage:
  python mcp_server.py                        # with MISER_URL env var
  MISER_URL=http://localhost:7860 python mcp_server.py
"""

import json, os, sys
import urllib.request
import urllib.error

MISER_URL = os.environ.get("MISER_URL", "http://127.0.0.1:7860")

def _post(endpoint: str, data: dict) -> dict:
    """POST to Miser, return JSON response."""
    url = f"{MISER_URL}/{endpoint}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    # Zero-LLM tools (no token cost - instant)
    {
        "name": "miser_read",
        "description": "Read a file via Miser. Zero API tokens - served instantly from disk on the Miser host.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file on the Miser host"},
                "limit": {"type": "integer", "description": "Max characters to return", "default": 8000},
            },
            "required": ["path"],
        },
    },
    {
        "name": "miser_grep",
        "description": "Search file contents via Miser. Zero API tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory or file path on the Miser host", "default": "."},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "miser_run",
        "description": "Run a shell command via Miser. Zero API tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute on the Miser host"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["command"],
        },
    },
    {
        "name": "miser_write",
        "description": "Write content to a file via Miser. Zero API tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path on the Miser host"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "miser_patch",
        "description": "Patch a file via Miser (find-and-replace). Zero API tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path on the Miser host"},
                "old_string": {"type": "string", "description": "Text to find"},
                "new_string": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "miser_tree",
        "description": "Directory tree view via Miser. Zero API tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path on the Miser host", "default": "~/Desktop"},
                "depth": {"type": "integer", "description": "Max depth", "default": 2},
            },
            "required": [],
        },
    },

    # Local LLM tools (zero API cost - runs on local GPU)
    {
        "name": "miser_ask",
        "description": "Ask the local LLM a question. Runs on local GPU - zero API cost.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The question or task"},
                "max_tokens": {"type": "integer", "description": "Max tokens in response", "default": 600},
            },
            "required": ["task"],
        },
    },
    {
        "name": "miser_codegen",
        "description": "Generate code via local LLM. Zero API cost.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Code generation task description"},
                "lang": {"type": "string", "description": "Target language", "default": "python"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "miser_explain",
        "description": "Explain code or text via local LLM. Zero API cost.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code or text to explain"},
                "path": {"type": "string", "description": "Alternatively, path to a file to explain"},
            },
            "required": [],
        },
    },
    {
        "name": "miser_review",
        "description": "Code review via local LLM. Zero API cost.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to review"},
                "path": {"type": "string", "description": "Alternatively, path to a file to review"},
            },
            "required": [],
        },
    },
    {
        "name": "miser_summarize",
        "description": "Summarize content via local LLM. Zero API cost.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Content to summarize"},
                "path": {"type": "string", "description": "Alternatively, path to a file to summarize"},
            },
            "required": [],
        },
    },
]

# Mapping: MCP tool name → Miser HTTP endpoint
ENDPOINT_MAP = {
    "miser_read": "read",
    "miser_grep": "grep",
    "miser_run": "run",
    "miser_write": "write",
    "miser_patch": "patch",
    "miser_tree": "tree",
    "miser_ask": "ask",
    "miser_codegen": "codegen",
    "miser_explain": "explain",
    "miser_review": "review",
    "miser_summarize": "summarize",
}

# ── MCP stdio server ──────────────────────────────────────────────────────────

def handle_request(request: dict) -> dict | None:
    """Handle a single JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "miser-mcp", "version": "2.0.2"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = request["params"]["name"]
        arguments = request["params"].get("arguments", {})
        endpoint = ENDPOINT_MAP.get(tool_name, tool_name.replace("miser_", ""))

        # Map MCP argument names to Miser API field names
        arg_map = {
            "miser_run": {"command": "cmd"},
        }
        mapped = dict(arguments)
        for k, v in arg_map.get(tool_name, {}).items():
            if k in mapped:
                mapped[v] = mapped.pop(k)

        result = _post(endpoint, mapped)

        # Extract result
        if "result" in result:
            text = result["result"]
        elif "error" in result:
            text = f"ERROR: {result['error']}"
        elif "content" in result:
            text = result["content"]
        elif "summary" in result:
            text = result["summary"]
        elif "explanation" in result:
            text = result["explanation"]
        elif "review" in result:
            text = result["review"]
        elif "code" in result:
            text = result["code"]
        elif "matches" in result:
            text = result["matches"]
        elif "tree" in result:
            text = result["tree"]
        elif "output" in result:
            text = result["output"]
        else:
            text = json.dumps(result)

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": text}]},
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    """MCP stdio loop - reads JSON-RPC from stdin, writes to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            if response:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            pass
        except Exception as e:
            rid = request.get("id") if "request" in dir() else None
            err_resp = {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32603, "message": str(e)},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
