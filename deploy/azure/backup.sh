#!/usr/bin/env bash
# Dump diario de Postgres en /srv/ia-juridica/backups (conserva 7 días).
# Cron (lo instala deploy/azure/README.md §3): 0 4 * * * /opt/ia-juridica/deploy/azure/backup.sh
set -euo pipefail

DEST=/srv/ia-juridica/backups
mkdir -p "$DEST"
docker exec iajuridica-postgres-1 pg_dump -U juridica_user juridica_db \
  | gzip >"$DEST/juridica_db-$(date +%F).sql.gz"
find "$DEST" -name 'juridica_db-*.sql.gz' -mtime +7 -delete
