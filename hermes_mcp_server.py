#!/usr/bin/env python3
"""
Miser MCP Server — Exposes Miser (local GPU co-processor) tools to Hermes Agent.
Proxies zero-token file ops and gemma4-powered LLM tasks via MCP stdio protocol.

Usage (in ~/.hermes/config.yaml):
  mcp_servers:
    miser:
      command: "~/.hermes/hermes-agent/venv/bin/python"
      args: ["~/miser/hermes_mcp_server.py"]
      env:
        MISER_URL: "http://127.0.0.1:7860"
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
    # Zero-LLM tools (no token cost)
    {"name": "miser_read", "description": "Read a file via Miser. Zero API tokens — served instantly from disk on the Miser host.",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "Absolute path to the file on the Miser host"},
         "limit": {"type": "integer", "description": "Max lines to return", "default": 500},
     }, "required": ["path"]}},
    {"name": "miser_grep", "description": "Search file contents via Miser. Zero API tokens.",
     "inputSchema": {"type": "object", "properties": {
         "pattern": {"type": "string", "description": "Regex pattern to search for"},
         "path": {"type": "string", "description": "Directory or file path on the Miser host", "default": "."},
     }, "required": ["pattern"]}},
    {"name": "miser_run", "description": "Run a shell command via Miser. Zero API tokens.",
     "inputSchema": {"type": "object", "properties": {
         "command": {"type": "string", "description": "Shell command to execute on the Miser host"},
     }, "required": ["command"]}},
    {"name": "miser_write", "description": "Write content to a file via Miser. Zero API tokens.",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "Absolute path on the Miser host"},
         "content": {"type": "string", "description": "Content to write"},
     }, "required": ["path", "content"]}},
    {"name": "miser_patch", "description": "Patch a file via Miser. Zero API tokens.",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "Absolute path on the Miser host"},
         "old_string": {"type": "string", "description": "Text to find"},
         "new_string": {"type": "string", "description": "Replacement text"},
     }, "required": ["path", "old_string", "new_string"]}},

    # LLM tools (gemma4 via Miser — zero API cost)
    {"name": "miser_ask", "description": "Ask gemma4 a question via Miser. Runs on local GPU — zero API cost.",
     "inputSchema": {"type": "object", "properties": {
         "task": {"type": "string", "description": "The question or task for gemma4"},
         "max_tokens": {"type": "integer", "description": "Max tokens in response", "default": 600},
     }, "required": ["task"]}},
    {"name": "miser_codegen", "description": "Generate code via gemma4 on Miser. Zero API cost.",
     "inputSchema": {"type": "object", "properties": {
         "task": {"type": "string", "description": "Code generation task description"},
         "from": {"type": "string", "description": "Requestor identifier"},
     }, "required": ["task"]}},
    {"name": "miser_explain", "description": "Explain code via gemma4 on Miser. Zero API cost.",
     "inputSchema": {"type": "object", "properties": {
         "task": {"type": "string", "description": "Code to explain + question"},
     }, "required": ["task"]}},
    {"name": "miser_review", "description": "Code review via gemma4 on Miser. Zero API cost.",
     "inputSchema": {"type": "object", "properties": {
         "task": {"type": "string", "description": "Code to review"},
     }, "required": ["task"]}},
    {"name": "miser_summarize", "description": "Summarize content via gemma4 on Miser. Zero API cost.",
     "inputSchema": {"type": "object", "properties": {
         "task": {"type": "string", "description": "Content to summarize"},
     }, "required": ["task"]}},
]

# Mapping: tool name → miser endpoint
ENDPOINT_MAP = {
    "miser_read": "read",
    "miser_grep": "grep",
    "miser_run": "run",
    "miser_write": "write",
    "miser_patch": "patch",
    "miser_ask": "ask",
    "miser_codegen": "codegen",
    "miser_explain": "explain",
    "miser_review": "review",
    "miser_summarize": "summarize",
}

# ── MCP stdio server ──────────────────────────────────────────────────────────

def handle_request(request: dict) -> dict:
    """Handle a single JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "miser-mcp", "version": "1.0.0"},
        }}
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        tool_name = request["params"]["name"]
        arguments = request["params"].get("arguments", {})
        endpoint = ENDPOINT_MAP.get(tool_name, tool_name.replace("miser_", ""))

        result = _post(endpoint, arguments)

        # Extract result/error from miser response
        if "result" in result:
            text = result["result"]
        elif "error" in result:
            text = f"ERROR: {result['error']}"
        elif "content" in result:
            text = result["content"]
        else:
            text = json.dumps(result)

        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "content": [{"type": "text", "text": text}]
        }}
    else:
        return {"jsonrpc": "2.0", "id": req_id, "error": {
            "code": -32601, "message": f"Method not found: {method}"
        }}

def main():
    """MCP stdio loop — reads JSON-RPC from stdin, writes to stdout."""
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
            err_resp = {"jsonrpc": "2.0", "id": request.get("id") if 'request' in dir() else None,
                        "error": {"code": -32603, "message": str(e)}}
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()
