#!/usr/bin/env python3
"""
Miser MCP Server v1.5.3 — Drop-in MCP bridge for ANY agent.

Usage — add to agent's MCP config:
  {"mcpServers": {"miser": {"command": "python3", "args": [".../mcp_server.py"]}}}

Miser auto-starts on first call. Zero-LLM tools work without a GPU.
"""

import json, os, sys, subprocess, time, threading
import urllib.request, urllib.error

MISER_URL  = os.environ.get("MISER_URL", "http://127.0.0.1:7860")
MISER_PORT = int(os.environ.get("MISER_PORT", "7860"))

# ═══════════════════════════════════════════════════════════════════════════
#  Status cache
# ═══════════════════════════════════════════════════════════════════════════

_status_cache = None
_status_lock  = threading.Lock()

def _miser_has_llm() -> bool:
    """True if Miser reports a working LLM backend."""
    global _status_cache
    with _status_lock:
        if _status_cache is not None:
            return _status_cache.get("backend", "?") != "?"
    try:
        with urllib.request.urlopen(f"{MISER_URL}/health", timeout=3) as resp:
            _status_cache = json.loads(resp.read().decode())
    except Exception:
        _status_cache = {}
    return _status_cache.get("backend", "?") != "?"


# ═══════════════════════════════════════════════════════════════════════════
#  Auto-launch
# ═══════════════════════════════════════════════════════════════════════════

def _miser_is_alive() -> bool:
    try:
        urllib.request.urlopen(f"{MISER_URL}/health", timeout=2)
        return True
    except Exception:
        return False

def _ensure_miser_running() -> bool:
    """Launch Miser in background if not already running. Returns True when ready."""
    if _miser_is_alive():
        return True

    script_dir = os.path.dirname(os.path.abspath(__file__))
    miser_py   = os.path.join(script_dir, "miser.py")

    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    subprocess.Popen(
        [sys.executable, "-u", miser_py, "--port", str(MISER_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs,
    )

    deadline = time.time() + 15
    while time.time() < deadline:
        time.sleep(0.5)
        if _miser_is_alive():
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
#  HTTP bridge
# ═══════════════════════════════════════════════════════════════════════════

def _post(endpoint: str, data: dict) -> dict:
    if not _ensure_miser_running():
        return {"error": "Miser service could not be started."}
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


# ═══════════════════════════════════════════════════════════════════════════
#  Tool definitions
# ═══════════════════════════════════════════════════════════════════════════

TOOLS = [
    # ── Zero-token tools — always available, no GPU needed ──────────────
    {
        "name": "miser_read",
        "description": (
            "Read a file from disk via Miser. ZERO API tokens — use this "
            "INSTEAD of reading files directly through the agent. Saves ~95% "
            "tokens vs cloud-based file read. Ideal for understanding code, "
            "checking configs, inspecting logs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string",
                          "description": "Absolute path to the file"},
                "limit": {"type": "integer", "default": 8000,
                          "description": "Max characters to return"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "miser_outline",
        "description": (
            "Get a file's structure — function/class/method listing with line "
            "numbers. ZERO tokens. Use this INSTEAD of reading a whole file "
            "just to understand its structure. Saves 90%+ tokens vs full read."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string",
                         "description": "Absolute path to the file"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "miser_grep",
        "description": (
            "Search file contents with regex. ZERO tokens. Use this INSTEAD "
            "of the agent's built-in grep or shell grep — runs on Miser host "
            "at no token cost."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string",
                            "description": "Regex pattern to search for"},
                "path":    {"type": "string", "default": ".",
                            "description": "Directory or file path"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "miser_tree",
        "description": (
            "Directory tree view. ZERO tokens. Use this INSTEAD of ls/find "
            "to understand project structure. Returns nested file listing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string", "default": "~/Desktop",
                          "description": "Directory path"},
                "depth": {"type": "integer", "default": 2,
                          "description": "Max depth"},
            },
            "required": [],
        },
    },
    {
        "name": "miser_exists",
        "description": (
            "Check if a file or directory exists. ZERO tokens. Use this "
            "INSTEAD of shell test/ls to check file presence."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string",
                         "description": "Absolute path to check"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "miser_run",
        "description": (
            "Run a shell command on the Miser host. ZERO tokens. Use this "
            "for git, pytest, npm, pip, and other local CLI tools."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string",
                            "description": "Shell command to execute"},
                "timeout": {"type": "integer", "default": 30,
                            "description": "Timeout in seconds"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "miser_write",
        "description": (
            "Write content to a file. ZERO tokens. Use this for creating "
            "or overwriting files on the Miser host."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string",
                            "description": "Absolute path to the file"},
                "content": {"type": "string",
                            "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "miser_patch",
        "description": (
            "Find-and-replace in a file. ZERO tokens. More efficient than "
            "read+edit+write for targeted changes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":       {"type": "string",
                               "description": "Absolute path"},
                "old_string": {"type": "string",
                               "description": "Text to find"},
                "new_string": {"type": "string",
                               "description": "Replacement text"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },

    # ── Local-LLM tools — run on local GPU, zero cloud API cost ──────────
    {
        "name": "miser_ask",
        "description": (
            "Ask the local LLM a question. Runs on LOCAL GPU — zero cloud API "
            "cost. Use for quick lookups, definitions, simple reasoning."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task":       {"type": "string",
                               "description": "The question or task"},
                "max_tokens": {"type": "integer", "default": 600},
            },
            "required": ["task"],
        },
    },
    {
        "name": "miser_explain",
        "description": (
            "Explain what a piece of code does. Local GPU, zero cost. Use "
            "this INSTEAD of reading a file and reasoning about it yourself."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string",
                         "description": "Code or text to explain"},
                "path": {"type": "string",
                         "description": "Or: path to a file to explain"},
            },
            "required": [],
        },
    },
    {
        "name": "miser_review",
        "description": (
            "Code review via local LLM. Local GPU, zero cost. Returns bugs, "
            "improvements, and verdict."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string",
                         "description": "Code to review"},
                "path": {"type": "string",
                         "description": "Or: path to a file to review"},
            },
            "required": [],
        },
    },
    {
        "name": "miser_summarize",
        "description": (
            "Summarize content into concise bullet points. Local GPU, zero cost."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string",
                         "description": "Content to summarize"},
                "path": {"type": "string",
                         "description": "Or: path to a file to summarize"},
            },
            "required": [],
        },
    },
    {
        "name": "miser_codegen",
        "description": (
            "Generate code via local LLM. Local GPU, zero cost. Use for "
            "boilerplate, utility functions, test stubs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string",
                         "description": "Code generation task"},
                "lang": {"type": "string", "default": "python",
                         "description": "Target language"},
            },
            "required": ["task"],
        },
    },
]

