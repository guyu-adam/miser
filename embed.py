"""
embed.py — Embedding infrastructure for Miser v1.5.5.

Powers two features:
  #5 Semantic Search (miser_search): embed query → kNN over chunk embeddings
  #2 Semantic Cache (miser_read): embed path+query → return cached result if similar

Uses Ollama's nomic-embed-text for embeddings (already available if Ollama is running).
Falls back to zero-LLM mode if embeddings unavailable.
"""

import json
import math
import threading
from pathlib import Path
from typing import Optional

import requests as req

EMBED_URL = "http://192.168.0.102:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
CACHE_FILE = Path(__file__).parent / "embed_cache.json"

_cache_lock = threading.Lock()
_cache: dict = {}  # key → {"query": str, "embedding": list[float], "result": str}


def _load_cache():
    """Load persisted embedding cache."""
    global _cache
    if CACHE_FILE.exists():
        try:
            _cache = json.loads(CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            _cache = {}


def _save_cache():
    """Persist cache, cap at 200 entries."""
    capped = dict(list(_cache.items())[-200:])
    CACHE_FILE.write_text(json.dumps(capped, ensure_ascii=False))


def embed(text: str) -> list[float]:
    """Get embedding vector for text. Returns [] if Ollama unavailable."""
    try:
        r = req.post(EMBED_URL, json={"model": EMBED_MODEL, "prompt": text}, timeout=10)
        if r.status_code == 200:
            emb = r.json().get("embedding", [])
            if emb:
                return emb
    except Exception:
        pass
    return []


def cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


# ═══════════════════════════════════════════════════════════════════════════
#  #5 SEMANTIC SEARCH
# ═══════════════════════════════════════════════════════════════════════════

def chunk_file(path: str, chunk_size: int = 512, overlap: int = 64) -> list[dict]:
    """
    Split file into overlapping chunks.
    Returns [{"index": 0, "text": "...", "start_line": 1, "end_line": N}, ...]
    """
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    lines = content.split("\n")
    chunks = []
    i = 0
    chunk_idx = 0
    
    while i < len(lines):
        end = min(i + chunk_size, len(lines))
        chunk_lines = lines[i:end]
        chunk_text = "\n".join(chunk_lines)
        chunks.append({
            "index": chunk_idx,
            "text": chunk_text,
            "start_line": i + 1,
            "end_line": end,
        })
        chunk_idx += 1
        i += (chunk_size - overlap)
        if i >= len(lines):
            break
    
    return chunks


def search(query: str, path: str, top_k: int = 3, threshold: float = 0.3) -> str:
    """
    Semantic search inside a file.
    
    1. Chunk the file
    2. Embed the query
    3. Embed all chunks (or load cached)
    4. Return top_k most similar chunks
    
    Returns formatted string or error message.
    """
    # Check file exists
    p = Path(path)
    if not p.exists():
        return f"File not found: {path}"
    
    # Get query embedding
    q_emb = embed(query)
    if not q_emb:
        return f"[embedding unavailable] Semantic search requires Ollama with nomic-embed-text.\n  Fix: ollama pull nomic-embed-text"
    
    # Chunk file
    chunks = chunk_file(path)
    if not chunks:
        return f"File empty or unreadable: {path}"
    
    # Embed chunks (cache by file hash for reuse)
    import hashlib
    file_hash = hashlib.sha256(p.read_bytes()).hexdigest()
    cache_key_base = f"chunks_{file_hash}_{len(chunks)}"
    
    # Try cached embeddings
    chunk_embs = []
    with _cache_lock:
        for i, ch in enumerate(chunks):
            ck = f"{cache_key_base}_{i}"
            if ck in _cache:
                chunk_embs.append(_cache[ck].get("embedding", []))
            else:
                break
    
    # Embed missing
    if len(chunk_embs) < len(chunks):
        for i in range(len(chunk_embs), len(chunks)):
            e = embed(chunks[i]["text"])
            chunk_embs.append(e)
            ck = f"{cache_key_base}_{i}"
            with _cache_lock:
                _cache[ck] = {"embedding": e}
            _save_cache()
    
    # Score and rank
    scored = []
    for i, (ch, emb) in enumerate(zip(chunks, chunk_embs)):
        if emb:
            sim = cosine_sim(q_emb, emb)
            if sim >= threshold:
                scored.append((sim, ch))
    
    scored.sort(key=lambda x: -x[0])
    top = scored[:top_k]
    
    if not top:
        # Fallback: return first chunk
        return f"[no semantic matches above {threshold}] Try a more specific query.\nFirst chunk preview:\n{chunks[0]['text'][:300]}"
    
    lines = []
    lines.append(f"Semantic search: \"{query[:80]}\" — {len(chunks)} chunks scanned, top {len(top)} matches:")
    for sim, ch in top:
        lines.append(f"\n--- Match {sim:.2f} (lines {ch['start_line']}-{ch['end_line']}) ---")
        lines.append(ch["text"][:1000])
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  #2 SEMANTIC CACHE
# ═══════════════════════════════════════════════════════════════════════════

def cache_lookup(key: str, query_hint: str = "", threshold: float = 0.92) -> Optional[str]:
    """
    Look up cached result by key + query similarity.
    Returns cached result string if found, None otherwise.
    """
    with _cache_lock:
        if key in _cache:
            entry = _cache[key]
            cached_query = entry.get("query", "")
            cached_result = entry.get("result", "")
            
            # If no query hint, just return by key match
            if not query_hint or not cached_query:
                return cached_result
            
            # Semantic similarity check
            q_emb = embed(query_hint)
            if not q_emb:
                return cached_result  # fallback: return anyway
            
            c_emb = entry.get("embedding", [])
            if c_emb and cosine_sim(q_emb, c_emb) >= threshold:
                return cached_result
            
            return None  # similar key but different query
    
    return None


def cache_store(key: str, result: str, query: str = ""):
    """Store result in semantic cache."""
    q_emb = embed(query) if query else []
    with _cache_lock:
        _cache[key] = {
            "query": query[:200],
            "embedding": q_emb,
            "result": result[:5000],
        }
    _save_cache()


# Initialize
_load_cache()
