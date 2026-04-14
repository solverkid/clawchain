from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

from repository import FakeRepository
import schemas


def test_fake_repository_upserts_and_lists_final_rankings_by_tournament_and_window():
    async def scenario():
        repo = FakeRepository()
        first = final_ranking_row(
            row_id="poker_mtt_final_ranking:mtt-1:7:1",
            tournament_id="mtt-1",
            miner_address="claw1miner7",
            rank=2,
            created_at="2026-04-10T09:00:00Z",
        )
        second = final_ranking_row(
            row_id="poker_mtt_final_ranking:mtt-1:8:1",
            tournament_id="mtt-1",
            miner_address="claw1miner8",
            rank=1,
            created_at="2026-04-10T09:00:01Z",
        )

        await repo.save_poker_mtt_final_ranking(first)
        await repo.save_poker_mtt_final_ranking(second)
        updated = await repo.save_poker_mtt_final_ranking({**first, "rank": 3, "updated_at": "2026-04-10T09:05:00Z"})

        assert updated["rank"] == 3
        assert (await repo.get_poker_mtt_final_ranking(first["id"]))["rank"] == 3
        assert [
            row["id"] for row in await repo.list_poker_mtt_final_rankings_for_tournament("mtt-1")
        ] == [
            second["id"],
            first["id"],
        ]
        assert [
            row["id"]
            for row in await repo.list_poker_mtt_final_rankings_for_window(
                "2026-04-10T00:00:00Z",
                "2026-04-11T00:00:00Z",
            )
        ] == [
            first["id"],
            second["id"],
        ]
        assert await repo.list_poker_mtt_results() == []

    asyncio.run(scenario())


def test_fake_repository_preserves_result_entry_projection_fields():
    async def scenario():
        repo = FakeRepository()
        entry = await repo.save_poker_mtt_result(
            {
                "id": "poker_mtt:mtt-1:claw1miner7",
                "tournament_id": "mtt-1",
                "miner_address": "claw1miner7",
                "rated_or_practice": "rated",
                "human_only": True,
                "field_size": 30,
                "final_rank": 1,
                "finish_percentile": 1.0,
                "tournament_result_score": 1.0,
                "hidden_eval_score": 0.3,
                "consistency_input_score": 0.2,
                "total_score": 0.86,
                "eligible_for_multiplier": True,
                "rolling_score": None,
                "multiplier_before": 1.0,
                "multiplier_after": 1.0,
                "evaluation_state": "final",
                "evaluation_version": "poker_mtt_v1",
                "economic_unit_id": "claw1miner7",
                "entry_number": 2,
                "reentry_count": 2,
                "final_ranking_id": "poker_mtt_final_ranking:mtt-1:7:2",
                "standing_snapshot_id": "poker_mtt_standing_snapshot:mtt-1:abc",
                "standing_snapshot_hash": "sha256:abc",
                "evidence_root": "sha256:evidence",
                "evidence_state": "complete",
                "locked_at": "2026-04-10T10:00:00Z",
                "anchor_state": "unanchored",
                "anchor_payload_hash": None,
                "risk_flags": ["duplicate_entry_collapsed"],
                "no_multiplier_reason": None,
                "created_at": "2026-04-10T09:00:00Z",
                "updated_at": "2026-04-10T10:00:00Z",
            }
        )

        assert entry["economic_unit_id"] == "claw1miner7"
        assert entry["reentry_count"] == 2
        assert entry["standing_snapshot_id"] == "poker_mtt_standing_snapshot:mtt-1:abc"
        assert entry["evidence_state"] == "complete"
        assert entry["locked_at"] == "2026-04-10T10:00:00Z"
        assert entry["risk_flags"] == ["duplicate_entry_collapsed"]

    asyncio.run(scenario())


def test_final_ranking_projection_request_schema_accepts_canonical_rows():
    row = schemas.PokerMTTFinalRankingRow(**final_ranking_row())
    request = schemas.ApplyPokerMTTFinalRankingProjectionRequest(
        tournament_id="mtt-1",
        rated_or_practice="rated",
        human_only=True,
        field_size=30,
        policy_bundle_version="poker_mtt_v1",
        rows=[row],
    )

    assert request.rows[0].standing_snapshot_id == "poker_mtt_standing_snapshot:mtt-1:abc"
    assert request.rows[0].rank == 1
    assert request.rows[0].rank_state == "ranked"


def final_ranking_row(
    *,
    row_id: str = "poker_mtt_final_ranking:mtt-1:7:1",
    tournament_id: str = "mtt-1",
    miner_address: str = "claw1miner7",
    rank: int | None = 1,
    created_at: str = "2026-04-10T09:00:00Z",
) -> dict:
    return {
        "id": row_id,
        "tournament_id": tournament_id,
        "source_mtt_id": tournament_id,
        "source_user_id": "7",
        "miner_address": miner_address,
        "economic_unit_id": miner_address,
        "member_id": "7:1",
        "entry_number": 1,
        "reentry_count": 1,
        "rank": rank,
        "rank_state": "ranked" if rank is not None else "waiting_no_show",
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
        "evidence_state": "complete",
        "policy_bundle_version": "poker_mtt_v1",
        "snapshot_found": True,
        "status": "alive",
        "player_name": "miner 7",
        "room_id": "room-1",
        "start_chip": 3000.0,
        "stand_up_status": "",
        "source_rank": "1" if rank is not None else "",
        "source_rank_numeric": rank is not None,
        "zset_score": 9000.0,
        "created_at": created_at,
        "updated_at": created_at,
    }
