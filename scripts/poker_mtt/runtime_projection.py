from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
SKILL_SCRIPT_DIR = ROOT / "skill" / "scripts"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))
if str(SKILL_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPT_DIR))

import forecast_engine
from setup import generate_wallet


DEFAULT_RUNTIME_SOURCE = "lepoker_gameserver"
DEFAULT_FINAL_RANKING_SOURCE = "donor_redis_rankings"
DEFAULT_POLICY_BUNDLE_VERSION = "poker_mtt_v1"
DEFAULT_DAILY_POLICY_VERSION = "poker_mtt_daily_policy_v2"
DEFAULT_WEEKLY_POLICY_VERSION = "poker_mtt_weekly_policy_v2"
WAITING_ENTRY_STATES = frozenset({"waiting", "waitlist", "no_show"})


def hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def deterministic_wallet(tournament_id: str, source_user_id: str) -> dict[str, str]:
    seed = f"{tournament_id}:{source_user_id}"
    private_key_hex = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return generate_wallet(private_key_override=private_key_hex)


def derive_reward_window_bounds(lane: str, locked_at: datetime) -> tuple[datetime, datetime]:
    if lane == "poker_mtt_daily":
        start = locked_at.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    weekday_start = locked_at - timedelta(days=locked_at.weekday())
    start = weekday_start.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=7)


def derive_reward_window_policy_version(lane: str, configured_version: str | None) -> str:
    if configured_version:
        return configured_version
    if lane == "poker_mtt_weekly":
        return DEFAULT_WEEKLY_POLICY_VERSION
    return DEFAULT_DAILY_POLICY_VERSION


def derive_runtime_hand_history_root(summary: dict[str, Any], evidence: dict[str, Any]) -> str:
    payload = {
        "tournament_id": summary["mtt_id"],
        "summary_artifact": evidence.get("summary_artifact"),
        "connections": evidence.get("connections"),
        "room_assignments": evidence.get("room_assignments"),
        "final_standings": evidence.get("final_standings"),
        "log_truth": evidence.get("log_truth"),
    }
    return hash_payload(payload)


def derive_runtime_consumer_checkpoint_root(summary: dict[str, Any], evidence: dict[str, Any]) -> str:
    payload = {
        "tournament_id": summary["mtt_id"],
        "captured_at": evidence.get("captured_at"),
        "connections": evidence.get("connections"),
        "room_assignments": evidence.get("room_assignments"),
        "log_truth": evidence.get("log_truth"),
    }
    return hash_payload(payload)


def evaluate_runtime_entry(
    row: dict[str, Any],
    *,
    started_at: datetime | None,
    late_join_grace_seconds: int,
) -> dict[str, str | None]:
    entry_state = str(row.get("entry_state") or row.get("status") or "completed").strip().lower()
    if bool(row.get("waiting_or_no_show")) or entry_state in WAITING_ENTRY_STATES:
        return {
            "entry_state": entry_state or "waiting",
            "eligibility_state": "excluded",
            "exclusion_reason": "waiting_or_no_show",
            "rank_state": "waiting_or_no_show",
            "evidence_state": "pending",
        }
    if entry_state == "cancelled":
        return {
            "entry_state": entry_state,
            "eligibility_state": "excluded",
            "exclusion_reason": "cancelled",
            "rank_state": "cancelled",
            "evidence_state": "pending",
        }
    if entry_state == "failed_to_start":
        return {
            "entry_state": entry_state,
            "eligibility_state": "excluded",
            "exclusion_reason": "failed_to_start",
            "rank_state": "failed_to_start",
            "evidence_state": "pending",
        }
    joined_at = parse_iso_datetime(row.get("joined_at"))
    if (
        joined_at is not None
        and started_at is not None
        and joined_at > started_at + timedelta(seconds=max(0, late_join_grace_seconds))
    ):
        return {
            "entry_state": entry_state or "completed",
            "eligibility_state": "excluded",
            "exclusion_reason": "late_join_after_grace_window",
            "rank_state": "late_join_after_grace_window",
            "evidence_state": "pending",
        }
    return {
        "entry_state": entry_state or "completed",
        "eligibility_state": "eligible",
        "exclusion_reason": None,
        "rank_state": "ranked",
        "evidence_state": "complete",
    }


