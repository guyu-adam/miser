"""
tools.py — Zero-LLM file & shell operations for Miser. All <50ms, deterministic.
"""

import os, re, subprocess, ast, operator, threading
from pathlib import Path

# ── i18n intent patterns (review item #10) ──────────────────────────────────────

I18N_PATTERNS = {
    "list_files": r"(ls|list|列出?|有什么|有哪些)",
    "file_dir_words": r"(文件|folder|目录|dir|~/|/\w)",
    "run_cmd": r"(run|exec|执行|运行)",
    "time_query": r"(几点|current time|what time|现在时间)",
    "exists_query": r"(exists?|存在|有没有)",
}

DANGEROUS_SHELL_PATTERNS = [
    re.compile(r'rm\s+-rf'), re.compile(r'>\s*/dev/'), re.compile(r'mkfs'),
    re.compile(r'dd\s+if='), re.compile(r'chmod\s+777'), re.compile(r':\(\)\s*\{'),
    re.compile(r'wget\s+\S+\s*-O\s*/'), re.compile(r'curl.*\|\s*(ba)?sh'),
    re.compile(r'sudo\s+'), re.compile(r'passwd'), re.compile(r'chown\s+-R\s+/'),
]

# ── token counter (thread-safe — review item #3) ────────────────────────────────

_tokens_saved = 0
_tokens_lock = threading.Lock()

def count_saved(chars: int):
    global _tokens_saved
    with _tokens_lock:
        _tokens_saved += int(chars / 4)   # ~4 chars per token for code/English

def get_tokens_saved() -> int:
    with _tokens_lock:
        return _tokens_saved

# ── safe math evaluator (review item #1) ────────────────────────────────────────

_SAFE_MATH_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.USub: operator.neg,
}

def _safe_eval(expr: str) -> str:
    """Evaluate a mathematical expression without exec/eval of arbitrary code."""
    try:
        tree = ast.parse(expr.replace("^", "**"), mode='eval')
        return str(_eval_node(tree.body))
    except Exception as e:
        return f"Math error: {e}"

def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        op = _SAFE_MATH_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _SAFE_MATH_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op(_eval_node(node.operand))
    raise ValueError(f"Unsupported expression type: {type(node).__name__}")

# ── file & shell operations ─────────────────────────────────────────────────────

def run_shell(cmd: str, timeout: int = 30) -> str:
    # Validate dangerous patterns (review item #2)
    for pat in DANGEROUS_SHELL_PATTERNS:
        if pat.search(cmd):
            return f"BLOCKED: dangerous command pattern detected ({pat.pattern})"
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return (r.stdout + r.stderr).strip() or "(no output)"

def read_file(path: str, limit: int = 8000) -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"File not found: {path}"
    text = p.read_text(errors="replace")
    return text[:limit] + (f"\n...[truncated, total {len(text)} chars]" if len(text) > limit else "")

def list_dir(path: str, pattern: str = "*") -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"Path not found: {path}"
    items = sorted(p.glob(pattern))
    return "\n".join(
        f"{'[dir]' if i.is_dir() else '[file]'} {i.name}  ({i.stat().st_size//1024}KB)"
        for i in items
    ) or "(empty)"

def grep_file(path: str, pattern: str, context: int = 2, ignore_case: bool = True) -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"File not found: {path}"
    lines = p.read_text(errors="replace").splitlines()
    flags = re.IGNORECASE if ignore_case else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as e:
        return f"Invalid pattern: {e}"
    matches = []
    seen = set()
    for i, line in enumerate(lines):
        if rx.search(line):
            start = max(0, i - context)
            end   = min(len(lines), i + context + 1)
            for j in range(start, end):
                if j not in seen:
                    seen.add(j)
                    matches.append(f"{j+1:4d}  {lines[j]}")
            matches.append("---")
    return "\n".join(matches).rstrip("---").strip() or f"No matches for: {pattern}"

