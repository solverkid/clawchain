from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import chain_adapter
import forecast_engine
import poker_mtt_history
import poker_mtt_hud
from repository import FakeRepository


def test_poker_mtt_phase2_beta_gate_runs_evidence_to_anchor_query_confirmation():
    async def scenario():
        tournament_id = "mtt-phase2-e2e"
        miners = ["claw1phase2alice", "claw1phase2bob"]
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(
            repo,
            forecast_engine.ForecastSettings(
                poker_mtt_settlement_anchoring_enabled=True,
                poker_mtt_projection_artifact_page_size=1,
            ),
        )

        for miner_address in miners:
            await service.register_miner(
                address=miner_address,
                name=miner_address,
                public_key="pubkey",
                miner_version="0.4.0",
            )

        hand_event = completed_hand_event(tournament_id, miners)
        ingest = await service.ingest_poker_mtt_hand_event(
            hand_event,
            now=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )
        assert ingest["state"] == "inserted"

        for rank, miner_address in enumerate(miners, start=1):
            await repo.save_poker_mtt_final_ranking(final_ranking_row(tournament_id, miner_address, rank=rank))

        hud_store = poker_mtt_hud.InMemoryHUDHotStore()
        projected_hud = hud_store.project_hand(hand_event, settings=poker_mtt_hud.HUDProjectionSettings(enabled=True))
        assert projected_hud.state == "projected"
        for row in hud_store.snapshot_rows(tournament_id=tournament_id):
            await repo.save_poker_mtt_hud_snapshot(
                {
                    **row,
                    "policy_bundle_version": "poker_mtt_v1",
                    "created_at": "2026-04-10T09:00:10Z",
                    "updated_at": "2026-04-10T09:00:10Z",
                }
            )
        for miner_address in miners:
            await repo.save_poker_mtt_hud_snapshot(
                {
                    "tournament_id": tournament_id,
                    "miner_address": miner_address,
                    "hud_window": "long_term",
                    "hands_seen": 100,
                    "itm_count": 18,
                    "win_count": 3 if miner_address == miners[0] else 1,
                    "policy_bundle_version": "poker_mtt_v1",
                    "created_at": "2026-04-10T09:00:15Z",
                    "updated_at": "2026-04-10T09:00:15Z",
                }
            )

        first_evidence = await service.build_poker_mtt_evidence_manifests(
            tournament_id=tournament_id,
            policy_bundle_version="poker_mtt_v1",
            accepted_degraded_kinds=["poker_mtt_hidden_eval_manifest"],
            now=datetime(2026, 4, 10, 9, 5, 0, tzinfo=timezone.utc),
        )
        assert first_evidence["evidence_state"] == "accepted_degraded"

        hidden_eval = await service.finalize_poker_mtt_hidden_eval(
            tournament_id=tournament_id,
            policy_bundle_version="poker_mtt_v1",
            seed_assignment_id=f"hidden-seed:{tournament_id}",
            baseline_sample_id="baseline-sample:phase2",
            entries=[
                {
                    "miner_address": miners[0],
                    "final_ranking_id": final_ranking_id(tournament_id, miners[0]),
                    "hidden_eval_score": 0.2,
                    "score_components_json": {"shadow_eval": "winner"},
                    "evidence_root": first_evidence["evidence_root"],
                },
                {
                    "miner_address": miners[1],
                    "final_ranking_id": final_ranking_id(tournament_id, miners[1]),
                    "hidden_eval_score": 0.0,
                    "score_components_json": {"shadow_eval": "runner_up"},
                    "evidence_root": first_evidence["evidence_root"],
                },
            ],
            now=datetime(2026, 4, 10, 9, 6, 0, tzinfo=timezone.utc),
        )
        assert hidden_eval["manifest"]["evidence_state"] == "complete"

        complete_evidence = await service.build_poker_mtt_evidence_manifests(
            tournament_id=tournament_id,
            policy_bundle_version="poker_mtt_v1",
            now=datetime(2026, 4, 10, 9, 7, 0, tzinfo=timezone.utc),
        )
        assert complete_evidence["evidence_state"] == "complete"

        for rank, miner_address in enumerate(miners, start=1):
            await repo.save_poker_mtt_final_ranking(
                {
                    **final_ranking_row(tournament_id, miner_address, rank=rank),
                    "evidence_root": complete_evidence["evidence_root"],
                    "evidence_state": "complete",
                    "updated_at": "2026-04-10T09:07:00Z",
                }
            )

        final_projection = await service.project_poker_mtt_final_rankings(
            tournament_id=tournament_id,
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            locked_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
        )
        assert all(item["eligible_for_multiplier"] is True for item in final_projection["items"])
        assert all(item["locked_at"] == "2026-04-10T10:00:00Z" for item in final_projection["items"])

        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
            reward_pool_amount=100,
            include_provisional=False,
            policy_bundle_version="poker_mtt_daily_policy_v2",
            now=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert reward_window["artifact_page_count"] == 2
        projection_artifacts = await repo.list_artifacts_for_entity("reward_window", reward_window["id"])
        assert len([item for item in projection_artifacts if item["kind"] == "poker_mtt_reward_window_projection_page"]) == 2

        settlement_batch = (await repo.list_settlement_batches())[0]
        ready_batch = await service.retry_anchor_settlement_batch(
            settlement_batch["id"],
            now=datetime(2026, 4, 10, 12, 1, 0, tzinfo=timezone.utc),
        )
        assert len(ready_batch["anchor_payload_json"]["miner_reward_rows"]) == 2
        assert ready_batch["anchor_payload_json"]["miner_reward_rows_root"].startswith("sha256:")

        submitted_batch = await service.submit_anchor_job(
            ready_batch["id"],
            now=datetime(2026, 4, 10, 12, 2, 0, tzinfo=timezone.utc),
        )
        tx_plan = await service.build_chain_tx_plan(
            submitted_batch["anchor_job_id"],
            now=datetime(2026, 4, 10, 12, 3, 0, tzinfo=timezone.utc),
        )
        assert tx_plan["future_msg"]["value"]["settlement_batch_id"] == ready_batch["id"]
        assert tx_plan["future_msg"]["value"]["canonical_root"] == ready_batch["canonical_root"]

        async def fake_typed_broadcaster(plan, now):  # noqa: ANN001
            return {
                "tx_hash": "ABC123PHASE2",
                "broadcast_at": forecast_engine.isoformat_z(now),
                "broadcast_method": "typed_msg",
                "account_number": 1,
                "sequence": 7,
                "attempt_count": 1,
            }

        service.chain_typed_broadcaster = fake_typed_broadcaster
        broadcast = await service.broadcast_chain_tx_typed(
            submitted_batch["anchor_job_id"],
            now=datetime(2026, 4, 10, 12, 4, 0, tzinfo=timezone.utc),
        )
        assert broadcast["broadcast_method"] == "typed_msg"

        query_adapter = chain_adapter.FakeSettlementChainAdapter(
            query_response={
                "anchor": {
                    "settlement_batch_id": ready_batch["id"],
                    "anchor_job_id": submitted_batch["anchor_job_id"],
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
            }
        )

        async def fake_chain_confirmer(tx_hash, now):  # noqa: ANN001
            query_result = chain_adapter.confirm_settlement_anchor_response(
                query_response=query_adapter.query_response,
                settlement_batch_id=ready_batch["id"],
                canonical_root=ready_batch["canonical_root"],
                anchor_payload_hash=ready_batch["anchor_payload_hash"],
                tx_receipt={"confirmation_status": "confirmed", "tx_hash": tx_hash},
                broadcast_method="typed_msg",
            )
            return {
                **query_result,
                "height": 88,
                "code": 0,
                "raw_log": "",
                "confirmed_at": forecast_engine.isoformat_z(now),
            }

        service.chain_tx_confirmer = fake_chain_confirmer
        confirmation = await service.confirm_anchor_job_on_chain(
            submitted_batch["anchor_job_id"],
            now=datetime(2026, 4, 10, 12, 5, 0, tzinfo=timezone.utc),
        )
        anchored_batch = await repo.get_settlement_batch(ready_batch["id"])

        assert confirmation["chain_confirmation_status"] == "confirmed"
        assert anchored_batch["state"] == "anchored"

    asyncio.run(scenario())


def final_ranking_id(tournament_id: str, miner_address: str) -> str:
    return f"poker_mtt_final_ranking:{tournament_id}:{miner_address}"


def final_ranking_row(tournament_id: str, miner_address: str, *, rank: int) -> dict:
    return {
        "id": final_ranking_id(tournament_id, miner_address),
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
        "chip": 9000.0 - (rank * 1000.0),
        "chip_delta": 6000.0 - (rank * 1000.0),
        "died_time": None,
        "waiting_or_no_show": False,
        "bounty": 0.0,
        "defeat_num": max(0, 30 - rank),
        "field_size_policy": "exclude_waiting_no_show_from_reward_field_size",
        "standing_snapshot_id": f"poker_mtt_standing_snapshot:{tournament_id}:locked",
        "standing_snapshot_hash": "sha256:" + "a" * 64,
        "evidence_root": None,
        "evidence_state": "pending",
        "policy_bundle_version": "poker_mtt_v1",
        "snapshot_found": True,
        "status": "alive" if rank == 1 else "died",
        "player_name": miner_address,
        "room_id": "room-1",
        "start_chip": 3000.0,
        "stand_up_status": "",
        "source_rank": str(rank),
        "source_rank_numeric": True,
        "zset_score": 9000.0 - (rank * 1000.0),
        "created_at": "2026-04-10T09:00:00Z",
        "updated_at": "2026-04-10T09:00:00Z",
    }


def completed_hand_event(tournament_id: str, miners: list[str]) -> dict:
    return poker_mtt_history.build_hand_completed_event(
        tournament_id=tournament_id,
        table_id="table-1",
        hand_no=1,
        version=1,
        payload={
            "players": [
                {"miner_address": miners[0], "source_user_id": "alice"},
                {"miner_address": miners[1], "source_user_id": "bob"},
            ],
            "actions": [
                {"miner_address": miners[1], "street": "preflop", "action": "call"},
                {"miner_address": miners[0], "street": "preflop", "action": "raise", "raise_number": 1},
                {"miner_address": miners[0], "street": "preflop", "action": "raise", "raise_number": 3},
                {"miner_address": miners[1], "street": "flop", "action": "fold"},
            ],
        },
        source={
            "transport": "rocketmq",
            "topic": "POKER_RECORD_TOPIC",
            "message_id": f"msg-{tournament_id}-1",
            "biz_id": f"biz-{tournament_id}-1",
            "record_type": "recordType",
            "source_mtt_id": tournament_id,
            "source_room_id": "table-1",
        },
    )
