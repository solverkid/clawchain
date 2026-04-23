from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "three_lane"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import check_status


def test_forecast_ready_requires_full_completed_bucket_and_reward():
    acceptance_bucket = {
        "task_count": 2,
        "revealed_count": 66,
        "resolved_task_count": 2,
    }
    latest_reward_window = {"total_reward_amount": 123}

    assert check_status.forecast_ready_from_metrics(acceptance_bucket, latest_reward_window, miner_count=33) is True
    assert check_status.forecast_ready_from_metrics(
        {**acceptance_bucket, "revealed_count": 65},
        latest_reward_window,
        miner_count=33,
    ) is False
    assert check_status.forecast_ready_from_metrics(
        {**acceptance_bucket, "resolved_task_count": 1},
        latest_reward_window,
        miner_count=33,
    ) is False


def test_poker_ready_requires_reward_window_for_current_run():
    assert check_status.poker_ready_from_metrics({"miner_count": 33, "total_reward_amount": 3300}, miner_count=33) is True
    assert check_status.poker_ready_from_metrics({"miner_count": 32, "total_reward_amount": 3300}, miner_count=33) is False
    assert check_status.poker_ready_from_metrics({"miner_count": 33, "total_reward_amount": 0}, miner_count=33) is False


def test_arena_ready_requires_current_run_result_set_and_nondefault_multiplier():
    assert check_status.arena_ready_from_metrics({"result_count": 33, "nondefault_multiplier_count": 5}, miner_count=33) is True
    assert check_status.arena_ready_from_metrics({"result_count": 32, "nondefault_multiplier_count": 5}, miner_count=33) is False
    assert check_status.arena_ready_from_metrics({"result_count": 33, "nondefault_multiplier_count": 0}, miner_count=33) is False


def test_collect_status_uses_bucket_scoped_reward_window_and_distinct_task_counts(tmp_path, monkeypatch):
    addresses = [f"claw1test{i:02d}" for i in range(33)]
    manifest = {
        "count": 33,
        "manifest_root": "sha256:test-manifest",
        "miners": [{"address": address} for address in addresses],
    }

    class FakeConnection:
        async def fetchval(self, sql, *args):
            if "FROM miners" in sql:
                return 33
            if "FROM forecast_submissions fs" in sql and "JOIN forecast_task_runs tr" in sql:
                return 66
            raise AssertionError(f"unexpected fetchval sql: {sql}")

        async def fetchrow(self, sql, *args):
            if "WITH latest_bucket AS" in sql:
                return {
                    "publish_at": "2026-04-23 02:55:00+00:00",
                    "task_count": 2,
                    "committed_count": 0,
                    "revealed_count": 0,
                    "revealed_task_count": 0,
                    "revealed_miner_count": 0,
                    "resolved_task_count": 0,
                    "resolve_at": "2026-04-23 03:00:00+00:00",
                }
            if "WITH bucket_metrics AS" in sql:
                return {
                    "publish_at": "2026-04-23 02:50:00+00:00",
                    "task_count": 2,
                    "committed_count": 66,
                    "revealed_count": 66,
                    "revealed_task_count": 2,
                    "revealed_miner_count": 33,
                    "resolved_task_count": 2,
                    "resolve_at": "2026-04-23 02:55:00+00:00",
                }
            if "FROM bucket_reward_windows brw" in sql:
                return {
                    "id": "rw:forecast:bucket-0250",
                    "state": "finalized",
                    "miner_count": 33,
                    "total_reward_amount": 123,
                    "updated_at": "2026-04-23 02:55:03+00:00",
                }
            if "SELECT *" in sql and "WHERE task_count > 0" in sql and "revealed_count >= task_count * $3::int" in sql:
                return {
                    "publish_at": "2026-04-23 02:50:00+00:00",
                    "task_count": 2,
                    "committed_count": 66,
                    "revealed_count": 66,
                    "revealed_task_count": 2,
                    "revealed_miner_count": 33,
                    "resolved_task_count": 2,
                    "resolve_at": "2026-04-23 02:55:00+00:00",
                }
            if "lane LIKE 'poker_mtt_%'" in sql:
                return {
                    "id": "rw:poker:test",
                    "lane": "poker_mtt_daily",
                    "state": "finalized",
                    "miner_count": 33,
                    "total_reward_amount": 3300,
                    "settlement_batch_id": "sb:poker:test",
                    "updated_at": "2026-04-23 02:49:33+00:00",
                }
            if "FROM arena_result_entries" in sql and "ORDER BY updated_at DESC" in sql:
                return {
                    "tournament_id": "tour:wave-test-01",
                    "miner_address": addresses[0],
                    "multiplier_after": 1.1,
                    "updated_at": "2026-04-23 02:49:51+00:00",
                }
            if "COUNT(DISTINCT miner_address) AS result_count" in sql:
                return {
                    "result_count": 33,
                    "nondefault_multiplier_count": 20,
                    "updated_at": "2026-04-23 02:49:51+00:00",
                }
            if "FROM settlement_batches" in sql:
                return {
                    "id": "sb:test",
                    "lane": "forecast_15m",
                    "state": "open",
                    "miner_count": 33,
                    "total_reward_amount": 123,
                    "updated_at": "2026-04-23 02:55:05+00:00",
                }
            raise AssertionError(f"unexpected fetchrow sql: {sql}")

        async def close(self):
            return None

    async def fake_connect(*args, **kwargs):
        return FakeConnection()

    monkeypatch.setattr(check_status.asyncpg, "connect", fake_connect)
    output_path = tmp_path / "status.json"

    payload = asyncio.run(
        check_status.collect_status(
            database_url="postgresql://example.test/clawchain",
            manifest=manifest,
            output_path=output_path,
            tail_lines=5,
            forecast_publish_after=check_status._parse_optional_time("2026-04-23T02:49:21Z"),
            poker_reward_window_id="rw:poker:test",
            arena_tournament_prefix="tour:wave-test-",
        )
    )

    assert payload["forecast"]["latest_bucket"]["publish_at"] == "2026-04-23 02:55:00+00:00"
    assert payload["forecast"]["latest_completed_bucket"]["publish_at"] == "2026-04-23 02:50:00+00:00"
    assert payload["forecast"]["latest_fully_revealed_bucket"]["publish_at"] == "2026-04-23 02:50:00+00:00"
    assert payload["forecast"]["expected_revealed_count"] == 66
    assert payload["forecast"]["latest_completed_expected_revealed_count"] == 66
    assert payload["forecast"]["latest_fully_revealed_expected_revealed_count"] == 66
    assert payload["forecast"]["latest_reward_window"]["id"] == "rw:forecast:bucket-0250"
    assert payload["forecast"]["ready"] is True
    assert payload["all_ready"] is True
    assert output_path.exists() is True
