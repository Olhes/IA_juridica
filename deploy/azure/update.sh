#!/usr/bin/env bash
# Único comando de actualización en la VM: trae el código y despliega.
#
#   cd /opt/ia-juridica && git pull && bash deploy/azure/update.sh
set -euo pipefail

cd "$(dirname "$0")/../.."

git pull --ff-only

bash deploy/azure/deploy.sh
