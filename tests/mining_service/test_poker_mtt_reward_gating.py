from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine
from repository import FakeRepository


def test_final_ranking_projection_does_not_lock_incomplete_evidence():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1pendingevidence",
            name="pending-evidence",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await repo.save_poker_mtt_final_ranking(
            final_ranking_row(
                tournament_id="mtt-pending-evidence",
                miner_address="claw1pendingevidence",
                evidence_state="pending",
            )
        )

        projection = await service.project_poker_mtt_final_rankings(
            tournament_id="mtt-pending-evidence",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            locked_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
        )
        stored = (await repo.list_poker_mtt_results_for_miner("claw1pendingevidence"))[0]

        assert projection["items"][0]["eligible_for_multiplier"] is False
        assert stored["evaluation_state"] == "final"
        assert stored["evidence_state"] == "pending"
        assert stored["locked_at"] is None
        assert stored["no_multiplier_reason"] == "evidence_not_reward_ready"
        assert "evidence_not_reward_ready" in stored["risk_flags"]

        try:
            await service.build_poker_mtt_reward_window(
                lane="poker_mtt_daily",
                window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
                window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
                reward_pool_amount=100,
                include_provisional=False,
                now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
            )
        except ValueError as exc:
            assert str(exc) == "no poker mtt results found for reward window"
        else:
            raise AssertionError("reward window should reject unlocked final rows")

    asyncio.run(scenario())


def test_reward_window_membership_uses_locked_at_not_created_at():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1lockedpoker",
            name="locked-poker",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await repo.save_poker_mtt_final_ranking(
            final_ranking_row(
                tournament_id="mtt-locked",
                miner_address="claw1lockedpoker",
                created_at="2026-04-08T09:00:00Z",
                evidence_state="complete",
            )
        )

        await service.project_poker_mtt_final_rankings(
            tournament_id="mtt-locked",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            locked_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
        )

        try:
            await service.build_poker_mtt_reward_window(
                lane="poker_mtt_daily",
                window_start_at=datetime(2026, 4, 8, 0, 0, 0, tzinfo=timezone.utc),
                window_end_at=datetime(2026, 4, 9, 0, 0, 0, tzinfo=timezone.utc),
                reward_pool_amount=100,
                include_provisional=False,
                now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
            )
        except ValueError as exc:
            assert str(exc) == "no poker mtt results found for reward window"
        else:
            raise AssertionError("created_at-only membership should not include locked results")

        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
            reward_pool_amount=100,
            include_provisional=False,
            now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
        )

        stored = (await repo.list_poker_mtt_results_for_miner("claw1lockedpoker"))[0]
        assert stored["locked_at"] == "2026-04-10T10:00:00Z"
        assert stored["eligible_for_multiplier"] is True
        assert stored["multiplier_before"] == 1.0
        assert stored["multiplier_after"] == 1.0
        assert reward_window["task_run_ids"] == ["mtt-locked"]
        assert reward_window["submission_count"] == 1

    asyncio.run(scenario())


def test_legacy_apply_requires_final_ranking_refs_before_multiplier():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1missingrefs",
            name="missing-refs",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        for index in range(16):
            await service.apply_poker_mtt_results(
                tournament_id=f"mtt-missing-refs-{index}",
                rated_or_practice="rated",
                human_only=True,
                field_size=30,
                policy_bundle_version="poker_mtt_v1",
                results=[
                    {
                        "miner_id": "claw1missingrefs",
                        "final_rank": 1,
                        "tournament_result_score": 1.0,
                        "hidden_eval_score": 0.0,
                        "consistency_input_score": 0.0,
                        "evaluation_state": "final",
                        "evidence_state": "complete",
                        "evidence_root": f"sha256:evidence:{index}",
                        "locked_at": "2026-04-10T10:00:00Z",
                    }
                ],
                completed_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
            )

        miner = await repo.get_miner("claw1missingrefs")
        stored = (await repo.list_poker_mtt_results_for_miner("claw1missingrefs"))[0]

        assert miner["poker_mtt_multiplier"] == 1.0
        assert stored["eligible_for_multiplier"] is False
        assert stored["no_multiplier_reason"] == "missing_final_ranking_ref"

    asyncio.run(scenario())


def final_ranking_row(
    *,
    tournament_id: str,
    miner_address: str,
    created_at: str = "2026-04-10T09:00:00Z",
    evidence_state: str = "complete",
    rank_state: str = "ranked",
) -> dict:
    rank = 1 if rank_state == "ranked" else None
    return {
        "id": f"poker_mtt_final_ranking:{tournament_id}:{miner_address}",
        "tournament_id": tournament_id,
        "source_mtt_id": tournament_id,
        "source_user_id": miner_address,
        "miner_address": miner_address,
        "economic_unit_id": miner_address,
        "member_id": f"{miner_address}:1",
        "entry_number": 1,
        "reentry_count": 1,
        "rank": rank,
        "rank_state": rank_state,
        "chip": 9000.0,
        "chip_delta": 6000.0,
        "died_time": None,
        "waiting_or_no_show": rank is None,
        "bounty": 0.0,
        "defeat_num": 0,
        "field_size_policy": "exclude_waiting_no_show_from_reward_field_size",
        "standing_snapshot_id": f"poker_mtt_standing_snapshot:{tournament_id}:abc",
        "standing_snapshot_hash": "sha256:abc",
        "evidence_root": "sha256:evidence",
        "evidence_state": evidence_state,
        "policy_bundle_version": "poker_mtt_v1",
        "snapshot_found": True,
        "status": "alive",
        "player_name": miner_address,
        "room_id": "room-1",
        "start_chip": 3000.0,
        "stand_up_status": "",
        "source_rank": "1" if rank is not None else "",
        "source_rank_numeric": rank is not None,
        "zset_score": 9000.0,
        "created_at": created_at,
        "updated_at": created_at,
    }
