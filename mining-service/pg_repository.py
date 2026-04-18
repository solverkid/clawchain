from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import insert, select, update, func, text, or_
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

import poker_mtt_results
from models import (
    metadata,
    miners,
    forecast_task_runs,
    forecast_submissions,
    reward_windows,
    settlement_batches,
    anchor_jobs,
    artifacts,
    reward_hold_entries,
    risk_review_cases,
    arena_result_entries,
    poker_mtt_tournaments,
    poker_mtt_hand_events,
    poker_mtt_mq_checkpoints,
    poker_mtt_mq_conflicts,
    poker_mtt_mq_dlq,
    poker_mtt_short_term_hud_snapshots,
    poker_mtt_long_term_hud_snapshots,
    poker_mtt_hidden_eval_entries,
    poker_mtt_rating_snapshots,
    poker_mtt_multiplier_snapshots,
    poker_mtt_corrections,
    poker_mtt_final_rankings,
    poker_mtt_result_entries,
)


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row)


def _maybe_dt(value):
    if isinstance(value, str) and value.endswith("Z"):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _task_values(task: dict) -> dict:
    values = deepcopy(task)
    values["id"] = values.pop("task_run_id")
    for field in ("publish_at", "commit_deadline", "reveal_deadline", "resolve_at", "created_at", "updated_at"):
        if field in values:
            values[field] = _maybe_dt(values[field])
    return values


def _submission_values(submission: dict) -> dict:
    values = deepcopy(submission)
    for field in ("accepted_commit_at", "accepted_reveal_at", "created_at", "updated_at"):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    return values


def _hold_entry_values(hold_entry: dict) -> dict:
    values = deepcopy(hold_entry)
    for field in ("release_after", "created_at", "updated_at"):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    return values


def _reward_window_values(reward_window: dict) -> dict:
    values = deepcopy(reward_window)
    for field in ("window_start_at", "window_end_at", "created_at", "updated_at"):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    return values


def _settlement_batch_values(settlement_batch: dict) -> dict:
    values = deepcopy(settlement_batch)
    for field in ("window_start_at", "window_end_at", "created_at", "updated_at"):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    return values


def _anchor_job_values(anchor_job: dict) -> dict:
    values = deepcopy(anchor_job)
    for field in ("submitted_at", "anchored_at", "last_broadcast_at", "created_at", "updated_at"):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    return values


def _artifact_values(artifact: dict) -> dict:
    values = deepcopy(artifact)
    for field in ("created_at", "updated_at"):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    return values


def _miner_values(miner: dict) -> dict:
    values = deepcopy(miner)
    for field in (
        "created_at",
        "updated_at",
        "fast_window_start_at",
        "poker_mtt_reward_bound_at",
        "poker_mtt_identity_expires_at",
        "poker_mtt_identity_revoked_at",
    ):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    return values


def _poker_mtt_tournament_values(tournament: dict) -> dict:
    values = deepcopy(tournament)
    for field in ("started_at", "completed_at", "created_at", "updated_at"):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    return values


def _poker_mtt_hand_event_values(event: dict, *, created_at: datetime | str | None = None) -> dict:
    identity = event.get("identity") or {}
    now = datetime.now(timezone.utc)
    values = {
        "hand_id": identity.get("hand_id") or event.get("hand_id"),
        "tournament_id": identity.get("tournament_id") or event.get("tournament_id"),
        "table_id": identity.get("table_id") or event.get("table_id"),
        "hand_no": identity.get("hand_no") if identity.get("hand_no") is not None else event.get("hand_no"),
        "version": event.get("version"),
        "checksum": event["checksum"],
        "event_id": event.get("event_id"),
        "source_json": deepcopy(event.get("source_json") or event.get("source") or {}),
        "payload_json": deepcopy(event.get("payload_json") or event.get("payload") or {}),
        "ingest_state": event.get("ingest_state") or "inserted",
        "conflict_reason": event.get("conflict_reason"),
        "created_at": created_at or event.get("created_at") or now,
        "updated_at": event.get("updated_at") or now,
    }
    if not values["hand_id"]:
        raise ValueError("missing poker mtt hand_id")
    for field in ("created_at", "updated_at"):
        values[field] = _maybe_dt(values[field])
    return values


def _mq_row_values(row: dict) -> dict:
    values = deepcopy(row)
    for field in ("created_at", "updated_at", "last_processed_at", "lag_watermark_at"):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    return values


