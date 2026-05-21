"""
security.py — Rate limiting, CORS, and security middleware for Miser v1.4.
"""

import hashlib, threading, time
from collections import defaultdict
from flask import request, jsonify


# ═══ Rate Limiting (Phase 1 #1) ═══════════════════════════════════════════════

class RateLimiter:
    """Simple token-bucket rate limiter per endpoint category."""

    def __init__(self):
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _clean(self, key: str, window: float):
        now = time.time()
        with self._lock:
            self._buckets[key] = [t for t in self._buckets[key] if now - t < window]

    def allow(self, key: str, max_req: int, window: float = 60.0) -> bool:
        self._clean(key, window)
        with self._lock:
            if len(self._buckets[key]) >= max_req:
                return False
            self._buckets[key].append(time.time())
            return True

    def remaining(self, key: str, max_req: int) -> int:
        return max(0, max_req - len(self._buckets[key]))


_limiter = RateLimiter()

LLM_LIMIT = 30     # /ask /chat /codegen: 30 req/min
ZERO_LIMIT = 200   # file ops: 200 req/min


def rate_limit_middleware():
    """Flask before_request handler for rate limiting."""
    path = request.path

    if path in ("/ask", "/chat", "/codegen", "/condense",
                "/explain", "/fix", "/test", "/review",
                "/summarize", "/git_summary"):
        key = "llm"
        limit = LLM_LIMIT
    elif path in ("/read", "/grep", "/outline", "/tree", "/exists",
                  "/run", "/write", "/patch", "/batch", "/note"):
        key = "zero"
        limit = ZERO_LIMIT
    else:
        return  # /status /health /memory no limit

    if not _limiter.allow(key, limit):
        remaining_time = 60
        return jsonify({
            "error": {
                "code": "E_RATE_LIMITED",
                "message": f"Rate limit exceeded ({limit}/min)",
                "retry_after_s": remaining_time,
            }
        }), 429


# ═══ CORS Whitelist (Phase 1 #3) ══════════════════════════════════════════════

ALLOWED_ORIGINS = {"http://localhost", "http://127.0.0.1",
                   "http://localhost:7860", "http://127.0.0.1:7860"}


def cors_middleware(response):
    """Flask after_request handler for CORS."""
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


# ═══ Auth Hashing (Phase 1 #2) ═════════════════════════════════════════════════

def hash_token(token: str) -> str:
    """SHA256 hash for storing auth tokens securely."""
    if not token:
        return ""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token(provided: str, stored_hash: str) -> bool:
    """Compare a provided token against its stored hash."""
    if not stored_hash:
        return True  # No auth configured
    if not provided:
        return False
    return hash_token(provided) == stored_hash


# ═══ Standardized Errors (Phase 1 #5) ══════════════════════════════════════════

ERROR_CODES = {
    "E_MISSING_PARAM":   (400, "Required parameter missing"),
    "E_NOT_FOUND":       (404, "Resource not found"),
    "E_BUSY":            (429, "Server busy, try again"),
    "E_RATE_LIMITED":    (429, "Rate limit exceeded"),
    "E_QUEUE_FULL":      (429, "Task queue is full"),
    "E_AUTH_REQUIRED":   (401, "Authentication required"),
    "E_AUTH_INVALID":    (401, "Invalid authentication token"),
    "E_LARGE_BODY":      (413, "Request body too large"),
    "E_INTERNAL":        (500, "Internal server error"),
    "E_OLLAMA_DOWN":     (503, "Ollama service unavailable"),
}


def error_response(code: str, detail: str = "", status: int | None = None) -> tuple:
    """Build a standardized error response."""
    info = ERROR_CODES.get(code, (500, "Unknown error"))
    http_status = status if status is not None else info[0]
    body = {
        "error": {
            "code": code,
            "message": info[1],
            "detail": detail or info[1],
        }
    }
    return jsonify(body), http_status
