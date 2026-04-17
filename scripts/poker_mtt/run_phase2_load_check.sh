#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
PLAYERS=30
LOCAL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --players)
      PLAYERS="$2"
      shift 2
      ;;
    --local)
      LOCAL=true
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: run_phase2_load_check.sh [--players N] [--local]

Runs the local Poker MTT Phase 2 synthetic load-contract check. The --local
flag keeps the check offline; it does not require the donor game server,
Redis, or WebSocket sidecar.
USAGE
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "$LOCAL" != "true" ]]; then
  echo "run_phase2_load_check currently supports the offline --local contract only" >&2
  exit 2
fi

SUMMARY_FILE="$(mktemp "${TMPDIR:-/tmp}/poker-mtt-phase2-load.XXXXXX.json")"
trap 'rm -f "$SUMMARY_FILE"' EXIT

PYTHONPATH="$ROOT/mining-service:${PYTHONPATH:-}" "$PYTHON_BIN" \
  "$ROOT/scripts/poker_mtt/generate_hand_history_load.py" \
  --players "$PLAYERS" \
  --hands "$PLAYERS" \
  --output "$SUMMARY_FILE" \
  >/dev/null

"$PYTHON_BIN" - "$SUMMARY_FILE" "$PLAYERS" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path


summary_path = Path(sys.argv[1])
expected_players = int(sys.argv[2])
summary = json.loads(summary_path.read_text(encoding="utf-8"))

assert summary["schema_version"] == "poker_mtt.phase2_load.v1"
assert summary["smoke_mtt"]["player_count"] == expected_players
assert summary["smoke_mtt"]["hand_event_count"] == expected_players
assert summary["medium_check"]["player_count"] == 300
assert summary["synthetic_projection"]["player_count"] == 20000
assert summary["synthetic_projection"]["artifact_page_count"] > 1
assert summary["synthetic_projection"]["inline_rows_in_main_payload"] is False
assert summary["early_table_burst"]["table_count"] == 2000
assert {
    "poker_mtt.hand_ingest.count",
    "poker_mtt.hand_ingest.conflict_count",
    "poker_mtt.hud.project.duration_ms",
    "poker_mtt.reward_window.query.duration_ms",
    "poker_mtt.settlement_anchor.confirmation_state",
}.issubset(set(summary["observability_fields"]))

print(
    "phase2 load check ok: "
    f"players={expected_players} "
    f"tables={summary['smoke_mtt']['table_count']} "
    f"projection_pages={summary['synthetic_projection']['artifact_page_count']}"
)
PY
