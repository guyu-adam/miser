"""
diff.py — Incremental Diff for Miser v1.5.5 (Tier 1 #6).
SHA-256 file fingerprinting + difflib Myers diff.
Zero-LLM: only changed files are returned; unchanged files → 0 tokens.
"""

import hashlib
import difflib
import os
import json
from pathlib import Path
from typing import Optional


def _sha256(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    try:
        with open(os.path.expanduser(path), "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except (FileNotFoundError, PermissionError, OSError):
        return ""
    return h.hexdigest()


def _fingerprint_dir(root: str, exclude: set = None) -> dict[str, str]:
    """Walk a directory and return {relpath: sha256} for all files."""
    if exclude is None:
        exclude = {"__pycache__", ".git", "node_modules", ".DS_Store", ".venv", "venv"}
    root = os.path.expanduser(root)
    if not os.path.isdir(root):
        return {}
    fps = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude]
        for fname in filenames:
            if fname in exclude:
                continue
            abspath = os.path.join(dirpath, fname)
            relpath = os.path.relpath(abspath, root)
            digest = _sha256(abspath)
            if digest:
                fps[relpath] = digest
    return fps


def diff_file(path: str, old_hash: str, old_content: str = "") -> dict:
    """
    Compute incremental diff for a single file.
    Returns {
        "path": ...,
        "changed": bool,
        "hash": current SHA-256,
        "diff": unified diff lines (empty if unchanged),
        "content": full content (only if changed),
        "savings": tokens saved vs full read
    }
    """
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return {"path": path, "changed": True, "hash": "", "diff": "FILE_DELETED",
                "content": "", "error": "File not found"}

    current_hash = _sha256(path)
    if not current_hash:
        return {"path": path, "changed": True, "hash": "", "diff": "UNREADABLE",
                "content": "", "error": "Permission denied or unreadable"}

    if old_hash == current_hash:
        # Unchanged — zero tokens
        return {"path": path, "changed": False, "hash": current_hash,
                "diff": "", "content": "",
                "savings": p.stat().st_size // 4}

    # Changed — compute diff
    current_text = p.read_text(errors="replace")
    old_lines = old_content.splitlines(keepends=True) if old_content else []
    new_lines = current_text.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"{path} (cached)", tofile=f"{path} (current)",
        lineterm=""
    ))

    diff_str = "\n".join(diff_lines) if diff_lines else "(binary or identical)"
    full_tokens = len(current_text) // 4
    diff_tokens = len(diff_str) // 4
    savings = full_tokens - diff_tokens

    return {"path": path, "changed": True, "hash": current_hash,
            "diff": diff_str, "content": current_text,
            "savings": savings, "full_tokens": full_tokens, "diff_tokens": diff_tokens}


def diff_dir(directory: str, old_snapshot: dict = None) -> dict:
    """
    Compare current directory file hashes against a previous snapshot.
    Returns {
      "unchanged": N,
      "changed": [list of relpaths],
      "added": [list of relpaths],
      "removed": [list of relpaths],
      "snapshot": {relpath: sha256}  (current snapshot for next call)
    }
    """
    current = _fingerprint_dir(directory)
    if old_snapshot is None:
        old_snapshot = {}

    old_keys = set(old_snapshot.keys())
    new_keys = set(current.keys())

    unchanged = [k for k in old_keys & new_keys if old_snapshot[k] == current[k]]
    changed  = [k for k in old_keys & new_keys if old_snapshot[k] != current[k]]
    added    = list(new_keys - old_keys)
    removed  = list(old_keys - new_keys)

    return {
        "unchanged": len(unchanged),
        "changed": changed,
        "added": added,
        "removed": removed,
        "snapshot": current,
        "total_files": len(current),
    }
