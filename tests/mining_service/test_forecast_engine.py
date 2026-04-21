from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine
import models
from repository import FakeRepository
from pg_repository import normalize_database_url


class StaticTaskProvider:
    def __init__(self, resolutions, daily_resolutions=None):
        self.resolutions = list(resolutions)
        self.daily_resolutions = list(daily_resolutions or [])

    async def build_fast_task(self, now, settings, asset):  # noqa: ANN001
        return forecast_engine.build_fast_task(now, settings=settings, asset=asset)

    async def resolve_fast_task(self, task):  # noqa: ANN001
        if self.resolutions:
            return self.resolutions.pop(0)
        return {"outcome": None, "resolution_status": "pending", "commit_close_ref_price": task.get("commit_close_ref_price")}

    async def resolve_daily_task(self, task):  # noqa: ANN001
        if self.daily_resolutions:
            return self.daily_resolutions.pop(0)
        return {
            "outcome": 1,
            "resolution_status": "resolved",
            "start_ref_price": 70000.0,
            "end_ref_price": 71000.0,
        }

    async def aclose(self):
        return None


class GuardedMinerWriterRepository(FakeRepository):
    def __init__(self):
        super().__init__()
        self.writer_calls: list[tuple[str, str]] = []

    async def update_miner(self, address: str, updates: dict) -> dict:  # noqa: ARG002
        raise AssertionError("generic update_miner should not be used")

    async def update_miner_cluster_identity(
        self,
        address: str,
        *,
        economic_unit_id: str,
        updated_at,
        ip_address: str | None = None,
        user_agent_hash: str | None = None,
    ) -> dict:
        self.writer_calls.append(("cluster_identity", address))
        updates = {
            "economic_unit_id": economic_unit_id,
            "updated_at": updated_at,
        }
        if ip_address is not None:
            updates["ip_address"] = ip_address
        if user_agent_hash is not None:
            updates["user_agent_hash"] = user_agent_hash
        return await FakeRepository.update_miner(self, address, updates)

    async def update_miner_forecast_participation(
        self,
        address: str,
        *,
        updated_at,
        forecast_commits: int | None = None,
        forecast_reveals: int | None = None,
        ops_reliability: float | None = None,
        fast_task_opportunities: int | None = None,
        fast_task_misses: int | None = None,
        fast_window_start_at=None,
    ) -> dict:
        self.writer_calls.append(("forecast_participation", address))
        updates = {"updated_at": updated_at}
        if forecast_commits is not None:
            updates["forecast_commits"] = forecast_commits
        if forecast_reveals is not None:
            updates["forecast_reveals"] = forecast_reveals
        if ops_reliability is not None:
            updates["ops_reliability"] = ops_reliability
        if fast_task_opportunities is not None:
            updates["fast_task_opportunities"] = fast_task_opportunities
        if fast_task_misses is not None:
            updates["fast_task_misses"] = fast_task_misses
        if fast_window_start_at is not None:
            updates["fast_window_start_at"] = fast_window_start_at
        return await FakeRepository.update_miner(self, address, updates)

    async def update_miner_forecast_settlement(
        self,
        address: str,
        *,
        updated_at,
        total_rewards: int | None = None,
        held_rewards: int | None = None,
        settled_tasks: int | None = None,
        correct_direction_count: int | None = None,
        edge_score_total: float | None = None,
        model_reliability: float | None = None,
        admission_state: str | None = None,
    ) -> dict:
        self.writer_calls.append(("forecast_settlement", address))
        updates = {"updated_at": updated_at}
        if total_rewards is not None:
            updates["total_rewards"] = total_rewards
        if held_rewards is not None:
            updates["held_rewards"] = held_rewards
        if settled_tasks is not None:
            updates["settled_tasks"] = settled_tasks
        if correct_direction_count is not None:
            updates["correct_direction_count"] = correct_direction_count
        if edge_score_total is not None:
            updates["edge_score_total"] = edge_score_total
        if model_reliability is not None:
            updates["model_reliability"] = model_reliability
        if admission_state is not None:
            updates["admission_state"] = admission_state
        return await FakeRepository.update_miner(self, address, updates)

    async def update_miner_public_ranking(self, address: str, *, public_rank: int, public_elo: int) -> dict:
        self.writer_calls.append(("public_ranking", address))
        return await FakeRepository.update_miner(
            self,
            address,
            {
                "public_rank": public_rank,
                "public_elo": public_elo,
            },
        )

    async def update_arena_miner_multiplier(self, address: str, *, arena_multiplier: float, updated_at) -> dict:
        self.writer_calls.append(("arena_multiplier", address))
        return await FakeRepository.update_miner(
            self,
            address,
            {
                "arena_multiplier": arena_multiplier,
                "updated_at": updated_at,
            },
        )

    async def update_poker_mtt_miner_multiplier(self, address: str, *, poker_mtt_multiplier: float, updated_at) -> dict:
        self.writer_calls.append(("poker_mtt_multiplier", address))
        return await FakeRepository.update_miner(
            self,
            address,
            {
                "poker_mtt_multiplier": poker_mtt_multiplier,
                "updated_at": updated_at,
            },
        )


class GuardedSettlementWriterRepository(GuardedMinerWriterRepository):
    async def save_reward_window(self, reward_window: dict) -> dict:  # noqa: ARG002
        raise AssertionError("generic save_reward_window should not be used")

    async def save_settlement_batch(self, settlement_batch: dict) -> dict:  # noqa: ARG002
        raise AssertionError("generic save_settlement_batch should not be used")

    async def link_reward_window_settlement_batch(
        self,
        reward_window_id: str,
        *,
        settlement_batch_id: str,
        updated_at,
    ) -> dict:
        self.writer_calls.append(("reward_window_link", reward_window_id))
        return await FakeRepository.save_reward_window(
            self,
            {
                "id": reward_window_id,
                "settlement_batch_id": settlement_batch_id,
                "updated_at": updated_at,
            },
        )

    async def sync_open_settlement_batch(
        self,
        settlement_batch_id: str,
        *,
        lane: str,
        window_start_at,
        window_end_at,
        reward_window_ids: list[str],
        policy_bundle_version: str,
        task_count: int,
        miner_count: int,
        total_reward_amount: int,
        updated_at,
        created_at=None,
    ) -> dict:
        self.writer_calls.append(("settlement_sync_open", settlement_batch_id))
        payload = {
            "id": settlement_batch_id,
            "lane": lane,
            "state": "open",
            "window_start_at": window_start_at,
            "window_end_at": window_end_at,
            "reward_window_ids": reward_window_ids,
            "policy_bundle_version": policy_bundle_version,
            "task_count": task_count,
            "miner_count": miner_count,
            "total_reward_amount": total_reward_amount,
            "updated_at": updated_at,
        }
        if created_at is not None:
            payload["created_at"] = created_at
            payload["anchor_job_id"] = None
            payload["anchor_schema_version"] = None
            payload["canonical_root"] = None
            payload["anchor_payload_json"] = None
            payload["anchor_payload_hash"] = None
        return await FakeRepository.save_settlement_batch(self, payload)

    async def mark_settlement_batch_anchor_ready(
        self,
        settlement_batch_id: str,
        *,
        policy_bundle_version: str,
        anchor_schema_version: str,
        canonical_root: str,
        anchor_payload_json: dict,
        anchor_payload_hash: str,
        updated_at,
    ) -> dict:
        self.writer_calls.append(("settlement_anchor_ready", settlement_batch_id))
        return await FakeRepository.save_settlement_batch(
            self,
            {
                "id": settlement_batch_id,
                "state": "anchor_ready",
                "anchor_job_id": None,
                "policy_bundle_version": policy_bundle_version,
                "anchor_schema_version": anchor_schema_version,
                "canonical_root": canonical_root,
                "anchor_payload_json": anchor_payload_json,
                "anchor_payload_hash": anchor_payload_hash,
                "updated_at": updated_at,
            },
        )

    async def mark_settlement_batch_anchor_submitted(
        self,
        settlement_batch_id: str,
        *,
        anchor_job_id: str,
        updated_at,
    ) -> dict:
        self.writer_calls.append(("settlement_anchor_submitted", settlement_batch_id))
        return await FakeRepository.save_settlement_batch(
            self,
            {
                "id": settlement_batch_id,
                "state": "anchor_submitted",
                "anchor_job_id": anchor_job_id,
                "updated_at": updated_at,
            },
        )

    async def mark_settlement_batch_terminal(
        self,
        settlement_batch_id: str,
        *,
        state: str,
        updated_at,
    ) -> dict:
        self.writer_calls.append(("settlement_terminal", settlement_batch_id))
        return await FakeRepository.save_settlement_batch(
            self,
            {
                "id": settlement_batch_id,
                "state": state,
                "updated_at": updated_at,
            },
        )

    async def cancel_settlement_batch(
        self,
        settlement_batch_id: str,
        *,
        total_reward_amount: int,
        updated_at,
    ) -> dict:
        self.writer_calls.append(("settlement_cancel", settlement_batch_id))
        return await FakeRepository.save_settlement_batch(
            self,
            {
                "id": settlement_batch_id,
                "state": "cancelled",
                "total_reward_amount": total_reward_amount,
                "anchor_job_id": None,
                "anchor_schema_version": None,
                "canonical_root": None,
                "anchor_payload_json": None,
                "anchor_payload_hash": None,
                "updated_at": updated_at,
            },
        )


def test_build_fast_task_window():
    now = datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc)
    settings = forecast_engine.ForecastSettings(
        fast_task_seconds=900,
        commit_window_seconds=3,
        reveal_window_seconds=13,
    )

    task = forecast_engine.build_fast_task(now, settings=settings, asset="BTCUSDT")

    assert task["lane"] == "forecast_15m"
    assert task["publish_at"] == "2026-04-09T09:00:00Z"
    assert task["commit_deadline"] == "2026-04-09T09:00:03Z"
    assert task["reveal_deadline"] == "2026-04-09T09:00:13Z"
    assert task["resolve_at"] == "2026-04-09T09:15:00Z"
    assert task["pack_hash"].startswith("sha256:")
    assert task["created_at"] == "2026-04-09T09:00:01Z"
    assert task["updated_at"] == "2026-04-09T09:00:01Z"


