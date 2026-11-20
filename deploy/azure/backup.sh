#!/usr/bin/env bash
# Respaldo diario de las bases de SurrealDB para la VM.
set -euo pipefail

cd "$(dirname "$0")/../.."
COMPOSE=(docker compose -f deploy/azure/compose.yml --env-file /etc/ia-juridica/compose.env)
DEST=/srv/ia-juridica/backups
umask 077
mkdir -p "$DEST"
pending=$(mktemp -d "$DEST/.surreal-pending.XXXXXXXX")
trap 'find "$pending" -maxdepth 1 -type f -delete; rmdir "$pending"' EXIT

for database in sat_graph sat_candidates sat_voyage auth_schema conversations_schema rag_schema legal_schema; do
  "${COMPOSE[@]}" exec -T surreal /surreal export \
    --endpoint http://127.0.0.1:8000 --db "$database" - \
    | gzip > "$pending/$database.surql.gz"
done

mv -T -- "$pending" "$DEST/surreal-$(date -u +%Y%m%dT%H%M%S)-${pending##*.}"
trap - EXIT
find "$DEST" -mindepth 2 -maxdepth 2 -path "$DEST/surreal-*/*.surql.gz" -mtime +7 -delete
find "$DEST" -mindepth 1 -maxdepth 1 -type d -name 'surreal-*' -empty -delete
