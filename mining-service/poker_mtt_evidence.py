from __future__ import annotations

from datetime import datetime
from typing import Sequence

from canonical import canonical_hash, canonicalize, fixed_decimal, rows_root


EVIDENCE_MANIFEST_SCHEMA_VERSION = "poker_mtt.evidence_manifest.v1"
FINAL_RANKING_MANIFEST_KIND = "poker_mtt_final_ranking_manifest"
HAND_HISTORY_MANIFEST_KIND = "poker_mtt_hand_history_manifest"
HIDDEN_EVAL_MANIFEST_KIND = "poker_mtt_hidden_eval_manifest"
CONSUMER_CHECKPOINT_MANIFEST_KIND = "poker_mtt_consumer_checkpoint_manifest"
STUB_MANIFEST_KINDS = {
    HAND_HISTORY_MANIFEST_KIND,
    "poker_mtt_short_term_hud_manifest",
    "poker_mtt_long_term_hud_manifest",
    HIDDEN_EVAL_MANIFEST_KIND,
    CONSUMER_CHECKPOINT_MANIFEST_KIND,
}
FINAL_RANKING_FIXED_DECIMAL_FIELDS = {"chip", "chip_delta", "bounty", "start_chip", "zset_score"}
HAND_HISTORY_ROW_SORT_KEYS = ("tournament_id", "table_id", "hand_no", "hand_id")
HIDDEN_EVAL_ROW_SORT_KEYS = ("tournament_id", "miner_address", "final_ranking_id")


def build_final_ranking_manifest(
    *,
    tournament_id: str,
    rows: Sequence[dict],
    policy_bundle_version: str,
    generated_at: datetime | str,
) -> dict:
    return build_manifest(
        kind=FINAL_RANKING_MANIFEST_KIND,
        tournament_id=tournament_id,
        rows=[_normalize_final_ranking_row(row) for row in rows],
        row_sort_keys=("tournament_id", "member_id"),
        policy_bundle_version=policy_bundle_version,
        evidence_state="complete",
        generated_at=generated_at,
    )


def build_hand_history_manifest(
    *,
    tournament_id: str,
    rows: Sequence[dict],
    policy_bundle_version: str,
    generated_at: datetime | str,
) -> dict:
    return build_manifest(
        kind=HAND_HISTORY_MANIFEST_KIND,
        tournament_id=tournament_id,
        rows=[_normalize_hand_history_row(row) for row in rows],
        row_sort_keys=HAND_HISTORY_ROW_SORT_KEYS,
        policy_bundle_version=policy_bundle_version,
        evidence_state="complete",
        generated_at=generated_at,
    )


def build_hidden_eval_manifest(
    *,
    tournament_id: str,
    rows: Sequence[dict],
    policy_bundle_version: str,
    generated_at: datetime | str,
) -> dict:
    return build_manifest(
        kind=HIDDEN_EVAL_MANIFEST_KIND,
        tournament_id=tournament_id,
        rows=[_normalize_hidden_eval_row(row) for row in rows],
        row_sort_keys=HIDDEN_EVAL_ROW_SORT_KEYS,
        policy_bundle_version=policy_bundle_version,
        evidence_state="complete",
        generated_at=generated_at,
    )


def build_consumer_checkpoint_manifest(
    *,
    tournament_id: str,
    rows: Sequence[dict],
    policy_bundle_version: str,
    generated_at: datetime | str,
) -> dict:
    return build_manifest(
        kind=CONSUMER_CHECKPOINT_MANIFEST_KIND,
        tournament_id=tournament_id,
        rows=[_normalize_checkpoint_row(row) for row in rows],
        row_sort_keys=("topic", "consumer_group", "queue"),
        policy_bundle_version=policy_bundle_version,
        evidence_state="complete",
        generated_at=generated_at,
    )


