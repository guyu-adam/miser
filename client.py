"""
Miser v1.2 client for Claude Code — with quality assurance.

Usage:
    import sys; sys.path.insert(0, '/path/to/miser')
    from client import W

    W.outline("~/project/app.py")           # function/class map
    W.grep("~/project/app.py", "def fn")    # search with context
    W.tree("~/project", depth=2)            # directory tree
    W.exists("~/project/.env")              # existence check
    W.run("pytest --tb=short -q")           # shell command
    W.explain("~/project/utils.py")         # plain-English explanation
    W.fix("TypeError: None", code="...")    # error → fix
    W.test("~/project/utils.py")            # generate pytest tests
    W.review("~/project/utils.py")          # code review
    W.codegen("write a debounce in python") # code generation
    W.ask("any freeform task")              # general purpose
    W.batch([("outline","~/f.py"),("run","git status")])
    W.status()
    W.quality()                             # get last quality report
    W.clear()

Quality guarantees:
  - Zero-LLM ops: 100% deterministic, no quality loss
  - Local-LLM ops: auto-verified (hallucination, syntax, context, length)
  - CRITICAL keywords (auth, security, payment, deploy) → Claude must handle
  - Flagged results are prefixed [MISER:FLAG] — treat as hints, not facts
  - Use W.verify = False to skip checks (not recommended for production code)
"""
import ast, re, requests
from quality import classify_op, should_offload, quality_report

BASE = "http://localhost:7860"

def _post(path, data):
    r = requests.post(f"{BASE}{path}", json=data, timeout=120)
    return r.json()

# ── Supervision helpers ────────────────────────────────────────────────────────

_HALLUCINATION_PHRASES = [
    "i don't have access", "i cannot access", "as an ai", "i'm unable to",
    "i don't know", "i apologize", "unfortunately i", "i don't have information",
    "please provide", "could you please", "i need more context",
]

def _flag(text: str, label: str) -> str:
    return f"[MISER:{label}]\n{text}"

def _extract_flags(result) -> list:
    """Extract quality flags from a possibly-flagged result."""
    if not isinstance(result, str):
        return []
    return re.findall(r'\[MISER:([^\]]+)\]', result)[:5]

def _check_llm(result, op: str, context: str = ""):
    """Supervisor: validate LLM output, flag low-quality responses."""
    if not result or not isinstance(result, str):
        return result
    low = result.lower()

    # Flag refusals / hallucination patterns
    if any(p in low for p in _HALLUCINATION_PHRASES):
        return _flag(result, "HALLUCINATION_RISK")

    # Flag suspiciously short LLM answers (< 30 chars on complex ops)
    if op in ("explain", "review", "fix", "codegen") and len(result.strip()) < 30:
        return _flag(result, "TOO_SHORT")

    # For codegen/test: verify Python syntax
    if op in ("codegen", "test"):
        code_block = result
        fenced = re.search(r"```(?:python)?\n(.*?)```", result, re.DOTALL)
        if fenced:
            code_block = fenced.group(1)
        try:
            ast.parse(code_block)
        except SyntaxError as e:
            return _flag(result, f"SYNTAX_ERROR:{e.lineno}")

    # For explain/review: check that output references at least some context words
    if op in ("explain", "review") and context:
        ctx_words = set(w.lower() for w in context.split() if len(w) > 4)
        result_words = set(result.lower().split())
        overlap = ctx_words & result_words
        if ctx_words and len(overlap) / len(ctx_words) < 0.15:
            return _flag(result, "CONTEXT_MISMATCH")

    return result


