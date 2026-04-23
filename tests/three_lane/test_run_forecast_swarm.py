from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "three_lane"
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import common
import run_forecast_swarm
from forecast_engine import compute_commit_hash


def test_prepare_submission_uses_task_and_miner_in_commit_hash(monkeypatch):
    manifest = common.build_manifest(count=1, namespace="forecast-test")
    miner = manifest["miners"][0]
    task = {
        "task_run_id": "tr_fast_202604230045_btcusdt",
        "asset": "BTCUSDT",
        "lane": "forecast_15m",
        "publish_at": "2026-04-23T00:45:00Z",
        "commit_deadline": "2026-04-23T00:45:03Z",
        "reveal_deadline": "2026-04-23T00:45:13Z",
    }
    task_detail = {
        "task_run_id": task["task_run_id"],
        "asset": task["asset"],
        "market_context": {},
        "market_pack": {},
    }

    monkeypatch.setattr(
        run_forecast_swarm,
        "compute_heuristic_prediction",
        lambda _: {"p_yes_bps": 6123, "provider": "test-provider"},
    )

    prepared = run_forecast_swarm._prepare_submission(miner, task, task_detail)

    assert prepared["task_run_id"] == task["task_run_id"]
    assert prepared["miner_address"] == miner["address"]
    assert prepared["prediction"]["p_yes_bps"] == 6123
    assert prepared["reveal_deadline"] == task["reveal_deadline"]

    commit_payload = prepared["commit_payload"]
    reveal_payload = prepared["reveal_payload"]
    assert commit_payload["task_run_id"] == task["task_run_id"]
    assert reveal_payload["task_run_id"] == task["task_run_id"]
    assert commit_payload["miner_id"] == miner["address"]
    assert reveal_payload["miner_id"] == miner["address"]
    assert commit_payload["nonce"] == reveal_payload["nonce"]
    assert commit_payload["request_id"] != reveal_payload["request_id"]
    assert commit_payload["commit_hash"] == compute_commit_hash(
        task["task_run_id"],
        miner["address"],
        reveal_payload["p_yes_bps"],
        reveal_payload["nonce"],
    )


def test_parse_args_supports_skip_register_miners(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_forecast_swarm.py", "--skip-register-miners", "--wait-seconds", "12"],
    )

    args = run_forecast_swarm.parse_args()

    assert args.skip_register_miners is True
    assert args.wait_seconds == 12
    assert args.submit_max_workers == 33


def test_build_error_event_preserves_phase_and_identity():
    event = run_forecast_swarm._build_error_event(
        phase="commit",
        prepared={
            "task_run_id": "tr_fast_202604230045_btcusdt",
            "miner_address": "claw1test",
            "prediction": {"p_yes_bps": 5000, "provider": "unit-test"},
        },
        exc=RuntimeError("boom"),
    )

    assert event["event"] == "forecast_submission_error"
    assert event["phase"] == "commit"
    assert event["task_run_id"] == "tr_fast_202604230045_btcusdt"
    assert event["miner_address"] == "claw1test"
    assert event["p_yes_bps"] == 5000
    assert event["provider"] == "unit-test"
    assert event["error"] == "boom"


def test_find_upcoming_tasks_filters_forecast_items(monkeypatch):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "items": [
                        {"task_run_id": "tr_fast_202604230045_btcusdt", "lane": "forecast_15m"},
                        {"task_run_id": "tr_daily_20260423_btc", "lane": "daily_anchor"},
                    ]
                }
            }

    monkeypatch.setattr(run_forecast_swarm.requests, "get", lambda *args, **kwargs: _Response())

    tasks = run_forecast_swarm._find_upcoming_tasks(
        "http://127.0.0.1:1317",
        request_timeout_seconds=5,
    )

    assert tasks == [{"task_run_id": "tr_fast_202604230045_btcusdt", "lane": "forecast_15m"}]


def test_collect_upcoming_tasks_merges_additional_tasks(monkeypatch):
    responses = [
        [{"task_run_id": "tr_fast_202604230045_btcusdt", "lane": "forecast_15m", "publish_at": "2026-04-23T00:45:00Z"}],
        [
            {"task_run_id": "tr_fast_202604230045_btcusdt", "lane": "forecast_15m", "publish_at": "2026-04-23T00:45:00Z"},
            {"task_run_id": "tr_fast_202604230045_ethusdt", "lane": "forecast_15m", "publish_at": "2026-04-23T00:45:00Z"},
        ],
    ]
    sleeps: list[float] = []
    base_now = datetime.now(timezone.utc)
    now = {"value": base_now.timestamp()}

    monkeypatch.setattr(
        run_forecast_swarm,
        "_find_upcoming_tasks",
        lambda *args, **kwargs: responses.pop(0) if responses else [],
    )
    monkeypatch.setattr(
        run_forecast_swarm,
        "parse_time",
        lambda _: base_now + timedelta(seconds=0.2),
    )
    monkeypatch.setattr(run_forecast_swarm.time, "time", lambda: now["value"])

    def _sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now["value"] += seconds

    monkeypatch.setattr(run_forecast_swarm.time, "sleep", _sleep)
    initial = [{"task_run_id": "tr_fast_202604230045_btcusdt", "lane": "forecast_15m", "publish_at": "2026-04-23T00:45:00Z"}]
    tasks = run_forecast_swarm._collect_upcoming_tasks(
        "http://127.0.0.1:1317",
        initial_tasks=initial,
        request_timeout_seconds=3,
        poll_interval_seconds=0.1,
        collection_cutoff_seconds=0.05,
    )

    assert [task["task_run_id"] for task in tasks] == [
        "tr_fast_202604230045_btcusdt",
        "tr_fast_202604230045_ethusdt",
    ]
    assert sleeps


