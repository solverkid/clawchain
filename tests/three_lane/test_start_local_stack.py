from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "three_lane"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import start_local_stack


def test_wait_for_arena_ready_checks_health_then_active(monkeypatch):
    calls: list[tuple[str, float]] = []

    def fake_wait_for_http(url: str, *, timeout_seconds: float = 60.0) -> None:
        calls.append((url, timeout_seconds))

    monkeypatch.setattr(start_local_stack, "wait_for_http", fake_wait_for_http)

    start_local_stack._wait_for_arena_ready("http://127.0.0.1:18117", timeout_seconds=180.0)

    assert calls == [
        ("http://127.0.0.1:18117/healthz", 180.0),
        ("http://127.0.0.1:18117/v1/arena/waves/active", 180.0),
    ]


def test_main_uses_local_acceptance_forecast_timing_overrides(monkeypatch, tmp_path: Path):
    manifest = {"manifest_root": "sha256:test", "count": 33}
    started: list[dict[str, object]] = []
    status_payload: dict[str, object] = {}

    monkeypatch.setattr(sys, "argv", ["start_local_stack.py"])
    monkeypatch.setattr(start_local_stack, "load_or_create_manifest", lambda *args, **kwargs: manifest)
    monkeypatch.setattr(start_local_stack, "_port_is_open", lambda *args, **kwargs: False)
    monkeypatch.setattr(start_local_stack, "_wait_for_arena_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(start_local_stack, "wait_for_http", lambda *args, **kwargs: None)
    monkeypatch.setattr(start_local_stack, "DEFAULT_BUILD_DIR", tmp_path)

    def fake_start_process(*, cmd, workdir, env, log_path, pid_path):  # noqa: ANN001
        started.append({"cmd": cmd, "env": env, "log_path": str(log_path), "pid_path": str(pid_path)})
        pid_path.write_text("123\n", encoding="utf-8")
        return 123

    def fake_write_status(path, payload):  # noqa: ANN001
        status_payload["path"] = str(path)
        status_payload["payload"] = payload

    monkeypatch.setattr(start_local_stack, "_start_process", fake_start_process)
    monkeypatch.setattr(start_local_stack, "write_status", fake_write_status)

    exit_code = start_local_stack.main()

    assert exit_code == 0
    forecast_start = next(item for item in started if item["cmd"][0].endswith("python") or item["cmd"][0] == sys.executable)
    assert forecast_start["env"]["CLAWCHAIN_FAST_TASK_PREWARM_SECONDS"] == "90"
    assert forecast_start["env"]["CLAWCHAIN_FAST_TASK_LIVE_BUILD_TIMEOUT_SECONDS"] == "1.0"
    assert status_payload["payload"]["forecast"]["fast_task_prewarm_seconds"] == 90
