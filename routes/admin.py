"""routes/admin.py — Admin endpoints for Miser v1.4 (Phase 3 #19)."""
from flask import Blueprint, jsonify, request

from tools import get_tokens_saved
from prefetch import get_stats as prefetch_stats
from task_queue import get_queue
from cache import cache_stats
from breaker import ollama_breaker
from memory import Memory
from config import DEFAULTS

admin = Blueprint("admin", __name__)

MODEL = None       # set by miser.py at startup
ADAPTER = None
MEM = None


@admin.route("/health")
def health():
    q = get_queue()
    return jsonify({
        "status": "ok",
        "version": "1.4.0",
        "model": MODEL,
        "model_family": ADAPTER.family if ADAPTER else "?",
        "queue_size": q.size,
        "ollama": ollama_breaker.state,
    })


@admin.route("/status")
def status():
    q = get_queue()
    return jsonify({
        "model": MODEL,
        "model_family": ADAPTER.family if ADAPTER else "?",
        "tokens_saved_est": get_tokens_saved(),
        "prefetch": prefetch_stats(),
        "queue": q.stats,
        "cache": cache_stats(),
        "breaker": ollama_breaker.state,
    })


@admin.route("/metrics")
def metrics():
    """Prometheus-compatible metrics endpoint (Phase 3 #23)."""
    q = get_queue()
    cs = cache_stats()
    lines = [
        "# HELP miser_tokens_saved_est Estimated API tokens saved",
        "# TYPE miser_tokens_saved_est counter",
        f"miser_tokens_saved_est {get_tokens_saved()}",
        "# HELP miser_queue_size Current task queue depth",
        "# TYPE miser_queue_size gauge",
        f"miser_queue_size {q.size}",
        "# HELP miser_cache_hits_total Cache hit count",
        "# TYPE miser_cache_hits_total counter",
        f"miser_cache_hits_total {cs['hits']}",
        "# HELP miser_cache_misses_total Cache miss count",
        "# TYPE miser_cache_misses_total counter",
        f"miser_cache_misses_total {cs['misses']}",
        "# HELP miser_breaker_state Circuit breaker state (0=closed, 1=half_open, 2=open)",
        "# TYPE miser_breaker_state gauge",
        f"miser_breaker_state { {'closed': 0, 'half_open': 1, 'open': 2}.get(ollama_breaker.state, -1) }",
    ]
    from flask import Response
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


@admin.route("/memory")
def memory_ep():
    if MEM is None:
        return jsonify({"notes": {}, "history": []})
    return jsonify({"notes": MEM.notes, "history": MEM.history[-10:]})


@admin.route("/memory/clear", methods=["POST"])
def memory_clear():
    if MEM is not None:
        MEM.clear()
    return jsonify({"cleared": True})
