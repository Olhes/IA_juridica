#!/usr/bin/env bash
# Único comando de actualización en la VM: trae el código, migra PostgreSQL si
# todavía está en 15 y despliega. Es idempotente: repetirlo no vuelve a migrar.
#
#   cd /opt/ia-juridica && git pull && bash deploy/azure/update.sh
set -euo pipefail

cd "$(dirname "$0")/../.."

git pull --ff-only

bash deploy/azure/upgrade-postgres-18.sh --execute
