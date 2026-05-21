"""
gunicorn.conf.py — Multi-worker WSGI config for Miser v1.4 (Phase 3 #20, fix #32).
Usage: gunicorn -c gunicorn.conf.py miser:app
"""

import os

bind = f"0.0.0.0:{os.environ.get('MISER_PORT', '7860')}"
workers = int(os.environ.get("MISER_WORKERS", "2"))
worker_class = "gthread"
threads = 2
timeout = 120
keepalive = 5
max_requests = 5000
max_requests_jitter = 100
loglevel = "info"
accesslog = "-"
errorlog = str(os.path.join(os.path.dirname(__file__), "miser.log"))
