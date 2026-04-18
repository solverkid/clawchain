#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
PYTEST_ARGS=(
  "tests/mining_service/test_poker_mtt_phase3_db_load.py"
)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --postgres-url)
      export CLAWCHAIN_DATABASE_URL="$2"
      shift 2
      ;;
    --local)
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: run_phase3_db_load_check.sh [--local] [--postgres-url URL]

Runs the Poker MTT Phase 3 DB-backed reward-window scale contract:
300-row build, 20k-row paged projection, response-size gate,
idempotent rebuild, bounded auto reconcile, and index contract checks.

The default test path is deterministic and offline. Pass --postgres-url to
make the target database URL available to follow-up staging checks.
USAGE
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

cd "$ROOT"
PYTHONPATH="$ROOT/mining-service:${PYTHONPATH:-}" "$PYTHON_BIN" -m pytest -q "${PYTEST_ARGS[@]}"