def build_apply_payload(
    summary: dict[str, Any],
    evidence: dict[str, Any],
    *,
    locked_at: datetime,
    started_minutes_before_lock: int,
    late_join_grace_seconds: int,
    runtime_source: str,
    final_ranking_source: str,
    policy_bundle_version: str,
) -> tuple[dict[str, Any], dict[str, dict[str, str]], dict[str, Any]]:
    standings = sorted(
        summary["standings"]["standings"],
        key=lambda row: (
            int(row.get("payout_rank") or row.get("display_rank") or 0),
            str(row.get("member_id") or ""),
        ),
    )
    field_size = len(standings)
    started_at = locked_at - timedelta(minutes=started_minutes_before_lock)
    hand_history_evidence_root = derive_runtime_hand_history_root(summary, evidence)
    consumer_checkpoint_root = derive_runtime_consumer_checkpoint_root(summary, evidence)
    wallet_bindings: dict[str, dict[str, str]] = {}
    result_rows: list[dict[str, Any]] = []

    for row in standings:
        source_user_id = str(row["user_id"])
        wallet = deterministic_wallet(summary["mtt_id"], source_user_id)
        wallet_bindings[source_user_id] = wallet
        payout_rank = int(row.get("payout_rank") or row.get("display_rank") or field_size)
        display_rank = int(row.get("display_rank") or payout_rank)
        source_rank = int(row.get("display_rank") or payout_rank)
        finish_percentile = round((field_size - payout_rank) / max(1, field_size - 1), 6)
        eligibility = evaluate_runtime_entry(
            row,
            started_at=started_at,
            late_join_grace_seconds=late_join_grace_seconds,
        )
        entry_number = max(1, int(row.get("entry_number") or 1))
        result_rows.append(
            {
                "miner_id": wallet["address"],
                "source_user_id": source_user_id,
                "canonical_entry_id": row.get("member_id") or f"{source_user_id}:1",
                "final_rank": payout_rank,
                "display_rank": display_rank,
                "source_rank": source_rank,
                "payout_rank": payout_rank,
                "entry_number": entry_number,
                "reentry_count": entry_number,
                "entry_state": eligibility["entry_state"],
                "waiting_or_no_show": eligibility["exclusion_reason"] == "waiting_or_no_show",
                "joined_at": row.get("joined_at"),
                "rank_state": eligibility["rank_state"],
                "eligibility_state": eligibility["eligibility_state"],
                "exclusion_reason": eligibility["exclusion_reason"],
                "economic_unit_id": f"eu:poker-mtt:{summary['mtt_id']}:{source_user_id}",
                "reward_owner_address": wallet["address"],
                "reward_identity_state": "bound",
                "tournament_result_score": finish_percentile,
                "hidden_eval_score": 0.0,
                "consistency_input_score": 0.0,
                "evaluation_state": "final",
                "evidence_root": hand_history_evidence_root,
                "hand_history_evidence_root": hand_history_evidence_root,
                "consumer_checkpoint_root": consumer_checkpoint_root,
                "evidence_state": eligibility["evidence_state"],
                "status": row.get("status") or eligibility["entry_state"],
                "player_name": row.get("player_name"),
                "room_id": row.get("room_id"),
                "start_chip": row.get("start_chip"),
                "end_chip": row.get("end_chip"),
                "chip_delta": row.get("chip_delta"),
                "died_time": row.get("died_time"),
                "stand_up_status": row.get("stand_up_status"),
                "zset_score": row.get("zset_score"),
                "snapshot_found": row.get("snapshot_found", True),
            }
        )

    payload = {
        "tournament_id": summary["mtt_id"],
        "rated_or_practice": "rated",
        "human_only": True,
        "field_size": field_size,
        "runtime_source": runtime_source,
        "final_ranking_source": final_ranking_source,
        "started_at": forecast_engine.isoformat_z(started_at),
        "late_join_grace_seconds": late_join_grace_seconds,
        "policy_bundle_version": policy_bundle_version,
        "results": result_rows,
    }
    replay_notes = {
        "hand_history_evidence_root": hand_history_evidence_root,
        "consumer_checkpoint_root": consumer_checkpoint_root,
        "joined_at_strategy": "omitted; donor runtime sample does not expose canonical entrant join timestamps unless explicitly present in the replay fixture",
        "scoring_strategy": "finish_percentile_only; hidden_eval_score and consistency_input_score are held at 0.0 for donor-safe Phase 3 release proof",
        "started_at": forecast_engine.isoformat_z(started_at),
        "locked_at": forecast_engine.isoformat_z(locked_at),
    }
    return payload, wallet_bindings, replay_notes