def test_build_fast_task_freezes_snapshot_metadata_with_canonical_pack_hash():
    now = datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc)
    settings = forecast_engine.ForecastSettings()

    task = forecast_engine.build_fast_task(now, settings=settings, asset="BTCUSDT")
    expected_pack_hash = "sha256:" + hashlib.sha256(
        json.dumps(task["pack_json"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    assert task["pack_json"]["snapshot_source"] == "synthetic"
    assert task["pack_json"]["snapshot_frozen_at"] == task["created_at"]
    assert task["pack_json"]["snapshot_freshness_seconds"] == {"binance": None, "polymarket": None}
    assert task["pack_hash"] == expected_pack_hash


def test_build_daily_anchor_task_contains_prediction_inputs():
    now = datetime(2026, 4, 10, 0, 0, 1, tzinfo=timezone.utc)

    task = forecast_engine.build_daily_anchor_task(now, asset="BTC")

    pack = task["pack_json"]
    assert task["lane"] == "daily_anchor"
    assert "polymarket_snapshot" in pack
    assert "binance_snapshot" in pack
    assert "noisy_fragments" in pack


def test_score_probability_rewards_edge_over_baseline():
    strong = forecast_engine.score_probability(p_yes_bps=6500, baseline_q_bps=5500, outcome=1)
    copier = forecast_engine.score_probability(p_yes_bps=5510, baseline_q_bps=5500, outcome=1)

    assert strong > copier
    assert copier >= 0


def test_score_probability_applies_copy_cap_within_three_percent():
    capped = forecast_engine.score_probability(p_yes_bps=5600, baseline_q_bps=5500, outcome=1)
    expected = (((0.55 - 1.0) ** 2 - (0.56 - 1.0) ** 2) + 0.015) * 0.25

    assert capped == expected


def test_compute_economic_unit_components_is_transitive_over_server_evidence():
    miners = [
        {"address": "claw1a", "ip_address": "10.0.0.1", "user_agent_hash": None},
        {"address": "claw1b", "ip_address": "10.0.0.2", "user_agent_hash": "ua:shared"},
        {"address": "claw1c", "ip_address": "10.0.0.1", "user_agent_hash": "ua:shared"},
    ]

    components = forecast_engine.compute_economic_unit_components(miners)

    assert components["claw1a"] == components["claw1b"] == components["claw1c"]


def test_compute_commit_hash_is_stable():
    commit_hash = forecast_engine.compute_commit_hash(
        task_run_id="tr_fast_202604090900_btcusdt",
        miner_address="claw1miner",
        p_yes_bps=6200,
        reveal_nonce="salt-1",
    )

    assert len(commit_hash) == 64
    assert commit_hash == forecast_engine.compute_commit_hash(
        task_run_id="tr_fast_202604090900_btcusdt",
        miner_address="claw1miner",
        p_yes_bps=6200,
        reveal_nonce="salt-1",
    )


def test_resolve_fast_task_produces_deterministic_outcome():
    task = {
        "task_run_id": "tr_fast_202604090900_btcusdt",
        "asset": "BTCUSDT",
        "baseline_q_bps": 5420,
    }

    result_1 = forecast_engine.resolve_fast_task(task)
    result_2 = forecast_engine.resolve_fast_task(task)

    assert result_1 == result_2
    assert result_1["outcome"] in (0, 1)
    assert result_1["commit_close_ref_price"] > 0
    assert result_1["end_ref_price"] > 0


def test_normalize_database_url_prefers_asyncpg():
    assert (
        normalize_database_url("postgresql://clawchain:pw@127.0.0.1:55432/clawchain")
        == "postgresql+asyncpg://clawchain:pw@127.0.0.1:55432/clawchain"
    )


def test_models_expose_deterministic_settlement_columns():
    task_columns = set(models.forecast_task_runs.c.keys())
    reward_window_columns = set(models.reward_windows.c.keys())
    settlement_batch_columns = set(models.settlement_batches.c.keys())
    budget_ledger_columns = set(models.poker_mtt_budget_ledgers.c.keys())
    poker_mtt_final_ranking_columns = set(models.poker_mtt_final_rankings.c.keys())
    poker_mtt_result_columns = set(models.poker_mtt_result_entries.c.keys())
    poker_mtt_multiplier_columns = set(models.poker_mtt_multiplier_snapshots.c.keys())

    assert {"task_state", "degraded_reason", "void_reason", "resolution_source"} <= task_columns
    assert {"policy_bundle_version", "canonical_root"} <= reward_window_columns
    assert "policy_bundle_version" in settlement_batch_columns
    assert {"budget_source_id", "emission_epoch_id", "approved_amount", "budget_root"} <= budget_ledger_columns
    assert {"rank_state", "chip_delta", "locked_at", "anchorable_at"} <= poker_mtt_final_ranking_columns
    assert {"rank_state", "chip_delta", "locked_at", "anchorable_at"} <= poker_mtt_result_columns
    assert {"effective_window_start_at", "effective_window_end_at"} <= poker_mtt_multiplier_columns
    assert (
        normalize_database_url("postgresql+asyncpg://clawchain:pw@127.0.0.1:55432/clawchain")
        == "postgresql+asyncpg://clawchain:pw@127.0.0.1:55432/clawchain"
    )


def test_reconcile_marks_fast_task_pending_until_official_resolution():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": None, "resolution_status": "pending", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1pendingminer",
            name="pending-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        task["commit_close_ref_price"] = 70000.5
        await repo.upsert_task(task)

        await service.commit_submission(
            task_run_id=task["task_run_id"],
            miner_address="claw1pendingminer",
            economic_unit_id="eu:pending",
            request_id="req-commit",
            commit_hash="hash",
            commit_nonce="nonce",
            accepted_at=datetime(2026, 4, 10, 9, 0, 2, tzinfo=timezone.utc),
        )
        await repo.save_submission(
            {
                **(await repo.get_submission(task["task_run_id"], "claw1pendingminer")),
                "p_yes_bps": 6200,
                "state": "revealed",
                "accepted_reveal_at": "2026-04-10T09:00:06Z",
                "updated_at": "2026-04-10T09:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 9, 1, 5, tzinfo=timezone.utc))

        saved_task = await repo.get_task(task["task_run_id"])
        saved_submission = await repo.get_submission(task["task_run_id"], "claw1pendingminer")
        miner = await repo.get_miner("claw1pendingminer")
        status = await service.get_miner_status("claw1pendingminer", datetime(2026, 4, 10, 9, 1, 6, tzinfo=timezone.utc))

        assert saved_task["state"] == "awaiting_resolution"
        assert saved_submission["state"] == "pending_resolution"
        assert saved_submission["reward_amount"] == 0
        assert miner["settled_tasks"] == 0
        assert status["maturity_state"] == "pending_resolution"

    import asyncio

    asyncio.run(scenario())


def test_reconcile_persists_resolution_source_for_pending_and_resolved_fast_tasks():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(
            fast_task_seconds=60,
            commit_window_seconds=5,
            reveal_window_seconds=10,
        )
        provider = StaticTaskProvider(
            [
                {
                    "outcome": None,
                    "resolution_status": "pending",
                    "resolution_method": "polymarket_gamma_pending",
                    "commit_close_ref_price": 70000.5,
                    "end_ref_price": None,
                },
                {
                    "outcome": 1,
                    "resolution_status": "resolved",
                    "resolution_method": "polymarket_gamma",
                    "commit_close_ref_price": 70000.5,
                    "end_ref_price": None,
                },
            ]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1resolutionminer",
            name="resolution-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 10, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        task["commit_close_ref_price"] = 70000.5
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1resolutionminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1resolutionminer",
                "economic_unit_id": "eu:resolution",
                "commit_request_id": "req-resolution-commit",
                "reveal_request_id": "req-resolution-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6200,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T10:00:02Z",
                "accepted_reveal_at": "2026-04-10T10:00:06Z",
                "created_at": "2026-04-10T10:00:02Z",
                "updated_at": "2026-04-10T10:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 10, 1, 5, tzinfo=timezone.utc))
        pending_task = await repo.get_task(task["task_run_id"])

        await service.reconcile(datetime(2026, 4, 10, 10, 3, 5, tzinfo=timezone.utc))
        resolved_task = await repo.get_task(task["task_run_id"])

        assert pending_task["state"] == "awaiting_resolution"
        assert pending_task["resolution_source"] == "polymarket_gamma_pending"
        assert resolved_task["state"] == "resolved"
        assert resolved_task["resolution_source"] == "polymarket_gamma"

    import asyncio

    asyncio.run(scenario())


def test_confirm_anchor_job_on_chain_marks_anchored():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )
        typed_confirmation = {}

        async def fake_confirmer(tx_hash, now):  # noqa: ANN001
            return {
                "tx_hash": tx_hash,
                "found": True,
                "confirmation_status": "confirmed",
                "height": 123,
                "code": 0,
                "raw_log": "",
                **typed_confirmation,
            }

        service = forecast_engine.ForecastMiningService(
            repo,
            settings,
            task_provider=provider,
            chain_tx_confirmer=fake_confirmer,
        )

        await service.register_miner(
            address="claw1confirmminer",
            name="confirm-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 17, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1confirmminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1confirmminer",
                "economic_unit_id": "eu:confirm",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6400,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T17:00:02Z",
                "accepted_reveal_at": "2026-04-10T17:00:06Z",
                "created_at": "2026-04-10T17:00:02Z",
                "updated_at": "2026-04-10T17:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 17, 1, 5, tzinfo=timezone.utc))
        batch = (await repo.list_settlement_batches())[0]
        await service.retry_anchor_settlement_batch(batch["id"], now=datetime(2026, 4, 10, 17, 1, 6, tzinfo=timezone.utc))
        ready_batch = await repo.get_settlement_batch(batch["id"])
        submitted = await service.submit_anchor_job(batch["id"], now=datetime(2026, 4, 10, 17, 1, 7, tzinfo=timezone.utc))
        await repo.save_anchor_job(
            {
                **(await repo.get_anchor_job(submitted["anchor_job_id"])),
                "broadcast_status": "broadcast_submitted",
                "broadcast_tx_hash": "CONFIRM123TX",
                "last_broadcast_at": "2026-04-10T17:01:08Z",
                "updated_at": "2026-04-10T17:01:08Z",
            }
        )

        tx_only_receipt = await service.confirm_anchor_job_on_chain(
            submitted["anchor_job_id"],
            now=datetime(2026, 4, 10, 17, 1, 9, tzinfo=timezone.utc),
        )
        tx_only_job = await repo.get_anchor_job(submitted["anchor_job_id"])
        tx_only_batch = await repo.get_settlement_batch(batch["id"])

        assert tx_only_receipt["chain_confirmation_status"] == "typed_state_missing"
        assert tx_only_receipt["anchor_job_state"] == "anchor_failed"
        assert tx_only_job["state"] == "anchor_failed"
        assert tx_only_job["chain_confirmation_status"] == "typed_state_missing"
        assert tx_only_batch["state"] == "anchor_failed"

        typed_confirmation.update(
            {
                "confirmed": True,
                "query_response": {
                    "anchor": {
                        "settlement_batch_id": batch["id"],
                        "anchor_job_id": submitted["anchor_job_id"],
                        "lane": ready_batch["lane"],
                        "schema_version": ready_batch["anchor_schema_version"],
                        "policy_bundle_version": ready_batch["anchor_payload_json"]["policy_bundle_version"],
                        "canonical_root": ready_batch["canonical_root"],
                        "anchor_payload_hash": ready_batch["anchor_payload_hash"],
                        "reward_window_ids_root": ready_batch["anchor_payload_json"]["reward_window_ids_root"],
                        "task_run_ids_root": ready_batch["anchor_payload_json"]["task_run_ids_root"],
                        "miner_reward_rows_root": ready_batch["anchor_payload_json"]["miner_reward_rows_root"],
                        "window_end_at": ready_batch["window_end_at"],
                        "total_reward_amount": ready_batch["total_reward_amount"],
                    }
                },
            }
        )
        receipt = await service.confirm_anchor_job_on_chain(
            submitted["anchor_job_id"],
            now=datetime(2026, 4, 10, 17, 1, 10, tzinfo=timezone.utc),
        )
        saved_job = await repo.get_anchor_job(submitted["anchor_job_id"])
        saved_batch = await repo.get_settlement_batch(batch["id"])
        artifacts = await repo.list_artifacts_for_entity("anchor_job", submitted["anchor_job_id"])

        assert receipt["chain_confirmation_status"] == "confirmed"
        assert receipt["anchor_job_state"] == "anchored"
        assert receipt["chain_height"] == 123
        assert saved_job["state"] == "anchored"
        assert saved_batch["state"] == "anchored"
        assert any(item["kind"] == "chain_confirmation_receipt" for item in artifacts)

    import asyncio

    asyncio.run(scenario())


def test_confirm_anchor_job_on_chain_keeps_submitted_when_pending():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )

        async def fake_confirmer(tx_hash, now):  # noqa: ANN001
            return {
                "tx_hash": tx_hash,
                "found": False,
                "confirmation_status": "pending",
                "height": None,
                "code": None,
                "raw_log": "",
            }

        service = forecast_engine.ForecastMiningService(
            repo,
            settings,
            task_provider=provider,
            chain_tx_confirmer=fake_confirmer,
        )

        await service.register_miner(
            address="claw1pendingminer",
            name="pending-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 18, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1pendingminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1pendingminer",
                "economic_unit_id": "eu:pending",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6400,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T18:00:02Z",
                "accepted_reveal_at": "2026-04-10T18:00:06Z",
                "created_at": "2026-04-10T18:00:02Z",
                "updated_at": "2026-04-10T18:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 18, 1, 5, tzinfo=timezone.utc))
        batch = (await repo.list_settlement_batches())[0]
        await service.retry_anchor_settlement_batch(batch["id"], now=datetime(2026, 4, 10, 18, 1, 6, tzinfo=timezone.utc))
        submitted = await service.submit_anchor_job(batch["id"], now=datetime(2026, 4, 10, 18, 1, 7, tzinfo=timezone.utc))
        await repo.save_anchor_job(
            {
                **(await repo.get_anchor_job(submitted["anchor_job_id"])),
                "broadcast_status": "broadcast_submitted",
                "broadcast_tx_hash": "PENDING123TX",
                "last_broadcast_at": "2026-04-10T18:01:08Z",
                "updated_at": "2026-04-10T18:01:08Z",
            }
        )

        receipt = await service.confirm_anchor_job_on_chain(
            submitted["anchor_job_id"],
            now=datetime(2026, 4, 10, 18, 1, 9, tzinfo=timezone.utc),
        )
        saved_job = await repo.get_anchor_job(submitted["anchor_job_id"])
        saved_batch = await repo.get_settlement_batch(batch["id"])

        assert receipt["chain_confirmation_status"] == "pending"
        assert receipt["anchor_job_state"] == "anchor_submitted"
        assert saved_job["state"] == "anchor_submitted"
        assert saved_batch["state"] == "anchor_submitted"

    import asyncio

    asyncio.run(scenario())


def test_reconcile_pending_anchor_jobs_on_chain_confirms_broadcast_jobs():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )
        typed_confirmation = {}

        async def fake_confirmer(tx_hash, now):  # noqa: ANN001
            return {
                "tx_hash": tx_hash,
                "found": True,
                "confirmation_status": "confirmed",
                "height": 456,
                "code": 0,
                "raw_log": "",
                **typed_confirmation,
            }

        service = forecast_engine.ForecastMiningService(
            repo,
            settings,
            task_provider=provider,
            chain_tx_confirmer=fake_confirmer,
        )

        await service.register_miner(
            address="claw1sweepminer",
            name="sweep-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 19, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1sweepminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1sweepminer",
                "economic_unit_id": "eu:sweep",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6400,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T19:00:02Z",
                "accepted_reveal_at": "2026-04-10T19:00:06Z",
                "created_at": "2026-04-10T19:00:02Z",
                "updated_at": "2026-04-10T19:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 19, 1, 5, tzinfo=timezone.utc))
        batch = (await repo.list_settlement_batches())[0]
        await service.retry_anchor_settlement_batch(batch["id"], now=datetime(2026, 4, 10, 19, 1, 6, tzinfo=timezone.utc))
        ready_batch = await repo.get_settlement_batch(batch["id"])
        submitted = await service.submit_anchor_job(batch["id"], now=datetime(2026, 4, 10, 19, 1, 7, tzinfo=timezone.utc))
        await repo.save_anchor_job(
            {
                **(await repo.get_anchor_job(submitted["anchor_job_id"])),
                "broadcast_status": "broadcast_submitted",
                "broadcast_tx_hash": "SWEEP123TX",
                "last_broadcast_at": "2026-04-10T19:01:08Z",
                "updated_at": "2026-04-10T19:01:08Z",
            }
        )
        typed_confirmation.update(
            {
                "confirmed": True,
                "query_response": {
                    "anchor": {
                        "settlement_batch_id": batch["id"],
                        "anchor_job_id": submitted["anchor_job_id"],
                        "lane": ready_batch["lane"],
                        "schema_version": ready_batch["anchor_schema_version"],
                        "policy_bundle_version": ready_batch["anchor_payload_json"]["policy_bundle_version"],
                        "canonical_root": ready_batch["canonical_root"],
                        "anchor_payload_hash": ready_batch["anchor_payload_hash"],
                        "reward_window_ids_root": ready_batch["anchor_payload_json"]["reward_window_ids_root"],
                        "task_run_ids_root": ready_batch["anchor_payload_json"]["task_run_ids_root"],
                        "miner_reward_rows_root": ready_batch["anchor_payload_json"]["miner_reward_rows_root"],
                        "window_end_at": ready_batch["window_end_at"],
                        "total_reward_amount": ready_batch["total_reward_amount"],
                    }
                },
            }
        )

        items = await service.reconcile_pending_anchor_jobs_on_chain(
            now=datetime(2026, 4, 10, 19, 1, 9, tzinfo=timezone.utc),
        )
        saved_job = await repo.get_anchor_job(submitted["anchor_job_id"])

        assert len(items) == 1
        assert items[0]["anchor_job_id"] == submitted["anchor_job_id"]
        assert items[0]["chain_confirmation_status"] == "confirmed"
        assert saved_job["state"] == "anchored"

    import asyncio

    asyncio.run(scenario())


def test_reconcile_settles_after_official_resolution_arrives():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [
                {"outcome": None, "resolution_status": "pending", "commit_close_ref_price": 70000.5, "end_ref_price": None},
                {"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None},
            ]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1resolvedminer",
            name="resolved-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        task["commit_close_ref_price"] = 70000.5
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1resolvedminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1resolvedminer",
                "economic_unit_id": "eu:resolved",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6200,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T09:00:02Z",
                "accepted_reveal_at": "2026-04-10T09:00:06Z",
                "created_at": "2026-04-10T09:00:02Z",
                "updated_at": "2026-04-10T09:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 9, 1, 5, tzinfo=timezone.utc))
        await service.reconcile(datetime(2026, 4, 10, 9, 3, 5, tzinfo=timezone.utc))

        saved_task = await repo.get_task(task["task_run_id"])
        saved_submission = await repo.get_submission(task["task_run_id"], "claw1resolvedminer")
        miner = await repo.get_miner("claw1resolvedminer")

        assert saved_task["state"] == "resolved"
        assert saved_task["outcome"] == 1
        assert saved_submission["state"] == "resolved"
        assert saved_submission["reward_amount"] > 0
        assert miner["settled_tasks"] == 1

    import asyncio

    asyncio.run(scenario())


def test_probationary_rewards_use_20_80_admission_hold():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1holdminer",
            name="hold-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        task["commit_close_ref_price"] = 70000.5
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1holdminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1holdminer",
                "economic_unit_id": "eu:assigned",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6200,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T09:00:02Z",
                "accepted_reveal_at": "2026-04-10T09:00:06Z",
                "created_at": "2026-04-10T09:00:02Z",
                "updated_at": "2026-04-10T09:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 9, 1, 5, tzinfo=timezone.utc))

        saved_submission = await repo.get_submission(task["task_run_id"], "claw1holdminer")
        miner = await repo.get_miner("claw1holdminer")
        status = await service.get_miner_status("claw1holdminer", datetime(2026, 4, 10, 9, 1, 6, tzinfo=timezone.utc))
        holds = await repo.list_hold_entries_for_miner("claw1holdminer")
        expected_released = int(round(saved_submission["reward_amount"] * 0.2))

        assert saved_submission["reward_amount"] > 0
        assert miner["total_rewards"] == expected_released
        assert miner["held_rewards"] == saved_submission["reward_amount"] - expected_released
        assert len(holds) == 1
        assert holds[0]["amount_held"] == miner["held_rewards"]
        assert holds[0]["state"] == "held"
        assert status["admission_state"] == "probation"
        assert status["anti_abuse_discount"] == 0.2

    import asyncio

    asyncio.run(scenario())


def test_matured_hold_entry_releases_via_ledger():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1matureminer",
            name="mature-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await repo.update_miner(
            "claw1matureminer",
            {
                "forecast_reveals": 500,
                "created_at": "2026-04-01T09:00:00Z",
                "held_rewards": 12345,
                "admission_state": "probation",
                "updated_at": "2026-04-01T09:00:00Z",
            },
        )
        await repo.save_hold_entry(
            {
                "id": "hold:test:claw1matureminer",
                "miner_address": "claw1matureminer",
                "task_run_id": "tr_fast_old_btcusdt",
                "submission_id": "sub:old",
                "amount_held": 12345,
                "amount_released": 0,
                "state": "held",
                "release_after": "2026-04-02T09:00:00Z",
                "created_at": "2026-04-02T09:00:00Z",
                "updated_at": "2026-04-02T09:00:00Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 9, 1, 5, tzinfo=timezone.utc))

        miner = await repo.get_miner("claw1matureminer")
        holds = await repo.list_hold_entries_for_miner("claw1matureminer")

        assert miner["held_rewards"] == 0
        assert miner["admission_state"] == "mature"
        assert len(holds) == 1
        assert holds[0]["state"] == "released"
        assert holds[0]["amount_released"] == holds[0]["amount_held"]

    import asyncio

    asyncio.run(scenario())


def test_registering_linked_miners_opens_cluster_risk_case():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings()
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1linka",
            name="link-a",
            public_key="pubkey-a",
            miner_version="0.4.0",
            ip_address="10.0.0.1",
            user_agent="shared-agent",
        )
        await service.register_miner(
            address="claw1linkb",
            name="link-b",
            public_key="pubkey-b",
            miner_version="0.4.0",
            ip_address="10.0.0.2",
            user_agent="shared-agent",
        )

        cases = await repo.list_risk_cases(state="open")

        assert len(cases) == 1
        assert cases[0]["case_type"] == "economic_unit_cluster"
        assert sorted(cases[0]["evidence_json"]["member_addresses"]) == ["claw1linka", "claw1linkb"]

    import asyncio

    asyncio.run(scenario())


def test_duplicate_reveal_creates_open_risk_case():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1dupa",
            name="dup-a",
            public_key="pubkey-a",
            miner_version="0.4.0",
            ip_address="10.0.0.1",
            user_agent="shared-agent",
        )
        await service.register_miner(
            address="claw1dupb",
            name="dup-b",
            public_key="pubkey-b",
            miner_version="0.4.0",
            ip_address="10.0.0.1",
            user_agent="shared-agent",
        )

        now = datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        await repo.upsert_task(task)

        for miner_address, p_yes_bps in [("claw1dupa", 6200), ("claw1dupb", 6300)]:
            reveal_nonce = f"nonce-{miner_address}"
            commit_hash = forecast_engine.compute_commit_hash(task["task_run_id"], miner_address, p_yes_bps, reveal_nonce)
            miner = await repo.get_miner(miner_address)
            await service.commit_submission(
                task_run_id=task["task_run_id"],
                miner_address=miner_address,
                economic_unit_id=miner["economic_unit_id"],
                request_id=f"commit-{miner_address}",
                commit_hash=commit_hash,
                commit_nonce=reveal_nonce,
                accepted_at=datetime(2026, 4, 10, 9, 0, 2, tzinfo=timezone.utc),
                ip_address="10.0.0.1",
                user_agent="shared-agent",
            )
            await service.reveal_submission(
                task_run_id=task["task_run_id"],
                miner_address=miner_address,
                economic_unit_id=miner["economic_unit_id"],
                request_id=f"reveal-{miner_address}",
                p_yes_bps=p_yes_bps,
                reveal_nonce=reveal_nonce,
                accepted_at=datetime(2026, 4, 10, 9, 0, 6, tzinfo=timezone.utc),
                ip_address="10.0.0.1",
                user_agent="shared-agent",
            )

        second_submission = await repo.get_submission(task["task_run_id"], "claw1dupb")
        cases = await repo.list_risk_cases(state="open")
        status = await service.get_miner_status("claw1dupb", datetime(2026, 4, 10, 9, 0, 7, tzinfo=timezone.utc))

        assert second_submission["eligibility_status"] == "audit_only"
        assert status["reward_eligibility_status"] == "audit_only"
        assert status["risk_review_state"] == "review_required"
        duplicate_cases = [case for case in cases if case["case_type"] == "economic_unit_duplicate"]
        assert len(duplicate_cases) == 1
        assert duplicate_cases[0]["task_run_id"] == task["task_run_id"]
        assert sorted(duplicate_cases[0]["evidence_json"]["miner_addresses"]) == ["claw1dupa", "claw1dupb"]

    import asyncio

    asyncio.run(scenario())


def test_missing_fast_tasks_penalizes_selective_participation():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [
                {"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None},
                {"outcome": 0, "resolution_status": "resolved", "commit_close_ref_price": 3490.5, "end_ref_price": None},
            ]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1selectiveminer",
            name="selective-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        now = datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc)
        btc_task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        eth_task = forecast_engine.build_fast_task(now, settings, asset="ETHUSDT")
        btc_task["commit_close_ref_price"] = 70000.5
        eth_task["commit_close_ref_price"] = 3490.5
        await repo.upsert_task(btc_task)
        await repo.upsert_task(eth_task)

        await repo.save_submission(
            {
                "id": f"sub:{btc_task['task_run_id']}:claw1selectiveminer",
                "task_run_id": btc_task["task_run_id"],
                "miner_address": "claw1selectiveminer",
                "economic_unit_id": "eu:assigned",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6200,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T09:00:02Z",
                "accepted_reveal_at": "2026-04-10T09:00:06Z",
                "created_at": "2026-04-10T09:00:02Z",
                "updated_at": "2026-04-10T09:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 9, 1, 5, tzinfo=timezone.utc))

        miner = await repo.get_miner("claw1selectiveminer")

        assert miner["fast_task_opportunities"] == 2
        assert miner["fast_task_misses"] == 1
        assert miner["ops_reliability"] < 1.0

    import asyncio

    asyncio.run(scenario())


def test_fast_participation_window_resets_after_one_day():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1windowminer",
            name="window-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await repo.update_miner(
            "claw1windowminer",
            {
                "fast_task_opportunities": 9,
                "fast_task_misses": 8,
                "fast_window_start_at": "2026-04-08T09:00:00Z",
            },
        )
        now = datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        task["commit_close_ref_price"] = 70000.5
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1windowminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1windowminer",
                "economic_unit_id": "eu:assigned",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6200,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T09:00:02Z",
                "accepted_reveal_at": "2026-04-10T09:00:06Z",
                "created_at": "2026-04-10T09:00:02Z",
                "updated_at": "2026-04-10T09:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 9, 1, 5, tzinfo=timezone.utc))

        miner = await repo.get_miner("claw1windowminer")

        assert miner["fast_task_opportunities"] == 1
        assert miner["fast_task_misses"] == 0
        assert miner["ops_reliability"] >= 1.0

    import asyncio

    asyncio.run(scenario())


def test_daily_anchor_updates_model_reliability_without_rewards():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [],
            daily_resolutions=[
                {
                    "outcome": 1,
                    "resolution_status": "resolved",
                    "start_ref_price": 70000.0,
                    "end_ref_price": 71200.0,
                }
            ],
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1dailyminer",
            name="daily-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 0, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_daily_anchor_task(now, asset="BTC")
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1dailyminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1dailyminer",
                "economic_unit_id": "eu:daily",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 8500,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T00:00:02Z",
                "accepted_reveal_at": "2026-04-10T00:00:06Z",
                "created_at": "2026-04-10T00:00:02Z",
                "updated_at": "2026-04-10T00:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 11, 0, 0, 5, tzinfo=timezone.utc))

        saved_task = await repo.get_task(task["task_run_id"])
        saved_submission = await repo.get_submission(task["task_run_id"], "claw1dailyminer")
        miner = await repo.get_miner("claw1dailyminer")

        assert saved_task["state"] == "resolved"
        assert saved_task["outcome"] == 1
        assert saved_submission["state"] == "resolved"
        assert saved_submission["reward_amount"] == 0
        assert miner["total_rewards"] == 0
        assert miner["model_reliability"] > 1.0

    import asyncio

    asyncio.run(scenario())


def test_daily_anchor_resolution_uses_forecast_settlement_writer():
    async def scenario():
        repo = GuardedMinerWriterRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [],
            daily_resolutions=[
                {
                    "outcome": 1,
                    "resolution_status": "resolved",
                    "start_ref_price": 70000.0,
                    "end_ref_price": 71200.0,
                }
            ],
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1dailywriter",
            name="daily-writer",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 0, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_daily_anchor_task(now, asset="BTC")
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1dailywriter",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1dailywriter",
                "economic_unit_id": "eu:dailywriter",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 8500,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T00:00:02Z",
                "accepted_reveal_at": "2026-04-10T00:00:06Z",
                "created_at": "2026-04-10T00:00:02Z",
                "updated_at": "2026-04-10T00:00:06Z",
            }
        )

        await service._settle_due_daily_tasks(datetime(2026, 4, 11, 0, 0, 5, tzinfo=timezone.utc))

        assert ("forecast_settlement", "claw1dailywriter") in repo.writer_calls

    import asyncio

    asyncio.run(scenario())


def test_release_matured_holds_uses_forecast_settlement_writer():
    async def scenario():
        repo = GuardedMinerWriterRepository()
        settings = forecast_engine.ForecastSettings()
        service = forecast_engine.ForecastMiningService(repo, settings)
        created_at = datetime(2026, 4, 9, 0, 0, 0, tzinfo=timezone.utc)
        await repo.register_miner(
            {
                "address": "claw1holdwriter",
                "name": "hold-writer",
                "public_key": "pubkey",
                "status": "active",
                "economic_unit_id": "eu:holdwriter",
                "miner_version": "0.4.0",
                "admission_state": "probation",
                "forecast_commits": 0,
                "forecast_reveals": settings.admission_mature_fast_reveals,
                "total_rewards": 100,
                "held_rewards": 80,
                "fast_task_opportunities": 0,
                "fast_task_misses": 0,
                "fast_window_start_at": created_at,
                "settled_tasks": 0,
                "correct_direction_count": 0,
                "edge_score_total": 0.0,
                "model_reliability": 1.0,
                "ops_reliability": 1.0,
                "arena_multiplier": 1.0,
                "poker_mtt_multiplier": 1.0,
                **forecast_engine._poker_mtt_reward_identity_defaults("claw1holdwriter", created_at),
                "public_rank": None,
                "public_elo": 1200,
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
        await repo.save_hold_entry(
            {
                "id": "hold:claw1holdwriter:1",
                "miner_address": "claw1holdwriter",
                "task_run_id": "task-hold-1",
                "submission_id": "submission-hold-1",
                "amount_held": 80,
                "amount_released": 0,
                "state": "held",
                "release_after": "2026-04-09T00:00:01Z",
                "created_at": "2026-04-09T00:00:01Z",
                "updated_at": "2026-04-09T00:00:01Z",
            }
        )

        await service._release_matured_holds(datetime(2026, 4, 11, 0, 0, 5, tzinfo=timezone.utc))

        assert ("forecast_settlement", "claw1holdwriter") in repo.writer_calls

    import asyncio

    asyncio.run(scenario())


def test_active_tasks_exclude_resolved_daily_tasks_from_prior_days():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings()
        service = forecast_engine.ForecastMiningService(repo, settings)

        yesterday = datetime(2026, 4, 9, 0, 0, 1, tzinfo=timezone.utc)
        today = datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc)
        old_task = forecast_engine.build_daily_anchor_task(yesterday, asset="BTC")
        old_task["state"] = "resolved"
        await repo.upsert_task(old_task)

        active = await service.get_active_tasks(today)
        daily_items = [item for item in active if item["lane"] == "daily_anchor"]

        assert all(item["task_run_id"] != old_task["task_run_id"] for item in daily_items)
        assert len(daily_items) == 2

    import asyncio

    asyncio.run(scenario())


def test_practice_arena_results_do_not_change_multiplier():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings()
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1arenapractice",
            name="arena-practice",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        result = await service.apply_arena_results(
            tournament_id="arena-practice-1",
            rated_or_practice="practice",
            human_only=True,
            results=[{"miner_id": "claw1arenapractice", "arena_score": 0.8}],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )
        miner = await repo.get_miner("claw1arenapractice")

        assert result["items"][0]["eligible_for_multiplier"] is False
        assert miner["arena_multiplier"] == 1.0

    import asyncio

    asyncio.run(scenario())


def test_arena_multiplier_changes_after_sixteenth_eligible_result():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings()
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1arenarated",
            name="arena-rated",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        for index in range(15):
            await service.apply_arena_results(
                tournament_id=f"arena-rated-{index}",
                rated_or_practice="rated",
                human_only=True,
                results=[{"miner_id": "claw1arenarated", "arena_score": 0.9}],
                completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
            )

        miner = await repo.get_miner("claw1arenarated")
        assert miner["arena_multiplier"] == 1.0

        result = await service.apply_arena_results(
            tournament_id="arena-rated-15",
            rated_or_practice="rated",
            human_only=True,
            results=[{"miner_id": "claw1arenarated", "arena_score": 0.9}],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        miner = await repo.get_miner("claw1arenarated")
        assert result["items"][0]["eligible_for_multiplier"] is True
        assert miner["arena_multiplier"] > 1.0
        assert miner["arena_multiplier"] <= 1.04

    import asyncio

    asyncio.run(scenario())


def test_apply_arena_results_uses_arena_multiplier_writer():
    async def scenario():
        repo = GuardedMinerWriterRepository()
        settings = forecast_engine.ForecastSettings()
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1arenawriter",
            name="arena-writer",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        for index in range(16):
            await service.apply_arena_results(
                tournament_id=f"arena-writer-{index}",
                rated_or_practice="rated",
                human_only=True,
                results=[{"miner_id": "claw1arenawriter", "arena_score": 0.8}],
                completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
            )

        assert ("arena_multiplier", "claw1arenawriter") in repo.writer_calls

    import asyncio

    asyncio.run(scenario())


def test_commit_submission_uses_cluster_identity_and_forecast_participation_writers():
    async def scenario():
        repo = GuardedMinerWriterRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1writercommit",
            name="writer-commit",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        task = forecast_engine.build_fast_task(datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc), settings, asset="BTCUSDT")
        await repo.upsert_task(task)

        await service.commit_submission(
            task_run_id=task["task_run_id"],
            miner_address="claw1writercommit",
            economic_unit_id="eu:writercommit",
            request_id="req-commit",
            commit_hash="hash",
            commit_nonce="nonce",
            accepted_at=datetime(2026, 4, 10, 9, 0, 2, tzinfo=timezone.utc),
            ip_address="10.0.0.1",
            user_agent="claw/1.0",
        )

        assert ("cluster_identity", "claw1writercommit") in repo.writer_calls
        assert ("forecast_participation", "claw1writercommit") in repo.writer_calls

    import asyncio

    asyncio.run(scenario())


def test_register_miner_rebinds_existing_cluster_with_cluster_identity_writer():
    async def scenario():
        repo = GuardedMinerWriterRepository()
        settings = forecast_engine.ForecastSettings()
        service = forecast_engine.ForecastMiningService(repo, settings)
        now = datetime(2026, 4, 10, 8, 0, 0, tzinfo=timezone.utc)

        await repo.register_miner(
            {
                "address": "claw1existingcluster",
                "name": "existing-cluster",
                "public_key": "pubkey-existing",
                "status": "active",
                "economic_unit_id": "eu:legacycluster",
                "miner_version": "0.4.0",
                "ip_address": "10.0.0.9",
                "user_agent_hash": "ua-existing",
                "admission_state": "probation",
                "forecast_commits": 0,
                "forecast_reveals": 0,
                "total_rewards": 0,
                "held_rewards": 0,
                "fast_task_opportunities": 0,
                "fast_task_misses": 0,
                "fast_window_start_at": now,
                "settled_tasks": 0,
                "correct_direction_count": 0,
                "edge_score_total": 0.0,
                "model_reliability": 1.0,
                "ops_reliability": 1.0,
                "arena_multiplier": 1.0,
                "poker_mtt_multiplier": 1.0,
                **forecast_engine._poker_mtt_reward_identity_defaults("claw1existingcluster", now),
                "public_rank": None,
                "public_elo": 1200,
                "created_at": now,
                "updated_at": now,
            }
        )

        original_compute = forecast_engine.compute_economic_unit_components
        original_utc_now = forecast_engine.utc_now
        forecast_engine.compute_economic_unit_components = lambda miners: {
            "claw1existingcluster": "eu:rebuiltcluster",
            "claw1newcluster": "eu:newcluster",
        }
        forecast_engine.utc_now = lambda: now
        try:
            await service.register_miner(
                address="claw1newcluster",
                name="new-cluster",
                public_key="pubkey-new",
                miner_version="0.4.0",
            )
        finally:
            forecast_engine.compute_economic_unit_components = original_compute
            forecast_engine.utc_now = original_utc_now

        assert ("cluster_identity", "claw1existingcluster") in repo.writer_calls

    import asyncio

    asyncio.run(scenario())


def test_settle_due_tasks_uses_forecast_settlement_writer():
    async def scenario():
        repo = GuardedMinerWriterRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": 70120.0}]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1writersettle",
            name="writer-settle",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        task_now = datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(task_now, settings, asset="BTCUSDT")
        task["commit_close_ref_price"] = 70000.5
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1writersettle",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1writersettle",
                "economic_unit_id": "eu:writersettle",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6200,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T09:00:02Z",
                "accepted_reveal_at": "2026-04-10T09:00:06Z",
                "created_at": "2026-04-10T09:00:02Z",
                "updated_at": "2026-04-10T09:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 9, 1, 5, tzinfo=timezone.utc))

        assert ("forecast_settlement", "claw1writersettle") in repo.writer_calls
        assert ("forecast_participation", "claw1writersettle") in repo.writer_calls
        assert ("public_ranking", "claw1writersettle") in repo.writer_calls

    import asyncio

    asyncio.run(scenario())


def test_refresh_public_ranks_uses_public_ranking_writer():
    async def scenario():
        repo = GuardedMinerWriterRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        now = datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc)

        for address, rewards, edge in [
            ("claw1rankone", 120, 0.7),
            ("claw1ranktwo", 90, 0.3),
        ]:
            await repo.register_miner(
                {
                    "address": address,
                    "name": address,
                    "public_key": f"{address}-pubkey",
                    "status": "active",
                    "economic_unit_id": f"eu:{address}",
                    "miner_version": "0.4.0",
                    "admission_state": "mature",
                    "forecast_commits": 0,
                    "forecast_reveals": 0,
                    "total_rewards": rewards,
                    "held_rewards": 0,
                    "fast_task_opportunities": 0,
                    "fast_task_misses": 0,
                    "fast_window_start_at": now,
                    "settled_tasks": 10,
                    "correct_direction_count": 5,
                    "edge_score_total": edge,
                    "model_reliability": 1.0,
                    "ops_reliability": 1.0,
                    "arena_multiplier": 1.0,
                    "poker_mtt_multiplier": 1.0,
                    **forecast_engine._poker_mtt_reward_identity_defaults(address, now),
                    "public_rank": None,
                    "public_elo": 1200,
                    "created_at": now,
                    "updated_at": now,
                }
            )

        await service._refresh_public_ranks()

        assert ("public_ranking", "claw1rankone") in repo.writer_calls
        assert ("public_ranking", "claw1ranktwo") in repo.writer_calls

    import asyncio

    asyncio.run(scenario())


def test_poker_mtt_practice_results_do_not_change_multiplier_and_compute_total_score():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings()
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1pokermttpractice",
            name="poker-mtt-practice",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        result = await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-practice-1",
            rated_or_practice="practice",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokermttpractice",
                    "final_rank": 3,
                    "tournament_result_score": 0.8,
                    "hidden_eval_score": 0.4,
                    "consistency_input_score": 0.2,
                }
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )
        miner = await repo.get_miner("claw1pokermttpractice")
        stored = await repo.list_poker_mtt_results_for_miner("claw1pokermttpractice")

        assert result["items"][0]["eligible_for_multiplier"] is False
        assert result["items"][0]["hidden_eval_score"] == 0.0
        assert result["items"][0]["total_score"] == 0.48
        assert miner["poker_mtt_multiplier"] == 1.0
        assert stored[0]["final_rank"] == 3
        assert stored[0]["total_score"] == 0.48

    import asyncio

    asyncio.run(scenario())


def poker_mtt_reward_ready_refs(
    tournament_id: str,
    miner_address: str,
    *,
    locked_at: str = "2026-04-10T09:00:00Z",
) -> dict:
    return {
        "final_ranking_id": f"poker_mtt_final_ranking:{tournament_id}:{miner_address}",
        "standing_snapshot_id": f"poker_mtt_standing_snapshot:{tournament_id}:abc",
        "standing_snapshot_hash": f"sha256:{tournament_id}",
        "evidence_root": f"sha256:evidence:{tournament_id}:{miner_address}",
        "evidence_state": "complete",
        "locked_at": locked_at,
    }


def poker_mtt_final_ranking_row(
    tournament_id: str,
    miner_address: str,
    *,
    final_rank: int,
    field_size: int = 30,
    policy_bundle_version: str = "poker_mtt_v1",
    economic_unit_id: str | None = None,
    locked_at: str = "2026-04-10T09:00:00Z",
) -> dict:
    refs = poker_mtt_reward_ready_refs(tournament_id, miner_address, locked_at=locked_at)
    chip_delta = float(field_size - final_rank)
    return {
        "id": refs["final_ranking_id"],
        "tournament_id": tournament_id,
        "source_mtt_id": tournament_id,
        "source_user_id": miner_address,
        "miner_address": miner_address,
        "economic_unit_id": economic_unit_id or miner_address,
        "member_id": f"{miner_address}:1",
        "entry_number": 1,
        "reentry_count": 1,
        "rank": final_rank,
        "rank_state": "ranked",
        "chip": 3000.0 + chip_delta,
        "chip_delta": chip_delta,
        "died_time": None,
        "waiting_or_no_show": False,
        "bounty": 0.0,
        "defeat_num": 0,
        "field_size_policy": "exclude_waiting_no_show_from_reward_field_size",
        "standing_snapshot_id": refs["standing_snapshot_id"],
        "standing_snapshot_hash": refs["standing_snapshot_hash"],
        "evidence_root": refs["evidence_root"],
        "evidence_state": refs["evidence_state"],
        "policy_bundle_version": policy_bundle_version,
        "snapshot_found": True,
        "status": "completed",
        "player_name": miner_address,
        "room_id": "room-1",
        "start_chip": 3000.0,
        "stand_up_status": "",
        "source_rank": str(final_rank),
        "source_rank_numeric": True,
        "zset_score": 3000.0 + chip_delta,
        "locked_at": locked_at,
        "anchorable_at": locked_at,
        "created_at": locked_at,
        "updated_at": locked_at,
    }


async def save_poker_mtt_final_ranking_refs(
    repo: FakeRepository,
    tournament_id: str,
    rankings: list[tuple[str, int]],
    *,
    policy_bundle_version: str = "poker_mtt_v1",
) -> None:
    for miner_address, final_rank in rankings:
        row = poker_mtt_final_ranking_row(
            tournament_id,
            miner_address,
            final_rank=final_rank,
            policy_bundle_version=policy_bundle_version,
        )
        await repo.save_poker_mtt_final_ranking(row)
        await repo.save_poker_mtt_hidden_eval_entry(
            {
                "tournament_id": tournament_id,
                "miner_address": miner_address,
                "final_ranking_id": row["id"],
                "seed_assignment_id": f"hidden-seed:{tournament_id}",
                "hidden_eval_score": 0.0,
                "score_components_json": {"test_fixture": True},
                "evidence_root": row["evidence_root"],
                "policy_bundle_version": policy_bundle_version,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )


def poker_mtt_rollout_settings(**overrides) -> forecast_engine.ForecastSettings:
    defaults = {
        "poker_mtt_reward_windows_enabled": True,
        "poker_mtt_settlement_anchoring_enabled": True,
    }
    defaults.update(overrides)
    return forecast_engine.ForecastSettings(**defaults)


async def build_poker_mtt_anchor_fixture(
    *,
    repo: FakeRepository,
    service: forecast_engine.ForecastMiningService,
    tournament_id: str,
    miner_addresses: list[str],
) -> dict:
    for index, miner_address in enumerate(miner_addresses, start=1):
        await service.register_miner(
            address=miner_address,
            name=miner_address,
            public_key="pubkey",
            miner_version="0.4.0",
        )
    await save_poker_mtt_final_ranking_refs(
        repo,
        tournament_id,
        [(miner_address, index) for index, miner_address in enumerate(miner_addresses, start=1)],
    )
    await service.apply_poker_mtt_results(
        tournament_id=tournament_id,
        rated_or_practice="rated",
        human_only=True,
        field_size=30,
        policy_bundle_version="poker_mtt_v1",
        results=[
            {
                "miner_id": miner_address,
                "final_rank": index,
                "tournament_result_score": 1.0 if index == 1 else 0.5,
                "hidden_eval_score": 0.0,
                "consistency_input_score": 0.0,
                "evaluation_state": "final",
                **poker_mtt_reward_ready_refs(tournament_id, miner_address),
            }
            for index, miner_address in enumerate(miner_addresses, start=1)
        ],
        completed_at=datetime(2026, 4, 10, 15, 0, 0, tzinfo=timezone.utc),
    )
    return await service.build_poker_mtt_reward_window(
        lane="poker_mtt_daily",
        window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
        window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
        reward_pool_amount=100,
        include_provisional=False,
        now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
    )


def test_reconcile_skips_poker_mtt_auto_windows_when_rollout_disabled():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(
            poker_mtt_daily_reward_pool_amount=100,
            poker_mtt_weekly_reward_pool_amount=250,
        )
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1pokerdisabledauto",
            name="poker-disabled-auto",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await save_poker_mtt_final_ranking_refs(
            repo,
            "poker-mtt-disabled-auto-1",
            [("claw1pokerdisabledauto", 1)],
        )
        await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-disabled-auto-1",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokerdisabledauto",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-disabled-auto-1", "claw1pokerdisabledauto"),
                }
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        await service.reconcile(datetime(2026, 4, 14, 0, 5, 0, tzinfo=timezone.utc))

        reward_windows = [window for window in await repo.list_reward_windows() if window["lane"].startswith("poker_mtt_")]
        assert reward_windows == []

    import asyncio

    asyncio.run(scenario())


def test_reconcile_builds_poker_mtt_window_for_provisional_rows_after_watermark():
    async def scenario():
        repo = FakeRepository()
        settings = poker_mtt_rollout_settings(
            poker_mtt_daily_reward_pool_amount=100,
            poker_mtt_weekly_reward_pool_amount=0,
            poker_mtt_finalization_watermark_seconds=60,
            poker_mtt_daily_policy_bundle_version="poker_mtt_daily_policy_v2",
        )
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1pokerprovisionalauto",
            name="poker-provisional-auto",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await save_poker_mtt_final_ranking_refs(
            repo,
            "poker-mtt-provisional-auto-1",
            [("claw1pokerprovisionalauto", 1)],
            policy_bundle_version="poker_mtt_daily_policy_v2",
        )
        await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-provisional-auto-1",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_daily_policy_v2",
            results=[
                {
                    "miner_id": "claw1pokerprovisionalauto",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "provisional",
                    **poker_mtt_reward_ready_refs(
                        "poker-mtt-provisional-auto-1",
                        "claw1pokerprovisionalauto",
                    ),
                }
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        await service.reconcile(datetime(2026, 4, 11, 0, 2, 0, tzinfo=timezone.utc))

        reward_windows = [window for window in await repo.list_reward_windows() if window["lane"] == "poker_mtt_daily"]
        assert len(reward_windows) == 1
        assert reward_windows[0]["state"] == "finalized"
        assert reward_windows[0]["submission_count"] == 1

    import asyncio

    asyncio.run(scenario())


def test_retry_anchor_settlement_batch_rejects_poker_mtt_when_rollout_disabled():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        reward_window = await build_poker_mtt_anchor_fixture(
            repo=repo,
            service=service,
            tournament_id="poker-mtt-anchor-disabled-1",
            miner_addresses=["claw1pokeranchordisabled"],
        )
        batch = await repo.get_settlement_batch(reward_window["settlement_batch_id"])

        try:
            await service.retry_anchor_settlement_batch(
                batch["id"],
                now=datetime(2026, 4, 11, 0, 6, 0, tzinfo=timezone.utc),
            )
        except ValueError as exc:
            assert str(exc) == "poker mtt settlement anchoring disabled"
        else:
            raise AssertionError("poker anchor should require explicit rollout enablement")

    import asyncio

    asyncio.run(scenario())


def test_poker_mtt_multiplier_changes_after_sixteenth_eligible_result():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings()
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1pokermttrated",
            name="poker-mtt-rated",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        for index in range(15):
            await save_poker_mtt_final_ranking_refs(
                repo,
                f"poker-mtt-rated-{index}",
                [("claw1pokermttrated", 1)],
            )
            await service.apply_poker_mtt_results(
                tournament_id=f"poker-mtt-rated-{index}",
                rated_or_practice="rated",
                human_only=True,
                field_size=30,
                policy_bundle_version="poker_mtt_v1",
                results=[
                    {
                        "miner_id": "claw1pokermttrated",
                        "final_rank": 1,
                        "tournament_result_score": 0.9,
                        "hidden_eval_score": 0.6,
                        "consistency_input_score": 0.3,
                        "evaluation_state": "final",
                        **poker_mtt_reward_ready_refs(
                            f"poker-mtt-rated-{index}",
                            "claw1pokermttrated",
                        ),
                    }
                ],
                completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
            )

        miner = await repo.get_miner("claw1pokermttrated")
        assert miner["poker_mtt_multiplier"] == 1.0

        await save_poker_mtt_final_ranking_refs(
            repo,
            "poker-mtt-rated-15",
            [("claw1pokermttrated", 2)],
        )
        result = await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-rated-15",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokermttrated",
                    "final_rank": 2,
                    "tournament_result_score": 0.9,
                    "hidden_eval_score": 0.6,
                    "consistency_input_score": 0.3,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs(
                        "poker-mtt-rated-15",
                        "claw1pokermttrated",
                    ),
                }
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        miner = await repo.get_miner("claw1pokermttrated")
        assert result["items"][0]["eligible_for_multiplier"] is True
        assert result["items"][0]["rolling_score"] > 0.0
        assert miner["poker_mtt_multiplier"] > 1.0
        assert miner["poker_mtt_multiplier"] <= 1.04
        snapshots = await repo.list_poker_mtt_multiplier_snapshots(miner_address="claw1pokermttrated")
        assert len(snapshots) == 1
        assert snapshots[0]["source_result_id"] == "poker_mtt:poker-mtt-rated-15:claw1pokermttrated"
        assert snapshots[0]["multiplier_before"] == 1.0
        assert snapshots[0]["multiplier_after"] == miner["poker_mtt_multiplier"]
        assert snapshots[0]["rolling_score"] == result["items"][0]["rolling_score"]

    import asyncio

    asyncio.run(scenario())


def test_apply_poker_mtt_results_uses_poker_multiplier_writer():
    async def scenario():
        repo = GuardedMinerWriterRepository()
        settings = forecast_engine.ForecastSettings()
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1pokerwriter",
            name="poker-writer",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        for index in range(16):
            tournament_id = f"poker-writer-{index}"
            await save_poker_mtt_final_ranking_refs(repo, tournament_id, [("claw1pokerwriter", 1)])
            await service.apply_poker_mtt_results(
                tournament_id=tournament_id,
                rated_or_practice="rated",
                human_only=True,
                field_size=30,
                policy_bundle_version="poker_mtt_v1",
                results=[
                    {
                        "miner_id": "claw1pokerwriter",
                        "final_rank": 1,
                        "tournament_result_score": 0.9,
                        "hidden_eval_score": 0.6,
                        "consistency_input_score": 0.3,
                        "evaluation_state": "final",
                        **poker_mtt_reward_ready_refs(tournament_id, "claw1pokerwriter"),
                    }
                ],
                completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
            )

        assert ("poker_mtt_multiplier", "claw1pokerwriter") in repo.writer_calls

    import asyncio

    asyncio.run(scenario())


def test_build_settlement_batches_uses_settlement_writer_helpers():
    async def scenario():
        repo = GuardedSettlementWriterRepository()
        now = datetime(2026, 4, 11, 0, 1, 0, tzinfo=timezone.utc)
        reward_window_id = "rw_forecast_20260411T000000Z"
        await FakeRepository.save_reward_window(
            repo,
            {
                "id": reward_window_id,
                "lane": "forecast_15m",
                "state": "finalized",
                "window_start_at": "2026-04-11T00:00:00Z",
                "window_end_at": "2026-04-11T00:15:00Z",
                "task_count": 1,
                "submission_count": 1,
                "miner_count": 1,
                "total_reward_amount": 37,
                "settlement_batch_id": None,
                "task_run_ids": ["task-1"],
                "miner_addresses": ["claw1settlementwriter"],
                "policy_bundle_version": "pb_2026_04_09_a",
                "created_at": "2026-04-11T00:00:00Z",
                "updated_at": "2026-04-11T00:00:00Z",
            },
        )
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())

        await service._build_settlement_batches(now)

        batch_id = "sb_forecast_20260411T000000Z"
        saved_batch = await repo.get_settlement_batch(batch_id)
        saved_window = await repo.get_reward_window(reward_window_id)

        assert ("settlement_sync_open", batch_id) in repo.writer_calls
        assert ("reward_window_link", reward_window_id) in repo.writer_calls
        assert saved_batch["state"] == "open"
        assert saved_window["settlement_batch_id"] == batch_id

    import asyncio

    asyncio.run(scenario())


def test_retry_anchor_settlement_batch_uses_anchor_ready_writer():
    async def scenario():
        repo = GuardedSettlementWriterRepository()
        now = datetime(2026, 4, 11, 0, 1, 6, tzinfo=timezone.utc)
        reward_window_id = "rw_anchor_ready"
        batch_id = "sb_anchor_ready"
        await FakeRepository.save_reward_window(
            repo,
            {
                "id": reward_window_id,
                "lane": "forecast_15m",
                "state": "finalized",
                "window_start_at": "2026-04-11T00:00:00Z",
                "window_end_at": "2026-04-11T00:15:00Z",
                "task_count": 1,
                "submission_count": 0,
                "miner_count": 0,
                "total_reward_amount": 11,
                "settlement_batch_id": batch_id,
                "task_run_ids": [],
                "miner_addresses": [],
                "policy_bundle_version": "pb_2026_04_09_a",
                "created_at": "2026-04-11T00:00:00Z",
                "updated_at": "2026-04-11T00:00:00Z",
            },
        )
        await FakeRepository.save_settlement_batch(
            repo,
            {
                "id": batch_id,
                "lane": "forecast_15m",
                "state": "open",
                "window_start_at": "2026-04-11T00:00:00Z",
                "window_end_at": "2026-04-11T00:15:00Z",
                "reward_window_ids": [reward_window_id],
                "policy_bundle_version": "pb_2026_04_09_a",
                "task_count": 1,
                "miner_count": 0,
                "total_reward_amount": 11,
                "anchor_job_id": None,
                "anchor_schema_version": None,
                "canonical_root": None,
                "anchor_payload_json": None,
                "anchor_payload_hash": None,
                "created_at": "2026-04-11T00:00:00Z",
                "updated_at": "2026-04-11T00:00:00Z",
            },
        )

        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())

        async def noop_reconcile(now=None):  # noqa: ANN001
            return None

        service.reconcile = noop_reconcile  # type: ignore[method-assign]

        saved = await service.retry_anchor_settlement_batch(batch_id, now=now)

        assert ("settlement_anchor_ready", batch_id) in repo.writer_calls
        assert saved["state"] == "anchor_ready"

    import asyncio

    asyncio.run(scenario())


def test_submit_anchor_job_uses_anchor_submitted_writer():
    async def scenario():
        repo = GuardedSettlementWriterRepository()
        now = datetime(2026, 4, 11, 0, 1, 7, tzinfo=timezone.utc)
        batch_id = "sb_anchor_submit"
        await FakeRepository.save_settlement_batch(
            repo,
            {
                "id": batch_id,
                "lane": "forecast_15m",
                "state": "anchor_ready",
                "window_start_at": "2026-04-11T00:00:00Z",
                "window_end_at": "2026-04-11T00:15:00Z",
                "reward_window_ids": ["rw_anchor_submit"],
                "policy_bundle_version": "pb_2026_04_09_a",
                "task_count": 1,
                "miner_count": 1,
                "total_reward_amount": 11,
                "anchor_job_id": None,
                "anchor_schema_version": "clawchain.anchor_payload.v1",
                "canonical_root": "sha256:" + "a" * 64,
                "anchor_payload_json": {"canonical_root": "sha256:" + "a" * 64},
                "anchor_payload_hash": "sha256:" + "b" * 64,
                "created_at": "2026-04-11T00:00:00Z",
                "updated_at": "2026-04-11T00:00:00Z",
            },
        )

        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())

        async def noop_reconcile(now=None):  # noqa: ANN001
            return None

        service.reconcile = noop_reconcile  # type: ignore[method-assign]

        saved = await service.submit_anchor_job(batch_id, now=now)

        assert ("settlement_anchor_submitted", batch_id) in repo.writer_calls
        assert saved["state"] == "anchor_submitted"
        assert saved["anchor_job_id"].startswith("aj_sb_anchor_submit_")

    import asyncio

    asyncio.run(scenario())


def test_mark_anchor_job_anchored_uses_terminal_writer():
    async def scenario():
        repo = GuardedSettlementWriterRepository()
        now = datetime(2026, 4, 11, 0, 1, 8, tzinfo=timezone.utc)
        batch_id = "sb_anchor_terminal"
        anchor_job_id = "aj_anchor_terminal"
        await FakeRepository.save_settlement_batch(
            repo,
            {
                "id": batch_id,
                "lane": "forecast_15m",
                "state": "anchor_submitted",
                "window_start_at": "2026-04-11T00:00:00Z",
                "window_end_at": "2026-04-11T00:15:00Z",
                "reward_window_ids": [],
                "policy_bundle_version": "pb_2026_04_09_a",
                "task_count": 1,
                "miner_count": 1,
                "total_reward_amount": 11,
                "anchor_job_id": anchor_job_id,
                "anchor_schema_version": "clawchain.anchor_payload.v1",
                "canonical_root": "sha256:" + "a" * 64,
                "anchor_payload_json": {"canonical_root": "sha256:" + "a" * 64},
                "anchor_payload_hash": "sha256:" + "b" * 64,
                "created_at": "2026-04-11T00:00:00Z",
                "updated_at": "2026-04-11T00:00:00Z",
            },
        )
        await repo.save_anchor_job(
            {
                "id": anchor_job_id,
                "settlement_batch_id": batch_id,
                "lane": "forecast_15m",
                "state": "anchor_submitted",
                "anchor_payload_hash": "sha256:" + "b" * 64,
                "broadcast_status": None,
                "broadcast_tx_hash": None,
                "chain_confirmation_status": None,
                "last_broadcast_at": None,
                "failure_reason": None,
                "submitted_at": "2026-04-11T00:00:01Z",
                "anchored_at": None,
                "created_at": "2026-04-11T00:00:01Z",
                "updated_at": "2026-04-11T00:00:01Z",
            }
        )

        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())

        async def noop_reconcile(now=None):  # noqa: ANN001
            return None

        service.reconcile = noop_reconcile  # type: ignore[method-assign]

        saved = await service.mark_anchor_job_anchored(anchor_job_id, now=now)
        saved_batch = await repo.get_settlement_batch(batch_id)

        assert ("settlement_terminal", batch_id) in repo.writer_calls
        assert saved["state"] == "anchored"
        assert saved_batch["state"] == "anchored"

    import asyncio

    asyncio.run(scenario())


