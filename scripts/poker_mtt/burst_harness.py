#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
SCRIPT_DIR = ROOT / "scripts" / "poker_mtt"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import forecast_engine
import poker_mtt_evidence
import mq_projector
import release_evidence_replay as replay
import runtime_projection as runtime
from repository import FakeRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a donor-shaped synthetic burst harness for poker MTT completed-hand ingest and settlement prep.",
    )
    parser.add_argument("--tournament-id", default="burst-mtt-1")
    parser.add_argument("--user-count", type=int, default=20_000)
    parser.add_argument("--table-count", type=int, default=2_000)
    parser.add_argument("--hands-per-table", type=int, default=1)
    parser.add_argument("--event-batch-size", type=int, default=500)
    parser.add_argument("--reward-pool-amount", type=int, default=100_000)
    parser.add_argument("--summary-file", type=Path)
    return parser.parse_args()


def isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_record_message(*, biz_id: str, room_id: str, seq: int, version: int, begin_time: int, end_time: int) -> dict:
    return {
        "bizID": biz_id,
        "record": json.dumps(
            {
                "roomID": room_id,
                "seq": seq,
                "version": version,
                "beginTime": begin_time,
                "endTime": end_time,
                "recordType": "recordType",
                "record": json.dumps(
                    {
                        "gameType": "mtt",
                        "subGameType": "token",
                        "tableId": room_id,
                    }
                ),
            }
        ),
    }


def _build_standup_message(*, biz_id: str, game_id: str, user_id: str, hub_sequence: int) -> dict:
    return {
        "bizID": biz_id,
        "gameID": game_id,
        "IDType": "mtt",
        "subIDType": "token",
        "userID": user_id,
        "hubSequence": hub_sequence,
    }


def build_burst_messages(*, table_count: int, hands_per_table: int) -> list[tuple[str, dict]]:
    messages: list[tuple[str, dict]] = []
    epoch_base = 1710000000
    for table_index in range(table_count):
        room_id = f"table-{table_index:04d}"
        for hand_index in range(hands_per_table):
            seq = hand_index + 1
            begin_time = epoch_base + (table_index * 90) + (hand_index * 15)
            end_time = begin_time + 10
            messages.append(
                (
                    mq_projector.COMPLETED_HAND_TOPIC,
                    _build_record_message(
                        biz_id=f"record-{table_index}-{seq}",
                        room_id=room_id,
                        seq=seq,
                        version=seq,
                        begin_time=begin_time,
                        end_time=end_time,
                    ),
                )
            )
        messages.append(
            (
                mq_projector.STANDUP_TOPIC,
                _build_standup_message(
                    biz_id=f"standup-{table_index}",
                    game_id=room_id,
                    user_id=f"user-{table_index * 10}",
                    hub_sequence=hands_per_table,
                ),
            )
        )
    return messages


async def _build_evidence_summary(
    *,
    repo,
    tournament_id: str,
    policy_bundle_version: str,
    accepted_event_count: int,
    generated_at: datetime,
) -> dict:
    hand_rows = await repo.list_poker_mtt_hand_events_for_tournament(tournament_id)
    checkpoints = await repo.list_poker_mtt_mq_checkpoints(tournament_id=tournament_id)
    hand_manifest = poker_mtt_evidence.build_hand_history_manifest(
        tournament_id=tournament_id,
        rows=hand_rows,
        policy_bundle_version=policy_bundle_version,
        generated_at=generated_at,
    )
    checkpoint_manifest = poker_mtt_evidence.build_consumer_checkpoint_manifest(
        tournament_id=tournament_id,
        rows=checkpoints,
        policy_bundle_version=policy_bundle_version,
        generated_at=generated_at,
    )
    freshness_candidates = [
        row.get("updated_at")
        for row in [*hand_rows, *checkpoints]
        if row.get("updated_at") is not None
    ]
    latest_freshness_at = max(freshness_candidates) if freshness_candidates else None
    return {
        "accepted_event_count": accepted_event_count,
        "checkpoint_count": len(checkpoints),
        "hand_history_evidence_root": hand_manifest["manifest_root"],
        "consumer_checkpoint_root": checkpoint_manifest["manifest_root"],
        "latest_freshness_at": latest_freshness_at,
    }