def build_projection_rows(
    apply_payload: dict[str, Any],
    *,
    locked_at: datetime,
) -> tuple[list[dict[str, Any]], str]:
    tournament_id = apply_payload["tournament_id"]
    locked_at_iso = forecast_engine.isoformat_z(locked_at)
    standing_snapshot_hash = hash_payload(
        {
            "tournament_id": tournament_id,
            "rows": [
                {
                    "canonical_entry_id": row["canonical_entry_id"],
                    "payout_rank": row["payout_rank"],
                    "rank_state": row["rank_state"],
                    "source_user_id": row["source_user_id"],
                }
                for row in apply_payload["results"]
            ],
        }
    )
    standing_snapshot_id = f"poker_mtt_standing_snapshot:{tournament_id}:{standing_snapshot_hash.removeprefix('sha256:')[:12]}"
    rows: list[dict[str, Any]] = []
    for result in apply_payload["results"]:
        payout_rank = int(result.get("payout_rank") or result["final_rank"])
        rank_state = str(result.get("rank_state") or "ranked")
        rank = payout_rank if rank_state == "ranked" else None
        source_rank_numeric = rank is not None
        rows.append(
            {
                "id": f"poker_mtt_final_ranking:{tournament_id}:{result['miner_id']}",
                "tournament_id": tournament_id,
                "source_mtt_id": tournament_id,
                "source_user_id": result["source_user_id"],
                "miner_address": result["miner_id"],
                "economic_unit_id": result["economic_unit_id"],
                "member_id": result["canonical_entry_id"],
                "entry_number": max(1, int(result.get("entry_number") or 1)),
                "reentry_count": max(1, int(result.get("reentry_count") or result.get("entry_number") or 1)),
                "rank": rank,
                "display_rank": int(result.get("display_rank") or payout_rank),
                "rank_state": rank_state,
                "rank_basis": "donor_runtime_replay",
                "rank_tiebreaker": result.get("exclusion_reason") or "donor_runtime_replay",
                "chip": float(result.get("end_chip") or 0.0),
                "chip_delta": float(result.get("chip_delta") or 0.0),
                "died_time": result.get("died_time"),
                "waiting_or_no_show": bool(result.get("waiting_or_no_show")),
                "bounty": 0.0,
                "defeat_num": 0,
                "field_size_policy": "exclude_waiting_no_show_from_reward_field_size",
                "standing_snapshot_id": standing_snapshot_id,
                "standing_snapshot_hash": standing_snapshot_hash,
                "evidence_root": result.get("evidence_root"),
                "evidence_state": result.get("evidence_state") or "complete",
                "policy_bundle_version": apply_payload["policy_bundle_version"],
                "snapshot_found": bool(result.get("snapshot_found", True)),
                "status": result.get("status") or result.get("entry_state") or "completed",
                "player_name": result.get("player_name") or result["source_user_id"],
                "room_id": result.get("room_id"),
                "start_chip": float(result.get("start_chip") or 0.0),
                "stand_up_status": result.get("stand_up_status"),
                "source_rank": str(result.get("source_rank")) if source_rank_numeric else None,
                "source_rank_numeric": source_rank_numeric,
                "zset_score": float(result.get("zset_score") or 0.0) if result.get("zset_score") is not None else None,
                "locked_at": locked_at_iso if rank is not None else None,
                "anchorable_at": locked_at_iso if rank is not None else None,
                "created_at": locked_at_iso,
                "updated_at": locked_at_iso,
            }
        )
    final_ranking_root = hash_payload(
        {
            "tournament_id": tournament_id,
            "standing_snapshot_id": standing_snapshot_id,
            "rows": [
                {
                    "id": row["id"],
                    "member_id": row["member_id"],
                    "rank": row["rank"],
                    "display_rank": row["display_rank"],
                    "rank_state": row["rank_state"],
                    "evidence_root": row["evidence_root"],
                }
                for row in rows
            ],
        }
    )
    return rows, final_ranking_root


def build_hidden_eval_entries(
    projection_rows: list[dict[str, Any]],
    *,
    tournament_id: str,
    policy_bundle_version: str,
) -> list[dict[str, Any]]:
    return [
        {
            "miner_address": row["miner_address"],
            "final_ranking_id": row["id"],
            "hidden_eval_score": 0.0,
            "score_components_json": {"runtime_projection": True},
            "evidence_root": row["evidence_root"],
            "seed_assignment_id": f"hidden-seed:{tournament_id}",
            "baseline_sample_id": None,
            "visibility_state": "service_internal",
            "policy_bundle_version": policy_bundle_version,
        }
        for row in projection_rows
        if row.get("rank_state") == "ranked" and row.get("evidence_state") == "complete"
    ]