def test_mark_anchor_job_failed_uses_terminal_writer():
    async def scenario():
        repo = GuardedSettlementWriterRepository()
        now = datetime(2026, 4, 11, 0, 1, 9, tzinfo=timezone.utc)
        batch_id = "sb_anchor_failed"
        anchor_job_id = "aj_anchor_failed"
        await FakeRepository.save_settlement_batch(
            repo,
            {
                "id": batch_id,
                "lane": "forecast_15m",
                "state": "anchor_submitted",
                "window_start_at": "2026-04-11T00:00:00Z",
                "window_end_at": "2026-04-11T00:15:00Z",
                "reward_window_ids": [],
                "policy_bundle_version": "pb_2026_04_09_a",
                "task_count": 1,
                "miner_count": 1,
                "total_reward_amount": 11,
                "anchor_job_id": anchor_job_id,
                "anchor_schema_version": "clawchain.anchor_payload.v1",
                "canonical_root": "sha256:" + "a" * 64,
                "anchor_payload_json": {"canonical_root": "sha256:" + "a" * 64},
                "anchor_payload_hash": "sha256:" + "b" * 64,
                "created_at": "2026-04-11T00:00:00Z",
                "updated_at": "2026-04-11T00:00:00Z",
            },
        )
        await repo.save_anchor_job(
            {
                "id": anchor_job_id,
                "settlement_batch_id": batch_id,
                "lane": "forecast_15m",
                "state": "anchor_submitted",
                "anchor_payload_hash": "sha256:" + "b" * 64,
                "broadcast_status": None,
                "broadcast_tx_hash": None,
                "chain_confirmation_status": None,
                "last_broadcast_at": None,
                "failure_reason": None,
                "submitted_at": "2026-04-11T00:00:01Z",
                "anchored_at": None,
                "created_at": "2026-04-11T00:00:01Z",
                "updated_at": "2026-04-11T00:00:01Z",
            }
        )

        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())

        async def noop_reconcile(now=None):  # noqa: ANN001
            return None

        service.reconcile = noop_reconcile  # type: ignore[method-assign]

        saved = await service.mark_anchor_job_failed(anchor_job_id, failure_reason="rpc timeout", now=now)
        saved_batch = await repo.get_settlement_batch(batch_id)

        assert ("settlement_terminal", batch_id) in repo.writer_calls
        assert saved["state"] == "anchor_failed"
        assert saved_batch["state"] == "anchor_failed"

    import asyncio

    asyncio.run(scenario())


