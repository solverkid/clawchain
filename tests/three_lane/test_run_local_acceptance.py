from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "three_lane"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_local_acceptance


def test_should_restart_forecast_swarm_before_capture():
    assert run_local_acceptance.should_restart_forecast_swarm(
        {
            "forecast_ready": False,
            "forecast_capture_ready": False,
        }
    ) is True


def test_should_not_restart_forecast_swarm_while_waiting_for_resolution():
    assert run_local_acceptance.should_restart_forecast_swarm(
        {
            "forecast_ready": False,
            "forecast_capture_ready": True,
        }
    ) is False


def test_should_not_restart_forecast_swarm_after_ready():
    assert run_local_acceptance.should_restart_forecast_swarm(
        {
            "forecast_ready": True,
            "forecast_capture_ready": True,
        }
    ) is False


def test_parse_args_uses_longer_arena_attempt_timeout_by_default(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_local_acceptance.py"])

    args = run_local_acceptance.parse_args()

    assert args.forecast_submit_max_workers == 33
    assert args.arena_attempt_timeout_seconds == 900.0