def test_commit_submission_retries_until_success(monkeypatch):
    attempts = {"count": 0}
    sleeps: list[float] = []
    commit_deadline = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")

    def _fake_post_commit(base_url, task_run_id, payload, config=None):  # noqa: ANN001
        attempts["count"] += 1
        assert 1.0 <= config["request_timeout_seconds"] <= 2.0
        if attempts["count"] == 1:
            response = requests.Response()
            response.status_code = 400
            response._content = b'{"detail":"task not yet published"}'
            raise requests.HTTPError("not yet", response=response)
        return {"data": {"validation_status": "accepted"}}

    monkeypatch.setattr(run_forecast_swarm, "post_commit", _fake_post_commit)
    monkeypatch.setattr(run_forecast_swarm.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = run_forecast_swarm._commit_submission(
        "http://127.0.0.1:1317",
        {
            "task_run_id": "tr_fast_202604230045_btcusdt",
            "commit_deadline": commit_deadline,
            "commit_payload": {},
        },
        commit_retry_interval_seconds=0.05,
        request_config={"request_timeout_seconds": 3},
    )

    assert attempts["count"] == 2
    assert sleeps == [0.05]
    assert result["commit"]["data"]["validation_status"] == "accepted"


def test_commit_submission_preserves_subsecond_timeout_budget(monkeypatch):
    captured = {}
    commit_deadline = (datetime.now(timezone.utc) + timedelta(seconds=0.35)).isoformat().replace("+00:00", "Z")

    def _fake_post_commit(base_url, task_run_id, payload, config=None):  # noqa: ANN001
        captured["timeout"] = config["request_timeout_seconds"]
        return {"data": {"validation_status": "accepted"}}

    monkeypatch.setattr(run_forecast_swarm, "post_commit", _fake_post_commit)

    result = run_forecast_swarm._commit_submission(
        "http://127.0.0.1:1317",
        {
            "task_run_id": "tr_fast_202604230045_btcusdt",
            "commit_deadline": commit_deadline,
            "commit_payload": {},
        },
        commit_retry_interval_seconds=0.05,
        request_config={"request_timeout_seconds": 0.75},
    )

    assert captured["timeout"] == pytest.approx(0.75)
    assert result["commit"]["data"]["validation_status"] == "accepted"


def test_should_attempt_reveal_after_timeout_commit_error():
    assert run_forecast_swarm._should_attempt_reveal_after_commit_error(requests.Timeout("read timeout")) is True


def test_should_not_attempt_reveal_after_client_commit_error():
    response = requests.Response()
    response.status_code = 400
    response._content = b'{"detail":"task not yet published"}'
    exc = requests.HTTPError("bad request", response=response)

    assert run_forecast_swarm._should_attempt_reveal_after_commit_error(exc) is False


def test_should_attempt_reveal_after_commit_window_closed_error():
    response = requests.Response()
    response.status_code = 400
    response._content = b'{"detail":"commit window closed"}'
    exc = requests.HTTPError("bad request", response=response)

    assert run_forecast_swarm._should_attempt_reveal_after_commit_error(exc) is True


def test_reveal_submission_retries_timeout_until_success(monkeypatch):
    attempts = {"count": 0}
    sleeps: list[float] = []
    reveal_deadline = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")

    def _fake_post_reveal(base_url, task_run_id, payload, config=None):  # noqa: ANN001
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise requests.Timeout("read timeout")
        assert 1.0 <= config["request_timeout_seconds"] <= 2.0
        return {"data": {"validation_status": "accepted"}, "already": False}

    monkeypatch.setattr(run_forecast_swarm, "post_reveal", _fake_post_reveal)
    monkeypatch.setattr(run_forecast_swarm.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = run_forecast_swarm._reveal_submission(
        "http://127.0.0.1:1317",
        {
            "task_run_id": "tr_fast_202604230045_btcusdt",
            "reveal_deadline": reveal_deadline,
            "reveal_payload": {},
        },
        reveal_retry_interval_seconds=0.05,
        request_config={"request_timeout_seconds": 3},
    )

    assert attempts["count"] == 2
    assert sleeps == [0.05]
    assert result["reveal"]["data"]["validation_status"] == "accepted"


def test_should_not_retry_reveal_after_client_error():
    response = requests.Response()
    response.status_code = 400
    response._content = b'{"detail":"reveal window closed"}'
    exc = requests.HTTPError("bad request", response=response)

    assert run_forecast_swarm._should_retry_reveal_error(exc) is False


def test_submission_worker_count_scales_to_prepared_submission_count():
    assert run_forecast_swarm._submission_worker_count(configured_max=12, submission_count=66, task_count=2) == 24
    assert run_forecast_swarm._submission_worker_count(configured_max=24, submission_count=66, task_count=2) == 48
    assert run_forecast_swarm._submission_worker_count(configured_max=12, submission_count=2, task_count=2) == 2
    assert run_forecast_swarm._submission_worker_count(configured_max=12, submission_count=0, task_count=2) == 12
    assert run_forecast_swarm._submission_worker_count(configured_max=12, submission_count=256, task_count=16) == 128
