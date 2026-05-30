#!/usr/bin/env python3
"""
Miser MCP Server v1.5 - Drop-in MCP bridge for ANY agent.

Usage — just add this to your agent's MCP config:
  {
    "mcpServers": {
      "miser": {
        "command": "python3",
        "args": ["/path/to/miser/mcp_server.py"]
      }
    }
  }

Miser auto-starts on first call. No separate 'miser' process needed.
Zero-LLM tools work even without a local GPU.
"""

import json, os, sys, subprocess, time, threading
import urllib.request
import urllib.error

MISER_URL  = os.environ.get("MISER_URL", "http://127.0.0.1:7860")
MISER_PORT = int(os.environ.get("MISER_PORT", "7860"))

# ── Status cache (refreshed once, avoids per-call /health hits) ──────────────
_status_cache = None
_status_lock  = threading.Lock()

def _miser_status() -> dict:
    """Fetch Miser /health once, cache result."""
    global _status_cache
    with _status_lock:
        if _status_cache is not None:
            return _status_cache
    try:
        with urllib.request.urlopen(f"{MISER_URL}/health", timeout=3) as resp:
            _status_cache = json.loads(resp.read().decode())
    except Exception:
        _status_cache = {}
    return _status_cache or {}


# ── Auto-launch ──────────────────────────────────────────────────────────────

def _miser_is_alive() -> bool:
    try:
        urllib.request.urlopen(f"{MISER_URL}/health", timeout=2)
        return True
    except Exception:
        return False


def _ensure_miser_running() -> bool:
    """Launch Miser in the background if it's not already running.
    Blocks up to 15s waiting for readiness on first launch.
    Returns True when Miser is reachable."""
    if _miser_is_alive():
        return True

    script_dir = os.path.dirname(os.path.abspath(__file__))
    miser_py   = os.path.join(script_dir, "miser.py")

    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    subprocess.Popen(
        [sys.executable, "-u", miser_py, "--port", str(MISER_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **kwargs,
    )

    deadline = time.time() + 15
    while time.time() < deadline:
        time.sleep(0.5)
        if _miser_is_alive():
            return True
    return False


# ── HTTP bridge ──────────────────────────────────────────────────────────────

def _post(endpoint: str, data: dict) -> dict:
    """POST to Miser, auto-launching if needed. Returns JSON response."""
    if not _ensure_miser_running():
        return {"error": "Miser service could not be started. Check: python3 miser.py"}

    url  = f"{MISER_URL}/{endpoint}"
    body = json.dumps(data).encode("utf-8")
    req  = urllib.request.Request(url, data=body,
                                   headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


# ── Tool definitions ─────────────────────────────────────────────────────────

TOOLS = [
    # ── Zero-LLM tools (always available, no GPU needed) ───────────────────
    {
        "name": "miser_read",
        "description": "Read a file via Miser. Zero API tokens - served instantly from disk.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string", "description": "Absolute path to the file"},
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
                "path":    {"type": "string", "description": "Directory or file path", "default": "."},
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
                "command": {"type": "string", "description": "Shell command to execute"},
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
                "path":    {"type": "string", "description": "Absolute path to the file"},
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
                "path":       {"type": "string", "description": "Absolute path"},
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
                "path":  {"type": "string", "description": "Directory path", "default": "~/Desktop"},
                "depth": {"type": "integer", "description": "Max depth", "default": 2},
            },
            "required": [],
        },
    },

    # ── Local LLM tools (require GPU + Ollama/LM Studio, zero API cost) ────
    {
        "name": "miser_ask",
        "description": "Ask the local LLM a question. Runs on local GPU - zero API cost. Falls back to error if no local LLM is configured.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task":       {"type": "string", "description": "The question or task"},
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
    "miser_read":       "read",
    "miser_grep":       "grep",
    "miser_run":        "run",
    "miser_write":      "write",
    "miser_patch":      "patch",
    "miser_tree":       "tree",
    "miser_ask":        "ask",
    "miser_codegen":    "codegen",
    "miser_explain":    "explain",
    "miser_review":     "review",
    "miser_summarize":  "summarize",
}

# LLM tools that need a backend
_LLM_TOOLS = {"miser_ask", "miser_codegen", "miser_explain", "miser_review", "miser_summarize"}


# ── MCP stdio server ─────────────────────────────────────────────────────────

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
                "serverInfo": {"name": "miser-mcp", "version": "1.5.0"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = request["params"]["name"]
        arguments = request["params"].get("arguments", {})
        endpoint  = ENDPOINT_MAP.get(tool_name, tool_name.replace("miser_", ""))

        # Map MCP argument names to Miser API field names
        arg_map = {"miser_run": {"command": "cmd"}}
        mapped  = dict(arguments)
        for k, v in arg_map.get(tool_name, {}).items():
            if k in mapped:
                mapped[v] = mapped.pop(k)

        result = _post(endpoint, mapped)

        # Extract result from Miser response
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
    """MCP stdio loop — reads JSON-RPC from stdin, writes to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request  = json.loads(line)
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
