from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine
from repository import FakeRepository


WINDOW_START = datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END = WINDOW_START + timedelta(days=1)
BUILD_NOW = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)


def test_reward_window_projection_writes_window_level_reputation_delta_root_and_lineage():
    async def scenario():
        repo = FakeRepository()
        miner_address = "claw1repdelta"
        _seed_reward_ready_result(repo, tournament_id="mtt-rep-delta", miner_address=miner_address, total_score=0.8)
        await repo.save_poker_mtt_rating_snapshot(
            {
                "id": "rating:claw1repdelta:pre-window",
                "miner_address": miner_address,
                "window_start_at": "2026-04-01T00:00:00Z",
                "window_end_at": "2026-04-10T00:00:00Z",
                "public_rating": 1234.5,
                "public_rank": 11,
                "confidence": 0.9,
                "policy_bundle_version": "poker_mtt_rating_v1",
                "created_at": "2026-04-10T00:00:00Z",
                "updated_at": "2026-04-10T00:00:00Z",
            }
        )
        await repo.save_poker_mtt_correction(
            {
                "id": "corr:rep-delta:1",
                "target_entity_type": "poker_mtt_result",
                "target_entity_id": f"poker_mtt_result:mtt-rep-delta:{miner_address}",
                "previous_root": "sha256:" + "1" * 64,
                "corrected_root": "sha256:" + "2" * 64,
                "reason": "late donor ranking correction",
                "operator_id": "admin:ops",
                "created_at": "2026-04-10T11:00:00Z",
            }
        )
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())

        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=WINDOW_START,
            window_end_at=WINDOW_END,
            reward_pool_amount=100,
            include_provisional=False,
            policy_bundle_version="poker_mtt_daily_policy_v2",
            now=BUILD_NOW,
        )
        artifacts = await repo.list_artifacts_for_entity("reward_window", reward_window["id"])
        projection = next(item for item in artifacts if item["kind"] == "poker_mtt_reward_window_projection")
        payload = projection["payload_json"]

        assert payload["reputation_delta_policy_version"] == "poker_mtt_reputation_delta_v1"
        assert payload["reputation_delta_rows_root"].startswith("sha256:")
        assert payload["reputation_delta_rows_count"] == 1
        row = payload["reputation_delta_rows_sample"][0]
        assert row["reward_window_id"] == reward_window["id"]
        assert row["settlement_batch_id"] == reward_window["settlement_batch_id"]
        assert row["policy_bundle_version"] == "poker_mtt_daily_policy_v2"
        assert row["prior_score_ref"] == "rating:claw1repdelta:pre-window"
        assert row["delta_cap"] == 10
        assert row["reason"] == "poker_mtt_window_performance"
        assert row["correction_count"] == 1
        assert row["correction_lineage_root"].startswith("sha256:")

    asyncio.run(scenario())


def test_settlement_anchor_includes_reputation_delta_root_without_reputation_chain_write():
    async def scenario():
        repo = FakeRepository()
        _seed_reward_ready_result(repo, tournament_id="mtt-rep-anchor", miner_address="claw1repanchor", total_score=1.0)
        service = forecast_engine.ForecastMiningService(
            repo,
            forecast_engine.ForecastSettings(poker_mtt_settlement_anchoring_enabled=True),
        )

        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=WINDOW_START,
            window_end_at=WINDOW_END,
            reward_pool_amount=100,
            include_provisional=False,
            now=BUILD_NOW,
        )
        batch = await repo.get_settlement_batch(reward_window["settlement_batch_id"])
        anchored = await service.retry_anchor_settlement_batch(
            batch["id"],
            now=datetime(2026, 4, 10, 12, 1, 0, tzinfo=timezone.utc),
        )

        payload = anchored["anchor_payload_json"]
        assert payload["reputation_delta_rows_root"].startswith("sha256:")
        assert payload["reputation_delta_window_roots"] == [
            {
                "reward_window_id": reward_window["id"],
                "reputation_delta_rows_root": payload["poker_projection_roots"][0]["reputation_delta_rows_root"],
            }
        ]
        assert not hasattr(repo, "save_reputation_delta")

    asyncio.run(scenario())


def test_single_tournament_result_does_not_write_reputation_delta_artifact():
    async def scenario():
        repo = FakeRepository()
        miner_address = "claw1repsingle"
        _seed_reward_identity_miner(repo, miner_address)
        _seed_final_ranking(repo, tournament_id="mtt-rep-single", miner_address=miner_address, rank=1)
        await repo.save_poker_mtt_hidden_eval_entry(
            {
                "tournament_id": "mtt-rep-single",
                "miner_address": miner_address,
                "final_ranking_id": _final_ranking_id("mtt-rep-single", miner_address),
                "seed_assignment_id": "seed-single",
                "baseline_sample_id": "baseline-single",
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
            tournament_id="mtt-rep-single",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": miner_address,
                    "final_rank": 1,
                    "evaluation_state": "final",
                    "final_ranking_id": _final_ranking_id("mtt-rep-single", miner_address),
                    "standing_snapshot_id": "snap:mtt-rep-single",
                    "standing_snapshot_hash": "sha256:" + "b" * 64,
                    "evidence_root": "sha256:" + "c" * 64,
                    "evidence_state": "complete",
                    "locked_at": "2026-04-10T10:00:00Z",
                    "anchorable_at": "2026-04-10T10:00:00Z",
                }
            ],
            completed_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
        )

        artifacts = list(repo._artifacts.values())
        assert all("reputation_delta" not in item.get("kind", "") for item in artifacts)

    asyncio.run(scenario())


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
