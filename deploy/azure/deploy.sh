#!/usr/bin/env bash
# Construye y (re)levanta el stack. Lo ejecuta el runner de GitHub Actions en cada
# push a v8, o a mano desde la raíz del repo en la VM.
set -euo pipefail

cd "$(dirname "$0")/../.."
COMPOSE=(docker compose -f deploy/azure/compose.yml --env-file /etc/ia-juridica/compose.env)
CORPUS_DUMP=backend/docs/sat_graph.pg_dump
OLD_VOLUME=${OLD_VOLUME:-iajuridica_postgres_data}
NEW_VOLUME=${NEW_VOLUME:-iajuridica_postgres_data_pg18}

# PostgreSQL 18 no abre un directorio de datos de 15. Si el volumen anterior
# todavía tiene los datos y el nuevo no existe, levantar el stack crearía una base
# vacía y se perderían usuarios e historial: se detiene y se pide la migración.
if docker volume inspect "$OLD_VOLUME" >/dev/null 2>&1 \
   && ! docker volume inspect "$NEW_VOLUME" >/dev/null 2>&1; then
  echo "Detenido: $OLD_VOLUME tiene datos de PostgreSQL 15 y $NEW_VOLUME no existe." >&2
  echo "Migra primero: bash deploy/azure/upgrade-postgres-18.sh --execute" >&2
  exit 1
fi

"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" build backend

# El corpus SAT es dato, no código: el esquema `sat_graph` se crea pero queda
# vacío. Se restaura con la base todavía sola —antes de que el backend pueda
# inicializar el esquema en paralelo— y solo si no hay revisiones publicadas.
"${COMPOSE[@]}" up -d --wait postgres
revisions=$("${COMPOSE[@]}" exec -T postgres psql -U juridica_user -d juridica_db -tAc \
  "SELECT count(*) FROM sat_graph.sat_nodes WHERE kind='DocumentaryRevision'" 2>/dev/null || echo "")
revisions=${revisions//[[:space:]]/}
if [[ ${revisions:-0} == 0 ]]; then
  if [[ -f $CORPUS_DUMP ]]; then
    echo "Corpus SAT vacío: restaurando $CORPUS_DUMP..."
    "${COMPOSE[@]}" cp "$CORPUS_DUMP" postgres:/tmp/sat_graph.pg_dump
    # Sin --schema: pg_restore filtra también el CREATE SCHEMA y la restauración
    # falla sobre una base nueva. El dump solo contiene objetos de sat_graph.
    "${COMPOSE[@]}" exec -T postgres pg_restore -U juridica_user -d juridica_db \
      --clean --if-exists --no-owner --no-privileges --exit-on-error /tmp/sat_graph.pg_dump
  else
    echo "Aviso: corpus SAT vacío y sin $CORPUS_DUMP; publica documentos en /sat-graph/review" >&2
  fi
fi

# SurrealDB debe estar arriba antes de migrar y antes de publicar las fuentes
# normativas (publish_cpc_tuo usa el backend por defecto, SurrealDB). PostgreSQL
# sigue levantado como fuente de la migración y como rollback.
"${COMPOSE[@]}" up -d --wait surreal

# Migración idempotente PostgreSQL -> SurrealDB: con --apply reconstruye cada
# tabla desde PostgreSQL y valida conteo + checksum. PostgreSQL no se modifica.
# Se ejecuta antes de activar el backend y aborta el despliegue si falla.
echo "Migrando PostgreSQL -> SurrealDB..."
if ! "${COMPOSE[@]}" run --rm --no-deps -T backend /app/.venv/bin/python -m scripts.migrate_postgres_to_surrealdb --apply --batch-size 1000; then
  echo "Fallo en la migración PostgreSQL -> SurrealDB; se aborta el despliegue." >&2
  exit 1
fi

# Los despliegues sobre un corpus existente no restauran el dump encima de
# la BD. Aplica solo las fuentes normativas de esta entrega, de forma idempotente.
"${COMPOSE[@]}" run --rm --no-deps -T backend /app/.venv/bin/python -m scripts.publish_cpc_tuo --apply

"${COMPOSE[@]}" up -d --remove-orphans

# /health responde aunque el corpus falle; /ready exige el corpus cargado.
echo "Esperando /ready..."
for _ in $(seq 1 60); do
  ready=$("${COMPOSE[@]}" exec -T backend curl -fsS http://127.0.0.1:8000/ready 2>/dev/null || true)
  if [[ -n $ready ]]; then
    echo "Backend listo: $ready"
    docker image prune -f >/dev/null
    exit 0
  fi
  sleep 5
done

echo "El backend no llegó a /ready en 5 minutos" >&2
"${COMPOSE[@]}" ps
"${COMPOSE[@]}" logs --tail=150 backend
exit 1
