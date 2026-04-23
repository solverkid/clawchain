from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "skill" / "scripts"
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import mine
import doctor
import status as status_script


def test_select_tasks_for_iteration_prioritizes_daily_and_caps_fast():
    tasks = [
        {"task_run_id": "fast-1", "lane": "forecast_15m"},
        {"task_run_id": "daily-btc", "lane": "daily_anchor"},
        {"task_run_id": "fast-2", "lane": "forecast_15m"},
        {"task_run_id": "daily-eth", "lane": "daily_anchor"},
        {"task_run_id": "fast-3", "lane": "forecast_15m"},
    ]

    selected = mine.select_tasks_for_iteration(tasks, max_fast_tasks=2)

    assert [task["task_run_id"] for task in selected] == [
        "daily-btc",
        "daily-eth",
        "fast-1",
        "fast-2",
    ]


def test_select_tasks_for_iteration_can_skip_daily_anchor():
    tasks = [
        {"task_run_id": "fast-1", "lane": "forecast_15m"},
        {"task_run_id": "daily-btc", "lane": "daily_anchor"},
        {"task_run_id": "fast-2", "lane": "forecast_15m"},
        {"task_run_id": "daily-eth", "lane": "daily_anchor"},
        {"task_run_id": "fast-3", "lane": "forecast_15m"},
    ]

    selected = mine.select_tasks_for_iteration(tasks, max_fast_tasks=2, include_daily=False)

    assert [task["task_run_id"] for task in selected] == [
        "fast-1",
        "fast-2",
    ]


def test_build_settlement_status_lines_includes_reward_window_and_anchor_state():
    miner = {
        "total_rewards": 120,
        "held_rewards": 30,
        "latest_reward_window": {
            "id": "rw_202604091000",
            "state": "settled",
            "canonical_root": "sha256:rw123",
        },
        "latest_settlement_batch": {
            "id": "sb_202604091000",
            "state": "anchor_submitted",
            "canonical_root": "sha256:sb123",
        },
        "latest_anchor_job": {
            "id": "aj_sb_202604091000_20260409100500",
            "state": "broadcast_submitted",
            "broadcast_tx_hash": "0xabc123",
        },
    }

    lines = status_script.build_settlement_status_lines(miner)

    assert any("Released / held:" in line and "120 / 30" in line for line in lines)
    assert any("Latest reward window:" in line and "rw_202604091000" in line for line in lines)
    assert any("Latest settlement batch:" in line and "anchor_submitted" in line for line in lines)
    assert any("Latest anchor job:" in line and "broadcast_submitted" in line and "0xabc123" in line for line in lines)


def test_summarize_anchor_readiness_reports_degraded_but_reachable_service():
    readiness = doctor.summarize_anchor_readiness(
        {
            "ready": False,
            "warnings": ["chain binary not found", "anchor key name not configured"],
            "binary": {"available": False},
            "rpc": {"reachable": True},
            "signing": {"ok": False},
            "source_key": {"ok": False},
            "target_address": "claw1target",
        }
    )

    assert readiness["ok"] is False
    assert readiness["status"] == "degraded"
    assert "chain binary not found" in readiness["detail"]
    assert "anchor key name not configured" in readiness["detail"]


def test_compute_prediction_uses_codex_mode_and_clamps(monkeypatch):
    task = {
        "task_run_id": "tr_fast_202604111000_btcusdt",
        "baseline_q_bps": 5050,
        "pack_json": {
            "binance_snapshot": {"depth_imbalance_bps": 200, "trade_imbalance_bps": 100, "micro_move_bps": 5},
            "polymarket_snapshot": {"q_yes_bps": 5300},
        },
    }
    captured = {}

    def fake_codex_prediction(task_arg, config_arg):  # noqa: ANN001
        captured["task"] = task_arg
        captured["config"] = config_arg
        return {
            "p_yes_bps": 9100,
            "provider": "codex_cli",
            "model": "gpt-5.4-mini",
            "reason": "bullish microstructure",
        }

    monkeypatch.setattr(mine, "compute_codex_prediction", fake_codex_prediction)

    prediction = mine.compute_prediction(
        task,
        {
            "forecast_mode": "codex_v1",
            "codex_model": "gpt-5.4-mini",
        },
    )

    assert captured["task"]["task_run_id"] == task["task_run_id"]
    assert captured["config"]["forecast_mode"] == "codex_v1"
    assert prediction["p_yes_bps"] == 8500
    assert prediction["provider"] == "codex_cli"
    assert prediction["reason"] == "bullish microstructure"


