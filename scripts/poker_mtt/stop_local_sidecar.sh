#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT/deploy/docker-compose.poker-mtt-local.yml"
STATE_DIR="$ROOT/build/poker-mtt"
PID_FILE="$STATE_DIR/run_server.pid"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" >/dev/null 2>&1; then
    kill "$PID"
    for _ in $(seq 1 20); do
      if ! kill -0 "$PID" >/dev/null 2>&1; then
        break
      fi
      sleep 0.5
    done
    if kill -0 "$PID" >/dev/null 2>&1; then
      kill -9 "$PID"
    fi
  fi
  rm -f "$PID_FILE"
fi

python3 "$ROOT/scripts/poker_mtt/prepare_local_env.py" --restore || true
docker compose -f "$COMPOSE_FILE" down -v

echo "poker-mtt sidecar stopped"
