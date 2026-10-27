#!/usr/bin/env bash
# Apunta el backend al dominio del frontend (Vercel): CORS y URLs de OAuth.
# Uso (en la VM, desde /opt/ia-juridica):
#   sudo FRONTEND_URL=https://mi-app.vercel.app bash deploy/azure/set-frontend.sh
# Para activar Google OAuth, añade además GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=...
set -euo pipefail

: "${FRONTEND_URL:?falta FRONTEND_URL, p. ej. https://mi-app.vercel.app}"
FRONTEND_URL=${FRONTEND_URL%/}
ENV_FILE=/etc/ia-juridica/backend.env

upsert() {
  local key=$1 value=$2
  if grep -q "^$key=" "$ENV_FILE"; then
    sed -i "s|^$key=.*|$key=$value|" "$ENV_FILE"
  else
    echo "$key=$value" >>"$ENV_FILE"
  fi
}

upsert CORS_ORIGINS "[\"$FRONTEND_URL\"]"
# Google vuelve al dominio del frontend; Vercel reenvía /api/* al backend, así las
# cookies de login quedan en el dominio del frontend.
upsert GOOGLE_REDIRECT_URI "$FRONTEND_URL/api/auth/google/callback"
upsert GOOGLE_FRONTEND_CALLBACK_URI "$FRONTEND_URL/auth/callback"
if [[ -n ${GOOGLE_CLIENT_ID:-} && -n ${GOOGLE_CLIENT_SECRET:-} ]]; then
  upsert GOOGLE_CLIENT_ID "$GOOGLE_CLIENT_ID"
  upsert GOOGLE_CLIENT_SECRET "$GOOGLE_CLIENT_SECRET"
fi

cd "$(dirname "$0")/../.."
docker compose -f deploy/azure/compose.yml --env-file /etc/ia-juridica/compose.env up -d --force-recreate backend
echo "Backend recreado con FRONTEND_URL=$FRONTEND_URL"
echo "URI de redirección para Google Cloud Console: $FRONTEND_URL/api/auth/google/callback"
