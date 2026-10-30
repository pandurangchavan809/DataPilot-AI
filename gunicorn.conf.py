"""Gunicorn settings. Threaded workers keep long-lived SSE streams cheap."""

import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
worker_class = "gthread"
workers = int(os.getenv("WEB_CONCURRENCY", min(4, multiprocessing.cpu_count())))
threads = int(os.getenv("GUNICORN_THREADS", "8"))
timeout = 180
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
