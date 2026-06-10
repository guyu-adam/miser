"""
search.py — Semantic search with embedding + BM25 fallback for Miser v1.5.5 (Tier 2 #5).

Two modes:
 1. Embedding mode (requires a running Ollama with embed model):
    Chunk files → embed chunks → cosine similarity → top-k results.
 2. BM25 keyword fallback (zero-dependency, always available):
    Tokenizes query into terms → ranks files by TF-IDF-like score.

Auto-detection: tries embedding first; falls back to BM25 if no embed model.
"""

import os, re, math, threading, subprocess
from pathlib import Path
from typing import Optional
from itertools import islice

# ── embedding client ─────────────────────────────────────────────────────────────

import requests as req

_embed_available = None          # None=unknown, True/False=known
_embed_lock = threading.Lock()
_embed_model = "nomic-embed-text"  # default; overridable
_ollama_url = "http://192.168.0.102:11434"
_pulling = False                  # True while background pull is running


def _ollama_alive() -> bool:
    """Check if Ollama server is reachable."""
    try:
        r = req.get(f"{_ollama_url}/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _start_pull():
    """Background pull of embedding model. Non-blocking."""
    global _pulling
    if _pulling:
        return
    _pulling = True

    def _pull():
        global _embed_available, _pulling
        try:
            subprocess.run(
                ["ollama", "pull", _embed_model],
                capture_output=True, text=True, timeout=600
            )
            # Re-check after pull
            with _embed_lock:
                try:
                    r = req.get(f"{_ollama_url}/api/tags", timeout=3)
                    models = [m["name"] for m in r.json().get("models", [])]
                    _embed_available = any(_embed_model in m for m in models)
                except Exception:
                    _embed_available = False
        except Exception:
            with _embed_lock:
                _embed_available = False
        finally:
            _pulling = False

    t = threading.Thread(target=_pull, daemon=True)
    t.start()


def _check_embed() -> bool:
    """Check if Ollama has the embedding model. Auto-pull if missing."""
    global _embed_available, _pulling
    if _embed_available is True:
        return True
    with _embed_lock:
        if _embed_available is True:
            return True
        if _embed_available is False and _pulling:
            # Still pulling — don't re-check, keep BM25
            return False
        try:
            r = req.get(f"{_ollama_url}/api/tags", timeout=3)
            models = [m["name"] for m in r.json().get("models", [])]
            _embed_available = any(_embed_model in m for m in models)
            if not _embed_available and not _pulling:
                # Ollama alive but no embed model → auto-pull in background
                _start_pull()
        except Exception:
            _embed_available = False
    return _embed_available


def _embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Batch-embed chunks via Ollama."""
    vectors = []
    for chunk in chunks:
        try:
            r = req.post(f"{_ollama_url}/api/embeddings", json={
                "model": _embed_model, "prompt": chunk
            }, timeout=10)
            vectors.append(r.json()["embedding"])
        except Exception:
            vectors.append([])
    return vectors


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-9)


# ── file chunker ─────────────────────────────────────────────────────────────────

_CHUNK_SIZE = 800  # chars per chunk


def _chunk_file(path: str, chunk_size: int = _CHUNK_SIZE) -> list[tuple[int, str]]:
    """Split a file into overlapping chunks. Returns [(line_start, chunk_text), ...]."""
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return []
    try:
        text = p.read_text(errors="replace")
    except Exception:
        return []
    lines = text.splitlines()
    chunks = []
    i = 0
    while i < len(lines):
        chunk_lines = lines[i:i + 50]  # ~50 lines per chunk
        chunk_text = "\n".join(chunk_lines)
        if len(chunk_text) > chunk_size:
            chunk_text = chunk_text[:chunk_size]
        chunks.append((i + 1, chunk_text))
        i += 25  # 50% overlap
    return chunks


# ── BM25 scorer (zero-dependency fallback) ───────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Simple tokenizer: split on non-alphanumeric, lowercase, filter short tokens."""
    tokens = re.findall(r"[a-zA-Z_]\w*", text.lower())
    return [t for t in tokens if len(t) > 1]


def _bm25_score(query_terms: list[str], doc_terms: list[str],
                avgdl: float, k1: float = 1.5, b: float = 0.75) -> float:
    if not doc_terms:
        return 0.0
    doc_len = len(doc_terms)
    term_freq = {}
    for t in doc_terms:
        term_freq[t] = term_freq.get(t, 0) + 1
    score = 0.0
    for term in set(query_terms):
        tf = term_freq.get(term, 0)
        if tf == 0:
            continue
        idf = math.log(1 + (avgdl - doc_len + 0.5) / (doc_len + 0.5) + 1)
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * doc_len / avgdl)
        score += idf * numerator / denominator
    return score


