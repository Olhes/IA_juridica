#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="/app/backend:${PYTHONPATH:-}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-1}"
EMBEDDED_SURREAL="${EMBEDDED_SURREAL:-true}"
AUTO_BOOTSTRAP_SAT="${AUTO_BOOTSTRAP_SAT:-true}"
SURREAL_DATA_DIR="${SURREAL_DATA_DIR:-/app/surreal_data}"
export SURREAL_URL="${SURREAL_URL:-ws://127.0.0.1:8010/rpc}"
export SURREAL_USER="${SURREAL_USER:-root}"
export SURREAL_PASSWORD="${SURREAL_PASSWORD:-root}"
export SURREAL_NAMESPACE="${SURREAL_NAMESPACE:-ia_juridica}"
export BUILD_SEED_PASS="ia-juridica-build-seed"

SURREAL_PID=""
UVICORN_PID=""

cleanup() {
  trap - TERM INT EXIT
  if [ -n "${UVICORN_PID}" ]; then
    kill -TERM "${UVICORN_PID}" 2>/dev/null || true
    wait "${UVICORN_PID}" 2>/dev/null || true
  fi
  if [ -n "${SURREAL_PID}" ]; then
    kill -TERM "${SURREAL_PID}" 2>/dev/null || true
    wait "${SURREAL_PID}" 2>/dev/null || true
  fi
}

rotate_embedded_root_password() {
  /app/.venv/bin/python - <<'PY'
import json
import os
import re
from surrealdb import Surreal

url = "ws://127.0.0.1:8010/rpc"
user = os.environ["SURREAL_USER"]
target_pass = os.environ["SURREAL_PASSWORD"]
seed_pass = os.environ["BUILD_SEED_PASS"]

if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", user):
    raise SystemExit("Invalid SURREAL_USER identifier for embedded SurrealDB")

# If runtime password already works (fresh datastore or already rotated), nothing to do.
for candidate_user, candidate_pass in ((user, target_pass), ("root", seed_pass)):
    conn = Surreal(url)
    try:
        conn.connect()
        conn.signin({"username": candidate_user, "password": candidate_pass})
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        continue
    try:
        if candidate_pass == seed_pass and (user != "root" or target_pass != seed_pass):
            literal_pass = json.dumps(target_pass)
            conn.query(
                f"DEFINE USER OVERWRITE {user} ON ROOT PASSWORD {literal_pass} ROLES OWNER;"
            ).execute()
            if user != "root":
                conn.query("REMOVE USER IF EXISTS root ON ROOT;").execute()
        raise SystemExit(0)
    finally:
        try:
            conn.close()
        except Exception:
            pass

raise SystemExit("Unable to authenticate against embedded SurrealDB")
PY
}

if [ "${EMBEDDED_SURREAL,,}" = "true" ]; then
  trap cleanup TERM INT EXIT
  mkdir -p "${SURREAL_DATA_DIR}"
  /usr/local/bin/surreal start \
    --user "${SURREAL_USER}" \
    --pass "${SURREAL_PASSWORD}" \
    --bind 127.0.0.1:8010 \
    --log "${SURREAL_LOG_LEVEL:-warn}" \
    "rocksdb:${SURREAL_DATA_DIR}/surreal.db" &
  SURREAL_PID=$!

  ready=0
  for _ in $(seq 1 30); do
    if /usr/local/bin/surreal is-ready --endpoint http://127.0.0.1:8010 --log none 2>/dev/null; then
      ready=1
      break
    fi
    sleep 1
  done
  if [ "${ready}" -ne 1 ]; then
    echo "Embedded SurrealDB did not become ready in time" >&2
    exit 1
  fi

  rotate_embedded_root_password

  if [ "${AUTO_BOOTSTRAP_SAT,,}" = "true" ] && [ -f /app/backend/docs/sat_graph.surql.gz ]; then
    /app/.venv/bin/python -m scripts.bootstrap_sat_corpus
  fi

  /app/.venv/bin/uvicorn main:app --host 0.0.0.0 --port "${PORT}" --workers "${WORKERS}" &
  UVICORN_PID=$!
  wait "${UVICORN_PID}"
else
  if [ "${AUTO_BOOTSTRAP_SAT,,}" = "true" ] && [ -f /app/backend/docs/sat_graph.surql.gz ]; then
    /app/.venv/bin/python -m scripts.bootstrap_sat_corpus
  fi
  exec /app/.venv/bin/uvicorn main:app --host 0.0.0.0 --port "${PORT}" --workers "${WORKERS}"
fi