def _poker_mtt_hud_snapshot_values(row: dict, *, created_at: datetime | str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    hud_window = row.get("hud_window") or "short_term"
    tournament_id = row.get("tournament_id") or ""
    miner_address = row.get("miner_address")
    if not miner_address:
        raise ValueError("missing poker mtt hud miner_address")
    base_fields = {
        "id",
        "tournament_id",
        "miner_address",
        "source_user_id",
        "hud_window",
        "hands_seen",
        "metrics_json",
        "policy_bundle_version",
        "manifest_root",
        "created_at",
        "updated_at",
    }
    metrics = deepcopy(row.get("metrics_json") or {})
    for key, value in row.items():
        if key not in base_fields:
            metrics[key] = deepcopy(value)
    values = {
        "id": row.get("id") or f"poker_mtt_hud:{hud_window}:{tournament_id}:{miner_address}",
        "tournament_id": tournament_id,
        "miner_address": miner_address,
        "source_user_id": row.get("source_user_id"),
        "hud_window": hud_window,
        "hands_seen": int(row.get("hands_seen") or metrics.get("hands_seen") or 0),
        "metrics_json": metrics,
        "policy_bundle_version": row.get("policy_bundle_version") or "poker_mtt_v1",
        "manifest_root": row.get("manifest_root"),
        "created_at": created_at or row.get("created_at") or now,
        "updated_at": row.get("updated_at") or now,
    }
    for field in ("created_at", "updated_at"):
        values[field] = _maybe_dt(values[field])
    return values


def _poker_mtt_hud_snapshot_table(hud_window: str):
    if hud_window == "long_term":
        return poker_mtt_long_term_hud_snapshots
    return poker_mtt_short_term_hud_snapshots


def _poker_mtt_hidden_eval_entry_values(row: dict, *, created_at: datetime | str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    tournament_id = row.get("tournament_id")
    miner_address = row.get("miner_address")
    final_ranking_id = row.get("final_ranking_id")
    if not tournament_id:
        raise ValueError("missing poker mtt hidden eval tournament_id")
    if not miner_address:
        raise ValueError("missing poker mtt hidden eval miner_address")
    if not final_ranking_id:
        raise ValueError("missing poker mtt hidden eval final_ranking_id")
    values = {
        "id": row.get("id") or f"poker_mtt_hidden_eval:{tournament_id}:{miner_address}:{final_ranking_id}",
        "tournament_id": tournament_id,
        "miner_address": miner_address,
        "final_ranking_id": final_ranking_id,
        "seed_assignment_id": row.get("seed_assignment_id"),
        "baseline_sample_id": row.get("baseline_sample_id"),
        "hidden_eval_score": float(row.get("hidden_eval_score") or 0.0),
        "score_components_json": deepcopy(row.get("score_components_json") or {}),
        "evidence_root": row.get("evidence_root"),
        "manifest_root": row.get("manifest_root"),
        "policy_bundle_version": row.get("policy_bundle_version") or "poker_mtt_v1",
        "visibility_state": row.get("visibility_state") or "service_internal",
        "created_at": created_at or row.get("created_at") or now,
        "updated_at": row.get("updated_at") or now,
    }
    for field in ("created_at", "updated_at"):
        values[field] = _maybe_dt(values[field])
    return values


def _poker_mtt_rating_snapshot_values(row: dict, *, created_at: datetime | str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    values = deepcopy(row)
    miner_address = values.get("miner_address")
    if not miner_address:
        raise ValueError("missing poker mtt rating miner_address")
    window_start_at = values.get("window_start_at")
    window_end_at = values.get("window_end_at")
    if not window_start_at or not window_end_at:
        raise ValueError("missing poker mtt rating window")
    values["id"] = values.get("id") or f"poker_mtt_rating:{miner_address}:{window_start_at}:{window_end_at}"
    values["public_rating"] = float(values.get("public_rating") or 0.0)
    values["confidence"] = float(values.get("confidence") or 0.0)
    values["policy_bundle_version"] = values.get("policy_bundle_version") or "poker_mtt_v1"
    values["created_at"] = created_at or values.get("created_at") or now
    values["updated_at"] = values.get("updated_at") or now
    for field in ("window_start_at", "window_end_at", "created_at", "updated_at"):
        values[field] = _maybe_dt(values[field])
    return values


def _poker_mtt_multiplier_snapshot_values(row: dict, *, created_at: datetime | str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    values = deepcopy(row)
    source_result_id = values.get("source_result_id")
    miner_address = values.get("miner_address")
    if not miner_address:
        raise ValueError("missing poker mtt multiplier miner_address")
    if not source_result_id:
        raise ValueError("missing poker mtt multiplier source_result_id")
    values["id"] = values.get("id") or f"poker_mtt_multiplier:{source_result_id}"
    values["multiplier_before"] = float(values.get("multiplier_before") or 1.0)
    values["multiplier_after"] = float(values.get("multiplier_after") or 1.0)
    values["policy_bundle_version"] = values.get("policy_bundle_version") or "poker_mtt_v1"
    values["created_at"] = created_at or values.get("created_at") or now
    values["updated_at"] = values.get("updated_at") or now
    for field in ("created_at", "updated_at"):
        values[field] = _maybe_dt(values[field])
    return values


def _poker_mtt_correction_values(correction: dict) -> dict:
    values = deepcopy(correction)
    if "created_at" in values and values["created_at"] is not None:
        values["created_at"] = _maybe_dt(values["created_at"])
    return values


def _poker_mtt_final_ranking_values(final_ranking: dict) -> dict:
    values = deepcopy(final_ranking)
    for field in ("locked_at", "anchorable_at", "created_at", "updated_at"):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    return values


def _poker_mtt_result_values(poker_mtt_result: dict) -> dict:
    values = deepcopy(poker_mtt_result)
    for field in ("locked_at", "anchorable_at", "created_at", "updated_at"):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    if values.get("risk_flags") is None:
        values["risk_flags"] = []
    return values


def _task_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    data["task_run_id"] = data.pop("id")
    for field in ("publish_at", "commit_deadline", "reveal_deadline", "resolve_at", "created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _submission_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("accepted_commit_at", "accepted_reveal_at", "created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _hold_entry_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("release_after", "created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _reward_window_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("window_start_at", "window_end_at", "created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _settlement_batch_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("window_start_at", "window_end_at", "created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _anchor_job_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("submitted_at", "anchored_at", "last_broadcast_at", "created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _artifact_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _risk_case_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("created_at", "updated_at", "reviewed_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _arena_result_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _poker_mtt_tournament_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    data["tournament_id"] = data.pop("id")
    for field in ("started_at", "completed_at", "created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _poker_mtt_hand_event_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _poker_mtt_hud_snapshot_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _poker_mtt_hidden_eval_entry_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _poker_mtt_rating_snapshot_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("window_start_at", "window_end_at", "created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _poker_mtt_multiplier_snapshot_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _poker_mtt_correction_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    if "created_at" in data and isinstance(data["created_at"], datetime):
        data["created_at"] = data["created_at"].isoformat().replace("+00:00", "Z")
    return data


def _poker_mtt_final_ranking_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("locked_at", "anchorable_at", "created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _poker_mtt_result_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("locked_at", "anchorable_at", "created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


class PostgresRepository:
    def __init__(self, database_url: str):
        self.engine: AsyncEngine = create_async_engine(normalize_database_url(database_url), future=True)

    async def init_schema(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            await conn.execute(text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS held_rewards INTEGER NOT NULL DEFAULT 0"))
            await conn.execute(
                text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS fast_task_opportunities INTEGER NOT NULL DEFAULT 0")
            )
            await conn.execute(text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS fast_task_misses INTEGER NOT NULL DEFAULT 0"))
            await conn.execute(text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS user_agent_hash VARCHAR NULL"))
            await conn.execute(
                text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS admission_state VARCHAR NOT NULL DEFAULT 'probation'")
            )
            await conn.execute(
                text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS poker_mtt_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0")
            )
            await conn.execute(
                text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS fast_window_start_at TIMESTAMPTZ NULL")
            )
            await conn.execute(text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS poker_mtt_user_id VARCHAR NULL"))
            await conn.execute(text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS poker_mtt_auth_source VARCHAR NULL"))
            await conn.execute(
                text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS poker_mtt_reward_bound BOOLEAN NOT NULL DEFAULT FALSE")
            )
            await conn.execute(
                text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS poker_mtt_reward_bound_at TIMESTAMPTZ NULL")
            )
            await conn.execute(
                text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS poker_mtt_is_synthetic BOOLEAN NOT NULL DEFAULT FALSE")
            )
            await conn.execute(
                text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS poker_mtt_identity_expires_at TIMESTAMPTZ NULL")
            )
            await conn.execute(
                text("ALTER TABLE miners ADD COLUMN IF NOT EXISTS poker_mtt_identity_revoked_at TIMESTAMPTZ NULL")
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_miners_poker_mtt_reward_identity "
                    "ON miners (poker_mtt_reward_bound, poker_mtt_is_synthetic, poker_mtt_identity_revoked_at)"
                )
            )
            await conn.execute(
                text("ALTER TABLE forecast_task_runs ADD COLUMN IF NOT EXISTS reward_window_id VARCHAR NULL")
            )
            await conn.execute(
                text(
                    "ALTER TABLE forecast_task_runs ADD COLUMN IF NOT EXISTS task_state VARCHAR NOT NULL DEFAULT 'reward_eligible'"
                )
            )
            await conn.execute(
                text("ALTER TABLE forecast_task_runs ADD COLUMN IF NOT EXISTS degraded_reason VARCHAR NULL")
            )
            await conn.execute(
                text("ALTER TABLE forecast_task_runs ADD COLUMN IF NOT EXISTS void_reason VARCHAR NULL")
            )
            await conn.execute(
                text("ALTER TABLE forecast_task_runs ADD COLUMN IF NOT EXISTS resolution_source VARCHAR NULL")
            )
            await conn.execute(
                text("ALTER TABLE forecast_submissions ADD COLUMN IF NOT EXISTS reward_window_id VARCHAR NULL")
            )
            await conn.execute(
                text("ALTER TABLE reward_windows ADD COLUMN IF NOT EXISTS settlement_batch_id VARCHAR NULL")
            )
            await conn.execute(
                text(
                    "ALTER TABLE reward_windows ADD COLUMN IF NOT EXISTS policy_bundle_version VARCHAR NOT NULL DEFAULT 'pb_2026_04_09_a'"
                )
            )
            await conn.execute(
                text("ALTER TABLE reward_windows ADD COLUMN IF NOT EXISTS canonical_root VARCHAR NULL")
            )
            await conn.execute(
                text("ALTER TABLE settlement_batches ADD COLUMN IF NOT EXISTS anchor_payload_json JSONB NULL")
            )
            await conn.execute(
                text("ALTER TABLE settlement_batches ADD COLUMN IF NOT EXISTS anchor_payload_hash VARCHAR NULL")
            )
            await conn.execute(
                text("ALTER TABLE settlement_batches ADD COLUMN IF NOT EXISTS anchor_job_id VARCHAR NULL")
            )
            await conn.execute(
                text(
                    "ALTER TABLE settlement_batches ADD COLUMN IF NOT EXISTS policy_bundle_version VARCHAR NOT NULL DEFAULT 'pb_2026_04_09_a'"
                )
            )
            await conn.execute(
                text("ALTER TABLE settlement_batches ADD COLUMN IF NOT EXISTS anchor_schema_version VARCHAR NULL")
            )
            await conn.execute(
                text("ALTER TABLE settlement_batches ADD COLUMN IF NOT EXISTS canonical_root VARCHAR NULL")
            )
            await conn.execute(
                text("ALTER TABLE anchor_jobs ADD COLUMN IF NOT EXISTS broadcast_status VARCHAR NULL")
            )
            await conn.execute(
                text("ALTER TABLE anchor_jobs ADD COLUMN IF NOT EXISTS broadcast_tx_hash VARCHAR NULL")
            )
            await conn.execute(
                text("ALTER TABLE anchor_jobs ADD COLUMN IF NOT EXISTS last_broadcast_at TIMESTAMPTZ NULL")
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_artifacts_entity_kind_id "
                    "ON artifacts (entity_type, entity_id, kind)"
                )
            )
            await conn.execute(text("ALTER TABLE risk_review_cases ADD COLUMN IF NOT EXISTS decision VARCHAR NULL"))
            await conn.execute(text("ALTER TABLE risk_review_cases ADD COLUMN IF NOT EXISTS decision_reason TEXT NULL"))
            await conn.execute(text("ALTER TABLE risk_review_cases ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR NULL"))
            await conn.execute(text("ALTER TABLE risk_review_cases ADD COLUMN IF NOT EXISTS authority_level VARCHAR NULL"))
            await conn.execute(text("ALTER TABLE risk_review_cases ADD COLUMN IF NOT EXISTS trace_id VARCHAR NULL"))
            await conn.execute(text("ALTER TABLE risk_review_cases ADD COLUMN IF NOT EXISTS override_log_id VARCHAR NULL"))
            await conn.execute(text("ALTER TABLE risk_review_cases ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ NULL"))
            await conn.execute(text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS economic_unit_id VARCHAR NULL"))
            await conn.execute(text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS entry_number INTEGER NULL"))
            await conn.execute(
                text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS reentry_count INTEGER NOT NULL DEFAULT 1")
            )
            await conn.execute(text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS rank_state VARCHAR NULL"))
            await conn.execute(text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS chip_delta DOUBLE PRECISION NULL"))
            await conn.execute(text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS final_ranking_id VARCHAR NULL"))
            await conn.execute(text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS standing_snapshot_id VARCHAR NULL"))
            await conn.execute(
                text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS standing_snapshot_hash VARCHAR NULL")
            )
            await conn.execute(
                text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS evidence_state VARCHAR NOT NULL DEFAULT 'pending'")
            )
            await conn.execute(text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ NULL"))
            await conn.execute(text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS anchorable_at TIMESTAMPTZ NULL"))
            await conn.execute(
                text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS anchor_state VARCHAR NOT NULL DEFAULT 'unanchored'")
            )
            await conn.execute(text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS anchor_payload_hash VARCHAR NULL"))
            await conn.execute(
                text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS risk_flags JSONB NOT NULL DEFAULT '[]'::jsonb")
            )
            await conn.execute(
                text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS no_multiplier_reason VARCHAR NULL")
            )
            await conn.execute(text("ALTER TABLE poker_mtt_final_rankings ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ NULL"))
            await conn.execute(text("ALTER TABLE poker_mtt_final_rankings ADD COLUMN IF NOT EXISTS anchorable_at TIMESTAMPTZ NULL"))
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_final_rankings_window_join "
                    "ON poker_mtt_final_rankings (id, tournament_id, miner_address, policy_bundle_version)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_hand_events_tournament_hand_no "
                    "ON poker_mtt_hand_events (tournament_id, hand_no)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_hand_events_tournament_ingest_state "
                    "ON poker_mtt_hand_events (tournament_id, ingest_state)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_hand_events_table_hand_no "
                    "ON poker_mtt_hand_events (table_id, hand_no)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_short_hud_tournament_miner "
                    "ON poker_mtt_short_term_hud_snapshots (tournament_id, miner_address)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_short_hud_miner_updated "
                    "ON poker_mtt_short_term_hud_snapshots (miner_address, updated_at)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_long_hud_tournament_miner "
                    "ON poker_mtt_long_term_hud_snapshots (tournament_id, miner_address)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_long_hud_miner_updated "
                    "ON poker_mtt_long_term_hud_snapshots (miner_address, updated_at)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_hidden_eval_tournament_miner "
                    "ON poker_mtt_hidden_eval_entries (tournament_id, miner_address)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_hidden_eval_final_ranking "
                    "ON poker_mtt_hidden_eval_entries (final_ranking_id)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_rating_miner_window "
                    "ON poker_mtt_rating_snapshots (miner_address, window_end_at)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_multiplier_miner_updated "
                    "ON poker_mtt_multiplier_snapshots (miner_address, updated_at)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_multiplier_source_result "
                    "ON poker_mtt_multiplier_snapshots (source_result_id)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_results_locked_reward_window "
                    "ON poker_mtt_result_entries (locked_at, rated_or_practice, human_only, evaluation_state)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_results_reward_window_ready "
                    "ON poker_mtt_result_entries "
                    "(locked_at, evaluation_version, evidence_state, rank_state, eligible_for_multiplier)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_poker_mtt_corrections_target "
                    "ON poker_mtt_corrections (target_entity_type, target_entity_id)"
                )
            )

    async def register_miner(self, miner: dict) -> dict:
        values = _miner_values(miner)
        async with self.engine.begin() as conn:
            exists = await conn.execute(select(miners.c.address).where(miners.c.address == miner["address"]))
            if exists.scalar_one_or_none():
                raise ValueError("miner already registered")
            await conn.execute(insert(miners).values(**values))
        return miner

    async def get_miner(self, address: str) -> dict | None:
        async with self.engine.connect() as conn:
            row = await conn.execute(select(miners).where(miners.c.address == address))
            return _row_to_dict(row.first())

    async def update_miner(self, address: str, updates: dict) -> dict:
        values = _miner_values(updates)
        async with self.engine.begin() as conn:
            await conn.execute(update(miners).where(miners.c.address == address).values(**values))
        miner = await self.get_miner(address)
        return miner or {}

    async def list_miners(self) -> list[dict]:
        async with self.engine.connect() as conn:
            rows = await conn.execute(select(miners))
            return [_row_to_dict(row) for row in rows.fetchall()]

    async def list_miners_by_addresses(self, addresses: list[str]) -> list[dict]:
        if not addresses:
            return []
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                select(miners)
                .where(miners.c.address.in_(sorted(set(addresses))))
                .order_by(miners.c.address.asc())
            )
            return [_row_to_dict(row) for row in rows.fetchall()]

    async def count_active_miners(self) -> int:
        async with self.engine.connect() as conn:
            row = await conn.execute(
                select(func.count()).select_from(miners).where(miners.c.status == "active")
            )
            return int(row.scalar_one())

    async def upsert_task(self, task: dict) -> dict:
        existing = await self.get_task(task["task_run_id"])
        values = _task_values(task)
        async with self.engine.begin() as conn:
            if existing:
                await conn.execute(
                    update(forecast_task_runs)
                    .where(forecast_task_runs.c.id == task["task_run_id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(forecast_task_runs).values(**values))
        task_row = await self.get_task(task["task_run_id"])
        return task_row or values

    async def get_task(self, task_run_id: str) -> dict | None:
        async with self.engine.connect() as conn:
            row = await conn.execute(select(forecast_task_runs).where(forecast_task_runs.c.id == task_run_id))
            return _task_row_to_dict(row.first())

    async def list_tasks(self) -> list[dict]:
        async with self.engine.connect() as conn:
            rows = await conn.execute(select(forecast_task_runs))
            return [_task_row_to_dict(row) for row in rows.fetchall()]

    async def list_due_unsettled_fast_tasks(self, now_iso: str) -> list[dict]:
        now_value = _maybe_dt(now_iso)
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                select(forecast_task_runs).where(
                    forecast_task_runs.c.lane == "forecast_15m",
                    forecast_task_runs.c.state.not_in(["settled", "resolved"]),
                    forecast_task_runs.c.resolve_at <= now_value,
                )
            )
            return [_task_row_to_dict(row) for row in rows.fetchall()]

    async def get_submission(self, task_run_id: str, miner_address: str) -> dict | None:
        async with self.engine.connect() as conn:
            row = await conn.execute(
                select(forecast_submissions).where(
                    forecast_submissions.c.task_run_id == task_run_id,
                    forecast_submissions.c.miner_address == miner_address,
                )
            )
            return _submission_row_to_dict(row.first())

    async def save_submission(self, submission: dict) -> dict:
        existing = await self.get_submission(submission["task_run_id"], submission["miner_address"])
        values = _submission_values(submission)
        async with self.engine.begin() as conn:
            if existing:
                await conn.execute(
                    update(forecast_submissions)
                    .where(
                        forecast_submissions.c.task_run_id == submission["task_run_id"],
                        forecast_submissions.c.miner_address == submission["miner_address"],
                    )
                    .values(**values)
                )
            else:
                await conn.execute(insert(forecast_submissions).values(**values))
        saved = await self.get_submission(submission["task_run_id"], submission["miner_address"])
        return saved or values

    async def list_submissions_for_task(self, task_run_id: str) -> list[dict]:
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                select(forecast_submissions).where(forecast_submissions.c.task_run_id == task_run_id)
            )
            return [_submission_row_to_dict(row) for row in rows.fetchall()]

    async def list_submissions_for_miner(self, miner_address: str, *, limit: int | None = None) -> list[dict]:
        query = (
            select(forecast_submissions)
            .where(forecast_submissions.c.miner_address == miner_address)
            .order_by(
                forecast_submissions.c.accepted_reveal_at.desc().nullslast(),
                forecast_submissions.c.updated_at.desc(),
                forecast_submissions.c.id.desc(),
            )
        )
        if limit is not None:
            query = query.limit(limit)
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_submission_row_to_dict(row) for row in rows.fetchall()]

    async def save_hold_entry(self, hold_entry: dict) -> dict:
        values = _hold_entry_values(hold_entry)
        async with self.engine.begin() as conn:
            existing = await conn.execute(select(reward_hold_entries.c.id).where(reward_hold_entries.c.id == hold_entry["id"]))
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(reward_hold_entries)
                    .where(reward_hold_entries.c.id == hold_entry["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(reward_hold_entries).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(select(reward_hold_entries).where(reward_hold_entries.c.id == hold_entry["id"]))
            return _hold_entry_row_to_dict(row.first()) or values

    async def list_hold_entries_for_miner(self, miner_address: str) -> list[dict]:
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                select(reward_hold_entries).where(reward_hold_entries.c.miner_address == miner_address)
            )
            return [_hold_entry_row_to_dict(row) for row in rows.fetchall()]

    async def list_due_hold_entries(self, now_iso: str) -> list[dict]:
        now_value = _maybe_dt(now_iso)
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                select(reward_hold_entries).where(
                    reward_hold_entries.c.state == "held",
                    reward_hold_entries.c.release_after <= now_value,
                )
            )
            return [_hold_entry_row_to_dict(row) for row in rows.fetchall()]

    async def save_reward_window(self, reward_window: dict) -> dict:
        values = _reward_window_values(reward_window)
        async with self.engine.begin() as conn:
            existing = await conn.execute(select(reward_windows.c.id).where(reward_windows.c.id == reward_window["id"]))
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(reward_windows)
                    .where(reward_windows.c.id == reward_window["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(reward_windows).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(select(reward_windows).where(reward_windows.c.id == reward_window["id"]))
            return _reward_window_row_to_dict(row.first()) or reward_window

    async def get_reward_window(self, reward_window_id: str) -> dict | None:
        async with self.engine.connect() as conn:
            row = await conn.execute(select(reward_windows).where(reward_windows.c.id == reward_window_id))
            return _reward_window_row_to_dict(row.first())

    async def list_reward_windows(self) -> list[dict]:
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                select(reward_windows).order_by(
                    reward_windows.c.window_end_at.desc(),
                    reward_windows.c.updated_at.desc(),
                    reward_windows.c.id.desc(),
                )
            )
            return [_reward_window_row_to_dict(row) for row in rows.fetchall()]

    async def save_settlement_batch(self, settlement_batch: dict) -> dict:
        values = _settlement_batch_values(settlement_batch)
        async with self.engine.begin() as conn:
            existing = await conn.execute(
                select(settlement_batches.c.id).where(settlement_batches.c.id == settlement_batch["id"])
            )
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(settlement_batches)
                    .where(settlement_batches.c.id == settlement_batch["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(settlement_batches).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(
                select(settlement_batches).where(settlement_batches.c.id == settlement_batch["id"])
            )
            return _settlement_batch_row_to_dict(row.first()) or settlement_batch

    async def get_settlement_batch(self, settlement_batch_id: str) -> dict | None:
        async with self.engine.connect() as conn:
            row = await conn.execute(
                select(settlement_batches).where(settlement_batches.c.id == settlement_batch_id)
            )
            return _settlement_batch_row_to_dict(row.first())

    async def list_settlement_batches(self) -> list[dict]:
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                select(settlement_batches).order_by(
                    settlement_batches.c.window_end_at.desc(),
                    settlement_batches.c.updated_at.desc(),
                    settlement_batches.c.id.desc(),
                )
            )
            return [_settlement_batch_row_to_dict(row) for row in rows.fetchall()]

    async def save_anchor_job(self, anchor_job: dict) -> dict:
        values = _anchor_job_values(anchor_job)
        async with self.engine.begin() as conn:
            existing = await conn.execute(select(anchor_jobs.c.id).where(anchor_jobs.c.id == anchor_job["id"]))
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(anchor_jobs)
                    .where(anchor_jobs.c.id == anchor_job["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(anchor_jobs).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(select(anchor_jobs).where(anchor_jobs.c.id == anchor_job["id"]))
            return _anchor_job_row_to_dict(row.first()) or anchor_job

    async def get_anchor_job(self, anchor_job_id: str) -> dict | None:
        async with self.engine.connect() as conn:
            row = await conn.execute(select(anchor_jobs).where(anchor_jobs.c.id == anchor_job_id))
            return _anchor_job_row_to_dict(row.first())

    async def list_anchor_jobs(self) -> list[dict]:
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                select(anchor_jobs).order_by(
                    anchor_jobs.c.updated_at.desc(),
                    anchor_jobs.c.created_at.desc(),
                    anchor_jobs.c.id.desc(),
                )
            )
            return [_anchor_job_row_to_dict(row) for row in rows.fetchall()]

    async def save_artifact(self, artifact: dict) -> dict:
        values = _artifact_values(artifact)
        async with self.engine.begin() as conn:
            existing = await conn.execute(select(artifacts.c.id).where(artifacts.c.id == artifact["id"]))
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(artifacts)
                    .where(artifacts.c.id == artifact["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(artifacts).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(select(artifacts).where(artifacts.c.id == artifact["id"]))
            return _artifact_row_to_dict(row.first()) or artifact

    async def save_artifacts_bulk(self, artifact_rows: list[dict]) -> list[dict]:
        if not artifact_rows:
            return []
        values = [_artifact_values(artifact) for artifact in artifact_rows]
        artifact_ids = [artifact["id"] for artifact in values]
        stmt = postgres_insert(artifacts).values(values)
        excluded = stmt.excluded
        update_values = {
            "kind": excluded.kind,
            "entity_type": excluded.entity_type,
            "entity_id": excluded.entity_id,
            "payload_json": excluded.payload_json,
            "payload_hash": excluded.payload_hash,
            "created_at": excluded.created_at,
            "updated_at": excluded.updated_at,
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=[artifacts.c.id],
            set_=update_values,
            where=or_(
                artifacts.c.kind.is_distinct_from(excluded.kind),
                artifacts.c.entity_type.is_distinct_from(excluded.entity_type),
                artifacts.c.entity_id.is_distinct_from(excluded.entity_id),
                artifacts.c.payload_hash.is_distinct_from(excluded.payload_hash),
                artifacts.c.payload_json.is_distinct_from(excluded.payload_json),
            ),
        )
        async with self.engine.begin() as conn:
            await conn.execute(stmt)
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                select(artifacts)
                .where(artifacts.c.id.in_(artifact_ids))
                .order_by(artifacts.c.id.asc())
            )
            return [_artifact_row_to_dict(row) for row in rows.fetchall()]

    async def get_artifact(self, artifact_id: str) -> dict | None:
        async with self.engine.connect() as conn:
            row = await conn.execute(select(artifacts).where(artifacts.c.id == artifact_id))
            return _artifact_row_to_dict(row.first())

    async def list_artifacts_for_entity(self, entity_type: str, entity_id: str) -> list[dict]:
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                select(artifacts)
                .where(artifacts.c.entity_type == entity_type, artifacts.c.entity_id == entity_id)
                .order_by(artifacts.c.updated_at.desc(), artifacts.c.created_at.desc(), artifacts.c.id.desc())
            )
            return [_artifact_row_to_dict(row) for row in rows.fetchall()]

    async def save_risk_case(self, risk_case: dict) -> dict:
        values = deepcopy(risk_case)
        for field in ("created_at", "updated_at", "reviewed_at"):
            if field in values and values[field] is not None:
                values[field] = _maybe_dt(values[field])
        async with self.engine.begin() as conn:
            existing = await conn.execute(select(risk_review_cases.c.id).where(risk_review_cases.c.id == risk_case["id"]))
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(risk_review_cases)
                    .where(risk_review_cases.c.id == risk_case["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(risk_review_cases).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(select(risk_review_cases).where(risk_review_cases.c.id == risk_case["id"]))
            return _risk_case_row_to_dict(row.first()) or values

    async def get_risk_case(self, risk_case_id: str) -> dict | None:
        async with self.engine.connect() as conn:
            row = await conn.execute(select(risk_review_cases).where(risk_review_cases.c.id == risk_case_id))
            return _risk_case_row_to_dict(row.first())

    async def list_risk_cases(
        self,
        *,
        state: str | None = None,
        miner_address: str | None = None,
        economic_unit_id: str | None = None,
    ) -> list[dict]:
        query = select(risk_review_cases)
        if state is not None:
            query = query.where(risk_review_cases.c.state == state)
        if miner_address is not None:
            query = query.where(risk_review_cases.c.miner_address == miner_address)
        if economic_unit_id is not None:
            query = query.where(risk_review_cases.c.economic_unit_id == economic_unit_id)
        query = query.order_by(risk_review_cases.c.updated_at.desc(), risk_review_cases.c.id.desc())
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_risk_case_row_to_dict(row) for row in rows.fetchall()]

    async def save_arena_result(self, arena_result: dict) -> dict:
        values = deepcopy(arena_result)
        for field in ("created_at", "updated_at"):
            if field in values and values[field] is not None:
                values[field] = _maybe_dt(values[field])
        async with self.engine.begin() as conn:
            existing = await conn.execute(select(arena_result_entries.c.id).where(arena_result_entries.c.id == arena_result["id"]))
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(arena_result_entries)
                    .where(arena_result_entries.c.id == arena_result["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(arena_result_entries).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(select(arena_result_entries).where(arena_result_entries.c.id == arena_result["id"]))
            return _arena_result_row_to_dict(row.first()) or values

    async def list_arena_results_for_miner(
        self,
        miner_address: str,
        *,
        eligible_only: bool = False,
        limit: int | None = None,
    ) -> list[dict]:
        query = select(arena_result_entries).where(arena_result_entries.c.miner_address == miner_address)
        if eligible_only:
            query = query.where(arena_result_entries.c.eligible_for_multiplier.is_(True))
        query = query.order_by(arena_result_entries.c.updated_at.desc(), arena_result_entries.c.id.desc())
        if limit is not None:
            query = query.limit(limit)
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_arena_result_row_to_dict(row) for row in rows.fetchall()]

    async def save_poker_mtt_tournament(self, tournament: dict) -> dict:
        values = _poker_mtt_tournament_values({**tournament, "id": tournament["id"]})
        async with self.engine.begin() as conn:
            existing = await conn.execute(
                select(poker_mtt_tournaments.c.id).where(poker_mtt_tournaments.c.id == tournament["id"])
            )
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(poker_mtt_tournaments)
                    .where(poker_mtt_tournaments.c.id == tournament["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(poker_mtt_tournaments).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(select(poker_mtt_tournaments).where(poker_mtt_tournaments.c.id == tournament["id"]))
            return _poker_mtt_tournament_row_to_dict(row.first()) or values

    async def get_poker_mtt_tournament(self, tournament_id: str) -> dict | None:
        async with self.engine.connect() as conn:
            row = await conn.execute(select(poker_mtt_tournaments).where(poker_mtt_tournaments.c.id == tournament_id))
            return _poker_mtt_tournament_row_to_dict(row.first())

    async def save_poker_mtt_hand_event(self, event: dict) -> dict:
        values = _poker_mtt_hand_event_values(event)
        existing = await self.get_poker_mtt_hand_event(values["hand_id"])
        if existing is None:
            if values.get("version") is None:
                return {
                    **values,
                    "state": "conflict",
                    "ingest_state": "conflict",
                    "conflict_reason": "missing_version_without_existing_event",
                }
            async with self.engine.begin() as conn:
                await conn.execute(insert(poker_mtt_hand_events).values(**values))
            saved = await self.get_poker_mtt_hand_event(values["hand_id"])
            return {**(saved or values), "state": "inserted"}

        version = values.get("version")
        if version is None:
            if values["checksum"] == existing.get("checksum"):
                return {**existing, "state": "duplicate"}
            return {
                **values,
                "state": "conflict",
                "ingest_state": "conflict",
                "conflict_reason": "missing_version_checksum_mismatch",
                "previous_event": existing,
            }

        existing_version = existing.get("version")
        if existing_version is not None and version < existing_version:
            return {**values, "state": "stale", "previous_event": existing}
        if existing_version == version:
            if values["checksum"] == existing.get("checksum"):
                return {**existing, "state": "duplicate"}
            return {
                **values,
                "state": "conflict",
                "ingest_state": "conflict",
                "conflict_reason": "same_version_checksum_mismatch",
                "previous_event": existing,
            }

        values["created_at"] = _maybe_dt(existing.get("created_at")) if existing.get("created_at") else values["created_at"]
        async with self.engine.begin() as conn:
            await conn.execute(
                update(poker_mtt_hand_events)
                .where(poker_mtt_hand_events.c.hand_id == values["hand_id"])
                .values(**values)
            )
        saved = await self.get_poker_mtt_hand_event(values["hand_id"])
        return {**(saved or values), "state": "updated", "previous_event": existing}

    async def get_poker_mtt_hand_event(self, hand_id: str) -> dict | None:
        async with self.engine.connect() as conn:
            row = await conn.execute(select(poker_mtt_hand_events).where(poker_mtt_hand_events.c.hand_id == hand_id))
            return _poker_mtt_hand_event_row_to_dict(row.first())

    async def list_poker_mtt_hand_events_for_tournament(self, tournament_id: str) -> list[dict]:
        query = (
            select(poker_mtt_hand_events)
            .where(poker_mtt_hand_events.c.tournament_id == tournament_id)
            .order_by(
                poker_mtt_hand_events.c.table_id.asc(),
                poker_mtt_hand_events.c.hand_no.asc(),
                poker_mtt_hand_events.c.hand_id.asc(),
            )
        )
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_poker_mtt_hand_event_row_to_dict(row) for row in rows.fetchall()]

    async def save_poker_mtt_mq_checkpoint(self, checkpoint: dict) -> dict:
        values = _mq_row_values(checkpoint)
        async with self.engine.begin() as conn:
            existing = await conn.execute(select(poker_mtt_mq_checkpoints.c.id).where(poker_mtt_mq_checkpoints.c.id == values["id"]))
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(poker_mtt_mq_checkpoints)
                    .where(poker_mtt_mq_checkpoints.c.id == values["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(poker_mtt_mq_checkpoints).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(select(poker_mtt_mq_checkpoints).where(poker_mtt_mq_checkpoints.c.id == values["id"]))
            return _row_to_dict(row.first()) or values

    async def list_poker_mtt_mq_checkpoints(self, *, tournament_id: str | None = None) -> list[dict]:
        query = select(poker_mtt_mq_checkpoints)
        if tournament_id is not None:
            query = query.where(poker_mtt_mq_checkpoints.c.tournament_id == tournament_id)
        query = query.order_by(
            poker_mtt_mq_checkpoints.c.topic.asc(),
            poker_mtt_mq_checkpoints.c.consumer_group.asc(),
            poker_mtt_mq_checkpoints.c.queue.asc(),
        )
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_row_to_dict(row) for row in rows.fetchall()]

    async def save_poker_mtt_mq_conflict(self, conflict: dict) -> dict:
        values = _mq_row_values(conflict)
        async with self.engine.begin() as conn:
            existing = await conn.execute(select(poker_mtt_mq_conflicts.c.id).where(poker_mtt_mq_conflicts.c.id == values["id"]))
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(poker_mtt_mq_conflicts)
                    .where(poker_mtt_mq_conflicts.c.id == values["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(poker_mtt_mq_conflicts).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(select(poker_mtt_mq_conflicts).where(poker_mtt_mq_conflicts.c.id == values["id"]))
            return _row_to_dict(row.first()) or values

    async def list_poker_mtt_mq_conflicts(
        self,
        *,
        tournament_id: str | None = None,
        state: str | None = None,
    ) -> list[dict]:
        query = select(poker_mtt_mq_conflicts)
        if tournament_id is not None:
            query = query.where(poker_mtt_mq_conflicts.c.tournament_id == tournament_id)
        if state is not None:
            query = query.where(poker_mtt_mq_conflicts.c.state == state)
        query = query.order_by(poker_mtt_mq_conflicts.c.created_at.asc(), poker_mtt_mq_conflicts.c.id.asc())
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_row_to_dict(row) for row in rows.fetchall()]

    async def save_poker_mtt_mq_dlq(self, dlq: dict) -> dict:
        values = _mq_row_values(dlq)
        async with self.engine.begin() as conn:
            existing = await conn.execute(select(poker_mtt_mq_dlq.c.id).where(poker_mtt_mq_dlq.c.id == values["id"]))
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(poker_mtt_mq_dlq)
                    .where(poker_mtt_mq_dlq.c.id == values["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(poker_mtt_mq_dlq).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(select(poker_mtt_mq_dlq).where(poker_mtt_mq_dlq.c.id == values["id"]))
            return _row_to_dict(row.first()) or values

    async def list_poker_mtt_mq_dlq(
        self,
        *,
        tournament_id: str | None = None,
        state: str | None = None,
    ) -> list[dict]:
        query = select(poker_mtt_mq_dlq)
        if tournament_id is not None:
            query = query.where(poker_mtt_mq_dlq.c.tournament_id == tournament_id)
        if state is not None:
            query = query.where(poker_mtt_mq_dlq.c.state == state)
        query = query.order_by(poker_mtt_mq_dlq.c.created_at.asc(), poker_mtt_mq_dlq.c.id.asc())
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_row_to_dict(row) for row in rows.fetchall()]

    async def save_poker_mtt_hud_snapshot(self, row: dict) -> dict:
        values = _poker_mtt_hud_snapshot_values(row)
        table = _poker_mtt_hud_snapshot_table(values["hud_window"])
        async with self.engine.begin() as conn:
            existing = await conn.execute(select(table.c.id).where(table.c.id == values["id"]))
            if existing.scalar_one_or_none():
                await conn.execute(update(table).where(table.c.id == values["id"]).values(**values))
            else:
                await conn.execute(insert(table).values(**values))
        async with self.engine.connect() as conn:
            saved = await conn.execute(select(table).where(table.c.id == values["id"]))
            return _poker_mtt_hud_snapshot_row_to_dict(saved.first()) or values

    async def list_poker_mtt_hud_snapshots(
        self,
        *,
        tournament_id: str | None = None,
        miner_address: str | None = None,
        hud_window: str | None = None,
    ) -> list[dict]:
        tables = (
            [_poker_mtt_hud_snapshot_table(hud_window)]
            if hud_window in {"short_term", "long_term"}
            else [poker_mtt_short_term_hud_snapshots, poker_mtt_long_term_hud_snapshots]
        )
        items: list[dict] = []
        async with self.engine.connect() as conn:
            for table in tables:
                query = select(table)
                if tournament_id is not None:
                    query = query.where(table.c.tournament_id == tournament_id)
                if miner_address is not None:
                    query = query.where(table.c.miner_address == miner_address)
                rows = await conn.execute(query.order_by(table.c.updated_at.desc(), table.c.id.desc()))
                items.extend(_poker_mtt_hud_snapshot_row_to_dict(row) for row in rows.fetchall())
        return [item for item in items if item is not None]

    async def save_poker_mtt_hidden_eval_entry(self, row: dict) -> dict:
        values = _poker_mtt_hidden_eval_entry_values(row)
        async with self.engine.begin() as conn:
            existing = await conn.execute(select(poker_mtt_hidden_eval_entries.c.id).where(poker_mtt_hidden_eval_entries.c.id == values["id"]))
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(poker_mtt_hidden_eval_entries)
                    .where(poker_mtt_hidden_eval_entries.c.id == values["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(poker_mtt_hidden_eval_entries).values(**values))
        async with self.engine.connect() as conn:
            saved = await conn.execute(select(poker_mtt_hidden_eval_entries).where(poker_mtt_hidden_eval_entries.c.id == values["id"]))
            return _poker_mtt_hidden_eval_entry_row_to_dict(saved.first()) or values

    async def list_poker_mtt_hidden_eval_entries_for_tournament(self, tournament_id: str) -> list[dict]:
        query = (
            select(poker_mtt_hidden_eval_entries)
            .where(poker_mtt_hidden_eval_entries.c.tournament_id == tournament_id)
            .order_by(
                poker_mtt_hidden_eval_entries.c.miner_address.asc(),
                poker_mtt_hidden_eval_entries.c.final_ranking_id.asc(),
            )
        )
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_poker_mtt_hidden_eval_entry_row_to_dict(row) for row in rows.fetchall()]

    async def save_poker_mtt_rating_snapshot(self, row: dict) -> dict:
        existing = None
        if row.get("id"):
            async with self.engine.connect() as conn:
                saved = await conn.execute(
                    select(poker_mtt_rating_snapshots).where(poker_mtt_rating_snapshots.c.id == row["id"])
                )
                existing = _poker_mtt_rating_snapshot_row_to_dict(saved.first())
        values = _poker_mtt_rating_snapshot_values(row, created_at=existing.get("created_at") if existing else None)
        async with self.engine.begin() as conn:
            existing_id = await conn.execute(
                select(poker_mtt_rating_snapshots.c.id).where(poker_mtt_rating_snapshots.c.id == values["id"])
            )
            if existing_id.scalar_one_or_none():
                await conn.execute(
                    update(poker_mtt_rating_snapshots)
                    .where(poker_mtt_rating_snapshots.c.id == values["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(poker_mtt_rating_snapshots).values(**values))
        async with self.engine.connect() as conn:
            saved = await conn.execute(
                select(poker_mtt_rating_snapshots).where(poker_mtt_rating_snapshots.c.id == values["id"])
            )
            return _poker_mtt_rating_snapshot_row_to_dict(saved.first()) or values

    async def list_poker_mtt_rating_snapshots(
        self,
        *,
        miner_address: str | None = None,
    ) -> list[dict]:
        query = select(poker_mtt_rating_snapshots)
        if miner_address is not None:
            query = query.where(poker_mtt_rating_snapshots.c.miner_address == miner_address)
        query = query.order_by(poker_mtt_rating_snapshots.c.window_end_at.desc(), poker_mtt_rating_snapshots.c.id.desc())
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_poker_mtt_rating_snapshot_row_to_dict(row) for row in rows.fetchall()]

    async def list_latest_poker_mtt_rating_snapshots_for_miners(self, miner_addresses: list[str]) -> list[dict]:
        if not miner_addresses:
            return []
        ranked = (
            select(
                *[column for column in poker_mtt_rating_snapshots.c],
                func.row_number()
                .over(
                    partition_by=poker_mtt_rating_snapshots.c.miner_address,
                    order_by=(
                        poker_mtt_rating_snapshots.c.window_end_at.desc(),
                        poker_mtt_rating_snapshots.c.id.desc(),
                    ),
                )
                .label("_snapshot_rank"),
            )
            .where(poker_mtt_rating_snapshots.c.miner_address.in_(sorted(set(miner_addresses))))
            .subquery()
        )
        query = (
            select(ranked)
            .where(ranked.c._snapshot_rank == 1)
            .order_by(ranked.c.miner_address.asc(), ranked.c.id.asc())
        )
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_poker_mtt_rating_snapshot_row_to_dict(row) for row in rows.fetchall()]

    async def save_poker_mtt_multiplier_snapshot(self, row: dict) -> dict:
        existing = None
        if row.get("id"):
            async with self.engine.connect() as conn:
                saved = await conn.execute(
                    select(poker_mtt_multiplier_snapshots).where(poker_mtt_multiplier_snapshots.c.id == row["id"])
                )
                existing = _poker_mtt_multiplier_snapshot_row_to_dict(saved.first())
        values = _poker_mtt_multiplier_snapshot_values(row, created_at=existing.get("created_at") if existing else None)
        async with self.engine.begin() as conn:
            existing_id = await conn.execute(
                select(poker_mtt_multiplier_snapshots.c.id).where(poker_mtt_multiplier_snapshots.c.id == values["id"])
            )
            if existing_id.scalar_one_or_none():
                await conn.execute(
                    update(poker_mtt_multiplier_snapshots)
                    .where(poker_mtt_multiplier_snapshots.c.id == values["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(poker_mtt_multiplier_snapshots).values(**values))
        async with self.engine.connect() as conn:
            saved = await conn.execute(
                select(poker_mtt_multiplier_snapshots).where(poker_mtt_multiplier_snapshots.c.id == values["id"])
            )
            return _poker_mtt_multiplier_snapshot_row_to_dict(saved.first()) or values

    async def list_poker_mtt_multiplier_snapshots(
        self,
        *,
        miner_address: str | None = None,
        source_result_id: str | None = None,
    ) -> list[dict]:
        query = select(poker_mtt_multiplier_snapshots)
        if miner_address is not None:
            query = query.where(poker_mtt_multiplier_snapshots.c.miner_address == miner_address)
        if source_result_id is not None:
            query = query.where(poker_mtt_multiplier_snapshots.c.source_result_id == source_result_id)
        query = query.order_by(
            poker_mtt_multiplier_snapshots.c.updated_at.desc(),
            poker_mtt_multiplier_snapshots.c.id.desc(),
        )
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_poker_mtt_multiplier_snapshot_row_to_dict(row) for row in rows.fetchall()]

    async def save_poker_mtt_final_ranking(self, final_ranking: dict) -> dict:
        values = _poker_mtt_final_ranking_values(final_ranking)
        async with self.engine.begin() as conn:
            existing = await conn.execute(
                select(poker_mtt_final_rankings.c.id).where(poker_mtt_final_rankings.c.id == final_ranking["id"])
            )
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(poker_mtt_final_rankings)
                    .where(poker_mtt_final_rankings.c.id == final_ranking["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(poker_mtt_final_rankings).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(
                select(poker_mtt_final_rankings).where(poker_mtt_final_rankings.c.id == final_ranking["id"])
            )
            return _poker_mtt_final_ranking_row_to_dict(row.first()) or values

    async def get_poker_mtt_final_ranking(self, final_ranking_id: str) -> dict | None:
        async with self.engine.connect() as conn:
            row = await conn.execute(select(poker_mtt_final_rankings).where(poker_mtt_final_rankings.c.id == final_ranking_id))
            return _poker_mtt_final_ranking_row_to_dict(row.first())

    async def list_poker_mtt_final_rankings_by_ids(self, final_ranking_ids: list[str]) -> list[dict]:
        if not final_ranking_ids:
            return []
        query = (
            select(poker_mtt_final_rankings)
            .where(poker_mtt_final_rankings.c.id.in_(sorted(set(final_ranking_ids))))
            .order_by(poker_mtt_final_rankings.c.id.asc())
        )
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_poker_mtt_final_ranking_row_to_dict(row) for row in rows.fetchall()]

    async def list_poker_mtt_final_rankings_for_tournament(self, tournament_id: str) -> list[dict]:
        query = (
            select(poker_mtt_final_rankings)
            .where(poker_mtt_final_rankings.c.tournament_id == tournament_id)
            .order_by(
                poker_mtt_final_rankings.c.rank.asc().nulls_last(),
                poker_mtt_final_rankings.c.id.asc(),
            )
        )
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_poker_mtt_final_ranking_row_to_dict(row) for row in rows.fetchall()]

    async def list_poker_mtt_final_rankings_for_window(self, window_start_at: str, window_end_at: str) -> list[dict]:
        window_start = _maybe_dt(window_start_at)
        window_end = _maybe_dt(window_end_at)
        query = (
            select(poker_mtt_final_rankings)
            .where(poker_mtt_final_rankings.c.created_at >= window_start)
            .where(poker_mtt_final_rankings.c.created_at < window_end)
            .order_by(
                poker_mtt_final_rankings.c.created_at.asc(),
                poker_mtt_final_rankings.c.id.asc(),
            )
        )
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_poker_mtt_final_ranking_row_to_dict(row) for row in rows.fetchall()]

    async def save_poker_mtt_result(self, poker_mtt_result: dict) -> dict:
        values = _poker_mtt_result_values(poker_mtt_result)
        async with self.engine.begin() as conn:
            existing = await conn.execute(
                select(poker_mtt_result_entries.c.id).where(poker_mtt_result_entries.c.id == poker_mtt_result["id"])
            )
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(poker_mtt_result_entries)
                    .where(poker_mtt_result_entries.c.id == poker_mtt_result["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(poker_mtt_result_entries).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(
                select(poker_mtt_result_entries).where(poker_mtt_result_entries.c.id == poker_mtt_result["id"])
            )
            return _poker_mtt_result_row_to_dict(row.first()) or values

    async def list_poker_mtt_results(self) -> list[dict]:
        query = select(poker_mtt_result_entries).order_by(
            poker_mtt_result_entries.c.updated_at.desc(),
            poker_mtt_result_entries.c.id.desc(),
        )
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_poker_mtt_result_row_to_dict(row) for row in rows.fetchall()]

    async def list_poker_mtt_results_for_miner(
        self,
        miner_address: str,
        *,
        eligible_only: bool = False,
        limit: int | None = None,
    ) -> list[dict]:
        query = select(poker_mtt_result_entries).where(poker_mtt_result_entries.c.miner_address == miner_address)
        if eligible_only:
            query = query.where(poker_mtt_result_entries.c.eligible_for_multiplier.is_(True))
        query = query.order_by(poker_mtt_result_entries.c.updated_at.desc(), poker_mtt_result_entries.c.id.desc())
        if limit is not None:
            query = query.limit(limit)
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_poker_mtt_result_row_to_dict(row) for row in rows.fetchall()]

    async def list_poker_mtt_results_for_reward_window(
        self,
        *,
        lane: str,
        window_start_at: datetime,
        window_end_at: datetime,
        include_provisional: bool,
        policy_bundle_version: str,
    ) -> list[dict]:
        window_start = _maybe_dt(window_start_at)
        window_end = _maybe_dt(window_end_at)
        compatible_policy_versions = poker_mtt_results.compatible_result_policy_versions(policy_bundle_version)
        query = (
            select(poker_mtt_result_entries)
            .where(poker_mtt_result_entries.c.locked_at.is_not(None))
            .where(poker_mtt_result_entries.c.locked_at >= window_start)
            .where(poker_mtt_result_entries.c.locked_at < window_end)
            .where(poker_mtt_result_entries.c.rated_or_practice == "rated")
            .where(poker_mtt_result_entries.c.human_only.is_(True))
            .where(poker_mtt_result_entries.c.evaluation_state == "final")
            .where(poker_mtt_result_entries.c.evaluation_version.in_(compatible_policy_versions))
            .where(poker_mtt_result_entries.c.evidence_state.in_(sorted(poker_mtt_results.REWARD_READY_EVIDENCE_STATES)))
            .where(poker_mtt_result_entries.c.final_ranking_id.is_not(None))
            .where(poker_mtt_result_entries.c.standing_snapshot_id.is_not(None))
            .where(poker_mtt_result_entries.c.evidence_root.is_not(None))
            .where(poker_mtt_result_entries.c.rank_state == "ranked")
            .where(poker_mtt_result_entries.c.no_multiplier_reason.is_(None))
            .where(poker_mtt_result_entries.c.eligible_for_multiplier.is_(True))
            .order_by(poker_mtt_result_entries.c.locked_at.asc(), poker_mtt_result_entries.c.id.asc())
        )
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_poker_mtt_result_row_to_dict(row) for row in rows.fetchall()]

    async def load_poker_mtt_reward_window_inputs(
        self,
        *,
        lane: str,
        window_start_at: datetime,
        window_end_at: datetime,
        include_provisional: bool,
        policy_bundle_version: str,
        current_at: datetime,
    ) -> dict:
        window_start = _maybe_dt(window_start_at)
        window_end = _maybe_dt(window_end_at)
        compatible_policy_versions = poker_mtt_results.compatible_result_policy_versions(policy_bundle_version)
        result_columns = [column.label(f"result__{column.name}") for column in poker_mtt_result_entries.c]
        final_columns = [column.label(f"final__{column.name}") for column in poker_mtt_final_rankings.c]
        miner_columns = [column.label(f"miner__{column.name}") for column in miners.c]
        query = (
            select(*result_columns, *final_columns, *miner_columns)
            .select_from(
                poker_mtt_result_entries.join(
                    poker_mtt_final_rankings,
                    poker_mtt_result_entries.c.final_ranking_id == poker_mtt_final_rankings.c.id,
                ).join(
                    miners,
                    poker_mtt_result_entries.c.miner_address == miners.c.address,
                )
            )
            .where(poker_mtt_result_entries.c.locked_at.is_not(None))
            .where(poker_mtt_result_entries.c.locked_at >= window_start)
            .where(poker_mtt_result_entries.c.locked_at < window_end)
            .where(poker_mtt_result_entries.c.rated_or_practice == "rated")
            .where(poker_mtt_result_entries.c.human_only.is_(True))
            .where(poker_mtt_result_entries.c.evaluation_state == "final")
            .where(poker_mtt_result_entries.c.evaluation_version.in_(compatible_policy_versions))
            .where(poker_mtt_result_entries.c.evidence_state.in_(sorted(poker_mtt_results.REWARD_READY_EVIDENCE_STATES)))
            .where(poker_mtt_result_entries.c.final_ranking_id.is_not(None))
            .where(poker_mtt_result_entries.c.standing_snapshot_id.is_not(None))
            .where(poker_mtt_result_entries.c.evidence_root.is_not(None))
            .where(poker_mtt_result_entries.c.rank_state == "ranked")
            .where(poker_mtt_result_entries.c.no_multiplier_reason.is_(None))
            .where(poker_mtt_result_entries.c.eligible_for_multiplier.is_(True))
            .order_by(poker_mtt_result_entries.c.locked_at.asc(), poker_mtt_result_entries.c.id.asc())
        )
        results: list[dict] = []
        final_rankings_by_id: dict[str, dict] = {}
        miners_by_address: dict[str, dict] = {}
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            for row in rows.fetchall():
                mapping = row._mapping
                result = _poker_mtt_result_row_to_dict(
                    {column.name: mapping[f"result__{column.name}"] for column in poker_mtt_result_entries.c}
                )
                final_ranking = _poker_mtt_final_ranking_row_to_dict(
                    {column.name: mapping[f"final__{column.name}"] for column in poker_mtt_final_rankings.c}
                )
                miner = _row_to_dict({column.name: mapping[f"miner__{column.name}"] for column in miners.c})
                if result:
                    results.append(result)
                if final_ranking:
                    final_rankings_by_id[final_ranking["id"]] = final_ranking
                if miner:
                    miners_by_address[miner["address"]] = miner
        miner_addresses = sorted(miners_by_address)
        rating_snapshots = await self.list_latest_poker_mtt_rating_snapshots_for_miners(miner_addresses)
        return {
            "results": results,
            "final_rankings_by_id": final_rankings_by_id,
            "miners_by_address": miners_by_address,
            "rating_snapshots_by_miner": {row["miner_address"]: row for row in rating_snapshots},
        }

    async def list_poker_mtt_closed_reward_window_candidates(
        self,
        *,
        locked_after_at: datetime,
        locked_before_at: datetime,
        policy_bundle_versions: list[str],
        limit: int = 100000,
    ) -> list[dict]:
        locked_after = _maybe_dt(locked_after_at)
        locked_before = _maybe_dt(locked_before_at)
        compatible_versions: set[str] = set()
        for policy_bundle_version in policy_bundle_versions:
            compatible_versions.update(poker_mtt_results.compatible_result_policy_versions(policy_bundle_version))
        query = (
            select(poker_mtt_result_entries)
            .where(poker_mtt_result_entries.c.locked_at.is_not(None))
            .where(poker_mtt_result_entries.c.locked_at >= locked_after)
            .where(poker_mtt_result_entries.c.locked_at < locked_before)
            .where(poker_mtt_result_entries.c.rated_or_practice == "rated")
            .where(poker_mtt_result_entries.c.human_only.is_(True))
            .where(poker_mtt_result_entries.c.evaluation_version.in_(sorted(compatible_versions)))
            .where(poker_mtt_result_entries.c.evidence_state.in_(sorted(poker_mtt_results.REWARD_READY_EVIDENCE_STATES)))
            .where(poker_mtt_result_entries.c.final_ranking_id.is_not(None))
            .where(poker_mtt_result_entries.c.standing_snapshot_id.is_not(None))
            .where(poker_mtt_result_entries.c.evidence_root.is_not(None))
            .where(poker_mtt_result_entries.c.no_multiplier_reason.is_(None))
            .where(poker_mtt_result_entries.c.eligible_for_multiplier.is_(True))
            .order_by(poker_mtt_result_entries.c.locked_at.asc(), poker_mtt_result_entries.c.id.asc())
            .limit(limit)
        )
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_poker_mtt_result_row_to_dict(row) for row in rows.fetchall()]

    async def save_poker_mtt_correction(self, correction: dict) -> dict:
        values = _poker_mtt_correction_values(correction)
        async with self.engine.begin() as conn:
            existing = await conn.execute(
                select(poker_mtt_corrections.c.id).where(poker_mtt_corrections.c.id == correction["id"])
            )
            if existing.scalar_one_or_none():
                await conn.execute(
                    update(poker_mtt_corrections)
                    .where(poker_mtt_corrections.c.id == correction["id"])
                    .values(**values)
                )
            else:
                await conn.execute(insert(poker_mtt_corrections).values(**values))
        async with self.engine.connect() as conn:
            row = await conn.execute(select(poker_mtt_corrections).where(poker_mtt_corrections.c.id == correction["id"]))
            return _poker_mtt_correction_row_to_dict(row.first()) or values

    async def list_poker_mtt_corrections(
        self,
        *,
        target_entity_type: str | None = None,
        target_entity_id: str | None = None,
    ) -> list[dict]:
        query = select(poker_mtt_corrections)
        if target_entity_type is not None:
            query = query.where(poker_mtt_corrections.c.target_entity_type == target_entity_type)
        if target_entity_id is not None:
            query = query.where(poker_mtt_corrections.c.target_entity_id == target_entity_id)
        query = query.order_by(poker_mtt_corrections.c.created_at.asc(), poker_mtt_corrections.c.id.asc())
        async with self.engine.connect() as conn:
            rows = await conn.execute(query)
            return [_poker_mtt_correction_row_to_dict(row) for row in rows.fetchall()]