def test_compute_prediction_in_codex_mode_does_not_fallback_to_heuristic(monkeypatch):
    task = {
        "task_run_id": "tr_fast_202604111000_ethusdt",
        "baseline_q_bps": 5050,
        "pack_json": {
            "binance_snapshot": {"depth_imbalance_bps": 200, "trade_imbalance_bps": 100, "micro_move_bps": 5},
            "polymarket_snapshot": {"q_yes_bps": 5300},
        },
    }

    monkeypatch.setattr(
        mine,
        "compute_codex_prediction",
        lambda task_arg, config_arg: (_ for _ in ()).throw(RuntimeError("codex unavailable")),
    )

    with pytest.raises(RuntimeError, match="codex unavailable"):
        mine.compute_prediction(task, {"forecast_mode": "codex_v1"})


def test_compute_prediction_in_codex_mode_reins_in_aggressive_output_when_signals_are_weak(monkeypatch):
    task = {
        "task_run_id": "tr_fast_202604111005_btcusdt",
        "baseline_q_bps": 5000,
        "pack_json": {
            "binance_snapshot": {
                "depth_imbalance_bps": 5600,
                "trade_imbalance_bps": 1800,
                "micro_move_bps": 0.4,
            },
            "polymarket_snapshot": {
                "q_yes_bps": 5040,
                "spread_bps": 6200,
                "volume24hr_clob": 80,
                "liquidity_clob": 18000,
            },
        },
    }

    monkeypatch.setattr(
        mine,
        "compute_codex_prediction",
        lambda task_arg, config_arg: {
            "p_yes_bps": 7000,
            "provider": "codex_cli",
            "model": "gpt-5.4-mini",
            "reason": "binance order flow points up",
            "confidence": 0.58,
        },
    )

    prediction = mine.compute_prediction(task, {"forecast_mode": "codex_v1"})

    assert prediction["p_yes_bps"] == 5300
    assert prediction["aggression_tier"] == "low"
    assert prediction["aggression_cap_bps"] == 300


def test_compute_prediction_in_codex_mode_allows_larger_move_when_signals_align(monkeypatch):
    task = {
        "task_run_id": "tr_fast_202604111010_ethusdt",
        "baseline_q_bps": 5000,
        "pack_json": {
            "binance_snapshot": {
                "depth_imbalance_bps": 4300,
                "trade_imbalance_bps": 3600,
                "micro_move_bps": 3.2,
            },
            "polymarket_snapshot": {
                "q_yes_bps": 5440,
                "spread_bps": 140,
                "volume24hr_clob": 2100,
                "liquidity_clob": 150000,
            },
        },
    }

    monkeypatch.setattr(
        mine,
        "compute_codex_prediction",
        lambda task_arg, config_arg: {
            "p_yes_bps": 7000,
            "provider": "codex_cli",
            "model": "gpt-5.4-mini",
            "reason": "pm and binance both lean up",
            "confidence": 0.84,
        },
    )

    prediction = mine.compute_prediction(task, {"forecast_mode": "codex_v1"})

    assert prediction["p_yes_bps"] == 6400
    assert prediction["aggression_tier"] == "high"
    assert prediction["aggression_cap_bps"] == 1400


def test_resolve_request_timeout_preserves_subsecond_values():
    assert mine.resolve_request_timeout({"request_timeout_seconds": 0.75}) == pytest.approx(0.75)
    assert mine.resolve_request_timeout({"request_timeout_seconds": 0.01}) == pytest.approx(0.1)


