"""
Miser v1.1 — Claude Code's local co-processor.
Two execution paths:
  1. Zero-LLM (<50ms): shell, file read/write/grep/tree/exists/outline/patch
  2. Local LLM (no API cost): summarize, codegen, explain, fix, test, review, git_summary
"""

import os, re, threading, time
from datetime import datetime
from pathlib import Path

os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"

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

console = Console()
app = Flask(__name__)

MODEL = os.environ.get("MISER_MODEL", "miser-qwen")
AUTH_TOKEN = os.environ.get("MISER_AUTH_TOKEN", "")   # review item #4: optional token

adapter = ModelAdapter(MODEL)
mem = Memory()

# ── state ───────────────────────────────────────────────────────────────────────

class State:
    def __init__(self):
        self.status = "IDLE"
        self.task   = "—"
        self.result = ""
        self.count  = 0
        self._lock  = threading.Lock()
    def set(self, status, task=None):
        with self._lock:
            self.status = status
            if task is not None: self.task = task

st = State()

# ── auth helper (review item #4) ────────────────────────────────────────────────

def _check_auth(req_data: dict) -> bool:
    """If AUTH_TOKEN is configured, require it in every request."""
    if not AUTH_TOKEN:
        return True
    token = (req_data or {}).get("_token", "")
    return token == AUTH_TOKEN

# ── LLM call ────────────────────────────────────────────────────────────────────

def llm(task: str, system: str = "", max_tokens: int = 600, mode: str = "text") -> str:
    is_code    = mode == "code"    or re.search(r'\b(write|def|function|code|implement|class)\b', task, re.I)
    is_bullets = mode == "bullets" or re.search(r'\b(summarize|bullet|list|summary|points)\b', task, re.I)
    detected_mode = "code" if is_code and not is_bullets else ("bullets" if is_bullets else "text")

    sys_prompt = "You are Miser, Claude Code's local assistant.\nOutput ONLY the final answer, no preamble.\n"
    if detected_mode == "text":
        ctx_text = mem.ctx(task)
        if ctx_text:
            sys_prompt += f"Context: {ctx_text}\n"
    if system:
        sys_prompt += system

    payload = adapter.generate_payload(sys_prompt, task, max_tokens=max_tokens)

    for attempt in range(3):
        try:
            resp = req.post(adapter.url, json=payload, timeout=240)
            raw  = adapter.extract_text(resp.json())
            if raw:
                answer = adapter.clean(raw, mode=detected_mode)
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

# Legacy regex routing — now only for /ask fallback (review item #9)
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
        st.set("IDLE", "—")
    return result

# ── endpoints ────────────────────────────────────────────────────────────────────

def _auth_fail():
    return jsonify({"error": "unauthorized — MISER_AUTH_TOKEN required"}), 401

@app.route("/status")
def status():
    pref = prefetch_stats()
    return jsonify({
        "status":           st.status,
        "task":             st.task,
        "count":            st.count,
        "last":             st.result,
        "tokens_saved_est": get_tokens_saved(),
        "model":            MODEL,
        "model_family":     adapter.family,
        "prefetch":         pref,
    })

@app.route("/memory")
def memory():
    return jsonify({"notes": mem.notes, "history": mem.history[-10:]})

@app.route("/ask", methods=["POST"])
def ask():
    d = request.json or {}
    if not _check_auth(d): return _auth_fail()       # review item #4
    task = d.get("task","").strip()
    if not task: return jsonify({"error":"task required"}), 400
    if st.status == "WORKING": return jsonify({"error":"busy"}), 429
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
    if st.status == "WORKING": return jsonify({"error":"busy"}), 429
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
    if st.status == "WORKING": return jsonify({"error":"busy"}), 429
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[cyan]codegen  {ts}[/cyan]"))
    result = llm(task, system=f"Output {lang} code only. No explanation. No markdown fences.\n",
                 max_tokens=700)
    console.print(Panel(result, title="[cyan]code[/cyan]", border_style="cyan"))
    st.count += 1
    mem.record(st.count, task, result[:200])
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

@app.route("/memory/clear", methods=["POST"])
def memory_clear():
    if not _check_auth(request.json or {}): return _auth_fail()
    mem.clear()
    return jsonify({"cleared": True, "notes": mem.notes})

@app.route("/note", methods=["POST"])
def note():
    d = request.json or {}
    key = d.get("key","").strip()
    val = d.get("value","").strip()
    if not key or not val: return jsonify({"error":"key and value required"}), 400
    mem.save(key, val)
    return jsonify({"saved": {key: val}})

# ── main ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    # Review item #12: threaded=True is deprecated in Flask 2.3+, removed.
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=7860),
        daemon=True
    ).start()

    def _warmup():
        """Pre-load the LLM into memory so it's ready on first real request."""
        time.sleep(3)
        try:
            payload = adapter.generate_payload("", "ok", max_tokens=1)
            req.post(adapter.url, json=payload, timeout=60)
            console.print("[dim green]✓ LLM warmed up[/dim green]")
        except Exception:
            pass
    threading.Thread(target=_warmup, daemon=True).start()

    auth_note = "[yellow]AUTH enabled[/yellow]" if AUTH_TOKEN else "no auth"
    console.print(Panel(
        "[bold cyan]Miser v1.1[/bold cyan]  ·  Claude Code's local co-processor\n\n"
        "[bold]Zero-LLM endpoints (<50ms):[/bold]\n"
        "  [green]/run /read /grep /outline /tree /exists /write /patch[/green]\n\n"
        "[bold]Local-LLM endpoints (0 API tokens):[/bold]\n"
        "  [cyan]/ask /summarize /codegen /explain /fix /test /review /git_summary /batch[/cyan]\n\n"
        f"[bold]Model:[/bold]  {MODEL}  (family: {adapter.family})\n"
        f"[bold]Auth:[/bold]   {auth_note}\n"
        f"[bold]Memory:[/bold] {len(mem.notes)} notes · {len(mem.history)} past tasks\n"
        "[dim]http://localhost:7860[/dim]",
        border_style="cyan", title="[bold]Ready[/bold]"
    ))
    console.print("[green]✓ Waiting...[/green]\n")

    while True:
        time.sleep(1)