def _build_synthetic_runtime_summary(*, tournament_id: str, user_count: int) -> tuple[dict, dict]:
    standings = []
    for index in range(user_count):
        rank = index + 1
        standings.append(
            {
                "member_id": f"user-{index}:1",
                "user_id": f"{index}",
                "entry_number": 1,
                "display_rank": rank,
                "payout_rank": rank,
                "player_name": f"user-{index}",
                "room_id": f"table-{index % max(1, min(user_count, 10)):04d}",
                "start_chip": 6000,
                "end_chip": max(0, 6000 - (rank * 3)),
                "died_time": "0" if rank == 1 else str(1710000000 + rank),
                "stand_up_status": None if rank == 1 else "standUpDieStatus",
                "snapshot_found": True,
            }
        )
    summary = {
        "mtt_id": tournament_id,
        "standings": {"standings": standings},
    }
    evidence = {
        "captured_at": "2026-04-20T08:00:00Z",
        "mtt_id": tournament_id,
        "connections": {
            "joined_users": user_count,
            "sent_action_total": user_count * 4,
            "timeout_no_action_total": user_count // 3,
        },
        "room_assignments": {
            "unique_rooms": max(1, min(user_count, 2000)),
        },
        "final_standings": {
            "winner": {"user_id": "0", "payout_rank": 1},
            "runner_up": {"user_id": "1", "payout_rank": 2},
        },
        "log_truth": {
            "main_log": {"roomID_not_correct": 0, "onLooker_action": 0},
        },
    }
    return summary, evidence