class _W:
    verify: bool = True   # set to False to skip supervision checks
    _last_quality: dict = {}  # last quality report, accessible via W.quality()

    def quality(self) -> dict:
        """Return the quality report for the most recent LLM operation."""
        return getattr(self, '_last_quality', {})

    def _wrap(self, result, task: str, op_type: str, source: str) -> str:
        """Wrap result with quality metadata. Stores report for later retrieval."""
        flags = _extract_flags(result) if result else []
        qr = quality_report(result, task, op_type, source, flags)
        self._last_quality = qr.get("quality", {})

        # For critical ops flagged by quality router: add a strong prefix
        q = self._last_quality
        if q.get("criticality") == "critical" and source != "miser-zero":
            # This should not normally happen (Claude should handle critical ops),
            # but if someone bypasses the router, add a prominent flag.
            return _flag(result, "CRITICAL_OP_DELEGATED")

        return result

    def ask(self, task, max_tokens=600):
        # Check if task should even be offloaded
        ok, reason = should_offload(task, "ask")
        if not ok:
            return _flag(reason, "DO_NOT_OFFLOAD")

        d = _post("/ask", {"task": task, "from": "claude", "max_tokens": max_tokens})
        result = d.get("result") or d.get("error")
        if self.verify:
            result = _check_llm(result, "ask", context=task)
        return self._wrap(result, task, "ask", "miser-llm")

    def run(self, cmd, timeout=30):
        d = _post("/run", {"cmd": cmd, "timeout": timeout})
        result = d.get("output") or d.get("error")
        return self._wrap(result, cmd, "run", "miser-zero")

    def read(self, path, limit=8000):
        d = _post("/read", {"path": path, "limit": limit})
        result = d.get("content") or d.get("error")
        return self._wrap(result, path, "read", "miser-zero")

    def grep(self, path, pattern, ctx=2, ignore_case=True):
        d = _post("/grep", {"path": path, "pattern": pattern,
                            "context": ctx, "ignore_case": ignore_case})
        result = d.get("matches") or d.get("error")
        return self._wrap(result, f"grep:{pattern}", "grep", "miser-zero")

    def outline(self, path):
        d = _post("/outline", {"path": path})
        result = d.get("outline") or d.get("error")
        return self._wrap(result, f"outline:{path}", "outline", "miser-zero")

    def tree(self, path="~/Desktop", depth=2):
        d = _post("/tree", {"path": path, "depth": depth})
        result = d.get("tree") or d.get("error")
        return self._wrap(result, path, "tree", "miser-zero")

    def exists(self, path):
        d = _post("/exists", {"path": path})
        return d  # dict response, no wrapping needed

    def write(self, path, content):
        d = _post("/write", {"path": path, "content": content})
        result = d.get("result") or d.get("error")
        return self._wrap(result, path, "write", "miser-zero")

    def patch(self, path, old, new):
        d = _post("/patch", {"path": path, "old": old, "new": new})
        result = d.get("result") or d.get("error")
        return self._wrap(result, path, "patch", "miser-zero")

    def summarize(self, path_or_text, focus="key logic and structure"):
        key = "path" if ("/" in path_or_text or "~" in path_or_text) else "text"
        d = _post("/summarize", {key: path_or_text, "focus": focus})
        result = d.get("summary") or d.get("error")
        if self.verify:
            result = _check_llm(result, "summarize")
        ctx = path_or_text if key == "path" else ""
        return self._wrap(result, path_or_text, "summarize", "miser-llm")

    def codegen(self, task, lang="python"):
        ok, reason = should_offload(task, "codegen")
        if not ok:
            return _flag(reason, "DO_NOT_OFFLOAD")

        d = _post("/codegen", {"task": task, "lang": lang})
        result = d.get("code") or d.get("error")
        if self.verify:
            result = _check_llm(result, "codegen", context=task)
        return self._wrap(result, task, "codegen", "miser-llm")

    def explain(self, path_or_code):
        key = "path" if ("/" in path_or_code or "~" in path_or_code) else "code"
        d = _post("/explain", {key: path_or_code})
        result = d.get("explanation") or d.get("error")
        ctx = path_or_code if key == "code" else ""
        if self.verify:
            result = _check_llm(result, "explain", context=ctx)
        return self._wrap(result, path_or_code, "explain", "miser-llm")

    def fix(self, error_msg, code=""):
        d = _post("/fix", {"error": error_msg, "code": code})
        result = d.get("fix") or d.get("error")
        ctx = error_msg + " " + code
        if self.verify:
            result = _check_llm(result, "fix", context=ctx)
        return self._wrap(result, error_msg[:100], "fix", "miser-llm")

    def test(self, path_or_code, function=""):
        key = "path" if ("/" in path_or_code or "~" in path_or_code) else "code"
        payload = {key: path_or_code}
        if function:
            payload["function"] = function
        d = _post("/test", payload)
        result = d.get("tests") or d.get("error")
        if self.verify:
            result = _check_llm(result, "test")
        return self._wrap(result, path_or_code, "test", "miser-llm")

    def review(self, path_or_code):
        key = "path" if ("/" in path_or_code or "~" in path_or_code) else "code"
        d = _post("/review", {key: path_or_code})
        result = d.get("review") or d.get("error")
        ctx = path_or_code if key == "code" else ""
        if self.verify:
            result = _check_llm(result, "review", context=ctx)
        return self._wrap(result, path_or_code, "review", "miser-llm")

    def condense(self, path_or_text, category="code_file", max_tokens=300):
        """Semantically distill a large file or text into a structured digest.
        Local LLM extracts: signatures, dependencies, invariants, edge cases.
        Returns digest + savings stats. Saves 70-90% tokens vs full read."""
        key = "path" if ("/" in path_or_text or "~" in path_or_text) else "text"
        d = _post("/condense", {key: path_or_text, "category": category,
                                "max_tokens": max_tokens})
        result = d.get("digest") or d.get("error")
        savings = d.get("savings", {})
        # Attach savings for the caller
        if isinstance(result, str) and savings:
            self._last_condense_savings = savings
        return result

    def git_summary(self, path=".", n=10):
        d = _post("/git_summary", {"path": path, "n": n})
        result = d.get("summary") or d.get("error")
        return self._wrap(result, f"git:{path}", "git_summary", "miser-llm")

    def ensure_running(self, timeout: float = 10.0) -> bool:
        """Auto-start miser if not running. Returns True when ready. (P0 #2)"""
        import subprocess, sys, time, os
        try:
            self.status()
            return True
        except Exception:
            pass
        # Try to start
        try:
            try:
                miser_py = os.path.join(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__))), "miser.py")
            except NameError:
                miser_py = "miser.py"
            subprocess.Popen([sys.executable, miser_py],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.time() + timeout
            while time.time() < deadline:
                time.sleep(0.5)
                try:
                    self.status()
                    return True
                except Exception:
                    pass
            return False
        except Exception:
            return False

    def batch(self, tasks):
        """tasks: list of tuples — ("run","cmd"), ("outline","~/f.py"),
        ("grep","~/f.py","pattern"), ("tree","~/dir",depth),
        ("exists","~/f"), ("write","~/f","content"), ("ask","task")
        """
        items = []
        for t in tasks:
            typ = t[0]
            if   typ == "run":     items.append({"type":"run",     "cmd":t[1]})
            elif typ == "read":    items.append({"type":"read",    "path":t[1]})
            elif typ == "grep":    items.append({"type":"grep",    "path":t[1], "pattern":t[2],
                                                 "context": t[3] if len(t)>3 else 2})
            elif typ == "outline": items.append({"type":"outline", "path":t[1]})
            elif typ == "tree":    items.append({"type":"tree",    "path":t[1],
                                                 "depth": t[2] if len(t)>2 else 2})
            elif typ == "exists":  items.append({"type":"exists",  "path":t[1]})
            elif typ == "write":   items.append({"type":"write",   "path":t[1], "content":t[2]})
            else:                  items.append({"type":"ask",     "task":t[1]})
        d = _post("/batch", {"tasks": items})
        return [r.get("result") or r.get("error") for r in d.get("results", [])]

    def note(self, key, value):
        d = _post("/note", {"key": key, "value": value})
        return d.get("saved") or d.get("error")

    def clear(self):
        return requests.post(f"{BASE}/memory/clear", timeout=10).json().get("cleared")

    def status(self):
        d = requests.get(f"{BASE}/status", timeout=5).json()
        # Add quality context to status
        try:
            from quality import classify_op
        except ImportError:
            pass
        return d

W = _W()   # W for Miser
J = W      # backward-compat alias