ENDPOINT_MAP = {
    "miser_read":       "read",
    "miser_outline":    "outline",
    "miser_grep":       "grep",
    "miser_tree":       "tree",
    "miser_exists":     "exists",
    "miser_run":        "run",
    "miser_write":      "write",
    "miser_patch":      "patch",
    "miser_ask":        "ask",
    "miser_explain":    "explain",
    "miser_review":     "review",
    "miser_summarize":  "summarize",
    "miser_codegen":    "codegen",
}

ARG_MAP = {"miser_run": {"command": "cmd"}}


# ═══════════════════════════════════════════════════════════════════════════
#  MCP stdio server
# ═══════════════════════════════════════════════════════════════════════════

_INSTRUCTIONS = """## Miser — Local Token Saver (ALWAYS USE THESE TOOLS)

Miser tools run on the local machine at ZERO cloud API token cost.

### Decision rules:

| Instead of | Use | Why |
|---|---|---|
| Reading a file directly | miser_read | 95% token savings |
| Reading file to see structure | miser_outline | 90%+ vs full read |
| Shell grep/find | miser_grep | zero tokens |
| ls / find / tree | miser_tree | zero tokens |
| Shell test -f / ls | miser_exists | zero tokens |
| Any shell command | miser_run | zero tokens |
| Reasoning about code yourself | miser_explain | local GPU, free |
| Code review yourself | miser_review | local GPU, free |
| Generating boilerplate | miser_codegen | local GPU, free |
| Quick questions/lookups | miser_ask | local GPU, free |

**Default rule**: If ANY file operation, shell command, or local-LLM task can be done via Miser, use Miser FIRST. Only fall back to direct operations if Miser returns an error.

Zero-LLM tools work even without a GPU. LLM tools work when Ollama/LM Studio is running."""


def handle_request(request: dict) -> dict | None:
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "miser-mcp", "version": "1.5.3"},
                "instructions": _INSTRUCTIONS,
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = request["params"]["name"]
        arguments = request["params"].get("arguments", {})
        endpoint  = ENDPOINT_MAP.get(tool_name,
                                     tool_name.replace("miser_", ""))

        mapped = dict(arguments)
        for k, v in ARG_MAP.get(tool_name, {}).items():
            if k in mapped:
                mapped[v] = mapped.pop(k)

        result = _post(endpoint, mapped)

        # Extract result from Miser response
        for key in ("result", "content", "summary", "explanation",
                     "review", "code", "matches", "tree", "outline",
                     "output"):
            if key in result:
                text = result[key]
                break
        else:
            if "error" in result:
                text = f"ERROR: {result['error']}"
            elif "data" in result:
                text = json.dumps(result["data"])
            else:
                text = json.dumps(result)

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": str(text)}]},
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    """MCP stdio loop."""
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