async def run_burst_harness(
    *,
    tournament_id: str,
    user_count: int,
    table_count: int,
    hands_per_table: int,
    event_batch_size: int,
    reward_pool_amount: int,
) -> dict:
    repo = FakeRepository()
    completed_at = datetime(2026, 4, 20, 8, 0, 0, tzinfo=timezone.utc)

    async def fake_typed_broadcaster(plan, now):  # noqa: ANN001
        return {
            "tx_hash": "TYPED-BURST-" + tournament_id,
            "code": 0,
            "raw_log": "",
            "memo": plan["fallback_memo"],
            "broadcast_at": forecast_engine.isoformat_z(now),
            "account_number": 0,
            "sequence": 1,
            "attempt_count": 1,
            "broadcast_method": "typed_msg",
        }

    async def fake_confirmer(tx_hash, now):  # noqa: ANN001
        return {
            "tx_hash": tx_hash,
            "found": True,
            "confirmed": True,
            "confirmation_status": "confirmed",
            "height": 987655,
            "code": 0,
            "raw_log": "",
        }

    service = forecast_engine.ForecastMiningService(
        repo,
        forecast_engine.ForecastSettings(
            poker_mtt_reward_windows_enabled=True,
            poker_mtt_settlement_anchoring_enabled=True,
            poker_mtt_daily_reward_pool_amount=reward_pool_amount,
            poker_mtt_weekly_reward_pool_amount=reward_pool_amount,
        ),
        chain_typed_broadcaster=fake_typed_broadcaster,
        chain_tx_confirmer=fake_confirmer,
    )

    messages = build_burst_messages(table_count=table_count, hands_per_table=hands_per_table)
    lag_high_water_mark = 0
    completed_hand_processed = 0
    standup_processed = 0
    accepted_event_count = 0

    ingest_started = time.perf_counter()
    for offset in range(0, len(messages), max(1, event_batch_size)):
        batch = messages[offset : offset + max(1, event_batch_size)]
        lag_high_water_mark = max(lag_high_water_mark, len(messages) - offset)
        for message_index, (topic, message) in enumerate(batch, start=1):
            received_at = completed_at.replace(second=min(59, message_index % 60))
            result = await mq_projector.replay_donor_message(
                service=service,
                repo=repo,
                tournament_id=tournament_id,
                topic=topic,
                message=message,
                consumer_name="burst-harness",
                received_at=received_at,
            )
            if not result["status"].startswith("accepted"):
                continue
            accepted_event_count += 1
            if topic == mq_projector.COMPLETED_HAND_TOPIC:
                completed_hand_processed += 1
            elif topic == mq_projector.STANDUP_TOPIC:
                standup_processed += 1
    ingest_elapsed_ms = round((time.perf_counter() - ingest_started) * 1000, 3)

    evidence_summary = await _build_evidence_summary(
        repo=repo,
        tournament_id=tournament_id,
        policy_bundle_version=runtime.DEFAULT_POLICY_BUNDLE_VERSION,
        accepted_event_count=accepted_event_count,
        generated_at=completed_at,
    )

    synthetic_summary, synthetic_evidence = _build_synthetic_runtime_summary(
        tournament_id=tournament_id,
        user_count=user_count,
    )
    apply_payload, wallet_bindings, _ = runtime.build_apply_payload(
        synthetic_summary,
        synthetic_evidence,
        locked_at=completed_at,
        started_minutes_before_lock=45,
        late_join_grace_seconds=600,
        runtime_source=runtime.DEFAULT_RUNTIME_SOURCE,
        final_ranking_source=runtime.DEFAULT_FINAL_RANKING_SOURCE,
        policy_bundle_version=runtime.DEFAULT_POLICY_BUNDLE_VERSION,
    )

    projection_rows, final_ranking_root = runtime.build_projection_rows(apply_payload, locked_at=completed_at)

    finalize_started = time.perf_counter()
    for source_user_id, wallet in sorted(wallet_bindings.items(), key=lambda item: int(item[0])):
        await service.register_miner(
            address=wallet["address"],
            name=f"burst-{source_user_id}",
            public_key=wallet["public_key"],
            miner_version="0.4.0",
        )

    for result, row in zip(apply_payload["results"], projection_rows, strict=True):
        await repo.save_poker_mtt_final_ranking(row)
        final_rank = int(result["final_rank"])
        finish_percentile = round((user_count - final_rank) / max(1, user_count - 1), 6)
        eligible = row.get("rank_state") == "ranked"
        await repo.save_poker_mtt_result(
            {
                "id": f"poker_mtt:{tournament_id}:{result['miner_id']}",
                "tournament_id": tournament_id,
                "miner_address": result["miner_id"],
                "economic_unit_id": result["economic_unit_id"],
                "rated_or_practice": "rated",
                "human_only": True,
                "field_size": user_count,
                "final_rank": final_rank,
                "rank_state": row["rank_state"],
                "chip_delta": row.get("chip_delta"),
                "entry_number": row.get("entry_number"),
                "reentry_count": row.get("reentry_count"),
                "finish_percentile": finish_percentile,
                "tournament_result_score": finish_percentile,
                "hidden_eval_score": 0.0,
                "consistency_input_score": 0.0,
                "total_score": finish_percentile,
                "eligible_for_multiplier": eligible,
                "rolling_score": 0.0 if eligible else None,
                "evaluation_state": "final",
                "evaluation_version": runtime.DEFAULT_POLICY_BUNDLE_VERSION,
                "final_ranking_id": row["id"],
                "standing_snapshot_id": row["standing_snapshot_id"],
                "standing_snapshot_hash": row["standing_snapshot_hash"],
                "evidence_root": result["evidence_root"],
                "evidence_state": row["evidence_state"],
                "locked_at": row["locked_at"],
                "anchorable_at": row["anchorable_at"],
                "anchor_state": "unanchored",
                "anchor_payload_hash": None,
                "risk_flags": [] if eligible else [row["rank_state"]],
                "no_multiplier_reason": None if eligible else "rank_state_not_ranked",
                "multiplier_before": 1.0,
                "multiplier_after": 1.0,
                "created_at": isoformat_z(completed_at),
                "updated_at": isoformat_z(completed_at),
            }
        )
    finalize_elapsed_ms = round((time.perf_counter() - finalize_started) * 1000, 3)

    reward_started = time.perf_counter()
    reward_window = await service.build_poker_mtt_reward_window(
        lane="poker_mtt_daily",
        window_start_at=datetime(2026, 4, 20, 0, 0, 0, tzinfo=timezone.utc),
        window_end_at=datetime(2026, 4, 21, 0, 0, 0, tzinfo=timezone.utc),
        reward_pool_amount=reward_pool_amount,
        include_provisional=False,
        policy_bundle_version=runtime.DEFAULT_DAILY_POLICY_VERSION,
        projection_metadata={
            "hand_history_evidence_root": evidence_summary["hand_history_evidence_root"],
            "consumer_checkpoint_root": evidence_summary["consumer_checkpoint_root"],
            "final_ranking_root": final_ranking_root,
        },
        now=datetime(2026, 4, 21, 0, 5, 0, tzinfo=timezone.utc),
    )
    reward_elapsed_ms = round((time.perf_counter() - reward_started) * 1000, 3)

    anchor_started = time.perf_counter()
    batch = await repo.get_settlement_batch(reward_window["settlement_batch_id"])
    anchored = await service.retry_anchor_settlement_batch(
        batch["id"],
        now=datetime(2026, 4, 21, 0, 6, 0, tzinfo=timezone.utc),
    )
    anchor_elapsed_ms = round((time.perf_counter() - anchor_started) * 1000, 3)

    checkpoints = await repo.list_poker_mtt_mq_checkpoints(tournament_id=tournament_id)
    dlq_entries = await repo.list_poker_mtt_mq_dlq(tournament_id=tournament_id)
    conflicts = await repo.list_poker_mtt_mq_conflicts(tournament_id=tournament_id)
    projection_artifacts = await repo.list_artifacts_for_entity("reward_window", reward_window["id"])
    projection = next(
        artifact for artifact in projection_artifacts if artifact["kind"] == "poker_mtt_reward_window_projection"
    )

    return {
        "tournament_id": tournament_id,
        "user_count": user_count,
        "table_count": table_count,
        "hands_per_table": hands_per_table,
        "event_batch_size": event_batch_size,
        "events": {
            "total": len(messages),
            "completed_hand_total": table_count * hands_per_table,
            "standup_total": table_count,
            "completed_hand_processed": completed_hand_processed,
            "standup_processed": standup_processed,
        },
        "mq_metrics": {
            "lag_high_water_mark": lag_high_water_mark,
        },
        "checkpoint_metrics": [
            {
                "consumer_name": checkpoint["consumer_group"],
                "topic": checkpoint["topic"],
                "accepted_count": 1 if str(checkpoint.get("last_ingest_state", "")).startswith("accepted") else 0,
                "stale_ignored_count": 0,
                "conflict_count": 0,
                "dlq_count": 0,
                "last_event_version": checkpoint.get("last_offset"),
            }
            for checkpoint in checkpoints
        ],
        "dlq_total": len(dlq_entries),
        "conflict_total": len(conflicts),
        "timings_ms": {
            "ingest_total": ingest_elapsed_ms,
            "finalize_total": finalize_elapsed_ms,
            "reward_window_total": reward_elapsed_ms,
            "anchor_prep_total": anchor_elapsed_ms,
        },
        "finalize": {
            "item_count": len(projection_rows),
            "eligible_count": sum(1 for row in projection_rows if row.get("rank_state") == "ranked"),
            "hand_history_evidence_root": evidence_summary["hand_history_evidence_root"],
            "consumer_checkpoint_root": evidence_summary["consumer_checkpoint_root"],
        },
        "reward_window": {
            "id": reward_window["id"],
            "submission_count": reward_window["submission_count"],
            "miner_count": reward_window["miner_count"],
            "total_reward_amount": reward_window["total_reward_amount"],
            "consumer_checkpoint_root": evidence_summary["consumer_checkpoint_root"],
        },
        "anchor": {
            "settlement_batch_id": batch["id"],
            "canonical_root": anchored["canonical_root"],
            "anchor_payload_hash": anchored["anchor_payload_hash"],
            "consumer_checkpoint_root": evidence_summary["consumer_checkpoint_root"],
        },
    }


def main() -> int:
    args = parse_args()
    summary = asyncio.run(
        run_burst_harness(
            tournament_id=args.tournament_id,
            user_count=args.user_count,
            table_count=args.table_count,
            hands_per_table=args.hands_per_table,
            event_batch_size=args.event_batch_size,
            reward_pool_amount=args.reward_pool_amount,
        )
    )
    output = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.summary_file:
        args.summary_file.parent.mkdir(parents=True, exist_ok=True)
        args.summary_file.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