def test_codex_system_prompt_includes_short_horizon_calibration_rules():
    prompt = mine._codex_system_prompt()

    assert "thin or wide Polymarket books are weak evidence" in prompt
    assert "Do not swing far from 5000" in prompt


def test_mine_selected_tasks_can_run_in_parallel():
    started = []
    finished = []

    def fake_mine_task(rpc_url, wallet, task, config=None):  # noqa: ANN001
        started.append(task["task_run_id"])
        time.sleep(0.2)
        finished.append(task["task_run_id"])
        return True

    tasks = [
        {"task_run_id": "fast-btc", "lane": "forecast_15m"},
        {"task_run_id": "fast-eth", "lane": "forecast_15m"},
    ]

    start = time.perf_counter()
    mined = mine.mine_selected_tasks(
        "http://127.0.0.1:18131",
        {"address": "claw1test", "private_key": "00" * 32},
        tasks,
        config={"forecast_mode": "codex_v1"},
        parallel_tasks=2,
        mine_task_fn=fake_mine_task,
    )
    elapsed = time.perf_counter() - start

    assert mined == 2
    assert started == ["fast-btc", "fast-eth"]
    assert sorted(finished) == ["fast-btc", "fast-eth"]
    assert elapsed < 0.35


def test_get_task_detail_uses_configured_request_timeout(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"task_run_id": "fast-btc"}}

    def fake_get(url, timeout):  # noqa: ANN001
        captured["url"] = url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(mine.requests, "get", fake_get)

    task = mine.get_task_detail(
        "http://127.0.0.1:18131",
        "fast-btc",
        config={"request_timeout_seconds": 35},
    )

    assert task["task_run_id"] == "fast-btc"
    assert captured["url"] == "http://127.0.0.1:18131/v1/forecast/task-runs/fast-btc"
    assert captured["timeout"] == 35


def test_mine_task_skips_codex_when_commit_window_is_too_short(monkeypatch):
    task = {
        "task_run_id": "fast-btc",
        "asset": "BTCUSDT",
        "lane": "forecast_15m",
        "commit_deadline": (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
    }
    compute_called = False

    def fake_compute_prediction(task_arg, config=None):  # noqa: ANN001
        nonlocal compute_called
        compute_called = True
        return {"p_yes_bps": 5100, "provider": "codex_cli"}

    monkeypatch.setattr(mine, "get_task_detail", lambda rpc_url, task_id, config=None: task)
    monkeypatch.setattr(mine, "compute_prediction", fake_compute_prediction)

    mined = mine.mine_task(
        "http://127.0.0.1:18131",
        {"address": "claw1test", "private_key": "01" * 32},
        {"task_run_id": "fast-btc"},
        config={"forecast_mode": "codex_v1", "min_commit_time_remaining_seconds": 90},
    )

    assert mined is False
    assert compute_called is False


def test_mine_task_skips_commit_if_prediction_finishes_after_deadline(monkeypatch):
    task = {
        "task_run_id": "fast-btc",
        "asset": "BTCUSDT",
        "lane": "forecast_15m",
        "commit_deadline": (datetime.now(timezone.utc) + timedelta(seconds=90)).isoformat(),
    }

    def fake_compute_prediction(task_arg, config=None):  # noqa: ANN001
        task_arg["commit_deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        return {"p_yes_bps": 5100, "provider": "codex_cli"}

    def fail_post_commit(*args, **kwargs):  # noqa: ANN002, ANN003
        pytest.fail("post_commit should not be called after commit deadline passes")

    monkeypatch.setattr(mine, "get_task_detail", lambda rpc_url, task_id, config=None: task)
    monkeypatch.setattr(mine, "compute_prediction", fake_compute_prediction)
    monkeypatch.setattr(mine, "post_commit", fail_post_commit)

    mined = mine.mine_task(
        "http://127.0.0.1:18131",
        {"address": "claw1test", "private_key": "01" * 32},
        {"task_run_id": "fast-btc"},
        config={"forecast_mode": "codex_v1", "min_commit_time_remaining_seconds": 1},
    )

    assert mined is False
