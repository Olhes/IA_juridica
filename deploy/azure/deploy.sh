#!/usr/bin/env bash
# Construye y (re)levanta el stack. Lo ejecuta el runner de GitHub Actions en cada
# push a v8, o a mano desde la raíz del repo en la VM.
set -euo pipefail

cd "$(dirname "$0")/../.."
COMPOSE=(docker compose -f deploy/azure/compose.yml --env-file /etc/ia-juridica/compose.env)

"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" build backend
"${COMPOSE[@]}" up -d --remove-orphans

# /health responde aunque el corpus falle; /ready exige el corpus cargado.
echo "Esperando /ready..."
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T backend curl -fsS http://127.0.0.1:8000/ready >/dev/null 2>&1; then
    echo "Backend listo: $("${COMPOSE[@]}" exec -T backend curl -fsS http://127.0.0.1:8000/ready)"
    docker image prune -f >/dev/null
    exit 0
  fi
  sleep 5
done

echo "El backend no llegó a /ready en 5 minutos" >&2
"${COMPOSE[@]}" ps
"${COMPOSE[@]}" logs --tail=150 backend
exit 1
