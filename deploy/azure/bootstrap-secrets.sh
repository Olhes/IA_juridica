#!/usr/bin/env bash
# Una sola vez en la VM: genera /etc/ia-juridica/{compose.env,backend.env}.
# Uso: sudo COHERE_API_KEY=... API_DOMAIN=api.example.com FRONTEND_ORIGIN=https://x.vercel.app \
#        bash deploy/azure/bootstrap-secrets.sh
# En una VM existente agrega parámetros nuevos usando los secretos ya guardados.
set -euo pipefail

DIR=/etc/ia-juridica
install -d -m 750 -o root -g docker "$DIR"
install -d -o 1000 -g 1000 /srv/ia-juridica/data /srv/ia-juridica/logs \
  /srv/ia-juridica/temp/pdfs /srv/ia-juridica/temp/sat-corpus-work \
  /srv/ia-juridica/backups

rand() { openssl rand -hex 32; }

if [[ ! -f $DIR/compose.env ]]; then
  : "${API_DOMAIN:?falta API_DOMAIN}"
  umask 027
  cat >"$DIR/compose.env" <<EOF
API_DOMAIN=$API_DOMAIN
REDIS_PASSWORD=$(rand)
SURREAL_PASSWORD=$(rand)
EOF
  chgrp docker "$DIR/compose.env"
fi

# shellcheck disable=SC1091
source "$DIR/compose.env"

# compose.env anterior a SurrealDB: generar el secreto sin rotar los existentes.
if [[ -z ${SURREAL_PASSWORD:-} ]]; then
  SURREAL_PASSWORD=$(rand)
  umask 027
  printf 'SURREAL_PASSWORD=%s\n' "$SURREAL_PASSWORD" >>"$DIR/compose.env"
fi
SURREAL_USER=${SURREAL_USER:-root}

if [[ ! -f $DIR/backend.env ]]; then
  : "${COHERE_API_KEY:?falta COHERE_API_KEY}"
  : "${FRONTEND_ORIGIN:?falta FRONTEND_ORIGIN}"
  umask 027
  cat >"$DIR/backend.env" <<EOF
ENVIRONMENT=production
DEBUG=false
APP_VERSION=v8
WORKERS=1
API_DOCS_ENABLED=false
LOG_LEVEL=INFO

COHERE_API_KEY=$COHERE_API_KEY
COHERE_EMBED_MODEL=embed-multilingual-v3.0
COHERE_RERANK_MODEL=rerank-multilingual-v3.0
COHERE_LLM_MODEL=command-r7b-12-2024

SECRET_KEY=$(rand)
JWT_SECRET_KEY=$(rand)
JWT_REFRESH_SECRET_KEY=$(rand)
ANONYMOUS_SESSION_SECRET=$(rand)
ANONYMOUS_SESSION_COOKIE_SECURE=true
ANONYMOUS_SESSION_COOKIE_SAMESITE=lax
# Header X-API-Key para /admin y /quality/admin (el panel web usa el rol admin).
ADMIN_ENDPOINTS_ENABLED=true
ADMIN_API_KEY=$(rand)

CORS_ORIGINS=["$FRONTEND_ORIGIN"]
CORS_ALLOW_METHODS=["GET","POST","PUT","DELETE","OPTIONS"]
CORS_ALLOW_HEADERS=["Content-Type","X-API-Key","X-Request-ID"]

# SurrealDB v4.0.1 (namespace ia_juridica).
SURREAL_URL=ws://surreal:8000/rpc
SURREAL_USER=$SURREAL_USER
SURREAL_PASSWORD=$SURREAL_PASSWORD
SURREAL_NAMESPACE=ia_juridica
SURREAL_POOL_SIZE=8

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=$REDIS_PASSWORD
REDIS_URL=redis://:$REDIS_PASSWORD@redis:6379/0
RATE_LIMIT_ENABLED=true
RATE_LIMIT_STORAGE_URI=redis://:$REDIS_PASSWORD@redis:6379/1

# Motor de recuperación: SAT es el corpus normativo versionado. Cambiar a
# lightrag solo para comparar contra el grafo probabilístico heredado.
RAG_ENGINE=sat
# Opcional: fija la fecha de corte del snapshot (YYYY-MM-DD). Vacío = versiones
# más recientes almacenadas, asumidas vigentes por la administración del corpus.
# SAT_AS_OF=

FEEDBACK_DIR=./data/feedback
LOAD_LOCAL_KG=true
NEO4J_ENABLED=false
EOF
  chgrp docker "$DIR/backend.env"
fi

# Un backend.env previo a SAT no tiene estas claves y el deploy fallaría en
# silencio con LightRAG: se completan sin tocar el resto del archivo.
ensure_key() {
  grep -qE "^$1=" "$DIR/backend.env" || printf '%s\n' "$1=$2" >>"$DIR/backend.env"
}
ensure_key RAG_ENGINE sat

# Completa claves de SurrealDB sin tocar el resto del archivo (idempotente).
ensure_key SURREAL_URL ws://surreal:8000/rpc
ensure_key SURREAL_USER "$SURREAL_USER"
ensure_key SURREAL_PASSWORD "$SURREAL_PASSWORD"
ensure_key SURREAL_NAMESPACE ia_juridica
ensure_key SURREAL_POOL_SIZE 8

echo "OK: $DIR/compose.env y $DIR/backend.env"