def test_poker_mtt_rating_snapshot_does_not_mutate_forecast_public_elo():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1rating",
            name="rating",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        before = await repo.get_miner("claw1rating")

        snapshot = await service.build_poker_mtt_rating_snapshot(
            miner_address="claw1rating",
            window_start_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
            public_rating=1512.5,
            public_rank=42,
            confidence=0.72,
            policy_bundle_version="poker_mtt_v1",
            now=datetime(2026, 4, 8, 1, tzinfo=timezone.utc),
        )
        after = await repo.get_miner("claw1rating")

        assert snapshot["public_rating"] == 1512.5
        assert snapshot["public_rank"] == 42
        assert after["public_elo"] == before["public_elo"]
        assert after["public_rank"] == before["public_rank"]

    import asyncio

    asyncio.run(scenario())


def test_poker_mtt_rating_snapshot_is_audit_only_for_reward_weights():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, poker_mtt_rollout_settings())
        miners = ["claw1ratinghigh", "claw1ratinglow"]
        for miner_address in miners:
            await service.register_miner(
                address=miner_address,
                name=miner_address,
                public_key="pubkey",
                miner_version="0.4.0",
            )

        await service.build_poker_mtt_rating_snapshot(
            miner_address="claw1ratinghigh",
            window_start_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
            public_rating=2400.0,
            public_rank=1,
            confidence=0.95,
            policy_bundle_version="poker_mtt_v1",
            now=datetime(2026, 4, 8, 1, tzinfo=timezone.utc),
        )
        await service.build_poker_mtt_rating_snapshot(
            miner_address="claw1ratinglow",
            window_start_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
            public_rating=900.0,
            public_rank=999,
            confidence=0.95,
            policy_bundle_version="poker_mtt_v1",
            now=datetime(2026, 4, 8, 1, tzinfo=timezone.utc),
        )

        tournament_id = "poker-mtt-rating-weight"
        await save_poker_mtt_final_ranking_refs(
            repo,
            tournament_id,
            [("claw1ratinghigh", 1), ("claw1ratinglow", 2)],
        )
        await service.apply_poker_mtt_results(
            tournament_id=tournament_id,
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": miner_address,
                    "final_rank": final_rank,
                    "tournament_result_score": 0.8,
                    "consistency_input_score": 0.2,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs(tournament_id, miner_address),
                }
                for miner_address, final_rank in [("claw1ratinghigh", 1), ("claw1ratinglow", 2)]
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=datetime(2026, 4, 10, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 11, tzinfo=timezone.utc),
            reward_pool_amount=100,
            include_provisional=False,
            policy_bundle_version="poker_mtt_v1",
            now=datetime(2026, 4, 10, 12, tzinfo=timezone.utc),
        )
        artifacts = await repo.list_artifacts_for_entity("reward_window", reward_window["id"])
        projection = next(
            artifact for artifact in artifacts if artifact["kind"] == "poker_mtt_reward_window_projection"
        )["payload_json"]
        reward_rows = sorted(projection["miner_reward_rows"], key=lambda row: row["miner_address"])

        assert [row["gross_reward_amount"] for row in reward_rows] == [51, 49]
        assert projection["rating_snapshot_root"].startswith("sha256:")

    import asyncio

    asyncio.run(scenario())


