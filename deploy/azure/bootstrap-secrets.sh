#!/usr/bin/env bash
# Una sola vez en la VM: genera /etc/ia-juridica/{compose.env,backend.env}.
# Uso: sudo COHERE_API_KEY=... API_DOMAIN=api.example.com FRONTEND_ORIGIN=https://x.vercel.app \
#        bash deploy/azure/bootstrap-secrets.sh
# No sobrescribe archivos existentes (rotar = borrar el archivo a mano y relanzar).
set -euo pipefail

: "${COHERE_API_KEY:?falta COHERE_API_KEY}"
: "${API_DOMAIN:?falta API_DOMAIN}"
: "${FRONTEND_ORIGIN:?falta FRONTEND_ORIGIN}"

DIR=/etc/ia-juridica
install -d -m 750 -o root -g docker "$DIR"
install -d -o 1000 -g 1000 /srv/ia-juridica/data /srv/ia-juridica/logs \
  /srv/ia-juridica/temp/pdfs /srv/ia-juridica/temp/sat-corpus-work \
  /srv/ia-juridica/backups

rand() { openssl rand -hex 32; }

if [[ ! -f $DIR/compose.env ]]; then
  umask 027
  cat >"$DIR/compose.env" <<EOF
API_DOMAIN=$API_DOMAIN
POSTGRES_PASSWORD=$(rand)
REDIS_PASSWORD=$(rand)
EOF
  chgrp docker "$DIR/compose.env"
fi

# shellcheck disable=SC1091
source "$DIR/compose.env"

if [[ ! -f $DIR/backend.env ]]; then
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

DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_NAME=juridica_db
DATABASE_USER=juridica_user
DATABASE_PASSWORD=$POSTGRES_PASSWORD
DATABASE_URL=postgresql://juridica_user:$POSTGRES_PASSWORD@postgres:5432/juridica_db
SQLALCHEMY_DATABASE_URL=postgresql+psycopg://juridica_user:$POSTGRES_PASSWORD@postgres:5432/juridica_db

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

echo "OK: $DIR/compose.env y $DIR/backend.env"
