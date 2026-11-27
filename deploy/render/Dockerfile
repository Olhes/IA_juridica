# Render Free Tier Dockerfile — FastAPI backend + embedded SurrealDB v4 binary
# Pre-seeds the SAT legal corpus into RocksDB at build time so Render cold starts
# avoid replaying 42k+ nodes / 100k+ edges on 0.1 vCPU.

FROM python:3.14.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/tmp/uv-cache \
    PORT=8000 \
    WORKERS=1 \
    EMBEDDED_SURREAL=true \
    AUTO_BOOTSTRAP_SAT=true \
    SURREAL_DATA_DIR=/app/surreal_data

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libgomp1 \
        libglib2.0-0 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Official uv binary (matches uv.lock) and SurrealDB v4.0.1 binary (matches docker-compose.yml).
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /bin/
COPY --from=surrealdb/surrealdb:v4.0.1 /surreal /usr/local/bin/surreal

COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --no-cache

RUN useradd --create-home appuser

COPY --chown=appuser:appuser backend /app/backend
COPY --chown=appuser:appuser deploy/render/entrypoint.sh /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

RUN install -d -o appuser -g appuser \
        /app/docs/raw_pdfs \
        /app/docs/processed \
        /app/docs/knowledge_graph \
        /app/docs/failed \
        /app/backend/docs/raw_pdfs \
        /app/backend/docs/failed \
        /app/backend/data/feedback \
        /app/backend/logs \
        /app/backend/temp/pdfs \
        /app/backend/templates/pdf \
        /app/surreal_data

# Pre-seed the versioned SAT corpus snapshot into embedded SurrealKV at build time.
# Runtime entrypoint rotates the temporary build-time root password to SURREAL_PASSWORD.
RUN if [ -f /app/backend/docs/sat_graph.surql.gz ]; then \
      cd /app/backend || exit 1; \
      /usr/local/bin/surreal start \
        --user root \
        --pass ia-juridica-build-seed \
        --bind 127.0.0.1:8010 \
        --log warn \
        "surrealkv://${SURREAL_DATA_DIR}/surreal.db" & \
      SURREAL_PID=$!; \
      ready=0; \
      for _ in $(seq 1 30); do \
        if /usr/local/bin/surreal is-ready --endpoint http://127.0.0.1:8010 --log none 2>/dev/null; then \
          ready=1; break; \
        fi; \
        sleep 1; \
      done; \
      if [ "$ready" -ne 1 ]; then \
        echo "SurrealDB failed to start during image build" >&2; \
        kill "$SURREAL_PID" 2>/dev/null || true; \
        exit 1; \
      fi; \
      rc=0; \
      SURREAL_URL=ws://127.0.0.1:8010/rpc \
      SURREAL_USER=root \
      SURREAL_PASSWORD=ia-juridica-build-seed \
      SURREAL_NAMESPACE=ia_juridica \
      PYTHONPATH=/app/backend \
      /app/.venv/bin/python -m scripts.bootstrap_sat_corpus || rc=$?; \
      kill -TERM "$SURREAL_PID" 2>/dev/null || true; \
      wait "$SURREAL_PID" || true; \
      if [ "$rc" -ne 0 ]; then \
        echo "SAT corpus bootstrap failed during image build (exit $rc)" >&2; \
        exit "$rc"; \
      fi; \
      chown -R appuser:appuser "${SURREAL_DATA_DIR}" /app/docs /app/backend/logs /app/backend/temp /app/backend/templates /app/backend/data; \
    fi

USER appuser
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/ready" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
