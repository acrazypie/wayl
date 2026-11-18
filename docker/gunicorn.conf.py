"""Gunicorn settings for the Docker image. Override with env vars, e.g. GUNICORN_THREADS=16."""
import os

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
# One process with threads: audio streams are long requests, and the rate limiter keeps its
# counters in memory (several processes would each count separately).
workers = int(os.getenv("GUNICORN_WORKERS", "1"))
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "12"))
timeout = 120  # a single streamed chunk must not take longer than this
graceful_timeout = 20
keepalive = 5
accesslog = "-"
errorlog = "-"
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1")
