# WAYL: self-hosted music log. Build: docker build -t wayl .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FLASK_APP=app \
    DATABASE_URL=sqlite:////data/wayl.db \
    SECRET_KEY_FILE=/data/secret_key \
    APP_URL=http://localhost:8000

WORKDIR /app

RUN useradd --create-home --uid 1000 wayl && mkdir /data && chown wayl:wayl /data

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=wayl:wayl . .
RUN chmod +x docker/entrypoint.sh

USER wayl
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)" || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["web"]
