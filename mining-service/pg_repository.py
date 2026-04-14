from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from sqlalchemy import insert, select, update, func, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

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
    for field in ("created_at", "updated_at", "fast_window_start_at"):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    return values


def _poker_mtt_tournament_values(tournament: dict) -> dict:
    values = deepcopy(tournament)
    for field in ("started_at", "completed_at", "created_at", "updated_at"):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    return values


def _poker_mtt_final_ranking_values(final_ranking: dict) -> dict:
    values = deepcopy(final_ranking)
    for field in ("created_at", "updated_at"):
        if field in values and values[field] is not None:
            values[field] = _maybe_dt(values[field])
    return values


def _poker_mtt_result_values(poker_mtt_result: dict) -> dict:
    values = deepcopy(poker_mtt_result)
    for field in ("locked_at", "created_at", "updated_at"):
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


def _poker_mtt_final_ranking_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("created_at", "updated_at"):
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].isoformat().replace("+00:00", "Z")
    return data


def _poker_mtt_result_row_to_dict(row) -> dict | None:
    data = _row_to_dict(row)
    if not data:
        return None
    for field in ("locked_at", "created_at", "updated_at"):
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
            await conn.execute(text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS final_ranking_id VARCHAR NULL"))
            await conn.execute(text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS standing_snapshot_id VARCHAR NULL"))
            await conn.execute(
                text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS standing_snapshot_hash VARCHAR NULL")
            )
            await conn.execute(
                text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS evidence_state VARCHAR NOT NULL DEFAULT 'pending'")
            )
            await conn.execute(text("ALTER TABLE poker_mtt_result_entries ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ NULL"))
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
