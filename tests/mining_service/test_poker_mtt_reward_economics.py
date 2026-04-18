from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine
from repository import FakeRepository


WINDOW_START = datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END = WINDOW_START + timedelta(days=1)
BUILD_NOW = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
POLICY_VERSION = "poker_mtt_daily_policy_v2"


def test_budget_source_missing_or_oversized_reward_window_rejects():
    async def scenario():
        repo = FakeRepository()
        _seed_reward_ready_result(repo, tournament_id="mtt-budget-missing", miner_address="claw1budgetmissing", total_score=1.0)
        service = forecast_engine.ForecastMiningService(
            repo,
            forecast_engine.ForecastSettings(
                poker_mtt_budget_enforcement_enabled=True,
                poker_mtt_emission_epoch_id="epoch-2026w15",
                poker_mtt_emission_epoch_budget_amount=100,
            ),
        )

        with pytest.raises(ValueError, match="budget_source_id"):
            await _build_window(service, reward_pool_amount=10)

        service_with_source = forecast_engine.ForecastMiningService(
            repo,
            forecast_engine.ForecastSettings(
                poker_mtt_budget_enforcement_enabled=True,
                poker_mtt_budget_source_id="treasury:poker-mtt:beta",
                poker_mtt_emission_epoch_id="epoch-2026w15",
                poker_mtt_emission_epoch_budget_amount=100,
            ),
        )
        with pytest.raises(ValueError, match="exceeds emission epoch budget"):
            await _build_window(service_with_source, reward_pool_amount=101)

    asyncio.run(scenario())


def test_daily_and_weekly_windows_share_one_emission_budget_slice():
    async def scenario():
        repo = FakeRepository()
        _seed_reward_ready_result(repo, tournament_id="mtt-budget-shared", miner_address="claw1budgetshared", total_score=1.0)
        service = forecast_engine.ForecastMiningService(
            repo,
            forecast_engine.ForecastSettings(
                poker_mtt_budget_enforcement_enabled=True,
                poker_mtt_budget_source_id="treasury:poker-mtt:beta",
                poker_mtt_emission_epoch_id="epoch-2026w15",
                poker_mtt_emission_epoch_budget_amount=100,
            ),
        )

        daily = await _build_window(service, reward_pool_amount=70)
        assert daily["total_reward_amount"] == 70
        with pytest.raises(ValueError, match="exceeds emission epoch budget"):
            await service.build_poker_mtt_reward_window(
                lane="poker_mtt_weekly",
                window_start_at=WINDOW_START,
                window_end_at=WINDOW_START + timedelta(days=7),
                reward_pool_amount=40,
                include_provisional=False,
                policy_bundle_version="poker_mtt_weekly_policy_v2",
                now=BUILD_NOW,
            )

        ledgers = await repo.list_poker_mtt_budget_ledgers(
            budget_source_id="treasury:poker-mtt:beta",
            emission_epoch_id="epoch-2026w15",
        )
        assert len(ledgers) == 1
        assert ledgers[0]["approved_amount"] == 70
        assert ledgers[0]["budget_root"].startswith("sha256:")

    asyncio.run(scenario())


def test_reward_window_uses_versioned_capped_top3_mean_not_lucky_single_max():
    async def scenario():
        repo = FakeRepository()
        for index, score in enumerate([0.7, 0.7, 0.7], start=1):
            _seed_reward_ready_result(
                repo,
                tournament_id=f"mtt-stable-{index}",
                miner_address="claw1stablegrinder",
                total_score=score,
            )
        for index, score in enumerate([1.0, 0.0, 0.0], start=1):
            _seed_reward_ready_result(
                repo,
                tournament_id=f"mtt-spike-{index}",
                miner_address="claw1luckyspike",
                total_score=score,
            )
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())

        window = await _build_window(service, reward_pool_amount=100)
        artifacts = await repo.list_artifacts_for_entity("reward_window", window["id"])
        projection = next(item for item in artifacts if item["kind"] == "poker_mtt_reward_window_projection")
        rows = sorted(projection["payload_json"]["miner_reward_rows"], key=lambda row: row["miner_address"])
        rewards = {row["miner_address"]: row["gross_reward_amount"] for row in rows}

        assert projection["payload_json"]["aggregation_policy_version"] == "capped_top3_mean_v1"
        assert rewards["claw1stablegrinder"] > rewards["claw1luckyspike"]

    asyncio.run(scenario())


