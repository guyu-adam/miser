"""routes/zero.py — Zero-LLM endpoints for Miser v1.4 (Phase 3 #19)."""
import os, time
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify

from tools import (
    read_file, grep_file, outline_file, tree_view,
    write_to_file, patch_file, run_shell, list_dir,
    count_saved,
)
from prefetch import observe_access
from cache import cached, cache_stats as _cache_stats

zero = Blueprint("zero", __name__)

# Set by miser.py at startup to avoid circular import
_run_task = None

def set_run_task(fn):
    global _run_task
    _run_task = fn


@zero.route("/read", methods=["POST"])
def read():
    d = request.json or {}
    path = d.get("path", "").strip()
    if not path:
        return jsonify({"error": {"code": "E_MISSING_PARAM", "message": "path required"}}), 400
    limit = d.get("limit", 8000)
    result = cached(("read", path, limit), lambda: read_file(path, limit))
    count_saved(len(result))
    observe_access(path)
    return jsonify({"data": {"content": result, "path": path}})


@zero.route("/grep", methods=["POST"])
def grep():
    d = request.json or {}
    path, pattern = d.get("path", "").strip(), d.get("pattern", "").strip()
    if not path or not pattern:
        return jsonify({"error": {"code": "E_MISSING_PARAM", "message": "path and pattern required"}}), 400
    ctx = d.get("context", 2)
    ic = d.get("ignore_case", True)
    result = cached(("grep", path, pattern, ctx, ic),
                    lambda: grep_file(path, pattern, ctx, ic))
    count_saved(len(read_file(path, 99999)) - len(result))
    return jsonify({"data": {"matches": result, "path": path, "pattern": pattern}})


@zero.route("/outline", methods=["POST"])
def outline():
    d = request.json or {}
    path = d.get("path", "").strip()
    if not path:
        return jsonify({"error": {"code": "E_MISSING_PARAM", "message": "path required"}}), 400
    result = cached(("outline", path), lambda: outline_file(path))
    count_saved(len(read_file(path, 99999)) - len(result))
    observe_access(path)
    return jsonify({"data": {"outline": result, "path": path}})


@zero.route("/tree", methods=["POST"])
def tree():
    d = request.json or {}
    path = d.get("path", "").strip() or "~/Desktop"
    depth = int(d.get("depth", 2))
    exclude = d.get("exclude", "__pycache__,.git,node_modules,.DS_Store")
    result = cached(("tree", path, depth, exclude),
                    lambda: tree_view(path, depth, exclude))
    count_saved(len(result) * 3)
    return jsonify({"data": {"tree": result, "path": path}})


@zero.route("/exists", methods=["POST"])
def exists():
    d = request.json or {}
    path = d.get("path", "").strip()
    if not path:
        return jsonify({"error": {"code": "E_MISSING_PARAM", "message": "path required"}}), 400
    p = Path(os.path.expanduser(path))
    info = {"exists": p.exists(), "path": str(p)}
    if p.exists():
        info["is_file"] = p.is_file()
        info["is_dir"] = p.is_dir()
        info["size"] = p.stat().st_size if p.is_file() else None
    return jsonify({"data": info})


@zero.route("/run", methods=["POST"])
def run():
    d = request.json or {}
    cmd = d.get("cmd", "").strip()
    if not cmd:
        return jsonify({"error": {"code": "E_MISSING_PARAM", "message": "cmd required"}}), 400
    out = run_shell(cmd, timeout=d.get("timeout", 30))
    count_saved(len(out))
    return jsonify({"data": {"output": out}})


@zero.route("/write", methods=["POST"])
def write():
    d = request.json or {}
    path, content = d.get("path", "").strip(), d.get("content", "")
    if not path:
        return jsonify({"error": {"code": "E_MISSING_PARAM", "message": "path required"}}), 400
    result = write_to_file(path, content)
    count_saved(len(content))
    return jsonify({"data": {"result": result, "path": path, "chars": len(content)}})


@zero.route("/patch", methods=["POST"])
def patch():
    d = request.json or {}
    path, old, new = d.get("path", "").strip(), d.get("old", ""), d.get("new", "")
    if not path or not old:
        return jsonify({"error": {"code": "E_MISSING_PARAM", "message": "path and old required"}}), 400
    result = patch_file(path, old, new)
    return jsonify({"data": {"result": result}})


@zero.route("/batch", methods=["POST"])
def batch():
    d = request.json or {}
    tasks = d.get("tasks", [])
    if not tasks:
        return jsonify({"error": {"code": "E_MISSING_PARAM", "message": "tasks required"}}), 400
    ask_tasks = [t for t in tasks if t.get("type") == "ask"]
    if len(ask_tasks) > 3:
        return jsonify({"error": {"code": "E_QUEUE_FULL", "message": "max 3 LLM tasks per batch"}}), 400
    results = []
    for t in tasks:
        typ = t.get("type", "ask")
        try:
            if typ == "run":
                results.append({"type": "run", "data": run_shell(t.get("cmd", ""))})
            elif typ == "read":
                results.append({"type": "read", "data": read_file(t.get("path", ""))})
            elif typ == "grep":
                results.append({"type": "grep", "data": grep_file(t.get("path", ""), t.get("pattern", ""), t.get("context", 2))})
            elif typ == "outline":
                results.append({"type": "outline", "data": outline_file(t.get("path", ""))})
            elif typ == "tree":
                results.append({"type": "tree", "data": tree_view(t.get("path", "~/Desktop"), t.get("depth", 2))})
            elif typ == "exists":
                p = Path(os.path.expanduser(t.get("path", "")))
                results.append({"type": "exists", "data": p.exists()})
            elif typ == "write":
                results.append({"type": "write", "data": write_to_file(t.get("path", ""), t.get("content", ""))})
            else:
                # #33 fix: restore LLM execution for ask-type batch tasks
                if _run_task:
                    result = _run_task(t.get("task", ""), "batch",
                                       t.get("system", ""),
                                       t.get("max_tokens", 600),
                                       t.get("explicit_type", "ask"))
                    results.append({"type": "ask", "data": result})
                else:
                    results.append({"type": "ask", "data": t.get("task", "")})
        except Exception as e:
            results.append({"type": typ, "error": str(e)})
    return jsonify({"data": {"results": results}})
