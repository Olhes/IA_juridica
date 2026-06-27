FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/tmp/uv-cache

WORKDIR /app

# Instalar UV y dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libgomp1 \
    libglib2.0-0 \
    libgl1 \
    && pip install uv \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivos de dependencias
COPY pyproject.toml uv.lock /app/

# Instalar dependencias con UV (CPU-only)
RUN uv sync --frozen --no-dev --no-cache --extra-index-url https://download.pytorch.org/whl/cpu

# Crear usuario de runtime antes de copiar el código para evitar
# un chown recursivo sobre /app/.venv (duplica varios GB en una capa).
RUN useradd --create-home appuser

# Copiar código fuente con ownership correcto desde el inicio
COPY --chown=appuser:appuser backend /app/backend

# Crear directorios necesarios con ownership correcto sin tocar /app/.venv
RUN install -d -o appuser -g appuser \
    /app/backend/docs/raw_pdfs \
    /app/backend/docs/processed \
    /app/backend/docs/knowledge_graph \
    /app/backend/docs/failed \
    /app/backend/logs \
    /app/backend/temp/pdfs

USER appuser
WORKDIR /app/backend

EXPOSE 8000

# Usar el entorno virtual de UV
CMD ["/app/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