def test_multiplier_snapshot_is_effective_only_for_next_window():
    async def scenario():
        repo = FakeRepository()
        miner_address = "claw1effectivemultiplier"
        _seed_reward_identity_miner(repo, miner_address)
        for index in range(16):
            repo._poker_mtt_results[f"old:{index}"] = {
                "id": f"old:{index}",
                "miner_address": miner_address,
                "eligible_for_multiplier": True,
                "total_score": 0.5,
                "updated_at": f"2026-04-09T00:{index:02d}:00Z",
            }
        _seed_final_ranking(repo, tournament_id="mtt-effective-multiplier", miner_address=miner_address, rank=1)
        await repo.save_poker_mtt_hidden_eval_entry(
            {
                "tournament_id": "mtt-effective-multiplier",
                "miner_address": miner_address,
                "final_ranking_id": _final_ranking_id("mtt-effective-multiplier", miner_address),
                "seed_assignment_id": "seed-effective",
                "baseline_sample_id": "baseline-effective",
                "hidden_eval_score": 0.0,
                "score_components_json": {},
                "evidence_root": "sha256:" + "c" * 64,
                "manifest_root": "sha256:" + "d" * 64,
                "policy_bundle_version": "poker_mtt_v1",
                "created_at": "2026-04-10T09:00:00Z",
                "updated_at": "2026-04-10T09:00:00Z",
            }
        )
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.apply_poker_mtt_results(
            tournament_id="mtt-effective-multiplier",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": miner_address,
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    "final_ranking_id": _final_ranking_id("mtt-effective-multiplier", miner_address),
                        "standing_snapshot_id": "snap:mtt-effective-multiplier",
                        "standing_snapshot_hash": "sha256:" + "b" * 64,
                        "evidence_root": "sha256:" + "c" * 64,
                        "evidence_state": "complete",
                        "locked_at": "2026-04-10T10:00:00Z",
                        "anchorable_at": "2026-04-10T10:00:00Z",
                    }
                ],
            completed_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
        )

        snapshots = await repo.list_poker_mtt_multiplier_snapshots(miner_address=miner_address)
        assert snapshots
        assert snapshots[0]["effective_window_start_at"] == "2026-04-11T00:00:00Z"
        assert snapshots[0]["effective_window_end_at"] == "2026-04-12T00:00:00Z"

    asyncio.run(scenario())


async def _build_window(service: forecast_engine.ForecastMiningService, *, reward_pool_amount: int) -> dict:
    return await service.build_poker_mtt_reward_window(
        lane="poker_mtt_daily",
        window_start_at=WINDOW_START,
        window_end_at=WINDOW_END,
        reward_pool_amount=reward_pool_amount,
        include_provisional=False,
        policy_bundle_version=POLICY_VERSION,
        now=BUILD_NOW,
    )


def _seed_reward_ready_result(
    repo: FakeRepository,
    *,
    tournament_id: str,
    miner_address: str,
    total_score: float,
) -> None:
    _seed_reward_identity_miner(repo, miner_address)
    _seed_final_ranking(repo, tournament_id=tournament_id, miner_address=miner_address, rank=1)
    result_id = f"poker_mtt_result:{tournament_id}:{miner_address}"
    repo._poker_mtt_results[result_id] = {
        "id": result_id,
        "tournament_id": tournament_id,
        "miner_address": miner_address,
        "economic_unit_id": miner_address,
        "rated_or_practice": "rated",
        "human_only": True,
        "field_size": 30,
        "final_rank": 1,
        "entry_number": 1,
        "reentry_count": 1,
        "finish_percentile": total_score,
        "tournament_result_score": total_score,
        "hidden_eval_score": 0.0,
        "consistency_input_score": 0.0,
        "total_score": total_score,
        "eligible_for_multiplier": True,
        "rolling_score": None,
        "multiplier_before": 1.0,
        "multiplier_after": 1.0,
        "evaluation_state": "final",
        "evaluation_version": "poker_mtt_v1",
        "rank_state": "ranked",
        "chip_delta": 1000.0,
        "final_ranking_id": _final_ranking_id(tournament_id, miner_address),
        "standing_snapshot_id": f"snap:{tournament_id}",
        "standing_snapshot_hash": "sha256:" + "b" * 64,
        "evidence_root": "sha256:" + "c" * 64,
        "evidence_state": "complete",
        "locked_at": "2026-04-10T10:00:00Z",
        "anchorable_at": "2026-04-10T10:00:00Z",
        "anchor_state": "unanchored",
        "anchor_payload_hash": None,
        "risk_flags": [],
        "no_multiplier_reason": None,
        "created_at": "2026-04-10T09:00:00Z",
        "updated_at": "2026-04-10T10:00:00Z",
    }


