# Winnow operator image: scheduler default, no secrets baked in.
FROM python:3.11-slim-bookworm

RUN groupadd --gid 1000 winnow \
    && useradd --uid 1000 --gid winnow --home-dir /home/winnow --shell /usr/sbin/nologin winnow

WORKDIR /app

COPY pyproject.toml README.md CLAUDE.md RUNBOOK.md ./
COPY config.yaml config_community.yaml config_segment_expansion.yaml ./
COPY src ./src

RUN pip install --no-cache-dir -e ".[cli]" \
    && mkdir -p /data /logs /backups \
    && chown -R winnow:winnow /data /logs /backups /app

USER winnow

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WINNOW_DB_PATH=/data/winnow.sqlite \
    WINNOW_DATA_DIR=/data \
    WINNOW_LOGS_DIR=/logs

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "-m", "winnow.healthcheck"]

CMD ["python", "-m", "winnow.scheduler", "--config", "config.yaml", "--logs-dir", "/logs"]