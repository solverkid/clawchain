from __future__ import annotations

from datetime import datetime, timezone


REWARD_READY_EVIDENCE_STATES = {"complete"}


def compatible_result_policy_versions(reward_policy_bundle_version: str) -> list[str]:
    if reward_policy_bundle_version.startswith("poker_mtt_daily_policy_v") or reward_policy_bundle_version.startswith(
        "poker_mtt_weekly_policy_v"
    ):
        return [reward_policy_bundle_version, "poker_mtt_v1"]
    return [reward_policy_bundle_version]


def result_policy_matches_reward_window(
    *,
    result_policy_bundle_version: str | None,
    reward_policy_bundle_version: str | None,
) -> bool:
    if not result_policy_bundle_version or not reward_policy_bundle_version:
        return False
    return result_policy_bundle_version in compatible_result_policy_versions(reward_policy_bundle_version)


def isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def tournament_result_score(*, final_rank: int, field_size: int) -> float:
    if field_size <= 1:
        raise ValueError("field_size must be at least 2")
    if final_rank < 1 or final_rank > field_size:
        raise ValueError("final_rank out of range")
    return round((field_size - final_rank) / max(1, field_size - 1), 6)


def total_score(
    *,
    tournament_score: float,
    hidden_eval_score: float = 0.0,
    consistency_input_score: float = 0.0,
) -> float:
    return round(
        clamp(
            (tournament_score * 0.55)
            + (hidden_eval_score * 0.25)
            + (consistency_input_score * 0.20),
            -1.0,
            1.0,
        ),
        6,
    )


def reward_gate_reason(
    *,
    rank_state: str | None,
    rank: int | None,
    rated_or_practice: str,
    human_only: bool,
    evidence_state: str | None,
    policy_bundle_version: str | None,
    locked_at: datetime | str | None,
    evidence_root: str | None = None,
    final_ranking_id: str | None = None,
    standing_snapshot_id: str | None = None,
) -> str | None:
    if rated_or_practice != "rated" or human_only is not True:
        return "not_rated_or_not_human"
    if not policy_bundle_version:
        return "missing_policy_bundle_version"
    if rank_state != "ranked" or rank is None:
        return "rank_state_not_ranked"
    if evidence_state not in REWARD_READY_EVIDENCE_STATES:
        return "evidence_not_reward_ready"
    if not final_ranking_id:
        return "missing_final_ranking_ref"
    if not standing_snapshot_id:
        return "missing_standing_snapshot_ref"
    if not evidence_root:
        return "missing_evidence_root"
    if locked_at is None:
        return "missing_lock"
    return None


def is_reward_ready(
    *,
    rank_state: str | None,
    rank: int | None,
    rated_or_practice: str,
    human_only: bool,
    evidence_state: str | None,
    policy_bundle_version: str | None,
    locked_at: datetime | str | None,
    evidence_root: str | None = None,
    final_ranking_id: str | None = None,
    standing_snapshot_id: str | None = None,
) -> bool:
    return (
        reward_gate_reason(
            rank_state=rank_state,
            rank=rank,
            rated_or_practice=rated_or_practice,
            human_only=human_only,
            evidence_state=evidence_state,
            policy_bundle_version=policy_bundle_version,
            locked_at=locked_at,
            evidence_root=evidence_root,
            final_ranking_id=final_ranking_id,
            standing_snapshot_id=standing_snapshot_id,
        )
        is None
    )


def project_final_ranking_row(
    row: dict,
    *,
    rated_or_practice: str,
    human_only: bool,
    field_size: int,
    policy_bundle_version: str,
    locked_at: datetime,
) -> dict:
    rank = row.get("rank")
    final_rank = int(rank) if rank is not None else field_size
    evidence_state = str(row.get("evidence_state") or "pending")
    locked_at_iso = isoformat_z(locked_at)
    reason = reward_gate_reason(
        rank_state=row.get("rank_state"),
        rank=rank,
        rated_or_practice=rated_or_practice,
        human_only=human_only,
        evidence_state=evidence_state,
        evidence_root=row.get("evidence_root"),
        final_ranking_id=row.get("id"),
        standing_snapshot_id=row.get("standing_snapshot_id"),
        policy_bundle_version=policy_bundle_version or row.get("policy_bundle_version"),
        locked_at=locked_at,
    )
    try:
        result_score = tournament_result_score(final_rank=final_rank, field_size=field_size)
    except ValueError:
        if reason is None:
            raise
        final_rank = max(1, min(field_size, final_rank))
        result_score = 0.0
    risk_flags = []
    if reason:
        risk_flags.append(reason)
    if row.get("rank_state") not in {None, "ranked"}:
        risk_flags.append(str(row["rank_state"]))

    miner_address = row.get("miner_address") or row.get("source_user_id")
    return {
        "id": f"poker_mtt:{row['tournament_id']}:{miner_address}",
        "tournament_id": row["tournament_id"],
        "miner_address": miner_address,
        "economic_unit_id": row.get("economic_unit_id") or miner_address,
        "rated_or_practice": rated_or_practice,
        "human_only": human_only,
        "field_size": field_size,
        "final_rank": final_rank,
        "rank_state": row.get("rank_state"),
        "chip_delta": row.get("chip_delta"),
        "entry_number": row.get("entry_number"),
        "reentry_count": int(row.get("reentry_count") or 1),
        "finish_percentile": result_score,
        "tournament_result_score": result_score,
        "hidden_eval_score": 0.0,
        "consistency_input_score": 0.0,
        "total_score": total_score(tournament_score=result_score),
        "eligible_for_multiplier": reason is None,
        "rolling_score": None,
        "evaluation_state": "final",
        "evaluation_version": policy_bundle_version,
        "final_ranking_id": row.get("id"),
        "standing_snapshot_id": row.get("standing_snapshot_id"),
        "standing_snapshot_hash": row.get("standing_snapshot_hash"),
        "evidence_root": row.get("evidence_root"),
        "evidence_state": evidence_state,
        "locked_at": locked_at_iso if reason is None else None,
        "anchorable_at": locked_at_iso if reason is None else None,
        "anchor_state": "unanchored",
        "anchor_payload_hash": None,
        "risk_flags": risk_flags,
        "no_multiplier_reason": reason,
        "created_at": row.get("created_at") or locked_at_iso,
        "updated_at": locked_at_iso,
    }


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
