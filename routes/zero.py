"""routes/zero.py — Zero-LLM endpoints for Miser v1.5.5."""
import os, time, json
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify

from tools import (
    read_file, grep_file, outline_file, tree_view,
    write_to_file, patch_file, run_shell, list_dir,
    count_saved,
)
from prefetch import observe_access
from cache import cached, cache_stats as _cache_stats, semantic_cached
from diff import diff_file, diff_dir
from search import search as _search_code
from compress import compress_text, compress_file

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


# ── v1.5.5 endpoints ─────────────────────────────────────────────────────────────

@zero.route("/diff", methods=["POST"])
def diff():
    """
    Incremental diff: only return changed content.
    Input: {"path": "file_or_dir", "hash": "prev_sha256" (optional),
            "snapshot": {relpath: sha256} (optional, for dir diff)}
    """
    d = request.json or {}
    path = d.get("path", "").strip()
    if not path:
        return jsonify({"error": {"code": "E_MISSING_PARAM", "message": "path required"}}), 400

    p = Path(os.path.expanduser(path))
    if p.is_dir():
        old_snapshot = d.get("snapshot", {})
        result = diff_dir(path, old_snapshot)
        count_saved(len(result.get("snapshot", {})) * 8)  # ~8 chars per hash
        return jsonify({"data": result})
    else:
        old_hash = d.get("hash", "")
        old_content = d.get("content", "")
        result = diff_file(path, old_hash, old_content)
        if result.get("savings", 0) > 0:
            count_saved(result["savings"])
        return jsonify({"data": result})


@zero.route("/search", methods=["POST"])
def search():
    """
    Semantic code search with auto-fallback to BM25.
    Input: {"directory": "...", "query": "find auth logic", "top_k": 10}
    """
    d = request.json or {}
    directory = d.get("directory", "").strip() or "."
    query = d.get("query", "").strip()
    if not query:
        return jsonify({"error": {"code": "E_MISSING_PARAM", "message": "query required"}}), 400

    top_k = min(int(d.get("top_k", 10)), 50)
    exclude = d.get("exclude", None)

    result = _search_code(directory, query, top_k, exclude)
    # Save tokens: we're returning snippets, not full files
    total_saved = sum(len(r.get("snippet", "")) * 3 for r in result.get("results", []))
    count_saved(total_saved)
    return jsonify({"data": result})


@zero.route("/compress", methods=["POST"])
def compress():
    """
    Compress text by filtering low-information-density lines.
    Input: {"text": "..."} or {"path": "file.py", "threshold": 0.5}
    """
    d = request.json or {}
    threshold = float(d.get("threshold", 0.5))

    if "text" in d:
        result = compress_text(d["text"], threshold)
    elif "path" in d:
        result = compress_file(d["path"], threshold)
    else:
        return jsonify({"error": {"code": "E_MISSING_PARAM", "message": "text or path required"}}), 400

    if result.get("tokens_saved", 0) > 0:
        count_saved(result["tokens_saved"])
    return jsonify({"data": result})


@zero.route("/ask", methods=["POST"])
def ask_cached():
    """
    LLM ask with semantic cache (v1.5.5).
    Falls through to LLM if no cache hit.
    """
    d = request.json or {}
    task = d.get("task", "").strip()
    if not task:
        return jsonify({"error": {"code": "E_MISSING_PARAM", "message": "task required"}}), 400

    embedding = d.get("embedding", None)
    result, was_cached = semantic_cached(task,
        lambda: _run_task(task, d.get("from", "?"), d.get("system", ""),
                          d.get("max_tokens", 600), d.get("explicit_type", "ask"))
        if _run_task else "(no LLM backend)", embedding)

    return jsonify({"data": {"result": result, "cached": was_cached}})
