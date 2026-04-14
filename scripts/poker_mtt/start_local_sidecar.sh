#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT/deploy/docker-compose.poker-mtt-local.yml"
STATE_DIR="$ROOT/build/poker-mtt"
PID_FILE="$STATE_DIR/run_server.pid"
LOG_FILE="$STATE_DIR/run_server.log"
BINARY="$STATE_DIR/run_server_local"

wait_for_port() {
  local host="$1"
  local port="$2"
  local timeout="${3:-60}"
  python3 - "$host" "$port" "$timeout" <<'PY'
import socket
import sys
import time

host = sys.argv[1]
port = int(sys.argv[2])
timeout = float(sys.argv[3])
deadline = time.time() + timeout
while time.time() < deadline:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        if sock.connect_ex((host, port)) == 0:
            raise SystemExit(0)
    time.sleep(0.5)
print(f"timeout waiting for {host}:{port}", file=sys.stderr)
raise SystemExit(1)
PY
}

wait_for_log() {
  local container="$1"
  local pattern="$2"
  local timeout="${3:-60}"
  local deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    if docker logs "$container" 2>&1 | rg -q "$pattern"; then
      return 0
    fi
    sleep 1
  done
  echo "timeout waiting for log pattern '$pattern' in $container" >&2
  return 1
}

create_topics_best_effort() {
  local -a topics=(
    DefaultHeartBeatSyncerTopic
    GAME_BUY_IN_TOPIC
    SNG_DIE_USER_POWER_TOPIC
    ROUND_INFO_TOPIC
    POKER_RECORD_TOPIC
    POKER_RECORD_TOPIC_ORDER
    POKER_RECORD_STANDUP_TOPIC
    PRIVATE_FINISH_TOPIC
    HUB_FINISH_TOPIC
    HUB_CONFIG_MODIFY_TOPIC
    IN_GAME_NOTIFICATION_TOPIC
    VDF_RECORD
  )
  for topic in "${topics[@]}"; do
    local ok=0
    for _ in $(seq 1 10); do
      if docker compose -f "$COMPOSE_FILE" exec -T poker_mtt_rmqbroker \
        sh -lc "/home/rocketmq/rocketmq-5.3.2/bin/mqadmin updatetopic -n poker_mtt_rmqnamesrv:9876 -c DefaultCluster -t '$topic' >/dev/null" >/dev/null 2>&1; then
        ok=1
        break
      fi
      sleep 2
    done
    if [[ "$ok" -ne 1 ]]; then
      echo "warning: failed to pre-create RocketMQ topic $topic; continuing with broker auto-create" >&2
    fi
  done
}

mkdir -p "$STATE_DIR"

if [[ -f "$PID_FILE" ]]; then
  EXISTING_PID="$(cat "$PID_FILE")"
  if kill -0 "$EXISTING_PID" >/dev/null 2>&1; then
    echo "poker-mtt sidecar already running with pid $EXISTING_PID"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

docker compose -f "$COMPOSE_FILE" up -d poker_mtt_redis poker_mtt_rmqnamesrv poker_mtt_rmqbroker

wait_for_port 127.0.0.1 36379 60
wait_for_log poker-mtt-rmqbroker "boot success" 120
create_topics_best_effort

docker compose -f "$COMPOSE_FILE" up -d poker_mtt_rmqproxy
wait_for_port 127.0.0.1 38081 120

python3 "$ROOT/scripts/poker_mtt/prepare_local_env.py" "$@"

(
  cd "$ROOT/lepoker-gameserver"
  go build -o "$BINARY" ./run_server
)

(
  cd "$ROOT/lepoker-gameserver"
  nohup env GAME_ENV=local "$BINARY" >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
)

wait_for_port 127.0.0.1 18082 60
wait_for_port 127.0.0.1 18083 60

echo "poker-mtt sidecar started"
echo "pid: $(cat "$PID_FILE")"
echo "log: $LOG_FILE"
