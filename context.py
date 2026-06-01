"""
context.py — Project awareness for Miser v1.5.4.

Provides miser_context — a zero-token tool that gives the agent a compact
snapshot of the current project: git status, recent file changes, project
structure, and last conversation context.

All operations are local and instantaneous (<50ms). No LLM involved.
"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


def _run(cmd: str, cwd: str = ".", timeout: int = 3) -> str:
    """Run a shell command, return stdout or '' on failure."""
    import subprocess
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            cwd=cwd, timeout=timeout,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {})
        )
        return r.stdout.strip()
    except Exception:
        return ""


def _is_git_repo(path: str) -> bool:
    """Check if path is inside a git repo."""
    return _run("git rev-parse --is-inside-work-tree 2>nul" if os.name == "nt" else
                "git rev-parse --is-inside-work-tree 2>/dev/null", cwd=path) == "true"


def _git_info(path: str) -> dict:
    """Extract git status info. Returns compact dict."""
    if not _is_git_repo(path):
        return {}

    info = {}

    # Branch
    branch = _run("git branch --show-current", cwd=path)
    if branch:
        info["branch"] = branch

    # Behind origin by N commits
    behind = _run("git rev-list --count HEAD..@{u} 2>/dev/null", cwd=path)
    if behind and behind.isdigit() and int(behind) > 0:
        info["behind"] = int(behind)

    # Modified (staged + unstaged)
    modified = _run("git diff --name-only HEAD 2>/dev/null", cwd=path)
    if modified:
        info["modified"] = [f.strip() for f in modified.split("\n") if f.strip()][:10]

    # Untracked
    untracked = _run("git ls-files --others --exclude-standard 2>/dev/null", cwd=path)
    if untracked:
        info["untracked"] = [f.strip() for f in untracked.split("\n") if f.strip()][:10]

    # Recent commits (for context on what's being worked on)
    recent = _run('git log --oneline --no-decorate -5 2>/dev/null', cwd=path)
    if recent:
        info["recent_commits"] = [
            line.strip() for line in recent.split("\n") if line.strip()
        ][:5]

    return info


def _project_stats(path: str) -> dict:
    """Quick project stats: file counts by extension, directory depth."""
    p = Path(path).resolve()
    stats = {"name": p.name, "files": 0, "extensions": {}}

    try:
        for f in p.rglob("*"):
            if f.is_file() and not _should_skip(f):
                stats["files"] += 1
                ext = f.suffix.lower() or "(no ext)"
                stats["extensions"][ext] = stats["extensions"].get(ext, 0) + 1
    except (PermissionError, OSError):
        pass

    # Top extensions
    top = sorted(stats["extensions"].items(), key=lambda x: -x[1])[:5]
    stats["top_extensions"] = [f"{ext}({n})" for ext, n in top]

    # Detect primary language
    lang_map = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".rs": "Rust", ".go": "Go", ".java": "Java", ".rb": "Ruby",
        ".c": "C", ".cpp": "C++", ".html": "HTML", ".css": "CSS",
        ".sh": "Shell", ".md": "Markdown", ".json": "JSON", ".yaml": "YAML",
    }
    primary_ext = top[0][0] if top else ""
    stats["language"] = lang_map.get(primary_ext, primary_ext.lstrip(".").upper() or "Unknown")

    return stats


def _should_skip(f: Path) -> bool:
    """Skip common noise dirs/files."""
    skip_dirs = {".git", "__pycache__", "node_modules", "venv", ".venv",
                 ".idea", ".vscode", ".DS_Store", "target", "build", "dist"}
    skip_exts = {".pyc", ".pyo", ".class", ".o", ".so", ".dll", ".exe"}
    return (any(d in f.parts for d in skip_dirs) or
            f.name in skip_dirs or
            f.suffix in skip_exts or
            f.name.startswith("."))


def _recent_files(path: str, minutes: int = 60) -> list[dict]:
    """Files modified in the last N minutes."""
    cutoff = time.time() - minutes * 60
    recent = []
    p = Path(path).resolve()

    try:
        for f in p.rglob("*"):
            if f.is_file() and not _should_skip(f):
                try:
                    mtime = f.stat().st_mtime
                    if mtime >= cutoff:
                        recent.append({
                            "path": str(f.relative_to(p)),
                            "minutes_ago": int((time.time() - mtime) / 60),
                        })
                except OSError:
                    pass
    except (PermissionError, OSError):
        pass

    recent.sort(key=lambda x: x["minutes_ago"])
    return recent[:8]


def _last_conversation(mem) -> str:
    """Extract recent conversation topics from Miser memory."""
    if mem is None:
        return ""
    try:
        recent = getattr(mem, "history", [])
        if not recent:
            return ""
        tasks = [h.get("task", "") for h in recent[-5:]]
        return " | ".join(t[:80] for t in tasks if t)
    except Exception:
        return ""


# ── Public API ──────────────────────────────────────────────────────────────

def scan(path: str = ".", mem=None) -> dict:
    """Full project context scan. All local, zero tokens."""
    p = str(Path(path).resolve())

    info = _project_stats(p)
    info["git"] = _git_info(p)
    info["recent_changes"] = _recent_files(p)
    info["conversation"] = _last_conversation(mem)
    info["timestamp"] = datetime.now().strftime("%H:%M:%S")

    return info


def summary(path: str = ".", mem=None) -> str:
    """Compact 4-7 line summary for agent consumption."""
    s = scan(path, mem)

    lines = []
    # Line 1: project name, language, file count
    lines.append(f"📁 {s['name']}/ ({s['language']}, {s['files']} files)")

    # Line 2: git status
    g = s.get("git", {})
    if g:
        parts = [f"🌿 {g.get('branch', '?')}"]
        if g.get("behind"):
            parts.append(f"↓{g['behind']}")
        parts.append("← origin")
        if g.get("modified"):
            parts.append(f"✏️ {', '.join(g['modified'][:3])}")
        lines.append("  ".join(parts))

        if g.get("untracked"):
            lines.append(f"📄 new: {', '.join(g['untracked'][:3])}")

    # Line 3-4: recent file changes
    recent = s.get("recent_changes", [])
    if recent:
        changed = ", ".join(
            f"{r['path']} ({r['minutes_ago']}m)" for r in recent[:4]
        )
        lines.append(f"🕐 {changed}")

    # Line 5: last conversation context
    conv = s.get("conversation", "")
    if conv:
        lines.append(f"💬 {conv}")

    return "\n".join(lines)


# ── Path override (so Miser can change scan root) ───────────────────────────

_SCAN_ROOT = "."


def set_scan_root(path: str):
    """Set the default scan root for context operations."""
    global _SCAN_ROOT
    _SCAN_ROOT = str(Path(path).resolve())


def get_scan_root() -> str:
    return _SCAN_ROOT