def tree_view(path: str, depth: int = 2, exclude: str = "__pycache__,.git,node_modules,.DS_Store") -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"Path not found: {path}"
    excl = set(exclude.split(","))
    lines = [str(p)]
    def _walk(d: Path, prefix: str, level: int):
        if level > depth:
            return
        try:
            entries = sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return
        entries = [e for e in entries if e.name not in excl]
        for i, e in enumerate(entries):
            is_last = i == len(entries) - 1
            conn = "└── " if is_last else "├── "
            size = f" ({e.stat().st_size//1024}KB)" if e.is_file() else ""
            lines.append(f"{prefix}{conn}{e.name}{size}")
            if e.is_dir() and level < depth:
                ext = "    " if is_last else "│   "
                _walk(e, prefix + ext, level + 1)
    _walk(p, "", 1)
    return "\n".join(lines)

# Per-language outline patterns (review #14)
_OUTLINE_PATTERNS = {
    ".py":  [(r"^(\s*)(def |class |async def )(\w+)", "py")],
    ".js":  [(r"^(\s*)(function |class |const |let |var )(\w+)", "js"),
             (r"^(\s*)(export (?:default )?(?:function |class |const |let |var ))(\w+)", "js")],
    ".ts":  [(r"^(\s*)(function |class |const |interface |type |enum |export (?:default )?(?:function |class |const |interface |type |enum ))(\w+)", "ts")],
    ".tsx": [(r"^(\s*)(function |class |const |interface |type |export (?:default )?(?:function |class |const ))(\w+)", "tsx")],
    ".go":  [(r"^(\s*)(func |type |var |const )(\w+)", "go")],
    ".rs":  [(r"^(\s*)(fn |pub fn |struct |enum |trait |impl |mod |const |type )(\w+)", "rs")],
    ".java":[(r"^(\s*)(public |private |protected )?(class |interface |enum |@\w+\n\s*)?(\w+)", "java")],
    ".rb":  [(r"^(\s*)(def |class |module |attr_)(\w+)", "rb")],
    ".sh":  [(r"^(\s*)(\w+\(\)|function \w+)", "sh")],
    ".sql": [(r"^(?i)(CREATE (?:TABLE|INDEX|VIEW|FUNCTION|PROCEDURE|TRIGGER) )(\w+)", "sql")],
}


def outline_file(path: str) -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"File not found: {path}"
    text = p.read_text(errors="replace")
    lines = text.splitlines()
    suffix = p.suffix.lower()
    patterns = _OUTLINE_PATTERNS.get(suffix, _OUTLINE_PATTERNS.get(".py"))
    results = []

    for i, line in enumerate(lines):
        for regex, _ in patterns:
            m = re.match(regex, line)
            if m:
                indent = len(m.group(1) or "") // 4
                # Extract kind and name from match groups
                all_groups = m.groups()
                kind = all_groups[-2].strip() if len(all_groups) >= 3 else ""
                name = all_groups[-1]
                doc = ""
                if i + 1 < len(lines):
                    dl = lines[i + 1].strip()
                    if dl.startswith('"""') or dl.startswith("'''") or dl.startswith("//") or dl.startswith("--"):
                        doc = " — " + dl.strip('"\' /-')[:60]
                results.append(f"{'  ' * indent}{kind} {name}{doc}  [L{i+1}]")
                break  # one match per line

    return "\n".join(results) or "(no functions/classes found)"

def write_to_file(path: str, content: str) -> str:
    p = Path(os.path.expanduser(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Written {len(content)} chars to {path}"

def patch_file(path: str, old: str, new: str) -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"File not found: {path}"
    text = p.read_text(errors="replace")
    count = text.count(old)
    if count == 0:
        return f"Pattern not found in {path}"
    updated = text.replace(old, new, 1)
    p.write_text(updated)
    return f"Patched {path}: replaced 1/{count} occurrence(s), {len(old)}→{len(new)} chars"

# ── path extraction (review item #5) ────────────────────────────────────────────

def extract_path(task: str, default: str) -> str:
    """Extract a file path from natural language task string.
    Uses shlex-style quote-aware parsing for paths with spaces."""
    # Try quoted paths first
    m = re.search(r"""['"](~/[^'"]+|/[^'"]+)['"]""", task)
    if m:
        return os.path.expanduser(m.group(1))
    # Unquoted paths
    m = re.search(r"(~/[^\s,;]+|/[^\s,;]+)", task)
    if m:
        return m.group(1)
    # Keyword fallback
    for kw, path in [("桌面","~/Desktop"),("desktop","~/Desktop"),("下载","~/Downloads")]:
        if kw.lower() in task.lower():
            return path
    return default
