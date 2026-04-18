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


LOCKED_AT = datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc)
WINDOW_START = datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_BUILD_AT = datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc)


def _final_ranking_row(tournament_id: str, miner_address: str, *, final_rank: int = 1) -> dict:
    locked_at = "2026-04-10T10:00:00Z"
    final_ranking_id = f"poker_mtt_final_ranking:{tournament_id}:{miner_address}"
    return {
        "id": final_ranking_id,
        "tournament_id": tournament_id,
        "source_mtt_id": tournament_id,
        "source_user_id": miner_address,
        "miner_address": miner_address,
        "economic_unit_id": miner_address,
        "member_id": f"{miner_address}:1",
        "entry_number": 1,
        "reentry_count": 1,
        "rank": final_rank,
        "rank_state": "ranked",
        "chip": 3000.0 + float(30 - final_rank),
        "chip_delta": float(30 - final_rank),
        "died_time": None,
        "waiting_or_no_show": False,
        "bounty": 0.0,
        "defeat_num": 0,
        "field_size_policy": "exclude_waiting_no_show_from_reward_field_size",
        "standing_snapshot_id": f"poker_mtt_standing_snapshot:{tournament_id}:abc",
        "standing_snapshot_hash": f"sha256:snapshot:{tournament_id}",
        "evidence_root": f"sha256:evidence:{tournament_id}:{miner_address}",
        "evidence_state": "complete",
        "policy_bundle_version": "poker_mtt_v1",
        "snapshot_found": True,
        "status": "completed",
        "player_name": miner_address,
        "room_id": "room-1",
        "start_chip": 3000.0,
        "stand_up_status": "",
        "source_rank": str(final_rank),
        "source_rank_numeric": True,
        "zset_score": 3000.0 + float(30 - final_rank),
        "locked_at": locked_at,
        "anchorable_at": locked_at,
        "created_at": locked_at,
        "updated_at": locked_at,
    }


async def _finalize_hidden_eval(
    service: forecast_engine.ForecastMiningService,
    *,
    tournament_id: str,
    miner_address: str,
) -> None:
    await service.finalize_poker_mtt_hidden_eval(
        tournament_id=tournament_id,
        policy_bundle_version="poker_mtt_v1",
        seed_assignment_id=f"seed:{tournament_id}",
        baseline_sample_id=None,
        entries=[
            {
                "miner_address": miner_address,
                "final_ranking_id": f"poker_mtt_final_ranking:{tournament_id}:{miner_address}",
                "hidden_eval_score": 0.0,
                "score_components_json": {"fixture": True},
                "evidence_root": f"sha256:evidence:{tournament_id}:{miner_address}",
            }
        ],
        now=LOCKED_AT,
    )


async def _project_ready_result(
    repo: FakeRepository,
    service: forecast_engine.ForecastMiningService,
    *,
    tournament_id: str,
    miner_address: str,
) -> dict:
    await repo.save_poker_mtt_final_ranking(_final_ranking_row(tournament_id, miner_address))
    await _finalize_hidden_eval(service, tournament_id=tournament_id, miner_address=miner_address)
    return await service.project_poker_mtt_final_rankings(
        tournament_id=tournament_id,
        rated_or_practice="rated",
        human_only=True,
        field_size=30,
        policy_bundle_version="poker_mtt_v1",
        locked_at=LOCKED_AT,
    )


async def _build_daily_window(service: forecast_engine.ForecastMiningService) -> dict:
    return await service.build_poker_mtt_reward_window(
        lane="poker_mtt_daily",
        window_start_at=WINDOW_START,
        window_end_at=WINDOW_END,
        reward_pool_amount=100,
        include_provisional=False,
        policy_bundle_version="poker_mtt_v1",
        now=WINDOW_BUILD_AT,
    )


def test_local_harness_identity_can_join_but_never_becomes_reward_bound():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1local-7",
            name="local-harness",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        projection = await _project_ready_result(
            repo,
            service,
            tournament_id="mtt-local-harness",
            miner_address="claw1local-7",
        )
        stored = (await repo.list_poker_mtt_results_for_miner("claw1local-7"))[0]

        assert projection["items"][0]["eligible_for_multiplier"] is False
        assert projection["items"][0]["no_multiplier_reason"] == "reward_identity_not_bound"
        assert stored["locked_at"] is None
        assert stored["anchorable_at"] is None
        assert "reward_identity_not_bound" in stored["risk_flags"]

        try:
            await _build_daily_window(service)
        except ValueError as exc:
            assert str(exc) == "no poker mtt results found for reward window"
        else:
            raise AssertionError("synthetic local harness identity must not enter reward windows")

    asyncio.run(scenario())


def test_projection_rejects_miner_missing_durable_reward_identity():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await repo.register_miner(
            {
                "address": "claw1missingidentity",
                "name": "missing-identity",
                "public_key": "pubkey",
                "status": "active",
                "economic_unit_id": "eu:missing-identity",
                "public_elo": 1200,
                "poker_mtt_multiplier": 1.0,
                "created_at": "2026-04-10T09:00:00Z",
                "updated_at": "2026-04-10T09:00:00Z",
            }
        )

        projection = await _project_ready_result(
            repo,
            service,
            tournament_id="mtt-missing-identity",
            miner_address="claw1missingidentity",
        )
        stored = (await repo.list_poker_mtt_results_for_miner("claw1missingidentity"))[0]

        assert projection["items"][0]["eligible_for_multiplier"] is False
        assert stored["no_multiplier_reason"] == "missing_reward_identity"
        assert stored["locked_at"] is None
        assert "missing_reward_identity" in stored["risk_flags"]

    asyncio.run(scenario())


def test_reward_window_skips_revoked_identity_after_projection():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1revokedidentity",
            name="revoked-identity",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        projection = await _project_ready_result(
            repo,
            service,
            tournament_id="mtt-revoked-identity",
            miner_address="claw1revokedidentity",
        )
        assert projection["items"][0]["eligible_for_multiplier"] is True

        await repo.update_miner(
            "claw1revokedidentity",
            {
                "poker_mtt_identity_revoked_at": "2026-04-10T11:00:00Z",
                "updated_at": "2026-04-10T11:00:00Z",
            },
        )

        try:
            await _build_daily_window(service)
        except ValueError as exc:
            assert str(exc) == "no poker mtt results found for reward window"
        else:
            raise AssertionError("revoked reward identity must not enter reward windows")

    asyncio.run(scenario())


def test_reward_window_skips_expired_identity_after_projection():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1expiredidentity",
            name="expired-identity",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        projection = await _project_ready_result(
            repo,
            service,
            tournament_id="mtt-expired-identity",
            miner_address="claw1expiredidentity",
        )
        assert projection["items"][0]["eligible_for_multiplier"] is True

        await repo.update_miner(
            "claw1expiredidentity",
            {
                "poker_mtt_identity_expires_at": "2026-04-10T23:59:00Z",
                "updated_at": "2026-04-10T23:59:00Z",
            },
        )

        try:
            await _build_daily_window(service)
        except ValueError as exc:
            assert str(exc) == "no poker mtt results found for reward window"
        else:
            raise AssertionError("expired reward identity must not enter reward windows")

    asyncio.run(scenario())