def _seed_final_ranking(repo: FakeRepository, *, tournament_id: str, miner_address: str, rank: int) -> None:
    repo._poker_mtt_final_rankings[_final_ranking_id(tournament_id, miner_address)] = {
        "id": _final_ranking_id(tournament_id, miner_address),
        "tournament_id": tournament_id,
        "source_mtt_id": tournament_id,
        "source_user_id": miner_address,
        "miner_address": miner_address,
        "economic_unit_id": miner_address,
        "member_id": f"{miner_address}:1",
        "entry_number": 1,
        "reentry_count": 1,
        "rank": rank,
        "rank_state": "ranked",
        "chip": 3000.0,
        "chip_delta": 1000.0,
        "died_time": None,
        "waiting_or_no_show": False,
        "bounty": 0.0,
        "defeat_num": 29,
        "field_size_policy": "exclude_waiting_no_show_from_reward_field_size",
        "standing_snapshot_id": f"snap:{tournament_id}",
        "standing_snapshot_hash": "sha256:" + "b" * 64,
        "evidence_root": "sha256:" + "c" * 64,
        "evidence_state": "complete",
        "policy_bundle_version": "poker_mtt_v1",
        "snapshot_found": True,
        "status": "alive",
        "player_name": miner_address,
        "room_id": "room-1",
        "start_chip": 3000.0,
        "stand_up_status": "",
        "source_rank": str(rank),
        "source_rank_numeric": True,
        "zset_score": 1000.0,
        "locked_at": "2026-04-10T10:00:00Z",
        "anchorable_at": "2026-04-10T10:00:00Z",
        "created_at": "2026-04-10T09:00:00Z",
        "updated_at": "2026-04-10T10:00:00Z",
    }


def _seed_reward_identity_miner(repo: FakeRepository, miner_address: str) -> None:
    repo._miners[miner_address] = {
        "address": miner_address,
        "name": miner_address,
        "registration_index": len(repo._miners) + 1,
        "public_key": "pubkey",
        "miner_version": "0.4.0",
        "status": "active",
        "economic_unit_id": miner_address,
        "total_rewards": 0,
        "held_rewards": 0,
        "forecast_commits": 0,
        "forecast_reveals": 0,
        "fast_task_opportunities": 0,
        "fast_task_misses": 0,
        "fast_window_start_at": "2026-04-01T00:00:00Z",
        "settled_tasks": 0,
        "correct_direction_count": 0,
        "edge_score_total": 0.0,
        "admission_state": "probation",
        "model_reliability": 1.0,
        "ops_reliability": 1.0,
        "arena_multiplier": 1.0,
        "poker_mtt_multiplier": 1.0,
        "poker_mtt_user_id": miner_address,
        "poker_mtt_auth_source": "donor_token",
        "poker_mtt_reward_bound": True,
        "poker_mtt_reward_bound_at": "2026-04-01T00:00:00Z",
        "poker_mtt_is_synthetic": False,
        "poker_mtt_identity_expires_at": None,
        "poker_mtt_identity_revoked_at": None,
        "public_rank": None,
        "public_elo": 1200,
        "created_at": "2026-04-01T00:00:00Z",
        "updated_at": "2026-04-01T00:00:00Z",
    }


def _final_ranking_id(tournament_id: str, miner_address: str) -> str:
    return f"poker_mtt_final_ranking:{tournament_id}:{miner_address}"
