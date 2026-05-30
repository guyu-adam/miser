"""
Miser v1.5 - Zero-token local AI co-processor.
Auto-detects any local LLM (Ollama, LM Studio, llama.cpp, vLLM, etc.).
Two execution paths:
  1. Zero-LLM (<50ms): shell, file read/write/grep/tree/exists/outline/patch
  2. Local LLM (no API cost): summarize, codegen, explain, fix, test, review, git_summary
"""

import os, re, threading, time, signal, uuid, sys
from datetime import datetime
from pathlib import Path

# Windows: force UTF-8 to prevent GBK encoding errors with emoji/special chars
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"

# ── Dependency self-check (v1.5: fail gracefully with fix instructions) ─────

def _check_deps():
    """Check required packages. Print install hint if missing."""
    missing = []
    for pkg in ("flask", "rich", "requests"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        pkgs = " ".join(missing)
        print(f"\n  Missing packages: {pkgs}")
        print(f"  Fix: pip install {pkgs}\n")
        sys.exit(1)

_check_deps()

import requests as req
from flask import Flask, request, jsonify
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from model_adapter import ModelAdapter
from memory import Memory
from tools import (
    run_shell, read_file, list_dir, grep_file, tree_view, outline_file,
    write_to_file, patch_file, extract_path, _safe_eval,
    count_saved, get_tokens_saved, I18N_PATTERNS,
)
from prefetch import observe_access, get_stats as prefetch_stats
from condenser import distill, condensation_ratio
from task_queue import get_queue, QueuedTask
from security import (
    rate_limit_middleware, cors_middleware, hash_token, verify_token,
    error_response,
)
from config import resolve as resolve_config
from cache import cache_stats
from breaker import ollama_breaker
from facade import set_facade_model

console = Console()
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024   # 5MB

# Module-level: env-only defaults (safe for test imports). CLI resolved in __main__.
cfg = resolve_config(argv=[])
MODEL = cfg["model"]       # "auto" until __main__ discovers
AUTH_TOKEN = cfg["auth_token"]
PORT = cfg["port"]
HOST = cfg["host"]
LOG_FORMAT = cfg["log_format"]
AUTH_HASH = hash_token(AUTH_TOKEN) if AUTH_TOKEN else ""

# Lazy placeholders - replaced in __main__ after auto-discovery
adapter = None
mem = Memory()
backend = None

import routes.admin as _admin
_admin.MODEL = MODEL
_admin.ADAPTER = adapter
_admin.MEM = mem
_admin.BACKEND = backend

# Register blueprints at module level (test-safe)
from routes.zero import zero as _zero_bp, set_run_task as _set_run
from routes.admin import admin as _admin_bp
app.register_blueprint(_zero_bp, url_prefix="/v1")
app.register_blueprint(_admin_bp)
from facade import facade as _facade_bp
app.register_blueprint(_facade_bp, url_prefix="/v1")

# ── state ───────────────────────────────────────────────────────────────────────

class State:
    def __init__(self):
        self.status = "IDLE"
        self.task   = "-"
        self.result = ""
        self.count  = 0
        self._lock  = threading.Lock()
    def set(self, status, task=None):
        with self._lock:
            self.status = status
            if task is not None: self.task = task

st = State()

# Flag set in main() during backend discovery
NO_LLM = False

# ── auth helper (review item #4) ────────────────────────────────────────────────

def _check_auth(req_data: dict) -> bool:
    """If AUTH_TOKEN is configured, require it in every request. (Phase 1 #2: hashed comparison)"""
    if not AUTH_HASH:
        return True
    token = (req_data or {}).get("_token", "")
    return verify_token(token, AUTH_HASH)

# ── LLM call ────────────────────────────────────────────────────────────────────

def llm(task: str, system: str = "", max_tokens: int = 600, mode: str = "text") -> str:
    if backend is None:
        return "ERROR: No local LLM backend available. Start Ollama/LM Studio first."

    is_code    = mode == "code"    or re.search(r'\b(write|def|function|code|implement|class)\b', task, re.I)
    is_bullets = mode == "bullets" or re.search(r'\b(summarize|bullet|list|summary|points)\b', task, re.I)
    detected_mode = "code" if is_code and not is_bullets else ("bullets" if is_bullets else "text")

    sys_prompt = "You are Miser, a local AI assistant.\nOutput ONLY the final answer, no preamble.\n"
    if detected_mode == "text":
        ctx_text = mem.ctx(task)
        if ctx_text:
            sys_prompt += f"Context: {ctx_text}\n"
    if system:
        sys_prompt += system

    for attempt in range(3):
        try:
            answer = backend.generate(MODEL, sys_prompt, task,
                                      max_tokens=max_tokens, temperature=0.2)
            if answer:
                # Post-clean through adapter for code/bullet mode extraction
                if detected_mode != "text":
                    answer = adapter.clean(answer, mode=detected_mode)
                if answer:
                    return answer
            console.print(f"[dim yellow]empty response, retry {attempt+1}/3[/dim yellow]")
        except Exception as e:
            if attempt == 2:
                return f"ERROR: {e}"
    return "(no response)"

# ── explicit routing (review item #9) ───────────────────────────────────────────

EXPLICIT_ROUTES = {
    "outline":  lambda d: outline_file(d.get("path", "")),
    "grep":     lambda d: grep_file(d.get("path",""), d.get("pattern",""),
                                     d.get("context",2), d.get("ignore_case",True)),
    "tree":     lambda d: tree_view(d.get("path","~/Desktop"), d.get("depth",2),
                                     d.get("exclude","__pycache__,.git,node_modules,.DS_Store")),
    "read":     lambda d: read_file(d.get("path",""), d.get("limit",8000)),
    "exists":   lambda d: str(Path(os.path.expanduser(d.get("path",""))).exists()),
    "write":    lambda d: write_to_file(d.get("path",""), d.get("content","")),
    "patch":    lambda d: patch_file(d.get("path",""), d.get("old",""), d.get("new","")),
    "run":      lambda d: run_shell(d.get("cmd",""), d.get("timeout",30)),
    "ls":       lambda d: list_dir(d.get("path","~/Desktop"), d.get("pattern","*")),
    "calc":     lambda d: _safe_eval(d.get("expr","0")),   # review item #1
}

# Legacy regex routing - now only for /ask fallback (review item #9)
FALLBACK_ROUTES = [
    (re.compile(I18N_PATTERNS["list_files"] + r".{0,20}?" + I18N_PATTERNS["file_dir_words"], re.I),
     lambda t: list_dir(extract_path(t, "~/Desktop"))),
    (re.compile(I18N_PATTERNS["run_cmd"] + r"[：:\s]+(.+)", re.I | re.S),
     lambda t: run_shell(re.search(r"^(?:run|exec|执行|运行)[：:\s]+(.+)", t, re.I | re.S).group(1))),
    (re.compile(I18N_PATTERNS["time_query"], re.I),
     lambda _: datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    (re.compile(r"^[\d\s\+\-\*\/\.\^\(\)]+$"),
     lambda t: _safe_eval(t)),    # review item #1
    (re.compile(I18N_PATTERNS["exists_query"] + r".{0,30}?" + I18N_PATTERNS["file_dir_words"], re.I),
     lambda t: str(Path(os.path.expanduser(extract_path(t, ""))).exists())),
]

def route(task: str, explicit_type: str = "") -> tuple[str, str]:
    """Route a task to either a direct (zero-LLM) handler or LLM.
    If explicit_type is set, try explicit routes first."""
    if explicit_type and explicit_type in EXPLICIT_ROUTES:
        try:
            return "direct", EXPLICIT_ROUTES[explicit_type]({})
        except Exception as e:
            return "direct", f"Error: {e}"

    if explicit_type == "ask":
        return "llm", ""

    # Fallback: legacy regex routing (review item #9)
    for pattern, fn in FALLBACK_ROUTES:
        if pattern.search(task):
            try:
                return "direct", fn(task)
            except Exception as e:
                return "direct", f"Error: {e}"

    return "llm", ""

# ── task runner ──────────────────────────────────────────────────────────────────

def run_task(task: str, sender: str, system: str = "", max_tokens: int = 600,
             explicit_type: str = "") -> str:
    st.count += 1
    st.set("WORKING", task)
    ts = datetime.now().strftime("%H:%M:%S")
    mode, pre = route(task, explicit_type)
    console.print()
    console.print(Rule(f"[cyan]#{st.count}  {ts}  [{mode}]  {sender}[/cyan]"))
    console.print(f"[yellow]▶ {task[:120]}[/yellow]\n")
    try:
        result = pre if mode == "direct" else llm(task, system, max_tokens)
        st.result = result
        mem.record(st.count, task, result)
        count_saved(len(result))
        console.print(Panel(result[:1000], title="[green]✓[/green]", border_style="green"))
    except Exception as e:
        result = f"ERROR: {e}"
        st.result = result
        console.print(Panel(result, title="[red]✗[/red]", border_style="red"))
    finally:
        st.set("IDLE", "-")
        # v1.3: drain queued tasks (commercialization P0)
        q = get_queue()
        next_task = q.dequeue()
        if next_task:
            threading.Thread(
                target=run_task,
                args=(next_task.task, next_task.sender,
                      next_task.system, next_task.max_tokens,
                      next_task.explicit_type),
                daemon=True
            ).start()
    return result

# ── endpoints ────────────────────────────────────────────────────────────────────

def _auth_fail():
    return jsonify({"error": "unauthorized - MISER_AUTH_TOKEN required"}), 401

@app.route("/ask", methods=["POST"])
def ask():
    d = request.json or {}
    if not _check_auth(d): return _auth_fail()
    task = d.get("task","").strip()
    if not task: return jsonify({"error":"task required"}), 400
    if st.status == "WORKING":
        # v1.3: queue instead of rejecting (commercialization P0)
        q = get_queue()
        qt = QueuedTask(
            task_id=str(uuid.uuid4())[:8],   # review #26
            task=task, sender=d.get("from","?"),
            system=d.get("system",""), max_tokens=d.get("max_tokens",600),
            explicit_type=d.get("type","ask"),
        )
        if q.enqueue(qt):
            return jsonify({"queued": True, "position": q.size, "task": task[:80]}), 202
        return jsonify({"error":"queue_full", "retry_in": 5}), 429
    result = run_task(task, d.get("from","?"), d.get("system",""),
                      d.get("max_tokens",600), d.get("type","ask"))
    ok = not result.startswith("ERROR:")
    return jsonify({"result": result} if ok else {"error": result}), (200 if ok else 500)

@app.route("/chat", methods=["POST"])
def chat():
    d = request.json or {}
    if not _check_auth(d): return _auth_fail()
    task = d.get("task","").strip()
    if not task: return jsonify({"error":"task required"}), 400
    if st.status == "WORKING":
        q = get_queue()
        qt = QueuedTask(task_id=str(uuid.uuid4())[:8], task=task, sender=d.get("from","?"),
                        system=d.get("system",""), max_tokens=d.get("max_tokens",600),
                        explicit_type=d.get("type",""))
        if q.enqueue(qt):
            return jsonify({"queued": True, "position": q.size, "task": task[:80]}), 202
        return jsonify({"error":"queue_full"}), 429
    threading.Thread(target=run_task, args=(task, d.get("from","?"),
                     d.get("system",""), d.get("max_tokens",600), d.get("type","")),
                     daemon=True).start()
    return jsonify({"accepted": True})

@app.route("/run", methods=["POST"])
def run_cmd():
    d = request.json or {}
    if not _check_auth(d): return _auth_fail()
    cmd = d.get("cmd","").strip()
    if not cmd: return jsonify({"error":"cmd required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[green]shell  {ts}[/green]"))
    console.print(f"[dim]$ {cmd}[/dim]")
    try:
        out = run_shell(cmd, timeout=d.get("timeout", 30))
        count_saved(len(out))
        console.print(f"[dim]{out[:300]}[/dim]")
        return jsonify({"output": out})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/read", methods=["POST"])
def read_file_ep():
    d = request.json or {}
    path = d.get("path","").strip()
    if not path: return jsonify({"error":"path required"}), 400
    content = read_file(path, d.get("limit", 8000))
    count_saved(len(content))
    observe_access(path)
    console.print(Rule(f"[green]read  {path}[/green]"))
    return jsonify({"content": content, "path": path})

@app.route("/grep", methods=["POST"])
def grep():
    d = request.json or {}
    path    = d.get("path","").strip()
    pattern = d.get("pattern","").strip()
    if not path or not pattern:
        return jsonify({"error":"path and pattern required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[green]grep  {ts}[/green]"))
    result = grep_file(path, pattern, d.get("context", 2), d.get("ignore_case", True))
    count_saved(len(read_file(path, 99999)) - len(result))
    return jsonify({"matches": result, "path": path, "pattern": pattern})

@app.route("/outline", methods=["POST"])
def outline():
    d = request.json or {}
    path = d.get("path","").strip()
    if not path: return jsonify({"error":"path required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[green]outline  {ts}[/green]"))
    result = outline_file(path)
    count_saved(len(read_file(path, 99999)) - len(result))
    observe_access(path)
    console.print(f"[dim]{result[:400]}[/dim]")
    return jsonify({"outline": result, "path": path})

@app.route("/tree", methods=["POST"])
def tree():
    d = request.json or {}
    path  = d.get("path","").strip() or "~/Desktop"
    depth = int(d.get("depth", 2))
    ts    = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[green]tree  {ts}[/green]"))
    result = tree_view(path, depth, d.get("exclude", "__pycache__,.git,node_modules,.DS_Store"))
    count_saved(len(result) * 3)
    return jsonify({"tree": result, "path": path})

@app.route("/exists", methods=["POST"])
def exists():
    d = request.json or {}
    path = d.get("path","").strip()
    if not path: return jsonify({"error":"path required"}), 400
    p = Path(os.path.expanduser(path))
    info = {"exists": p.exists(), "path": str(p)}
    if p.exists():
        info["is_file"] = p.is_file()
        info["is_dir"]  = p.is_dir()
        info["size"]    = p.stat().st_size if p.is_file() else None
    return jsonify(info)

@app.route("/write", methods=["POST"])
def write_file_ep():
    d = request.json or {}
    if not _check_auth(d): return _auth_fail()       # write requires auth
    path    = d.get("path","").strip()
    content = d.get("content","")
    if not path: return jsonify({"error":"path required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[green]write  {ts}[/green]"))
    try:
        result = write_to_file(path, content)
        count_saved(len(content))
        return jsonify({"result": result, "path": path, "chars": len(content)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/patch", methods=["POST"])
def patch():
    d = request.json or {}
    if not _check_auth(d): return _auth_fail()       # patch requires auth
    path = d.get("path","").strip()
    old  = d.get("old","")
    new  = d.get("new","")
    if not path or not old: return jsonify({"error":"path and old required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[green]patch  {ts}[/green]"))
    try:
        result = patch_file(path, old, new)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/summarize", methods=["POST"])
def summarize():
    d = request.json or {}
    focus = d.get("focus", "key logic and structure")
    if "path" in d:
        content = read_file(d["path"], limit=7000)
        label = d["path"]
    elif "text" in d:
        content = d["text"][:7000]
        label = "text"
    else:
        return jsonify({"error": "path or text required"}), 400
    if content.startswith("File not found"):
        return jsonify({"error": content}), 404
    full_len = len(content)
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[magenta]summarize  {ts}[/magenta]"))
    result = llm(f"Focus on: {focus}\n\nContent:\n{content}",
                 system="Summarize in ≤6 concise bullet points. Facts only. No preamble.\n",
                 max_tokens=400)
    count_saved(full_len - len(result))
    console.print(Panel(result, title="[magenta]summary[/magenta]", border_style="magenta"))
    return jsonify({"summary": result, "source": label, "original_chars": full_len})

@app.route("/codegen", methods=["POST"])
def codegen():
    d = request.json or {}
    task = d.get("task","").strip()
    lang = d.get("lang","python")
    if not task: return jsonify({"error":"task required"}), 400
    if st.status == "WORKING":
        q = get_queue()
        qt = QueuedTask(task_id=str(uuid.uuid4())[:8], task=task, sender=d.get("from","?"),
                        system=f"Output {lang} code only. No explanation. No markdown fences.\n",
                        max_tokens=700, explicit_type="codegen")
        if q.enqueue(qt):
            return jsonify({"queued": True, "position": q.size, "task": task[:80]}), 202
        return jsonify({"error":"queue_full"}), 429
    result = run_task(task, d.get("from","?"),
                      system=f"Output {lang} code only. No explanation. No markdown fences.\n",
                      max_tokens=700, explicit_type="codegen")
    return jsonify({"code": result, "lang": lang})

@app.route("/condense", methods=["POST"])
def condense():
    """Semantically distill a large context using local LLM.
    Returns a structured digest + savings stats.
    Unlike prompt compression, this preserves semantic meaning."""
    d = request.json or {}
    if "path" in d:
        content = read_file(d["path"], limit=10000)
        category = "code_file"
        label = d["path"]
        observe_access(d["path"])
    elif "text" in d:
        content = d["text"][:10000]
        category = d.get("category", "code_file")
        label = "text"
    else:
        return jsonify({"error": "path or text required"}), 400

    if content.startswith("File not found"):
        return jsonify({"error": content}), 404

    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[cyan]condense  {ts}[/cyan]"))
    console.print(f"[dim]Distilling {len(content)} chars as [{category}]...[/dim]")

    result = distill(content, category, MODEL, d.get("max_tokens", 300))
    stats = condensation_ratio(content, result)
    count_saved(stats["tokens_saved"])

    console.print(Panel(result[:600], title="[cyan]condensed[/cyan]", border_style="cyan"))
    return jsonify({
        "digest": result,
        "source": label,
        "category": category,
        "savings": stats,
    })

@app.route("/explain", methods=["POST"])
def explain():
    d = request.json or {}
    if "path" in d:
        content = read_file(d["path"], limit=4000)
        label = d["path"]
        if content.startswith("File not found"):
            return jsonify({"error": content}), 404
    elif "code" in d:
        content = d["code"][:4000]
        label = "snippet"
    else:
        return jsonify({"error": "path or code required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[blue]explain  {ts}[/blue]"))
    result = llm(f"Explain this code:\n\n{content}",
                 system="One sentence summary, then bullet points for key logic. No fences.\n",
                 max_tokens=400)
    count_saved(len(content))
    console.print(Panel(result[:600], title="[blue]explanation[/blue]", border_style="blue"))
    return jsonify({"explanation": result, "source": label})

@app.route("/fix", methods=["POST"])
def fix():
    d = request.json or {}
    error_msg = d.get("error", "").strip()
    code_ctx  = d.get("code", "")[:3000]
    if not error_msg: return jsonify({"error": "error field required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[red]fix  {ts}[/red]"))
    prompt = f"Error:\n{error_msg}\n"
    if code_ctx:
        prompt += f"\nCode context:\n{code_ctx}\n"
    prompt += "\nWhat is the fix?"
    result = llm(prompt,
                 system="One sentence root cause, then the corrected code or line. No fences.\n",
                 max_tokens=400)
    console.print(Panel(result[:600], title="[red]fix[/red]", border_style="red"))
    return jsonify({"fix": result})

@app.route("/test", methods=["POST"])
def gen_tests():
    d = request.json or {}
    fn_name = d.get("function", "")
    if "path" in d:
        content = read_file(d["path"], limit=3000)
        if fn_name:
            content = grep_file(d["path"], rf"def {fn_name}", context=15) or content
        label = d["path"]
    elif "code" in d:
        content = d["code"][:3000]
        label = "snippet"
    else:
        return jsonify({"error": "path or code required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[yellow]test  {ts}[/yellow]"))
    target = f"for the function `{fn_name}`" if fn_name else "for the code"
    result = llm(f"Write pytest unit tests {target}:\n\n{content}",
                 system="Output only the test code. Use pytest. No fences.\n",
                 max_tokens=600, mode="code")
    console.print(Panel(result[:800], title="[yellow]tests[/yellow]", border_style="yellow"))
    count_saved(len(content))
    return jsonify({"tests": result, "source": label})

@app.route("/review", methods=["POST"])
def review():
    d = request.json or {}
    if "path" in d:
        content = read_file(d["path"], limit=3000)
        label = d["path"]
        if content.startswith("File not found"):
            return jsonify({"error": content}), 404
    elif "code" in d:
        content = d["code"][:3000]
        label = "snippet"
    else:
        return jsonify({"error": "path or code required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[magenta]review  {ts}[/magenta]"))
    result = llm(f"Review this code:\n\n{content}",
                 system="Format: BUGS: (list or 'none'), IMPROVEMENTS: (top 2-3), VERDICT: (one line). No fences.\n",
                 max_tokens=350)
    count_saved(len(content))
    console.print(Panel(result[:600], title="[magenta]review[/magenta]", border_style="magenta"))
    return jsonify({"review": result, "source": label})

@app.route("/git_summary", methods=["POST"])
def git_summary():
    d = request.json or {}
    repo_path = os.path.expanduser(d.get("path", "."))
    n = int(d.get("n", 10))
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[cyan]git_summary  {ts}[/cyan]"))
    log_raw = run_shell(f"git -C {repo_path} log --oneline --stat -{n} 2>&1")
    if "not a git repository" in log_raw.lower():
        return jsonify({"error": f"Not a git repo: {repo_path}"}), 400
    result = llm(f"Summarize these recent git commits in plain English:\n\n{log_raw}",
                 system="2-4 bullet points. Focus on WHAT changed and WHY. No fences.\n",
                 max_tokens=250)
    count_saved(len(log_raw))
    console.print(Panel(result, title="[cyan]git summary[/cyan]", border_style="cyan"))
    return jsonify({"summary": result, "commits_analyzed": n})

@app.route("/batch", methods=["POST"])
def batch():
    d = request.json or {}
    if not _check_auth(d): return _auth_fail()
    tasks = d.get("tasks", [])
    if not tasks: return jsonify({"error": "tasks required"}), 400

    # Review item #8: cap LLM tasks in batch, serialize to avoid flooding Ollama
    ask_tasks = [t for t in tasks if t.get("type") == "ask"]
    if len(ask_tasks) > 3:
        return jsonify({"error": f"batch LLM tasks capped at 3, got {len(ask_tasks)}"}), 400

    results = []
    for t in tasks:
        typ = t.get("type", "ask")
        try:
            if typ == "run":
                results.append({"type": "run", "result": run_shell(t.get("cmd",""))})
            elif typ == "read":
                results.append({"type": "read", "result": read_file(t.get("path",""))})
            elif typ == "grep":
                results.append({"type": "grep", "result": grep_file(
                    t.get("path",""), t.get("pattern",""), t.get("context",2))})
            elif typ == "outline":
                results.append({"type": "outline", "result": outline_file(t.get("path",""))})
            elif typ == "tree":
                results.append({"type": "tree", "result": tree_view(
                    t.get("path","~/Desktop"), t.get("depth",2))})
            elif typ == "exists":
                p = Path(os.path.expanduser(t.get("path","")))
                results.append({"type": "exists", "result": p.exists()})
            elif typ == "write":
                results.append({"type": "write", "result": write_to_file(
                    t.get("path",""), t.get("content",""))})
            else:
                results.append({"type": "ask",
                    "result": run_task(t.get("task",""), "batch",
                                       explicit_type=t.get("explicit_type",""))})
        except Exception as e:
            results.append({"type": typ, "error": str(e)})
    return jsonify({"results": results})

@app.route("/note", methods=["POST"])
def note():
    d = request.json or {}
    key = d.get("key","").strip()
    val = d.get("value","").strip()
    if not key or not val: return jsonify({"error":"key and value required"}), 400
    mem.save(key, val)
    return jsonify({"saved": {key: val}})

# ── main ─────────────────────────────────────────────────────────────────────────
# ── v1.5: auto-detect backend + model on startup ───────────────────────────────

def main():
    """Entry point for 'miser' CLI command (pip install).
    Also called by if __name__ == '__main__'.
    """
    import sys as _sys, json as _json, logging as _log
    global MODEL, AUTH_TOKEN, PORT, HOST, LOG_FORMAT, AUTH_HASH, adapter, backend, NO_LLM
    _sys.argv[0] = "miser"

    # ── Re-resolve with CLI args ──────────────────────────────────────────
    cli_cfg = resolve_config(argv=_sys.argv[1:])
    MODEL      = cli_cfg["model"]
    AUTH_TOKEN = cli_cfg["auth_token"]
    PORT       = cli_cfg["port"]
    HOST       = cli_cfg["host"]
    LOG_FORMAT = cli_cfg["log_format"]
    AUTH_HASH  = hash_token(AUTH_TOKEN) if AUTH_TOKEN else ""

    cli = cli_cfg["_cli"]
    if cli.version:
        print("Miser v1.5.0")
        _sys.exit(0)

    # ── Auto-discovery ───────────────────────────────────────────────────
    console.print()
    console.print(Panel("[bold cyan]Miser v1.5[/bold cyan] - Auto-detecting local LLM...",
                        border_style="cyan"))

    from backends import discover_backend
    backend = discover_backend()

    if backend is None:
        console.print()
        console.print("[red]No local LLM backend found![/red]")
        console.print()
        console.print("[yellow]Quick start - pick one:[/yellow]")
        console.print()
        console.print("  [bold]Option A: Ollama[/bold] (recommended, easiest)")
        console.print("    1. Download: https://ollama.com")
        console.print("    2. Install and run: ollama serve")
        console.print("    3. Pull a model:   ollama pull gemma4:latest")
        console.print("    4. Restart Miser:  miser")
        console.print()
        console.print("  [bold]Option B: LM Studio[/bold] (GUI)")
        console.print("    1. Download: https://lmstudio.ai")
        console.print("    2. Download any model in the app")
        console.print("    3. Start the local server (port 1234)")
        console.print("    4. Restart Miser:  miser")
        console.print()
        console.print("[dim]Zero-LLM endpoints (/read, /grep, /run, etc.) work without a model.[/dim]")
        console.print("[dim]Add --setup to see this guide again.[/dim]")
        console.print()
        NO_LLM = True
    else:
        NO_LLM = False
        if MODEL == "auto":
            models = backend.list_models()
            if models:
                MODEL = models[0]
                console.print(f"  [green]Auto-selected model: {MODEL}[/green]")
            else:
                console.print("  [yellow]No models found in backend. LLM features disabled.[/yellow]")
                console.print("  [dim]Pull a model first: ollama pull gemma4:latest[/dim]")
                NO_LLM = True

        if not NO_LLM:
            try:
                adapter = ModelAdapter(MODEL)
                console.print(f"  [dim]Model family: {adapter.family}[/dim]")
            except Exception as e:
                console.print(f"  [red]Model init failed: {e}[/red]")
                NO_LLM = True

    # ── Bootstrap ────────────────────────────────────────────────────────
    _bootstrap_flag = Path(__file__).parent / ".miser_bootstrapped"
    if not _bootstrap_flag.exists() and not os.environ.get("MISER_NO_WIZARD"):
        _bootstrap_flag.touch()

    # ── Update cross-module state ────────────────────────────────────────
    _admin.MODEL   = MODEL
    _admin.ADAPTER = adapter
    _admin.MEM     = mem
    _admin.BACKEND = backend

    # Structured logging
    _log.getLogger("werkzeug").setLevel(_log.WARNING)

    class JsonFormatter(_log.Formatter):
        def format(self, record):
            entry = {
                "timestamp":  datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "level":      record.levelname,
                "message":    record.getMessage(),
                "module":     record.name,
                "version":    "1.5.0",
            }
            if record.exc_info and record.exc_info[0]:
                import traceback
                entry["traceback"] = "".join(traceback.format_exception(*record.exc_info))
            return _json.dumps(entry, ensure_ascii=False)

    handlers = [_log.FileHandler(Path(__file__).parent / "miser.log"), _log.StreamHandler()]
    if LOG_FORMAT == "json":
        for h in handlers:
            h.setFormatter(JsonFormatter())
    else:
        fmt = _log.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        for h in handlers:
            h.setFormatter(fmt)

    _log.basicConfig(level=_log.INFO, handlers=handlers, force=True)
    _log.info(f"Miser v1.5.0 port={PORT} model={MODEL} backend={backend.name if backend else 'none'}")

    # Register security middleware
    app.before_request(rate_limit_middleware)
    app.after_request(cors_middleware)

    # Wire up cross-module callbacks
    _set_run(run_task)
    if adapter is not None:
        set_facade_model(MODEL, adapter, backend)

    # Start Flask
    threading.Thread(
        target=lambda: app.run(host=HOST, port=PORT),
        daemon=True
    ).start()

    # Graceful shutdown
    _shutdown_flag = threading.Event()

    def _handle_shutdown(sig, frame):
        _log.info(f"Signal {sig}, draining queue...")
        _shutdown_flag.set()
        q = get_queue()
        drained = 0
        while q.size > 0:
            task = q.dequeue()
            if task:
                run_task(task.task, task.sender, task.system, task.max_tokens, task.explicit_type)
                drained += 1
        _log.info(f"Shutdown complete. Drained {drained} tasks.")
        _sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    # Warmup LLM if available
    if not NO_LLM and adapter is not None:
        def _warmup():
            time.sleep(3)
            try:
                payload = adapter.generate_payload("", "ok", max_tokens=1)
                req.post(adapter.url, json=payload, timeout=60)
                _log.info("LLM warmed up")
                console.print("[dim green]v LLM warmed up[/dim green]")
            except Exception:
                pass
        threading.Thread(target=_warmup, daemon=True).start()

    auth_note   = "[yellow]AUTH enabled[/yellow]" if AUTH_TOKEN else "no auth"
    log_note    = "json" if LOG_FORMAT == "json" else "text"
    backend_note = f"{backend.name} @ {backend.base_url}" if backend else "none"
    model_note  = MODEL if not NO_LLM else "[yellow]none (zero-LLM only)[/yellow]"

    console.print(Panel(
        "[bold cyan]Miser v1.5[/bold cyan]  *  Agent-agnostic local co-processor\n\n"
        "[bold]Zero-LLM endpoints (<50ms):[/bold]\n"
        "  [green]/read /grep /outline /tree /exists /run /write /patch[/green]\n\n"
        "[bold]Local-LLM endpoints (0 API tokens):[/bold]\n"
        "  [cyan]/ask /codegen /explain /fix /test /review /summarize /git_summary /batch[/cyan]\n\n"
        "[bold]Admin endpoints:[/bold]\n"
        "  [magenta]/health /status /metrics /memory /openapi.json[/magenta]\n\n"
        f"[bold]Backend:[/bold] {backend_note}\n"
        f"[bold]Model:[/bold]   {model_note}\n"
        f"[bold]Auth:[/bold]    {auth_note}  [bold]Log:[/bold] {log_note}\n\n"
        f"[dim]http://{HOST}:{PORT}[/dim]",
        border_style="cyan", title="[bold]Ready[/bold]"
    ))
    _log.info("Ready.")
    console.print("[green]v Waiting...[/green]\n")

    while not _shutdown_flag.is_set():
        time.sleep(1)

if __name__ == "__main__":
    main()
