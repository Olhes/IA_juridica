#!/usr/bin/env bash
# Migra el clúster de PostgreSQL 15 al 18 que usa deploy/azure/compose.yml.
#
# Un salto de versión mayor no se hace cambiando el tag: PostgreSQL 18 no puede
# abrir un directorio de datos de 15, y además cambió PGDATA a
# /var/lib/postgresql/18/docker. Por eso el compose monta un volumen nuevo
# (postgres_data_pg18) y este script copia los datos con pg_dump/pg_restore
# desde el servidor anterior todavía en marcha.
#
# El volumen viejo NO se borra: queda como respaldo si algo sale mal.
#
# Uso (en la VM, después de `git pull`):
#   bash deploy/azure/upgrade-postgres-18.sh            # muestra el plan
#   bash deploy/azure/upgrade-postgres-18.sh --execute  # migra de verdad
set -euo pipefail

cd "$(dirname "$0")/../.."
COMPOSE=(docker compose -f deploy/azure/compose.yml --env-file /etc/ia-juridica/compose.env)

OLD_VOLUME=${OLD_VOLUME:-iajuridica_postgres_data}
NEW_VOLUME=${NEW_VOLUME:-iajuridica_postgres_data_pg18}
DATABASE=${DATABASE:-juridica_db}
DB_USER=${DB_USER:-juridica_user}
DEST=${DEST:-/srv/ia-juridica/backups}
STAMP=$(date +%Y%m%dT%H%M%S)
SQL_DUMP=$DEST/pg15-$STAMP.sql.gz
BIN_DUMP=$DEST/pg15-$STAMP.dump

if [[ ${1:-} != --execute ]]; then
  cat <<EOF
Plan de migración PostgreSQL 15 -> 18

  1. Respaldo del servidor actual en $SQL_DUMP y $BIN_DUMP
  2. Parar backend y caddy (evita conexiones durante el cambio)
  3. Parar el contenedor postgres actual (el volumen $OLD_VOLUME queda intacto)
  4. Levantar PostgreSQL 18.7 sobre el volumen nuevo ($NEW_VOLUME)
  5. Reemplazar $DATABASE con el dump del clúster viejo
  6. Volver a desplegar con deploy.sh y esperar /ready

Si $NEW_VOLUME ya existe con datos, no migra: solo despliega.

El volumen $OLD_VOLUME se conserva hasta que confirmes los datos.

Ejecuta con --execute para aplicarlo.
EOF
  exit 0
fi

# Idempotente: si la migración ya ocurrió, solo despliega. Así el mismo comando
# puede repetirse sin volver a reemplazar la base.
if docker volume inspect "$NEW_VOLUME" >/dev/null 2>&1; then
  "${COMPOSE[@]}" up -d --wait postgres >/dev/null 2>&1 || true
  users=$("${COMPOSE[@]}" exec -T postgres psql -U "$DB_USER" -d "$DATABASE" -tAc \
    "SELECT count(*) FROM auth_schema.users" 2>/dev/null || echo "")
  users=${users//[[:space:]]/}
  if [[ ${users:-0} -gt 0 ]]; then
    echo "PostgreSQL 18 ya está migrado ($users usuarios); se omite la migración."
    bash "$(dirname "$0")/deploy.sh"
    exit 0
  fi
  echo "Existe $NEW_VOLUME pero la base no tiene usuarios. Revisa el estado a mano:" >&2
  echo "  docker compose -f deploy/azure/compose.yml --env-file /etc/ia-juridica/compose.env ps" >&2
  exit 1
fi

POSTGRES_ID=$("${COMPOSE[@]}" ps -q postgres)
if [[ -z $POSTGRES_ID ]]; then
  echo "No hay contenedor postgres en ejecución: hay que dumpear el clúster de 15 antes de cambiarlo." >&2
  exit 1
fi

mkdir -p "$DEST"

echo "[1/6] Respaldando el clúster actual..."
"${COMPOSE[@]}" exec -T postgres pg_dumpall -U "$DB_USER" | gzip >"$SQL_DUMP"
"${COMPOSE[@]}" exec -T postgres pg_dump -U "$DB_USER" -d "$DATABASE" \
  --format=custom >"$BIN_DUMP"
echo "      $SQL_DUMP ($(du -h "$SQL_DUMP" | cut -f1))"
echo "      $BIN_DUMP ($(du -h "$BIN_DUMP" | cut -f1))"
if [[ ! -s $BIN_DUMP ]]; then
  echo "El dump quedó vacío; se aborta sin tocar el volumen." >&2
  exit 1
fi

echo "[2/6] Parando backend y caddy..."
"${COMPOSE[@]}" stop backend caddy

echo "[3/6] Parando postgres..."
"${COMPOSE[@]}" stop postgres

echo "[4/6] Levantando PostgreSQL 18 sobre $NEW_VOLUME..."
"${COMPOSE[@]}" up -d --wait postgres

echo "[5/6] Restaurando $DATABASE..."
POSTGRES_ID=$("${COMPOSE[@]}" ps -q postgres)
docker cp "$BIN_DUMP" "$POSTGRES_ID:/tmp/pg15.dump"
# La base recién creada solo tiene lo que dejaron los scripts de initdb: se
# reemplaza entera por el dump para no mezclar dos orígenes de esquema.
"${COMPOSE[@]}" exec -T postgres psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DATABASE';
DROP DATABASE IF EXISTS $DATABASE;
CREATE DATABASE $DATABASE OWNER $DB_USER;
SQL
"${COMPOSE[@]}" exec -T postgres pg_restore -U "$DB_USER" -d "$DATABASE" \
  --no-owner --no-privileges --exit-on-error /tmp/pg15.dump

echo "[6/6] Desplegando con los datos restaurados..."
bash "$(dirname "$0")/deploy.sh"
echo "Migración completa. El volumen $OLD_VOLUME sigue disponible; bórralo cuando"
echo "confirmes los datos:  docker volume rm $OLD_VOLUME"