def test_build_poker_mtt_reward_window_creates_settlement_batch():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings()
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1pokerdailyone",
            name="poker-daily-one",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await service.register_miner(
            address="claw1pokerdailytwo",
            name="poker-daily-two",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await save_poker_mtt_final_ranking_refs(
            repo,
            "poker-mtt-daily-1",
            [("claw1pokerdailyone", 1), ("claw1pokerdailytwo", 2)],
        )

        await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-daily-1",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokerdailyone",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-daily-1", "claw1pokerdailyone"),
                },
                {
                    "miner_id": "claw1pokerdailytwo",
                    "final_rank": 2,
                    "tournament_result_score": 0.5,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-daily-1", "claw1pokerdailytwo"),
                },
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
            reward_pool_amount=100,
            include_provisional=False,
            now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
        )

        batches = await repo.list_settlement_batches()

        assert reward_window["lane"] == "poker_mtt_daily"
        assert reward_window["task_run_ids"] == ["poker-mtt-daily-1"]
        assert reward_window["submission_count"] == 2
        assert reward_window["miner_count"] == 2
        assert reward_window["total_reward_amount"] == 100
        assert reward_window["settlement_batch_id"] == batches[0]["id"]
        assert batches[0]["lane"] == "poker_mtt_daily"
        assert batches[0]["reward_window_ids"] == [reward_window["id"]]

    import asyncio

    asyncio.run(scenario())


def test_build_poker_mtt_reward_window_rejects_no_positive_weights():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())

        for miner_address in ("claw1pokerzeroweightone", "claw1pokerzeroweighttwo"):
            await service.register_miner(
                address=miner_address,
                name=miner_address,
                public_key="pubkey",
                miner_version="0.4.0",
            )
        await save_poker_mtt_final_ranking_refs(
            repo,
            "poker-mtt-zero-weight-1",
            [("claw1pokerzeroweightone", 30), ("claw1pokerzeroweighttwo", 30)],
        )

        await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-zero-weight-1",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokerzeroweightone",
                    "final_rank": 30,
                    "tournament_result_score": 0.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-zero-weight-1", "claw1pokerzeroweightone"),
                },
                {
                    "miner_id": "claw1pokerzeroweighttwo",
                    "final_rank": 30,
                    "tournament_result_score": 0.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-zero-weight-1", "claw1pokerzeroweighttwo"),
                },
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
            reward_pool_amount=100,
            include_provisional=False,
            now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
        )
        artifact = next(
            artifact
            for artifact in await repo.list_artifacts_for_entity("reward_window", reward_window["id"])
            if artifact["kind"] == "poker_mtt_reward_window_projection"
        )

        assert reward_window["state"] == "no_positive_weight"
        assert reward_window["total_reward_amount"] == 0
        assert reward_window["settlement_batch_id"] is None
        budget_disposition = artifact["payload_json"]["budget_disposition"]
        assert {
            key: budget_disposition[key]
            for key in ("forfeited_amount", "paid_amount", "requested_reward_pool_amount", "state")
        } == {
            "forfeited_amount": 100,
            "paid_amount": 0,
            "requested_reward_pool_amount": 100,
            "state": "forfeited",
        }
        assert budget_disposition["budget_enforcement"] == "disabled"
        assert budget_disposition["budget_root"].startswith("sha256:")
        assert all(row["gross_reward_amount"] == 0 for row in artifact["payload_json"]["miner_reward_rows"])

    import asyncio

    asyncio.run(scenario())


def test_reconcile_no_positive_poker_mtt_window_does_not_enter_settlement():
    async def scenario():
        repo = FakeRepository()
        settings = poker_mtt_rollout_settings(
            poker_mtt_daily_reward_pool_amount=100,
            poker_mtt_weekly_reward_pool_amount=0,
        )
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1pokerreconcilezero",
            name="poker-reconcile-zero",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await save_poker_mtt_final_ranking_refs(
            repo,
            "poker-mtt-reconcile-zero-1",
            [("claw1pokerreconcilezero", 30)],
        )
        await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-reconcile-zero-1",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokerreconcilezero",
                    "final_rank": 30,
                    "tournament_result_score": 0.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-reconcile-zero-1", "claw1pokerreconcilezero"),
                }
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        await service.reconcile(datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc))

        reward_windows = [window for window in await repo.list_reward_windows() if window["lane"].startswith("poker_mtt_")]
        settlement_batches = await repo.list_settlement_batches()

        assert len(reward_windows) == 1
        assert reward_windows[0]["state"] == "no_positive_weight"
        assert reward_windows[0]["settlement_batch_id"] is None
        assert settlement_batches == []

    import asyncio

    asyncio.run(scenario())


def test_no_positive_rebuild_cancels_stale_open_settlement_batch():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())

        await service.register_miner(
            address="claw1pokerstaleopen",
            name="poker-stale-open",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await save_poker_mtt_final_ranking_refs(
            repo,
            "poker-mtt-stale-open-1",
            [("claw1pokerstaleopen", 1)],
        )
        await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-stale-open-1",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokerstaleopen",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-stale-open-1", "claw1pokerstaleopen"),
                }
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )
        positive_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
            reward_pool_amount=100,
            include_provisional=False,
            now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
        )
        stale_batch_id = positive_window["settlement_batch_id"]

        stored = (await repo.list_poker_mtt_results_for_miner("claw1pokerstaleopen"))[0]
        await repo.save_poker_mtt_final_ranking(
            poker_mtt_final_ranking_row(
                "poker-mtt-stale-open-1",
                "claw1pokerstaleopen",
                final_rank=30,
            )
        )
        await repo.save_poker_mtt_result(
            {
                **stored,
                "final_rank": 30,
                "finish_percentile": 0.0,
                "tournament_result_score": 0.0,
                "total_score": 0.0,
                "updated_at": "2026-04-10T09:05:00Z",
            }
        )
        rebuilt = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
            reward_pool_amount=100,
            include_provisional=False,
            now=datetime(2026, 4, 11, 0, 10, 0, tzinfo=timezone.utc),
        )
        stale_batch = await repo.get_settlement_batch(stale_batch_id)

        assert rebuilt["state"] == "no_positive_weight"
        assert rebuilt["settlement_batch_id"] is None
        assert stale_batch["state"] == "cancelled"
        assert stale_batch["total_reward_amount"] == 0
        assert stale_batch["anchor_payload_json"] is None

        try:
            await service.retry_anchor_settlement_batch(stale_batch_id, now=datetime(2026, 4, 11, 0, 11, 0, tzinfo=timezone.utc))
        except ValueError as exc:
            assert str(exc) == "settlement batch not anchorable"
        else:
            raise AssertionError("cancelled no-positive batch should not be anchorable")

    import asyncio

    asyncio.run(scenario())


def test_build_poker_mtt_reward_window_folds_duplicate_economic_units():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())

        for miner_address in ("claw1pokerdupone", "claw1pokerduptwo", "claw1pokerfair"):
            await service.register_miner(
                address=miner_address,
                name=miner_address,
                public_key="pubkey",
                miner_version="0.4.0",
                ip_address="203.0.113.9" if miner_address != "claw1pokerfair" else "203.0.113.10",
            )
        await save_poker_mtt_final_ranking_refs(
            repo,
            "poker-mtt-duplicate-unit-1",
            [("claw1pokerdupone", 1), ("claw1pokerduptwo", 2), ("claw1pokerfair", 1)],
        )

        await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-duplicate-unit-1",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokerdupone",
                    "economic_unit_id": "claw1poker-shared-unit",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-duplicate-unit-1", "claw1pokerdupone"),
                },
                {
                    "miner_id": "claw1pokerduptwo",
                    "economic_unit_id": "claw1poker-shared-unit",
                    "final_rank": 2,
                    "tournament_result_score": 0.5,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-duplicate-unit-1", "claw1pokerduptwo"),
                },
                {
                    "miner_id": "claw1pokerfair",
                    "economic_unit_id": "claw1poker-fair-unit",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-duplicate-unit-1", "claw1pokerfair"),
                },
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
            reward_pool_amount=100,
            include_provisional=False,
            now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
        )
        artifact = next(
            artifact
            for artifact in await repo.list_artifacts_for_entity("reward_window", reward_window["id"])
            if artifact["kind"] == "poker_mtt_reward_window_projection"
        )

        assert reward_window["miner_count"] == 2
        assert reward_window["submission_count"] == 3
        assert artifact["payload_json"]["miner_reward_rows"] == [
            {
                "gross_reward_amount": 50,
                "miner_address": "claw1pokerfair",
                "submission_count": 1,
            },
            {
                "gross_reward_amount": 50,
                "miner_address": "claw1pokerdupone",
                "submission_count": 2,
            }
        ]

    import asyncio

    asyncio.run(scenario())


def test_build_poker_mtt_reward_window_propagates_explicit_policy_bundle_version():
    async def scenario():
        repo = FakeRepository()
        settings = poker_mtt_rollout_settings()
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1pokerpolicyone",
            name="poker-policy-one",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await save_poker_mtt_final_ranking_refs(
            repo,
            "poker-mtt-policy-1",
            [("claw1pokerpolicyone", 1)],
        )

        await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-policy-1",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokerpolicyone",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-policy-1", "claw1pokerpolicyone"),
                }
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
            reward_pool_amount=100,
            include_provisional=False,
            policy_bundle_version="poker_mtt_daily_policy_v2",
            now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
        )

        batch = await repo.get_settlement_batch(reward_window["settlement_batch_id"])
        anchored = await service.retry_anchor_settlement_batch(
            batch["id"],
            now=datetime(2026, 4, 11, 0, 6, 0, tzinfo=timezone.utc),
        )

        assert reward_window["policy_bundle_version"] == "poker_mtt_daily_policy_v2"
        assert batch["policy_bundle_version"] == "poker_mtt_daily_policy_v2"
        assert anchored["anchor_payload_json"]["policy_bundle_version"] == "poker_mtt_daily_policy_v2"

    import asyncio

    asyncio.run(scenario())


def test_retry_anchor_settlement_batch_materializes_poker_mtt_reward_rows():
    async def scenario():
        repo = FakeRepository()
        settings = poker_mtt_rollout_settings()
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1pokeranchorone",
            name="poker-anchor-one",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await service.register_miner(
            address="claw1pokeranchortwo",
            name="poker-anchor-two",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await save_poker_mtt_final_ranking_refs(
            repo,
            "poker-mtt-anchor-1",
            [("claw1pokeranchorone", 1), ("claw1pokeranchortwo", 2)],
        )

        await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-anchor-1",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokeranchorone",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-anchor-1", "claw1pokeranchorone"),
                },
                {
                    "miner_id": "claw1pokeranchortwo",
                    "final_rank": 2,
                    "tournament_result_score": 0.5,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-anchor-1", "claw1pokeranchortwo"),
                },
            ],
            completed_at=datetime(2026, 4, 10, 15, 0, 0, tzinfo=timezone.utc),
        )

        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
            reward_pool_amount=100,
            include_provisional=False,
            now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
        )

        batch = await repo.get_settlement_batch(reward_window["settlement_batch_id"])
        anchored = await service.retry_anchor_settlement_batch(
            batch["id"],
            now=datetime(2026, 4, 11, 0, 6, 0, tzinfo=timezone.utc),
        )

        assert anchored["state"] == "anchor_ready"
        assert anchored["anchor_payload_json"]["task_run_ids"] == ["poker-mtt-anchor-1"]
        assert anchored["anchor_payload_json"]["miner_reward_rows"] == [
            {
                "gross_reward_amount": 51,
                "miner_address": "claw1pokeranchorone",
                "submission_count": 1,
            },
            {
                "gross_reward_amount": 49,
                "miner_address": "claw1pokeranchortwo",
                "submission_count": 1,
            },
        ]
        assert anchored["canonical_root"].startswith("sha256:")

    import asyncio

    asyncio.run(scenario())


def test_retry_anchor_settlement_batch_rejects_incomplete_poker_mtt_projection_metadata():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, poker_mtt_rollout_settings())
        reward_window = await build_poker_mtt_anchor_fixture(
            repo=repo,
            service=service,
            tournament_id="poker-mtt-incomplete-anchor-1",
            miner_addresses=["claw1pokerincompleteanchor"],
        )
        projection_artifact = next(
            artifact
            for artifact in await repo.list_artifacts_for_entity("reward_window", reward_window["id"])
            if artifact["kind"] == "poker_mtt_reward_window_projection"
        )
        incomplete_payload = dict(projection_artifact["payload_json"])
        incomplete_payload.pop("evidence_root", None)
        await repo.save_artifact(
            {
                **projection_artifact,
                "payload_json": incomplete_payload,
                "payload_hash": "sha256:incomplete",
            }
        )

        batch = await repo.get_settlement_batch(reward_window["settlement_batch_id"])
        try:
            await service.retry_anchor_settlement_batch(
                batch["id"],
                now=datetime(2026, 4, 11, 0, 6, 0, tzinfo=timezone.utc),
            )
        except ValueError as exc:
            assert str(exc) == "poker mtt reward window projection metadata incomplete"
        else:
            raise AssertionError("poker anchor should reject incomplete projection metadata")

    import asyncio

    asyncio.run(scenario())


def test_retry_anchor_settlement_batch_includes_poker_mtt_projection_roots_and_is_stable():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, poker_mtt_rollout_settings())
        reward_window = await build_poker_mtt_anchor_fixture(
            repo=repo,
            service=service,
            tournament_id="poker-mtt-anchor-metadata-1",
            miner_addresses=["claw1pokermetadataone", "claw1pokermetadatatwo"],
        )
        batch = await repo.get_settlement_batch(reward_window["settlement_batch_id"])

        first_retry = await service.retry_anchor_settlement_batch(
            batch["id"],
            now=datetime(2026, 4, 11, 0, 6, 0, tzinfo=timezone.utc),
        )
        second_retry = await service.retry_anchor_settlement_batch(
            batch["id"],
            now=datetime(2026, 4, 11, 0, 7, 0, tzinfo=timezone.utc),
        )
        projection_roots = first_retry["anchor_payload_json"]["poker_projection_roots"]

        assert first_retry["canonical_root"] == second_retry["canonical_root"]
        assert first_retry["anchor_payload_hash"] == second_retry["anchor_payload_hash"]
        assert first_retry["anchor_payload_json"]["poker_projection_roots_root"].startswith("sha256:")
        assert len(projection_roots) == 1
        assert projection_roots[0]["reward_window_id"] == reward_window["id"]
        assert projection_roots[0]["policy_bundle_version"] == "poker_mtt_daily_policy_v1"
        assert projection_roots[0]["final_ranking_root"].startswith("sha256:")
        assert projection_roots[0]["evidence_root"].startswith("sha256:")
        assert projection_roots[0]["multiplier_snapshot_root"].startswith("sha256:")
        assert projection_roots[0]["projection_root"].startswith("sha256:")

    import asyncio

    asyncio.run(scenario())