def build_stub_manifest(
    *,
    kind: str,
    tournament_id: str,
    policy_bundle_version: str,
    evidence_state: str,
    degraded_reason: str,
    generated_at: datetime | str,
) -> dict:
    if kind not in STUB_MANIFEST_KINDS:
        raise ValueError(f"unsupported stub manifest kind: {kind}")
    if evidence_state != "accepted_degraded":
        raise ValueError("stub manifest must be accepted_degraded")
    return build_manifest(
        kind=kind,
        tournament_id=tournament_id,
        rows=[],
        row_sort_keys=(),
        policy_bundle_version=policy_bundle_version,
        evidence_state=evidence_state,
        generated_at=generated_at,
        degraded_reason=degraded_reason,
    )


def build_manifest(
    *,
    kind: str,
    tournament_id: str,
    rows: Sequence[dict],
    row_sort_keys: Sequence[str],
    policy_bundle_version: str,
    evidence_state: str,
    generated_at: datetime | str,
    degraded_reason: str | None = None,
) -> dict:
    row_sort_keys_list = list(row_sort_keys)
    normalized_rows = [canonicalize(row) for row in rows]
    manifest = {
        "schema_version": EVIDENCE_MANIFEST_SCHEMA_VERSION,
        "kind": kind,
        "tournament_id": tournament_id,
        "policy_bundle_version": policy_bundle_version,
        "evidence_state": evidence_state,
        "row_count": len(normalized_rows),
        "row_sort_keys": row_sort_keys_list,
        "rows_root": rows_root(normalized_rows, sort_keys=row_sort_keys),
    }
    if degraded_reason is not None:
        manifest["degraded_reason"] = degraded_reason
    manifest["manifest_root"] = canonical_hash(manifest)
    return manifest


def _normalize_final_ranking_row(row: dict) -> dict:
    normalized = canonicalize(row)
    for field in FINAL_RANKING_FIXED_DECIMAL_FIELDS:
        value = row.get(field)
        if value is not None:
            normalized[field] = fixed_decimal(value, places=6)
    return normalized


def _normalize_hand_history_row(row: dict) -> dict:
    normalized = canonicalize(
        {
            "tournament_id": row.get("tournament_id"),
            "table_id": row.get("table_id"),
            "hand_no": row.get("hand_no"),
            "hand_id": row.get("hand_id"),
            "version": row.get("version"),
            "checksum": row.get("checksum"),
            "ingest_state": row.get("ingest_state"),
        }
    )
    if row.get("conflict_reason") is not None:
        normalized["conflict_reason"] = row.get("conflict_reason")
    return normalized


def _normalize_hidden_eval_row(row: dict) -> dict:
    normalized = canonicalize(
        {
            "tournament_id": row.get("tournament_id"),
            "miner_address": row.get("miner_address"),
            "final_ranking_id": row.get("final_ranking_id"),
            "seed_assignment_id": row.get("seed_assignment_id"),
            "baseline_sample_id": row.get("baseline_sample_id"),
            "hidden_eval_score": fixed_decimal(row.get("hidden_eval_score") or 0.0, places=6),
            "score_components_json": row.get("score_components_json") or {},
            "evidence_root": row.get("evidence_root"),
            "policy_bundle_version": row.get("policy_bundle_version"),
            "visibility_state": row.get("visibility_state") or "service_internal",
        }
    )
    return normalized


def _normalize_checkpoint_row(row: dict) -> dict:
    return canonicalize(
        {
            "tournament_id": row.get("tournament_id"),
            "topic": row.get("topic"),
            "queue": row.get("queue"),
            "consumer_group": row.get("consumer_group"),
            "last_offset": row.get("last_offset"),
            "last_message_id": row.get("last_message_id"),
            "last_biz_id": row.get("last_biz_id"),
            "last_hand_id": row.get("last_hand_id"),
            "last_ingest_state": row.get("last_ingest_state"),
            "replay_root": row.get("replay_root"),
            "lag_messages": int(row.get("lag_messages") or 0),
        }
    )
