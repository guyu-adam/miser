"""
memory.py — Persistent memory with semantic search for Miser.
"""

import json, math, threading
from datetime import datetime
from pathlib import Path
import requests as req

MEMORY_FILE = Path(__file__).parent / "memory.json"
EMBED_FILE  = Path(__file__).parent / "embeddings.json"
EMBED_URL   = "http://192.168.0.102:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"

MAX_NOTES  = 200   # cap notes dictionary size (review item #7)
MAX_HIST   = 40    # keep latest N history entries


class Memory:
    def __init__(self):
        self.notes: dict = {}
        self.history: list = []
        self.embeddings: list = []
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if MEMORY_FILE.exists():
            try:
                d = json.loads(MEMORY_FILE.read_text())
                self.notes   = d.get("notes", {})
                self.history = d.get("history", [])
            except Exception:
                pass
        if EMBED_FILE.exists():
            try:
                self.embeddings = json.loads(EMBED_FILE.read_text())
            except Exception:
                pass

    def _save(self):
        self.history = self.history[-MAX_HIST:]
        MEMORY_FILE.write_text(json.dumps(
            {"notes": self.notes, "history": self.history},
            ensure_ascii=False, indent=2
        ))

    def _save_embeddings(self):
        self.embeddings = self.embeddings[-MAX_HIST:]
        EMBED_FILE.write_text(json.dumps(self.embeddings, ensure_ascii=False))

    def _embed(self, text: str) -> list:
        try:
            r = req.post(EMBED_URL, json={"model": EMBED_MODEL, "prompt": text}, timeout=10)
            return r.json().get("embedding", [])
        except Exception:
            return []

    def _cosine(self, a: list, b: list) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na  = math.sqrt(sum(x * x for x in a))
        nb  = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na and nb else 0.0

    def clear(self):
        with self._lock:
            self.history = []
            self.embeddings = []
            self._save()
            if EMBED_FILE.exists():
                EMBED_FILE.unlink()

    def save(self, key: str, val: str):
        with self._lock:
            self.notes[key] = val
            # Cap notes size: keep only the most recent MAX_NOTES entries.
            # dicts preserve insertion order in Python 3.7+, so simply
            # pop the oldest (first) keys until we're within bounds.
            while len(self.notes) > MAX_NOTES:
                oldest_key = next(iter(self.notes))
                del self.notes[oldest_key]
            self._save()

    def record(self, tid: int, task: str, result: str):
        with self._lock:
            # Don't _load() here — it discards in-memory changes from
            # other threads. We already loaded in __init__.
            self.history.append({
                "id": tid,
                "time": datetime.now().strftime("%m-%d %H:%M"),
                "task": task[:100],
                "result": result[:200],
            })
            self._save()
        def _do_embed():
            emb = self._embed(task)
            if emb:
                with self._lock:
                    self.embeddings.append({
                        "id": tid, "task": task[:100],
                        "result": result[:200], "emb": emb
                    })
                    self._save_embeddings()
        threading.Thread(target=_do_embed, daemon=True).start()

    def ctx(self, current_task: str = "") -> str:
        out = []
        if self.notes:
            out.append("Notes: " + " | ".join(f"{k}={v}" for k, v in list(self.notes.items())[-6:]))
        if not self.history:
            return "\n".join(out)
        if current_task and self.embeddings:
            q_emb = self._embed(current_task)
            if q_emb:
                scored = sorted(
                    self.embeddings, key=lambda e: self._cosine(q_emb, e["emb"]), reverse=True
                )[:3]
                out.append("Relevant: " + " | ".join(
                    f"#{e['id']} \"{e['task'][:50]}\"→{e['result'][:60]}" for e in scored
                ))
                return "\n".join(out)
        out.append("Recent: " + " | ".join(
            f"#{h['id']} \"{h['task'][:50]}\"→{h['result'][:60]}"
            for h in self.history[-3:]
        ))
        return "\n".join(out)