def test_retry_anchor_settlement_batch_rejects_poker_mtt_root_mismatch_after_ready():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, poker_mtt_rollout_settings())
        reward_window = await build_poker_mtt_anchor_fixture(
            repo=repo,
            service=service,
            tournament_id="poker-mtt-anchor-conflict-1",
            miner_addresses=["claw1pokeranchorconflict"],
        )
        batch = await repo.get_settlement_batch(reward_window["settlement_batch_id"])
        await service.retry_anchor_settlement_batch(
            batch["id"],
            now=datetime(2026, 4, 11, 0, 6, 0, tzinfo=timezone.utc),
        )
        projection_artifact = next(
            artifact
            for artifact in await repo.list_artifacts_for_entity("reward_window", reward_window["id"])
            if artifact["kind"] == "poker_mtt_reward_window_projection"
        )
        await repo.save_artifact(
            {
                **projection_artifact,
                "payload_json": {
                    **projection_artifact["payload_json"],
                    "evidence_root": "sha256:evidence:mutated",
                },
                "payload_hash": "sha256:mutated",
            }
        )

        try:
            await service.retry_anchor_settlement_batch(
                batch["id"],
                now=datetime(2026, 4, 11, 0, 7, 0, tzinfo=timezone.utc),
            )
        except ValueError as exc:
            assert str(exc) == "settlement batch canonical root conflict"
        else:
            raise AssertionError("poker anchor should reject root mismatch under the same settlement batch id")

    import asyncio

    asyncio.run(scenario())


def test_build_poker_mtt_reward_window_uses_locked_at_for_membership_time():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings()
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1pokerwindowtime",
            name="poker-window-time",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-window-time-1",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokerwindowtime",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "provisional",
                }
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        stored = (await repo.list_poker_mtt_results_for_miner("claw1pokerwindowtime"))[0]
        await repo.save_poker_mtt_final_ranking(
            poker_mtt_final_ranking_row(
                "poker-mtt-window-time-1",
                "claw1pokerwindowtime",
                final_rank=1,
            )
        )
        await repo.save_poker_mtt_result(
            {
                **stored,
                "evaluation_state": "final",
                "rank_state": "ranked",
                "chip_delta": 29.0,
                "evidence_state": "complete",
                "locked_at": "2026-04-10T09:00:00Z",
                "anchorable_at": "2026-04-10T09:00:00Z",
                "final_ranking_id": "poker_mtt_final_ranking:poker-mtt-window-time-1:claw1pokerwindowtime",
                "standing_snapshot_id": "poker_mtt_standing_snapshot:poker-mtt-window-time-1:abc",
                "standing_snapshot_hash": "sha256:poker-mtt-window-time-1",
                "evidence_root": "sha256:evidence:poker-mtt-window-time-1:claw1pokerwindowtime",
                "eligible_for_multiplier": True,
                "no_multiplier_reason": None,
                "risk_flags": [],
                "updated_at": "2026-04-12T00:00:00Z",
            }
        )

        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
            reward_pool_amount=25,
            include_provisional=False,
            now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
        )

        assert reward_window["task_run_ids"] == ["poker-mtt-window-time-1"]
        assert reward_window["submission_count"] == 1

    import asyncio

    asyncio.run(scenario())


def test_reconcile_auto_builds_closed_poker_mtt_daily_and_weekly_windows():
    async def scenario():
        repo = FakeRepository()
        settings = poker_mtt_rollout_settings(
            poker_mtt_daily_reward_pool_amount=100,
            poker_mtt_weekly_reward_pool_amount=250,
            poker_mtt_daily_policy_bundle_version="poker_mtt_daily_policy_v3",
            poker_mtt_weekly_policy_bundle_version="poker_mtt_weekly_policy_v4",
        )
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1pokerautodaily",
            name="poker-auto-daily",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await save_poker_mtt_final_ranking_refs(
            repo,
            "poker-mtt-auto-1",
            [("claw1pokerautodaily", 1)],
        )

        await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-auto-1",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokerautodaily",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    **poker_mtt_reward_ready_refs("poker-mtt-auto-1", "claw1pokerautodaily"),
                }
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        await service.reconcile(datetime(2026, 4, 14, 0, 5, 0, tzinfo=timezone.utc))

        reward_windows = await repo.list_reward_windows()
        lanes = {window["lane"]: window for window in reward_windows if window["lane"].startswith("poker_mtt_")}

        assert lanes["poker_mtt_daily"]["task_run_ids"] == ["poker-mtt-auto-1"]
        assert lanes["poker_mtt_daily"]["total_reward_amount"] == 100
        assert lanes["poker_mtt_daily"]["policy_bundle_version"] == "poker_mtt_daily_policy_v3"
        assert lanes["poker_mtt_weekly"]["task_run_ids"] == ["poker-mtt-auto-1"]
        assert lanes["poker_mtt_weekly"]["total_reward_amount"] == 250
        assert lanes["poker_mtt_weekly"]["policy_bundle_version"] == "poker_mtt_weekly_policy_v4"

    import asyncio

    asyncio.run(scenario())