def _bm25_search(directory: str, query: str, top_k: int = 10,
                 exclude: set = None) -> list[dict]:
    """BM25 keyword search across all files in a directory."""
    if exclude is None:
        exclude = {"__pycache__", ".git", "node_modules", ".DS_Store", ".venv", "venv"}

    query_terms = _tokenize(query)
    if not query_terms:
        return []

    # Collect all files and tokenize
    files = []
    all_docs = []
    total_len = 0
    root = os.path.expanduser(directory)
    if not os.path.isdir(root):
        return []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude]
        for fname in filenames:
            if fname in exclude:
                continue
            abspath = os.path.join(dirpath, fname)
            relpath = os.path.relpath(abspath, root)
            try:
                text = Path(abspath).read_text(errors="replace")
            except Exception:
                text = ""
            terms = _tokenize(text)
            if not terms:
                continue
            files.append({"path": relpath, "terms": terms, "text": text})
            all_docs.append(terms)
            total_len += len(terms)

    if not all_docs:
        return []

    avgdl = total_len / len(all_docs) if all_docs else 1.0

    # Score all files
    ranked = []
    for f in files:
        score = _bm25_score(query_terms, f["terms"], avgdl)
        if score > 0:
            # Find best matching snippet
            lines = f["text"].splitlines()
            snippet = "\n".join(lines[:10]) + ("..." if len(lines) > 10 else "")
            ranked.append({
                "path": f["path"],
                "score": round(score, 4),
                "snippet": snippet,
                "method": "bm25",
            })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:top_k]


# ── embedding search ─────────────────────────────────────────────────────────────

def _embedding_search(directory: str, query: str, top_k: int = 10,
                      exclude: set = None) -> list[dict]:
    """Semantic search using embedding model. Falls back to BM25 on failure."""
    if exclude is None:
        exclude = {"__pycache__", ".git", "node_modules", ".DS_Store", ".venv", "venv"}

    # Create query embedding
    try:
        q_vecs = _embed_chunks([query])
        if not q_vecs or not q_vecs[0]:
            raise RuntimeError("embedding failed")
        q_vec = q_vecs[0]
    except Exception:
        return _bm25_search(directory, query, top_k, exclude)

    # Walk files and chunk
    root = os.path.expanduser(directory)
    if not os.path.isdir(root):
        return []

    file_chunks = []  # [(relpath, line_start, chunk_text), ...]
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude]
        for fname in filenames:
            if fname in exclude:
                continue
            abspath = os.path.join(dirpath, fname)
            relpath = os.path.relpath(abspath, root)
            for line_start, chunk in _chunk_file(abspath):
                file_chunks.append((relpath, line_start, chunk))

    if not file_chunks:
        return []

    # Batch embed all chunks
    chunk_texts = [c[2] for c in file_chunks]
    try:
        chunk_vecs = _embed_chunks(chunk_texts)
    except Exception:
        return _bm25_search(directory, query, top_k, exclude)

    # Score
    scored = []
    for idx, (relpath, line_start, chunk) in enumerate(file_chunks):
        if idx < len(chunk_vecs) and chunk_vecs[idx]:
            sim = _cosine(q_vec, chunk_vecs[idx])
            if sim > 0.2:  # relevance threshold
                scored.append({
                    "path": relpath,
                    "line": line_start,
                    "score": round(sim, 4),
                    "snippet": chunk[:300],
                    "method": "embedding",
                })

    scored.sort(key=lambda x: x["score"], reverse=True)
    # Deduplicate by path, keep best score
    seen = set()
    unique = []
    for s in scored:
        if s["path"] not in seen:
            seen.add(s["path"])
            unique.append(s)
    return unique[:top_k]


# ── public API ───────────────────────────────────────────────────────────────────

def search(directory: str, query: str, top_k: int = 10,
           exclude: list = None) -> dict:
    """
    Search a directory for files relevant to a query.
    Auto-selects embedding or BM25 based on availability.
    """
    exclude_set = set(exclude) if exclude else None

    if _check_embed():
        results = _embedding_search(directory, query, top_k, exclude_set)
    else:
        results = _bm25_search(directory, query, top_k, exclude_set)

    method = results[0]["method"] if results else "bm25 (no matches)"
    return {
        "query": query,
        "directory": directory,
        "method": method,
        "top_k": top_k,
        "results": results,
    }
