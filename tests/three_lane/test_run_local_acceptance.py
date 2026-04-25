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


def test_should_admin_reconcile_forecast_after_capture_before_reward():
    assert run_local_acceptance.should_admin_reconcile_forecast(
        {
            "forecast_ready": False,
            "forecast_capture_ready": True,
        }
    ) is True
    assert run_local_acceptance.should_admin_reconcile_forecast(
        {
            "forecast_ready": False,
            "forecast_capture_ready": False,
        }
    ) is False
    assert run_local_acceptance.should_admin_reconcile_forecast(
        {
            "forecast_ready": True,
            "forecast_capture_ready": True,
        }
    ) is False


def test_build_poker_round_command_has_single_tournament_id_flag(tmp_path):
    manifest = tmp_path / "miners-33.json"

    command = run_local_acceptance.build_poker_round_command(
        base_url="http://127.0.0.1:1317",
        manifest=manifest,
        tournament_id="local-poker-20260423054333",
    )

    assert command.count("--tournament-id") == 1
    assert command[command.index("--tournament-id") + 1] == "local-poker-20260423054333"


def test_post_admin_reconcile_posts_to_admin_endpoint(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"success": true, "task_count": 12}'

    def fake_urlopen(request, timeout):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["data"] = request.data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(run_local_acceptance.urllib.request, "urlopen", fake_urlopen)

    result = run_local_acceptance.post_admin_reconcile("http://127.0.0.1:1317", timeout_seconds=1.5)

    assert result == {"success": True, "task_count": 12}
    assert captured == {
        "url": "http://127.0.0.1:1317/admin/reconcile",
        "method": "POST",
        "data": b"",
        "timeout": 1.5,
    }


def test_parse_args_uses_longer_arena_attempt_timeout_by_default(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_local_acceptance.py"])

    args = run_local_acceptance.parse_args()

    assert args.forecast_submit_max_workers == 33
    assert args.admin_reconcile_interval_seconds == 15.0
    assert args.arena_attempt_timeout_seconds == 900.0