def test_reconcile_skips_poker_mtt_auto_window_until_all_results_are_final():
    async def scenario():
        repo = FakeRepository()
        settings = poker_mtt_rollout_settings(
            poker_mtt_daily_reward_pool_amount=100,
            poker_mtt_weekly_reward_pool_amount=0,
        )
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1pokerautofinal",
            name="poker-auto-final",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-auto-final-1",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokerautofinal",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "provisional",
                }
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        await service.reconcile(datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc))
        reward_windows = [window for window in await repo.list_reward_windows() if window["lane"].startswith("poker_mtt_")]
        assert reward_windows == []

        stored = (await repo.list_poker_mtt_results_for_miner("claw1pokerautofinal"))[0]
        await repo.save_poker_mtt_final_ranking(
            poker_mtt_final_ranking_row(
                "poker-mtt-auto-final-1",
                "claw1pokerautofinal",
                final_rank=1,
            )
        )
        await repo.save_poker_mtt_result(
            {
                **stored,
                "evaluation_state": "final",
                "rank_state": "ranked",
                "chip_delta": 29.0,
                "evidence_state": "complete",
                "locked_at": "2026-04-10T09:00:00Z",
                "anchorable_at": "2026-04-10T09:00:00Z",
                "final_ranking_id": "poker_mtt_final_ranking:poker-mtt-auto-final-1:claw1pokerautofinal",
                "standing_snapshot_id": "poker_mtt_standing_snapshot:poker-mtt-auto-final-1:abc",
                "standing_snapshot_hash": "sha256:poker-mtt-auto-final-1",
                "evidence_root": "sha256:evidence:poker-mtt-auto-final-1:claw1pokerautofinal",
                "eligible_for_multiplier": True,
                "no_multiplier_reason": None,
                "risk_flags": [],
                "updated_at": "2026-04-11T00:10:00Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 11, 0, 15, 0, tzinfo=timezone.utc))
        reward_windows = [window for window in await repo.list_reward_windows() if window["lane"].startswith("poker_mtt_")]

        assert len(reward_windows) == 1
        assert reward_windows[0]["lane"] == "poker_mtt_daily"
        assert reward_windows[0]["task_run_ids"] == ["poker-mtt-auto-final-1"]

    import asyncio

    asyncio.run(scenario())


def test_reconcile_does_not_release_unlocked_poker_mtt_window_after_watermark():
    async def scenario():
        repo = FakeRepository()
        settings = poker_mtt_rollout_settings(
            poker_mtt_daily_reward_pool_amount=100,
            poker_mtt_weekly_reward_pool_amount=0,
            poker_mtt_finalization_watermark_seconds=3600,
        )
        service = forecast_engine.ForecastMiningService(repo, settings)

        await service.register_miner(
            address="claw1pokerwatermark",
            name="poker-watermark",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        await service.apply_poker_mtt_results(
            tournament_id="poker-mtt-watermark-1",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1pokerwatermark",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "provisional",
                }
            ],
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )

        await service.reconcile(datetime(2026, 4, 11, 0, 30, 0, tzinfo=timezone.utc))
        reward_windows = [window for window in await repo.list_reward_windows() if window["lane"].startswith("poker_mtt_")]
        assert reward_windows == []

        await service.reconcile(datetime(2026, 4, 11, 1, 5, 0, tzinfo=timezone.utc))
        reward_windows = [window for window in await repo.list_reward_windows() if window["lane"].startswith("poker_mtt_")]
        assert reward_windows == []

    import asyncio

    asyncio.run(scenario())


def test_resolved_fast_task_builds_reward_window_and_miner_histories():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1historyminer",
            name="history-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        task["commit_close_ref_price"] = 70000.5
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1historyminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1historyminer",
                "economic_unit_id": "eu:history",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6400,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T09:00:02Z",
                "accepted_reveal_at": "2026-04-10T09:00:06Z",
                "created_at": "2026-04-10T09:00:02Z",
                "updated_at": "2026-04-10T09:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 9, 1, 5, tzinfo=timezone.utc))

        saved_task = await repo.get_task(task["task_run_id"])
        saved_submission = await repo.get_submission(task["task_run_id"], "claw1historyminer")
        reward_windows = await repo.list_reward_windows()
        settlement_batches = await repo.list_settlement_batches()
        submissions = await service.get_miner_submission_history("claw1historyminer", limit=10, now=datetime(2026, 4, 10, 9, 1, 6, tzinfo=timezone.utc))
        holds = await service.get_miner_reward_hold_history("claw1historyminer", limit=10, now=datetime(2026, 4, 10, 9, 1, 6, tzinfo=timezone.utc))
        miner_windows = await service.get_miner_reward_window_history("claw1historyminer", limit=10, now=datetime(2026, 4, 10, 9, 1, 6, tzinfo=timezone.utc))
        task_history = await service.get_miner_task_history("claw1historyminer", limit=10, now=datetime(2026, 4, 10, 9, 1, 6, tzinfo=timezone.utc))

        assert saved_task["reward_window_id"].startswith("rw_2026041009")
        assert len(reward_windows) == 1
        assert len(settlement_batches) == 1
        assert reward_windows[0]["settlement_batch_id"] == settlement_batches[0]["id"]
        assert reward_windows[0]["id"] == saved_task["reward_window_id"]
        assert reward_windows[0]["task_count"] == 1
        assert reward_windows[0]["miner_count"] == 1
        assert reward_windows[0]["total_reward_amount"] == saved_submission["reward_amount"]
        assert submissions[0]["task_run_id"] == task["task_run_id"]
        assert submissions[0]["reward_window_id"] == reward_windows[0]["id"]
        assert holds[0]["task_run_id"] == task["task_run_id"]
        assert miner_windows[0]["id"] == reward_windows[0]["id"]
        assert task_history[0]["task_run_id"] == task["task_run_id"]
        assert task_history[0]["reward_window_id"] == reward_windows[0]["id"]
        assert task_history[0]["settlement_batch_id"] == settlement_batches[0]["id"]
        assert task_history[0]["pending_resolution"] is False
        assert task_history[0]["task_state"] == "resolved"
        assert task_history[0]["submission_state"] == "resolved"

    import asyncio

    asyncio.run(scenario())


def test_pending_resolution_appears_in_miner_task_history():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": None, "resolution_status": "pending", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1taskpending",
            name="task-pending",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1taskpending",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1taskpending",
                "economic_unit_id": "eu:taskpending",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6100,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T09:00:02Z",
                "accepted_reveal_at": "2026-04-10T09:00:06Z",
                "created_at": "2026-04-10T09:00:02Z",
                "updated_at": "2026-04-10T09:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 9, 1, 5, tzinfo=timezone.utc))

        items = await service.get_miner_task_history("claw1taskpending", limit=10, now=datetime(2026, 4, 10, 9, 1, 6, tzinfo=timezone.utc))

        assert items[0]["task_run_id"] == task["task_run_id"]
        assert items[0]["task_state"] == "awaiting_resolution"
        assert items[0]["submission_state"] == "pending_resolution"
        assert items[0]["pending_resolution"] is True
        assert items[0]["reward_window_id"] is None
        assert items[0]["settlement_batch_id"] is None

    import asyncio

    asyncio.run(scenario())


def test_reward_window_rebuild_replay_proof_and_anchor_payload():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1proofminer",
            name="proof-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 11, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1proofminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1proofminer",
                "economic_unit_id": "eu:proof",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6400,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T11:00:02Z",
                "accepted_reveal_at": "2026-04-10T11:00:06Z",
                "created_at": "2026-04-10T11:00:02Z",
                "updated_at": "2026-04-10T11:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 11, 1, 5, tzinfo=timezone.utc))

        reward_windows = await repo.list_reward_windows()
        settlement_batches = await repo.list_settlement_batches()
        artifacts = await repo.list_artifacts_for_entity("reward_window", reward_window_id := reward_windows[0]["id"])
        reward_window_id = reward_windows[0]["id"]
        batch_id = settlement_batches[0]["id"]

        rebuilt = await service.rebuild_reward_window(reward_window_id, now=datetime(2026, 4, 10, 11, 1, 6, tzinfo=timezone.utc))
        proof = await service.get_replay_proof("reward_window", reward_window_id, now=datetime(2026, 4, 10, 11, 1, 6, tzinfo=timezone.utc))
        anchored = await service.retry_anchor_settlement_batch(batch_id, now=datetime(2026, 4, 10, 11, 1, 7, tzinfo=timezone.utc))
        anchor_artifacts = await repo.list_artifacts_for_entity("settlement_batch", batch_id)

        assert rebuilt["id"] == reward_window_id
        assert rebuilt["policy_bundle_version"] == "pb_2026_04_09_a"
        assert rebuilt["canonical_root"].startswith("sha256:")
        assert proof["entity_type"] == "reward_window"
        assert proof["entity_id"] == reward_window_id
        assert proof["replay_proof_hash"].startswith("sha256:")
        assert proof["artifact_refs"]
        assert proof["policy_bundle_version"] == rebuilt["policy_bundle_version"]
        assert artifacts[0]["kind"] == "reward_window_membership"
        assert artifacts[0]["payload_hash"] == rebuilt["canonical_root"]
        assert proof["artifact_refs"][0]["payload_hash"] == rebuilt["canonical_root"]
        assert proof["membership"]["task_run_ids"] == [task["task_run_id"]]
        assert anchored["id"] == batch_id
        assert anchored["state"] == "anchor_ready"
        assert anchored["policy_bundle_version"] == rebuilt["policy_bundle_version"]
        assert anchored["anchor_payload_hash"].startswith("sha256:")
        assert anchored["anchor_payload_json"]["schema_version"] == "clawchain.anchor_payload.v1"
        assert anchored["anchor_payload_json"]["policy_bundle_version"] == "pb_2026_04_09_a"
        assert anchored["anchor_payload_json"]["reward_window_ids"] == [reward_window_id]
        assert anchored["anchor_payload_json"]["reward_window_ids_root"].startswith("sha256:")
        assert anchored["anchor_payload_json"]["task_run_ids_root"].startswith("sha256:")
        assert anchored["anchor_payload_json"]["miner_reward_rows_root"].startswith("sha256:")
        assert anchored["anchor_payload_json"]["canonical_root"].startswith("sha256:")
        assert anchored["anchor_payload_json"]["miner_reward_rows"][0]["miner_address"] == "claw1proofminer"
        assert anchored["anchor_payload_json"]["miner_reward_rows"][0]["gross_reward_amount"] > 0
        assert anchor_artifacts[0]["kind"] == "settlement_anchor_payload"

    import asyncio

    asyncio.run(scenario())


def test_anchor_job_save_preserves_unspecified_fields_on_update():
    async def scenario():
        repo = FakeRepository()
        await repo.save_anchor_job(
            {
                "id": "aj_contract",
                "settlement_batch_id": "sb_contract",
                "lane": "forecast_15m",
                "state": "anchor_submitted",
                "anchor_payload_hash": "sha256:anchor-job-contract",
                "broadcast_status": "broadcast_submitted",
                "broadcast_tx_hash": "ABC123",
                "chain_confirmation_status": "pending",
                "last_broadcast_at": "2026-04-10T12:00:05Z",
                "failure_reason": None,
                "submitted_at": "2026-04-10T12:00:01Z",
                "anchored_at": None,
                "created_at": "2026-04-10T12:00:01Z",
                "updated_at": "2026-04-10T12:00:05Z",
            }
        )

        saved = await repo.save_anchor_job(
            {
                "id": "aj_contract",
                "chain_confirmation_status": "confirmed",
                "updated_at": "2026-04-10T12:01:00Z",
            }
        )

        assert saved["settlement_batch_id"] == "sb_contract"
        assert saved["anchor_payload_hash"] == "sha256:anchor-job-contract"
        assert saved["broadcast_tx_hash"] == "ABC123"
        assert saved["chain_confirmation_status"] == "confirmed"
        assert saved["submitted_at"] == "2026-04-10T12:00:01Z"

    import asyncio

    asyncio.run(scenario())


def test_reward_window_save_preserves_unspecified_fields_on_update():
    async def scenario():
        repo = FakeRepository()
        await repo.save_reward_window(
            {
                "id": "rw_contract",
                "lane": "forecast_15m",
                "state": "finalized",
                "window_start_at": "2026-04-10T12:00:00Z",
                "window_end_at": "2026-04-10T12:15:00Z",
                "task_count": 1,
                "submission_count": 2,
                "miner_count": 1,
                "total_reward_amount": 33,
                "settlement_batch_id": None,
                "task_run_ids": ["task-contract"],
                "miner_addresses": ["claw1contract"],
                "policy_bundle_version": "pb_2026_04_09_a",
                "created_at": "2026-04-10T12:00:01Z",
                "updated_at": "2026-04-10T12:00:01Z",
            }
        )

        saved = await repo.save_reward_window(
            {
                "id": "rw_contract",
                "settlement_batch_id": "sb_contract",
                "updated_at": "2026-04-10T12:01:00Z",
            }
        )

        assert saved["lane"] == "forecast_15m"
        assert saved["task_run_ids"] == ["task-contract"]
        assert saved["miner_addresses"] == ["claw1contract"]
        assert saved["settlement_batch_id"] == "sb_contract"
        assert saved["created_at"] == "2026-04-10T12:00:01Z"

    import asyncio

    asyncio.run(scenario())


def test_reward_window_link_helper_only_patches_owned_fields():
    async def scenario():
        repo = FakeRepository()
        await repo.save_reward_window(
            {
                "id": "rw_link_helpers",
                "lane": "forecast_15m",
                "state": "finalized",
                "window_start_at": "2026-04-10T12:00:00Z",
                "window_end_at": "2026-04-10T12:15:00Z",
                "task_count": 1,
                "submission_count": 2,
                "miner_count": 1,
                "total_reward_amount": 33,
                "settlement_batch_id": None,
                "task_run_ids": ["task-link"],
                "miner_addresses": ["claw1link"],
                "policy_bundle_version": "pb_2026_04_09_a",
                "created_at": "2026-04-10T12:00:01Z",
                "updated_at": "2026-04-10T12:00:01Z",
            }
        )

        saved = await repo.link_reward_window_settlement_batch(
            "rw_link_helpers",
            settlement_batch_id="sb_link_helpers",
            updated_at="2026-04-10T12:01:00Z",
        )

        assert saved["lane"] == "forecast_15m"
        assert saved["task_count"] == 1
        assert saved["policy_bundle_version"] == "pb_2026_04_09_a"
        assert saved["settlement_batch_id"] == "sb_link_helpers"
        assert saved["updated_at"] == "2026-04-10T12:01:00Z"

    import asyncio

    asyncio.run(scenario())


def test_settlement_batch_save_preserves_unspecified_fields_on_update():
    async def scenario():
        repo = FakeRepository()
        await repo.save_settlement_batch(
            {
                "id": "sb_contract",
                "lane": "forecast_15m",
                "state": "open",
                "window_start_at": "2026-04-10T12:00:00Z",
                "window_end_at": "2026-04-10T12:15:00Z",
                "reward_window_ids": ["rw_contract"],
                "policy_bundle_version": "pb_2026_04_09_a",
                "task_count": 1,
                "miner_count": 1,
                "total_reward_amount": 33,
                "anchor_job_id": None,
                "anchor_schema_version": None,
                "canonical_root": None,
                "anchor_payload_json": None,
                "anchor_payload_hash": None,
                "created_at": "2026-04-10T12:00:01Z",
                "updated_at": "2026-04-10T12:00:01Z",
            }
        )

        saved = await repo.save_settlement_batch(
            {
                "id": "sb_contract",
                "state": "anchor_failed",
                "updated_at": "2026-04-10T12:01:00Z",
            }
        )

        assert saved["lane"] == "forecast_15m"
        assert saved["reward_window_ids"] == ["rw_contract"]
        assert saved["policy_bundle_version"] == "pb_2026_04_09_a"
        assert saved["state"] == "anchor_failed"
        assert saved["created_at"] == "2026-04-10T12:00:01Z"

    import asyncio

    asyncio.run(scenario())


def test_settlement_batch_helpers_only_patch_owned_fields():
    async def scenario():
        repo = FakeRepository()
        await repo.save_settlement_batch(
            {
                "id": "sb_helpers",
                "lane": "forecast_15m",
                "state": "open",
                "window_start_at": "2026-04-10T12:00:00Z",
                "window_end_at": "2026-04-10T12:15:00Z",
                "reward_window_ids": ["rw_helpers"],
                "policy_bundle_version": "pb_2026_04_09_a",
                "task_count": 1,
                "miner_count": 1,
                "total_reward_amount": 33,
                "anchor_job_id": None,
                "anchor_schema_version": None,
                "canonical_root": None,
                "anchor_payload_json": None,
                "anchor_payload_hash": None,
                "created_at": "2026-04-10T12:00:01Z",
                "updated_at": "2026-04-10T12:00:01Z",
            }
        )

        synced = await repo.sync_open_settlement_batch(
            "sb_helpers",
            lane="forecast_15m",
            window_start_at="2026-04-10T12:00:00Z",
            window_end_at="2026-04-10T12:15:00Z",
            reward_window_ids=["rw_helpers"],
            policy_bundle_version="pb_2026_04_09_a",
            task_count=2,
            miner_count=2,
            total_reward_amount=55,
            updated_at="2026-04-10T12:01:00Z",
        )
        ready = await repo.mark_settlement_batch_anchor_ready(
            "sb_helpers",
            policy_bundle_version="pb_2026_04_09_a",
            anchor_schema_version="clawchain.anchor_payload.v1",
            canonical_root="sha256:" + "a" * 64,
            anchor_payload_json={"canonical_root": "sha256:" + "a" * 64},
            anchor_payload_hash="sha256:" + "b" * 64,
            updated_at="2026-04-10T12:01:01Z",
        )
        submitted = await repo.mark_settlement_batch_anchor_submitted(
            "sb_helpers",
            anchor_job_id="aj_helpers",
            updated_at="2026-04-10T12:01:02Z",
        )
        anchored = await repo.mark_settlement_batch_terminal(
            "sb_helpers",
            state="anchored",
            updated_at="2026-04-10T12:01:03Z",
        )
        cancelled = await repo.cancel_settlement_batch(
            "sb_helpers",
            total_reward_amount=0,
            updated_at="2026-04-10T12:01:04Z",
        )

        assert synced["task_count"] == 2
        assert synced["miner_count"] == 2
        assert synced["state"] == "open"
        assert ready["state"] == "anchor_ready"
        assert ready["reward_window_ids"] == ["rw_helpers"]
        assert ready["canonical_root"] == "sha256:" + "a" * 64
        assert submitted["state"] == "anchor_submitted"
        assert submitted["anchor_job_id"] == "aj_helpers"
        assert anchored["state"] == "anchored"
        assert anchored["policy_bundle_version"] == "pb_2026_04_09_a"
        assert cancelled["state"] == "cancelled"
        assert cancelled["reward_window_ids"] == ["rw_helpers"]
        assert cancelled["anchor_payload_hash"] is None
        assert cancelled["total_reward_amount"] == 0

    import asyncio

    asyncio.run(scenario())


def test_anchor_job_helpers_only_patch_owned_fields():
    async def scenario():
        repo = FakeRepository()
        await repo.save_anchor_job(
            {
                "id": "aj_helpers",
                "settlement_batch_id": "sb_helpers",
                "lane": "forecast_15m",
                "state": "anchor_submitted",
                "anchor_payload_hash": "sha256:helper-anchor",
                "broadcast_status": None,
                "broadcast_tx_hash": None,
                "chain_confirmation_status": None,
                "last_broadcast_at": None,
                "failure_reason": None,
                "submitted_at": "2026-04-10T12:00:01Z",
                "anchored_at": None,
                "created_at": "2026-04-10T12:00:01Z",
                "updated_at": "2026-04-10T12:00:01Z",
            }
        )

        broadcasted = await repo.update_anchor_job_broadcast(
            "aj_helpers",
            broadcast_status="broadcast_submitted",
            broadcast_tx_hash="ABC999",
            last_broadcast_at="2026-04-10T12:00:05Z",
            updated_at="2026-04-10T12:00:05Z",
        )
        confirmed = await repo.update_anchor_job_confirmation(
            "aj_helpers",
            chain_confirmation_status="pending",
            updated_at="2026-04-10T12:00:06Z",
        )
        anchored = await repo.mark_anchor_job_terminal(
            "aj_helpers",
            state="anchored",
            anchored_at="2026-04-10T12:00:07Z",
            chain_confirmation_status="confirmed",
            failure_reason=None,
            updated_at="2026-04-10T12:00:07Z",
        )

        assert broadcasted["state"] == "anchor_submitted"
        assert broadcasted["broadcast_tx_hash"] == "ABC999"
        assert broadcasted["settlement_batch_id"] == "sb_helpers"
        assert confirmed["chain_confirmation_status"] == "pending"
        assert confirmed["anchor_payload_hash"] == "sha256:helper-anchor"
        assert anchored["state"] == "anchored"
        assert anchored["anchored_at"] == "2026-04-10T12:00:07Z"
        assert anchored["chain_confirmation_status"] == "confirmed"
        assert anchored["submitted_at"] == "2026-04-10T12:00:01Z"

    import asyncio

    asyncio.run(scenario())


def test_artifact_save_preserves_unspecified_fields_on_update():
    async def scenario():
        repo = FakeRepository()
        await repo.save_artifact(
            {
                "id": "art_contract",
                "kind": "chain_tx_plan",
                "entity_type": "anchor_job",
                "entity_id": "aj_contract",
                "payload_json": {"plan_hash": "sha256:plan-a"},
                "payload_hash": "sha256:artifact-a",
                "created_at": "2026-04-10T12:00:01Z",
                "updated_at": "2026-04-10T12:00:01Z",
            }
        )

        saved = await repo.save_artifact(
            {
                "id": "art_contract",
                "payload_hash": "sha256:artifact-b",
                "updated_at": "2026-04-10T12:00:02Z",
            }
        )

        assert saved["kind"] == "chain_tx_plan"
        assert saved["entity_type"] == "anchor_job"
        assert saved["entity_id"] == "aj_contract"
        assert saved["payload_json"] == {"plan_hash": "sha256:plan-a"}
        assert saved["payload_hash"] == "sha256:artifact-b"
        assert saved["created_at"] == "2026-04-10T12:00:01Z"

    import asyncio

    asyncio.run(scenario())


def test_anchor_job_progression_to_anchored():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1anchorjob",
            name="anchor-job",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 12, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1anchorjob",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1anchorjob",
                "economic_unit_id": "eu:anchorjob",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6400,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T12:00:02Z",
                "accepted_reveal_at": "2026-04-10T12:00:06Z",
                "created_at": "2026-04-10T12:00:02Z",
                "updated_at": "2026-04-10T12:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 12, 1, 5, tzinfo=timezone.utc))
        batch = (await repo.list_settlement_batches())[0]
        ready = await service.retry_anchor_settlement_batch(batch["id"], now=datetime(2026, 4, 10, 12, 1, 6, tzinfo=timezone.utc))
        submitted = await service.submit_anchor_job(batch["id"], now=datetime(2026, 4, 10, 12, 1, 7, tzinfo=timezone.utc))
        anchored = await service.mark_anchor_job_anchored(submitted["id"], now=datetime(2026, 4, 10, 12, 1, 8, tzinfo=timezone.utc))

        saved_batch = await repo.get_settlement_batch(batch["id"])
        jobs = await repo.list_anchor_jobs()

        assert ready["state"] == "anchor_ready"
        assert submitted["state"] == "anchor_submitted"
        assert submitted["anchor_job_id"] == anchored["id"]
        assert anchored["state"] == "anchored"
        assert saved_batch["state"] == "anchored"
        assert saved_batch["anchor_job_id"] == anchored["id"]
        assert jobs[0]["state"] == "anchored"

    import asyncio

    asyncio.run(scenario())


def test_anchor_job_persists_terminal_query_mismatch_state():
    async def scenario():
        repo = FakeRepository()
        current = datetime(2026, 4, 10, 12, 1, 0, tzinfo=timezone.utc)
        batch_id = "sb_query_mismatch"
        anchor_job_id = "aj_query_mismatch"
        root_a = "sha256:" + "a" * 64
        root_b = "sha256:" + "b" * 64
        root_c = "sha256:" + "c" * 64
        await repo.save_settlement_batch(
            {
                "id": batch_id,
                "lane": "poker_mtt_daily",
                "state": "anchor_submitted",
                "window_start_at": "2026-04-10T00:00:00Z",
                "window_end_at": "2026-04-11T00:00:00Z",
                "reward_window_ids": ["rw_query_mismatch"],
                "policy_bundle_version": "policy.v1",
                "task_count": 1,
                "miner_count": 1,
                "total_reward_amount": 10,
                "anchor_job_id": anchor_job_id,
                "anchor_schema_version": "clawchain.anchor_payload.v1",
                "canonical_root": root_a,
                "anchor_payload_hash": root_b,
                "anchor_payload_json": {
                    "schema_version": "clawchain.anchor_payload.v1",
                    "policy_bundle_version": "policy.v1",
                    "settlement_batch_id": batch_id,
                    "lane": "poker_mtt_daily",
                    "reward_window_ids_root": root_c,
                    "task_run_ids_root": root_c,
                    "miner_reward_rows_root": root_c,
                    "canonical_root": root_a,
                },
                "created_at": "2026-04-10T12:00:00Z",
                "updated_at": "2026-04-10T12:00:00Z",
            }
        )
        await repo.save_anchor_job(
            {
                "id": anchor_job_id,
                "settlement_batch_id": batch_id,
                "lane": "poker_mtt_daily",
                "state": "anchor_submitted",
                "anchor_payload_hash": root_b,
                "broadcast_status": "broadcast_submitted",
                "broadcast_tx_hash": "ABC123",
                "last_broadcast_at": "2026-04-10T12:00:05Z",
                "failure_reason": None,
                "submitted_at": "2026-04-10T12:00:01Z",
                "anchored_at": None,
                "created_at": "2026-04-10T12:00:01Z",
                "updated_at": "2026-04-10T12:00:05Z",
            }
        )

        async def confirmer(_tx_hash, _now):
            return {
                "confirmation_status": "confirmed",
                "query_response": {
                    "anchor": {
                        "settlement_batch_id": batch_id,
                        "canonical_root": "sha256:" + "d" * 64,
                        "anchor_payload_hash": root_b,
                    }
                },
                "broadcast_method": "typed_msg",
                "height": 42,
                "code": 0,
                "raw_log": "",
            }

        service = forecast_engine.ForecastMiningService(
            repo,
            poker_mtt_rollout_settings(),
            chain_tx_confirmer=confirmer,
        )
        result = await service.confirm_anchor_job_on_chain(anchor_job_id, now=current)
        saved_job = await repo.get_anchor_job(anchor_job_id)

        assert result["chain_confirmation_status"] == "root_mismatch"
        assert result["anchor_job_state"] == "anchor_failed"
        assert saved_job["chain_confirmation_status"] == "root_mismatch"
        assert "root_hash_mismatch" in saved_job["failure_reason"]

    import asyncio

    asyncio.run(scenario())


def test_confirm_anchor_job_on_chain_rejects_corrupted_local_settlement_artifacts():
    async def scenario():
        repo = FakeRepository()
        current = datetime(2026, 4, 11, 0, 7, 0, tzinfo=timezone.utc)
        confirmer_response = {}

        async def confirmer(_tx_hash, _now):
            return {
                "tx_hash": "TX-CORRUPT",
                "confirmation_status": "confirmed",
                "found": True,
                "height": 77,
                "code": 0,
                "raw_log": "",
                **confirmer_response,
            }

        service = forecast_engine.ForecastMiningService(
            repo,
            poker_mtt_rollout_settings(poker_mtt_projection_artifact_page_size=1),
            chain_tx_confirmer=confirmer,
        )
        reward_window = await build_poker_mtt_anchor_fixture(
            repo=repo,
            service=service,
            tournament_id="poker-mtt-corrupt-local-artifacts-1",
            miner_addresses=["claw1artifacta", "claw1artifactb"],
        )
        batch = await repo.get_settlement_batch(reward_window["settlement_batch_id"])
        ready_batch = await service.retry_anchor_settlement_batch(batch["id"], now=current)
        artifacts = await repo.list_artifacts_for_entity("settlement_batch", batch["id"])
        page_artifact = next(
            artifact
            for artifact in artifacts
            if artifact["kind"] == forecast_engine.SETTLEMENT_ANCHOR_PAGE_ARTIFACT_KIND
        )
        corrupted_page = {
            **page_artifact,
            "payload_json": {
                **page_artifact["payload_json"],
                "miner_reward_rows": [
                    {
                        **page_artifact["payload_json"]["miner_reward_rows"][0],
                        "gross_reward_amount": page_artifact["payload_json"]["miner_reward_rows"][0]["gross_reward_amount"] + 1,
                    }
                ],
                "page_root": page_artifact["payload_json"]["page_root"],
            },
            "updated_at": "2026-04-11T00:07:01Z",
        }
        await repo.save_artifact(corrupted_page)

        submitted = await service.submit_anchor_job(batch["id"], now=current + timedelta(seconds=1))
        await repo.save_anchor_job(
            {
                **(await repo.get_anchor_job(submitted["anchor_job_id"])),
                "broadcast_status": "broadcast_submitted",
                "broadcast_tx_hash": "TX-CORRUPT",
                "last_broadcast_at": "2026-04-11T00:07:02Z",
                "updated_at": "2026-04-11T00:07:02Z",
            }
        )
        confirmer_response.update(
            {
                "confirmed": True,
                "query_response": {
                    "anchor": {
                        "settlement_batch_id": batch["id"],
                        "anchor_job_id": submitted["anchor_job_id"],
                        "lane": ready_batch["lane"],
                        "schema_version": ready_batch["anchor_schema_version"],
                        "policy_bundle_version": ready_batch["anchor_payload_json"]["policy_bundle_version"],
                        "canonical_root": ready_batch["canonical_root"],
                        "anchor_payload_hash": ready_batch["anchor_payload_hash"],
                        "reward_window_ids_root": ready_batch["anchor_payload_json"]["reward_window_ids_root"],
                        "task_run_ids_root": ready_batch["anchor_payload_json"]["task_run_ids_root"],
                        "miner_reward_rows_root": ready_batch["anchor_payload_json"]["miner_reward_rows_root"],
                        "window_end_at": ready_batch["window_end_at"],
                        "total_reward_amount": ready_batch["total_reward_amount"],
                    }
                },
            }
        )

        receipt = await service.confirm_anchor_job_on_chain(
            submitted["anchor_job_id"],
            now=current + timedelta(seconds=3),
        )
        saved_job = await repo.get_anchor_job(submitted["anchor_job_id"])

        assert receipt["chain_confirmation_status"] == "root_mismatch"
        assert receipt["anchor_job_state"] == "anchor_failed"
        assert saved_job["chain_confirmation_status"] == "root_mismatch"
        assert "settlement anchor page root mismatch" in saved_job["failure_reason"]

    import asyncio

    asyncio.run(scenario())


def test_anchor_job_failure_can_retry_to_ready():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1anchorfail",
            name="anchor-fail",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 13, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1anchorfail",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1anchorfail",
                "economic_unit_id": "eu:anchorfail",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6400,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T13:00:02Z",
                "accepted_reveal_at": "2026-04-10T13:00:06Z",
                "created_at": "2026-04-10T13:00:02Z",
                "updated_at": "2026-04-10T13:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 13, 1, 5, tzinfo=timezone.utc))
        batch = (await repo.list_settlement_batches())[0]
        await service.retry_anchor_settlement_batch(batch["id"], now=datetime(2026, 4, 10, 13, 1, 6, tzinfo=timezone.utc))
        submitted = await service.submit_anchor_job(batch["id"], now=datetime(2026, 4, 10, 13, 1, 7, tzinfo=timezone.utc))
        failed = await service.mark_anchor_job_failed(
            submitted["id"],
            failure_reason="rpc timeout",
            now=datetime(2026, 4, 10, 13, 1, 8, tzinfo=timezone.utc),
        )
        retried = await service.retry_anchor_settlement_batch(batch["id"], now=datetime(2026, 4, 10, 13, 1, 9, tzinfo=timezone.utc))

        saved_batch = await repo.get_settlement_batch(batch["id"])

        assert failed["state"] == "anchor_failed"
        assert failed["failure_reason"] == "rpc timeout"
        assert retried["state"] == "anchor_ready"
        assert saved_batch["state"] == "anchor_ready"
        assert saved_batch["anchor_job_id"] is None

    import asyncio

    asyncio.run(scenario())


def test_broadcast_chain_tx_fallback_records_tx_hash():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )

        async def fake_broadcaster(plan, now):  # noqa: ANN001
            return {
                "tx_hash": "ABC123TX",
                "code": 0,
                "raw_log": "",
                "memo": plan["fallback_memo"],
                "broadcast_at": forecast_engine.isoformat_z(now),
                "account_number": 0,
                "sequence": 9,
                "attempt_count": 2,
            }

        service = forecast_engine.ForecastMiningService(
            repo,
            settings,
            task_provider=provider,
            chain_broadcaster=fake_broadcaster,
        )

        await service.register_miner(
            address="claw1broadcastminer",
            name="broadcast-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 15, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1broadcastminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1broadcastminer",
                "economic_unit_id": "eu:broadcast",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6400,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T15:00:02Z",
                "accepted_reveal_at": "2026-04-10T15:00:06Z",
                "created_at": "2026-04-10T15:00:02Z",
                "updated_at": "2026-04-10T15:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 15, 1, 5, tzinfo=timezone.utc))
        batch = (await repo.list_settlement_batches())[0]
        await service.retry_anchor_settlement_batch(batch["id"], now=datetime(2026, 4, 10, 15, 1, 6, tzinfo=timezone.utc))
        submitted = await service.submit_anchor_job(batch["id"], now=datetime(2026, 4, 10, 15, 1, 7, tzinfo=timezone.utc))

        receipt = await service.broadcast_chain_tx_fallback(
            submitted["anchor_job_id"],
            now=datetime(2026, 4, 10, 15, 1, 8, tzinfo=timezone.utc),
        )
        saved_job = await repo.get_anchor_job(submitted["anchor_job_id"])
        artifacts = await repo.list_artifacts_for_entity("anchor_job", submitted["anchor_job_id"])

        assert receipt["tx_hash"] == "ABC123TX"
        assert saved_job["state"] == "anchor_submitted"
        assert saved_job["broadcast_tx_hash"] == "ABC123TX"
        assert saved_job["broadcast_status"] == "broadcast_submitted"
        assert receipt["account_number"] == 0
        assert receipt["sequence"] == 9
        assert receipt["attempt_count"] == 2
        assert any(item["kind"] == "chain_broadcast_receipt" for item in artifacts)

    import asyncio

    asyncio.run(scenario())


def test_build_chain_tx_plan_from_anchor_job():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1chainplan",
            name="chain-plan",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 14, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1chainplan",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1chainplan",
                "economic_unit_id": "eu:chainplan",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6400,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T14:00:02Z",
                "accepted_reveal_at": "2026-04-10T14:00:06Z",
                "created_at": "2026-04-10T14:00:02Z",
                "updated_at": "2026-04-10T14:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 14, 1, 5, tzinfo=timezone.utc))
        batch = (await repo.list_settlement_batches())[0]
        await service.retry_anchor_settlement_batch(batch["id"], now=datetime(2026, 4, 10, 14, 1, 6, tzinfo=timezone.utc))
        submitted = await service.submit_anchor_job(batch["id"], now=datetime(2026, 4, 10, 14, 1, 7, tzinfo=timezone.utc))
        tx_plan = await service.build_chain_tx_plan(submitted["anchor_job_id"], now=datetime(2026, 4, 10, 14, 1, 8, tzinfo=timezone.utc))
        artifacts = await repo.list_artifacts_for_entity("anchor_job", submitted["anchor_job_id"])

        assert tx_plan["adapter_version"] == "clawchain.chain_adapter.v1"
        assert tx_plan["tx_builder_kind"] == "cosmos_anchor_intent_v1"
        assert tx_plan["execution_mode"] == "build_only"
        assert tx_plan["settlement_batch_id"] == batch["id"]
        assert tx_plan["anchor_job_id"] == submitted["anchor_job_id"]
        assert tx_plan["canonical_root"].startswith("sha256:")
        assert tx_plan["anchor_payload_hash"].startswith("sha256:")
        assert tx_plan["future_msg"]["type_url"] == "/clawchain.settlement.v1.MsgAnchorSettlementBatch"
        assert tx_plan["future_msg"]["value"]["canonical_root"] == tx_plan["canonical_root"]
        assert tx_plan["typed_tx_intent"]["version"] == "clawchain.typed_tx_intent.v1"
        assert tx_plan["typed_tx_intent"]["body"]["messages"][0] == tx_plan["future_msg"]
        assert tx_plan["typed_tx_intent"]["body"]["memo"] == tx_plan["fallback_memo"]
        assert tx_plan["typed_tx_intent"]["auth_info_hints"]["fee_hint"]["amount"] == "10uclaw"
        assert tx_plan["typed_tx_intent"]["auth_info_hints"]["fee_hint"]["gas_limit"] == 200000
        assert tx_plan["typed_tx_intent"]["auth_info_hints"]["signer_hint"]["role"] == "anchor_submitter"
        assert tx_plan["fallback_memo"].startswith("anchor:v1:")
        assert artifacts[0]["kind"] == "chain_tx_plan"

    import asyncio

    asyncio.run(scenario())


def test_broadcast_chain_tx_typed_records_tx_hash():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )

        async def fake_typed_broadcaster(plan, now):  # noqa: ANN001
            return {
                "tx_hash": "TYPED123TX",
                "code": 0,
                "raw_log": "",
                "memo": plan["fallback_memo"],
                "broadcast_at": forecast_engine.isoformat_z(now),
                "account_number": 0,
                "sequence": 6,
                "attempt_count": 1,
                "broadcast_method": "typed_msg",
            }

        service = forecast_engine.ForecastMiningService(
            repo,
            settings,
            task_provider=provider,
            chain_typed_broadcaster=fake_typed_broadcaster,
        )

        await service.register_miner(
            address="claw1typedminer",
            name="typed-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 16, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1typedminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1typedminer",
                "economic_unit_id": "eu:typed",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6400,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T16:00:02Z",
                "accepted_reveal_at": "2026-04-10T16:00:06Z",
                "created_at": "2026-04-10T16:00:02Z",
                "updated_at": "2026-04-10T16:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 16, 1, 5, tzinfo=timezone.utc))
        batch = (await repo.list_settlement_batches())[0]
        await service.retry_anchor_settlement_batch(batch["id"], now=datetime(2026, 4, 10, 16, 1, 6, tzinfo=timezone.utc))
        submitted = await service.submit_anchor_job(batch["id"], now=datetime(2026, 4, 10, 16, 1, 7, tzinfo=timezone.utc))

        receipt = await service.broadcast_chain_tx_typed(
            submitted["anchor_job_id"],
            now=datetime(2026, 4, 10, 16, 1, 8, tzinfo=timezone.utc),
        )
        saved_job = await repo.get_anchor_job(submitted["anchor_job_id"])
        artifacts = await repo.list_artifacts_for_entity("anchor_job", submitted["anchor_job_id"])

        assert receipt["tx_hash"] == "TYPED123TX"
        assert receipt["broadcast_method"] == "typed_msg"
        assert saved_job["state"] == "anchor_submitted"
        assert saved_job["broadcast_tx_hash"] == "TYPED123TX"
        assert saved_job["broadcast_status"] == "broadcast_submitted"
        assert any(item["kind"] == "chain_broadcast_receipt" for item in artifacts)

    import asyncio

    asyncio.run(scenario())


def test_retry_failed_anchor_job_broadcast_typed_creates_new_anchor_job():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
        )

        async def fake_typed_broadcaster(plan, now):  # noqa: ANN001
            return {
                "tx_hash": "RETRYTYPEDTX",
                "code": 0,
                "raw_log": "",
                "memo": plan["fallback_memo"],
                "broadcast_at": forecast_engine.isoformat_z(now),
                "account_number": 2,
                "sequence": 7,
                "attempt_count": 1,
                "broadcast_method": "typed_msg",
            }

        service = forecast_engine.ForecastMiningService(
            repo,
            settings,
            task_provider=provider,
            chain_typed_broadcaster=fake_typed_broadcaster,
        )

        await service.register_miner(
            address="claw1retrytyped",
            name="retry-typed",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 16, 30, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1retrytyped",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1retrytyped",
                "economic_unit_id": "eu:retrytyped",
                "commit_request_id": "req-commit",
                "reveal_request_id": "req-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6400,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T16:30:02Z",
                "accepted_reveal_at": "2026-04-10T16:30:06Z",
                "created_at": "2026-04-10T16:30:02Z",
                "updated_at": "2026-04-10T16:30:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 16, 31, 5, tzinfo=timezone.utc))
        batch = (await repo.list_settlement_batches())[0]
        await service.retry_anchor_settlement_batch(batch["id"], now=datetime(2026, 4, 10, 16, 31, 6, tzinfo=timezone.utc))
        submitted = await service.submit_anchor_job(batch["id"], now=datetime(2026, 4, 10, 16, 31, 7, tzinfo=timezone.utc))
        failed = await service.mark_anchor_job_failed(
            submitted["anchor_job_id"],
            failure_reason="rpc timeout",
            now=datetime(2026, 4, 10, 16, 31, 8, tzinfo=timezone.utc),
        )

        receipt = await service.retry_failed_anchor_job_broadcast_typed(
            failed["id"],
            now=datetime(2026, 4, 10, 16, 31, 9, tzinfo=timezone.utc),
        )

        saved_batch = await repo.get_settlement_batch(batch["id"])
        old_job = await repo.get_anchor_job(failed["id"])
        new_job = await repo.get_anchor_job(receipt["new_anchor_job_id"])
        jobs = await repo.list_anchor_jobs()

        assert receipt["previous_anchor_job_id"] == failed["id"]
        assert receipt["new_anchor_job_id"] != failed["id"]
        assert receipt["tx_hash"] == "RETRYTYPEDTX"
        assert receipt["broadcast_mode"] == "typed"
        assert old_job["state"] == "anchor_failed"
        assert new_job["state"] == "anchor_submitted"
        assert new_job["broadcast_tx_hash"] == "RETRYTYPEDTX"
        assert saved_batch["state"] == "anchor_submitted"
        assert saved_batch["anchor_job_id"] == receipt["new_anchor_job_id"]
        assert len(jobs) == 2

    import asyncio

    asyncio.run(scenario())


def test_miner_status_includes_score_explanation_and_reward_timeline():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(fast_task_seconds=60, commit_window_seconds=5, reveal_window_seconds=10)
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": 70120.0}],
            daily_resolutions=[
                {
                    "outcome": 1,
                    "resolution_status": "resolved",
                    "start_ref_price": 70000.0,
                    "end_ref_price": 71200.0,
                }
            ],
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1statusminer",
            name="status-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        fast_now = datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc)
        fast_task = forecast_engine.build_fast_task(fast_now, settings, asset="BTCUSDT")
        fast_task["commit_close_ref_price"] = 70000.5
        await repo.upsert_task(fast_task)
        await repo.save_submission(
            {
                "id": f"sub:{fast_task['task_run_id']}:claw1statusminer",
                "task_run_id": fast_task["task_run_id"],
                "miner_address": "claw1statusminer",
                "economic_unit_id": "eu:status",
                "commit_request_id": "req-fast-commit",
                "reveal_request_id": "req-fast-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6200,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T09:00:02Z",
                "accepted_reveal_at": "2026-04-10T09:00:06Z",
                "created_at": "2026-04-10T09:00:02Z",
                "updated_at": "2026-04-10T09:00:06Z",
            }
        )

        daily_now = datetime(2026, 4, 10, 0, 0, 1, tzinfo=timezone.utc)
        daily_task = forecast_engine.build_daily_anchor_task(daily_now, asset="BTC", settings=settings)
        await repo.upsert_task(daily_task)
        await repo.save_submission(
            {
                "id": f"sub:{daily_task['task_run_id']}:claw1statusminer",
                "task_run_id": daily_task["task_run_id"],
                "miner_address": "claw1statusminer",
                "economic_unit_id": "eu:status",
                "commit_request_id": "req-daily-commit",
                "reveal_request_id": "req-daily-reveal",
                "commit_hash": "hash2",
                "commit_nonce": "nonce2",
                "p_yes_bps": 8500,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T00:00:02Z",
                "accepted_reveal_at": "2026-04-10T00:00:06Z",
                "created_at": "2026-04-10T00:00:02Z",
                "updated_at": "2026-04-10T00:00:06Z",
            }
        )

        await service.apply_arena_results(
            tournament_id="arena-status-practice",
            rated_or_practice="practice",
            human_only=True,
            results=[{"miner_id": "claw1statusminer", "arena_score": 0.4}],
            completed_at=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
        )

        await service.reconcile(datetime(2026, 4, 11, 0, 0, 5, tzinfo=timezone.utc))
        status = await service.get_miner_status("claw1statusminer", datetime(2026, 4, 11, 0, 0, 6, tzinfo=timezone.utc))

        assert status["score_explanation"]["latest_fast"]["task_run_id"] == fast_task["task_run_id"]
        assert status["score_explanation"]["latest_fast"]["reward_amount"] > 0
        assert status["score_explanation"]["latest_daily"]["task_run_id"] == daily_task["task_run_id"]
        assert status["score_explanation"]["latest_daily"]["anchor_multiplier"] > 1.0
        assert status["score_explanation"]["latest_arena"]["tournament_id"] == "arena-status-practice"
        assert status["reward_timeline"]["open_hold_entry_count"] == 1
        assert status["reward_timeline"]["pending_resolution_count"] == 0
        assert status["reward_timeline"]["released_rewards"] == status["total_rewards"]

    import asyncio

    asyncio.run(scenario())


def test_reward_window_membership_stays_single_across_reconcile_passes():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(
            fast_task_seconds=60,
            commit_window_seconds=5,
            reveal_window_seconds=10,
        )
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": 70120.0}]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1windowminer",
            name="window-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 11, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        task["commit_close_ref_price"] = 70000.5
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1windowminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1windowminer",
                "economic_unit_id": "eu:window",
                "commit_request_id": "req-window-commit",
                "reveal_request_id": "req-window-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6200,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T11:00:02Z",
                "accepted_reveal_at": "2026-04-10T11:00:06Z",
                "created_at": "2026-04-10T11:00:02Z",
                "updated_at": "2026-04-10T11:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 11, 1, 5, tzinfo=timezone.utc))
        task_after_first = await repo.get_task(task["task_run_id"])
        submission_after_first = await repo.get_submission(task["task_run_id"], "claw1windowminer")
        reward_windows_after_first = await repo.list_reward_windows()

        await service.reconcile(datetime(2026, 4, 10, 11, 10, 5, tzinfo=timezone.utc))
        task_after_second = await repo.get_task(task["task_run_id"])
        submission_after_second = await repo.get_submission(task["task_run_id"], "claw1windowminer")
        reward_windows_after_second = await repo.list_reward_windows()

        assert len(reward_windows_after_first) == 1
        assert len(reward_windows_after_second) == 1
        assert task_after_first["reward_window_id"] == task_after_second["reward_window_id"]
        assert submission_after_first["reward_window_id"] == submission_after_second["reward_window_id"]

    import asyncio

    asyncio.run(scenario())


def test_retry_anchor_settlement_batch_keeps_canonical_root_stable():
    async def scenario():
        repo = FakeRepository()
        settings = forecast_engine.ForecastSettings(
            fast_task_seconds=60,
            commit_window_seconds=5,
            reveal_window_seconds=10,
        )
        provider = StaticTaskProvider(
            [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": 70120.0}]
        )
        service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

        await service.register_miner(
            address="claw1rootminer",
            name="root-miner",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        now = datetime(2026, 4, 10, 12, 0, 1, tzinfo=timezone.utc)
        task = forecast_engine.build_fast_task(now, settings, asset="BTCUSDT")
        task["commit_close_ref_price"] = 70000.5
        await repo.upsert_task(task)
        await repo.save_submission(
            {
                "id": f"sub:{task['task_run_id']}:claw1rootminer",
                "task_run_id": task["task_run_id"],
                "miner_address": "claw1rootminer",
                "economic_unit_id": "eu:root",
                "commit_request_id": "req-root-commit",
                "reveal_request_id": "req-root-reveal",
                "commit_hash": "hash",
                "commit_nonce": "nonce",
                "p_yes_bps": 6200,
                "eligibility_status": "eligible",
                "state": "revealed",
                "score": 0.0,
                "reward_amount": 0,
                "accepted_commit_at": "2026-04-10T12:00:02Z",
                "accepted_reveal_at": "2026-04-10T12:00:06Z",
                "created_at": "2026-04-10T12:00:02Z",
                "updated_at": "2026-04-10T12:00:06Z",
            }
        )

        await service.reconcile(datetime(2026, 4, 10, 12, 1, 5, tzinfo=timezone.utc))
        batch = (await repo.list_settlement_batches())[0]

        first_retry = await service.retry_anchor_settlement_batch(
            batch["id"],
            now=datetime(2026, 4, 10, 12, 1, 6, tzinfo=timezone.utc),
        )
        second_retry = await service.retry_anchor_settlement_batch(
            batch["id"],
            now=datetime(2026, 4, 10, 12, 2, 6, tzinfo=timezone.utc),
        )

        assert first_retry["canonical_root"] == second_retry["canonical_root"]
        assert first_retry["anchor_payload_hash"] == second_retry["anchor_payload_hash"]
        assert first_retry["anchor_payload_json"]["task_run_ids"] == second_retry["anchor_payload_json"]["task_run_ids"]

    import asyncio

    asyncio.run(scenario())
