#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg

from common import DEFAULT_BUILD_DIR, DEFAULT_MANIFEST_PATH, DEFAULT_STATUS_PATH, isoformat_z, load_manifest, utc_now, write_status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check integrated three-lane local status.")
    parser.add_argument("--database-url", default="postgresql://clawchain:clawchain_dev_pw@127.0.0.1:55432/clawchain")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument("--tail-lines", type=int, default=20)
    parser.add_argument("--forecast-publish-after")
    parser.add_argument("--poker-reward-window-id")
    parser.add_argument("--arena-tournament-prefix")
    return parser.parse_args()


def _tail(path: Path, lines: int) -> list[str]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return content[-lines:]


async def _fetchrow(conn: asyncpg.Connection, sql: str, *args: Any) -> dict[str, Any] | None:
    row = await conn.fetchrow(sql, *args)
    return dict(row) if row is not None else None


def _parse_optional_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


def forecast_ready_from_metrics(
    acceptance_bucket: dict[str, Any] | None,
    latest_reward_window: dict[str, Any] | None,
    *,
    miner_count: int,
) -> bool:
    if acceptance_bucket is None:
        return False
    task_count = int(acceptance_bucket.get("task_count") or 0)
    expected_revealed_count = task_count * miner_count
    revealed_count = int(acceptance_bucket.get("revealed_count") or 0)
    resolved_task_count = int(acceptance_bucket.get("resolved_task_count") or 0)
    reward_total = int((latest_reward_window or {}).get("total_reward_amount") or 0)
    return (
        task_count > 0
        and resolved_task_count == task_count
        and revealed_count >= expected_revealed_count
        and reward_total > 0
    )


def poker_ready_from_metrics(latest_reward_window: dict[str, Any] | None, *, miner_count: int) -> bool:
    if latest_reward_window is None:
        return False
    return int(latest_reward_window.get("miner_count") or 0) >= miner_count and int(
        latest_reward_window.get("total_reward_amount") or 0
    ) > 0


def arena_ready_from_metrics(current_run: dict[str, Any] | None, *, miner_count: int) -> bool:
    if current_run is None:
        return False
    return int(current_run.get("result_count") or 0) >= miner_count and int(
        current_run.get("nondefault_multiplier_count") or 0
    ) > 0


async def collect_status(
    *,
    database_url: str,
    manifest: dict[str, Any],
    output_path: Path,
    tail_lines: int,
    forecast_publish_after: datetime | None = None,
    poker_reward_window_id: str | None = None,
    arena_tournament_prefix: str | None = None,
) -> dict[str, Any]:
    addresses = [item["address"] for item in manifest["miners"]]
    conn = await asyncpg.connect(database_url)
    try:
        miner_count = await conn.fetchval("SELECT COUNT(*) FROM miners WHERE address = ANY($1::text[])", addresses)
        forecast_submission_count = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM forecast_submissions fs
            JOIN forecast_task_runs tr ON tr.id = fs.task_run_id
            WHERE fs.miner_address = ANY($1::text[])
              AND ($2::timestamptz IS NULL OR tr.publish_at >= $2)
            """,
            addresses,
            forecast_publish_after,
        )
        latest_forecast_bucket = await _fetchrow(
            conn,
            """
            WITH latest_bucket AS (
                SELECT publish_at
                FROM forecast_task_runs
                WHERE lane = 'forecast_15m'
                  AND ($2::timestamptz IS NULL OR publish_at >= $2)
                ORDER BY publish_at DESC
                LIMIT 1
            )
            SELECT
                lb.publish_at,
                COUNT(DISTINCT tr.id) AS task_count,
                COUNT(fs.*) FILTER (WHERE fs.accepted_commit_at IS NOT NULL) AS committed_count,
                COUNT(fs.*) FILTER (WHERE fs.accepted_reveal_at IS NOT NULL) AS revealed_count,
                COUNT(DISTINCT fs.task_run_id) FILTER (WHERE fs.accepted_reveal_at IS NOT NULL) AS revealed_task_count,
                COUNT(DISTINCT fs.miner_address) FILTER (WHERE fs.accepted_reveal_at IS NOT NULL) AS revealed_miner_count,
                COUNT(DISTINCT tr.id) FILTER (WHERE tr.outcome IS NOT NULL) AS resolved_task_count,
                MAX(tr.resolve_at) AS resolve_at
            FROM latest_bucket lb
            JOIN forecast_task_runs tr
              ON tr.publish_at = lb.publish_at
             AND tr.lane = 'forecast_15m'
            LEFT JOIN forecast_submissions fs
              ON fs.task_run_id = tr.id
             AND fs.miner_address = ANY($1::text[])
            GROUP BY lb.publish_at
            """,
            addresses,
            forecast_publish_after,
        )
        latest_completed_forecast_bucket = await _fetchrow(
            conn,
            """
            WITH bucket_metrics AS (
                SELECT
                    tr.publish_at,
                    COUNT(DISTINCT tr.id) AS task_count,
                    COUNT(fs.*) FILTER (WHERE fs.accepted_commit_at IS NOT NULL) AS committed_count,
                    COUNT(fs.*) FILTER (WHERE fs.accepted_reveal_at IS NOT NULL) AS revealed_count,
                    COUNT(DISTINCT fs.task_run_id) FILTER (WHERE fs.accepted_reveal_at IS NOT NULL) AS revealed_task_count,
                    COUNT(DISTINCT fs.miner_address) FILTER (WHERE fs.accepted_reveal_at IS NOT NULL) AS revealed_miner_count,
                    COUNT(DISTINCT tr.id) FILTER (WHERE tr.outcome IS NOT NULL) AS resolved_task_count,
                    MAX(tr.resolve_at) AS resolve_at
                FROM forecast_task_runs tr
                LEFT JOIN forecast_submissions fs
                  ON fs.task_run_id = tr.id
                 AND fs.miner_address = ANY($1::text[])
                WHERE tr.lane = 'forecast_15m'
                  AND ($2::timestamptz IS NULL OR tr.publish_at >= $2)
                GROUP BY tr.publish_at
            )
            SELECT *
            FROM bucket_metrics
            WHERE task_count > 0
              AND resolved_task_count = task_count
              AND revealed_count >= task_count * $3::int
            ORDER BY publish_at DESC
            LIMIT 1
            """,
            addresses,
            forecast_publish_after,
            manifest["count"],
        )
        latest_fully_revealed_forecast_bucket = await _fetchrow(
            conn,
            """
            WITH bucket_metrics AS (
                SELECT
                    tr.publish_at,
                    COUNT(DISTINCT tr.id) AS task_count,
                    COUNT(fs.*) FILTER (WHERE fs.accepted_commit_at IS NOT NULL) AS committed_count,
                    COUNT(fs.*) FILTER (WHERE fs.accepted_reveal_at IS NOT NULL) AS revealed_count,
                    COUNT(DISTINCT fs.task_run_id) FILTER (WHERE fs.accepted_reveal_at IS NOT NULL) AS revealed_task_count,
                    COUNT(DISTINCT fs.miner_address) FILTER (WHERE fs.accepted_reveal_at IS NOT NULL) AS revealed_miner_count,
                    COUNT(DISTINCT tr.id) FILTER (WHERE tr.outcome IS NOT NULL) AS resolved_task_count,
                    MAX(tr.resolve_at) AS resolve_at
                FROM forecast_task_runs tr
                LEFT JOIN forecast_submissions fs
                  ON fs.task_run_id = tr.id
                 AND fs.miner_address = ANY($1::text[])
                WHERE tr.lane = 'forecast_15m'
                  AND ($2::timestamptz IS NULL OR tr.publish_at >= $2)
                GROUP BY tr.publish_at
            )
            SELECT *
            FROM bucket_metrics
            WHERE task_count > 0
              AND revealed_count >= task_count * $3::int
            ORDER BY publish_at DESC
            LIMIT 1
            """,
            addresses,
            forecast_publish_after,
            manifest["count"],
        )
        latest_forecast_window = await _fetchrow(
            conn,
            """
            WITH latest_completed_bucket AS (
                SELECT publish_at
                FROM (
                    SELECT
                        tr.publish_at,
                        COUNT(DISTINCT tr.id) AS task_count,
                        COUNT(fs.*) FILTER (WHERE fs.accepted_reveal_at IS NOT NULL) AS revealed_count,
                        COUNT(DISTINCT tr.id) FILTER (WHERE tr.outcome IS NOT NULL) AS resolved_task_count
                    FROM forecast_task_runs tr
                    LEFT JOIN forecast_submissions fs
                      ON fs.task_run_id = tr.id
                     AND fs.miner_address = ANY($1::text[])
                    WHERE tr.lane = 'forecast_15m'
                      AND ($2::timestamptz IS NULL OR tr.publish_at >= $2)
                    GROUP BY tr.publish_at
                ) bucket_metrics
                WHERE task_count > 0
                  AND resolved_task_count = task_count
                  AND revealed_count >= task_count * $3::int
                ORDER BY publish_at DESC
                LIMIT 1
            ),
            bucket_tasks AS (
                SELECT tr.id, tr.reward_window_id
                FROM forecast_task_runs tr
                JOIN latest_completed_bucket lb
                  ON tr.publish_at = lb.publish_at
                 AND tr.lane = 'forecast_15m'
            ),
            bucket_reward_windows AS (
                SELECT DISTINCT COALESCE(fs.reward_window_id, bt.reward_window_id) AS reward_window_id
                FROM bucket_tasks bt
                LEFT JOIN forecast_submissions fs
                  ON fs.task_run_id = bt.id
                 AND fs.miner_address = ANY($1::text[])
                WHERE COALESCE(fs.reward_window_id, bt.reward_window_id) IS NOT NULL
            )
            SELECT rw.id, rw.state, rw.miner_count, rw.total_reward_amount, rw.updated_at
            FROM bucket_reward_windows brw
            JOIN reward_windows rw
              ON rw.id = brw.reward_window_id
            ORDER BY rw.updated_at DESC
            LIMIT 1
            """,
            addresses,
            forecast_publish_after,
            manifest["count"],
        )
        latest_poker_window = await _fetchrow(
            conn,
            """
            SELECT id, lane, state, miner_count, total_reward_amount, settlement_batch_id, updated_at
            FROM reward_windows
            WHERE ($1::text IS NULL AND lane LIKE 'poker_mtt_%')
               OR id = $1
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            poker_reward_window_id,
        )
        latest_arena_result = None
        current_run_arena = None
        try:
            latest_arena_result = await _fetchrow(
                conn,
                """
                SELECT tournament_id, miner_address, multiplier_after, updated_at
                FROM arena_result_entries
                WHERE miner_address = ANY($1::text[])
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                addresses,
            )
            current_run_arena = await _fetchrow(
                conn,
                """
                SELECT
                    COUNT(DISTINCT miner_address) AS result_count,
                    COUNT(DISTINCT miner_address) FILTER (WHERE ABS(multiplier_after - 1.0) > 1e-9) AS nondefault_multiplier_count,
                    MAX(updated_at) AS updated_at
                FROM arena_result_entries
                WHERE miner_address = ANY($1::text[])
                  AND ($2::text IS NULL OR tournament_id LIKE ($2 || '%'))
                """,
                addresses,
                arena_tournament_prefix,
            )
        except Exception as exc:  # noqa: BLE001
            latest_arena_result = {"error": str(exc)}
            current_run_arena = {"error": str(exc), "result_count": 0, "nondefault_multiplier_count": 0}
        latest_settlement_batch = await _fetchrow(
            conn,
            """
            SELECT id, lane, state, miner_count, total_reward_amount, updated_at
            FROM settlement_batches
            ORDER BY updated_at DESC
            LIMIT 1
            """,
        )
    finally:
        await conn.close()

    build_dir = DEFAULT_BUILD_DIR
    forecast_ready = forecast_ready_from_metrics(
        latest_completed_forecast_bucket,
        latest_forecast_window,
        miner_count=manifest["count"],
    )
    poker_ready = poker_ready_from_metrics(latest_poker_window, miner_count=manifest["count"])
    arena_ready = arena_ready_from_metrics(current_run_arena, miner_count=manifest["count"])
    all_ready = forecast_ready and poker_ready and arena_ready

    payload = {
        "updated_at": isoformat_z(utc_now()),
        "manifest_path": str(manifest.get("manifest_path") or ""),
        "manifest_root": manifest["manifest_root"],
        "miner_count": manifest["count"],
        "registered_miner_count": int(miner_count or 0),
        "scope": {
            "forecast_publish_after": isoformat_z(forecast_publish_after) if forecast_publish_after else None,
            "poker_reward_window_id": poker_reward_window_id,
            "arena_tournament_prefix": arena_tournament_prefix,
        },
        "forecast": {
            "submission_count": int(forecast_submission_count or 0),
            "latest_bucket": latest_forecast_bucket,
            "latest_completed_bucket": latest_completed_forecast_bucket,
            "latest_fully_revealed_bucket": latest_fully_revealed_forecast_bucket,
            "latest_reward_window": latest_forecast_window,
            "expected_revealed_count": int((latest_forecast_bucket or {}).get("task_count") or 0) * manifest["count"],
            "latest_completed_expected_revealed_count": int(
                (latest_completed_forecast_bucket or {}).get("task_count") or 0
            )
            * manifest["count"],
            "latest_fully_revealed_expected_revealed_count": int(
                (latest_fully_revealed_forecast_bucket or {}).get("task_count") or 0
            )
            * manifest["count"],
            "ready": forecast_ready,
            "log_tail": _tail(build_dir / "forecast-swarm.jsonl", tail_lines),
            "service_log_tail": _tail(build_dir / "forecast-service.log", tail_lines),
        },
        "poker": {
            "latest_reward_window": latest_poker_window,
            "ready": poker_ready,
            "log_tail": _tail(build_dir / "poker-round.jsonl", tail_lines),
        },
        "arena": {
            "current_run": current_run_arena,
            "latest_result": latest_arena_result,
            "ready": arena_ready,
            "log_tail": _tail(build_dir / "arena-runtime.log", tail_lines),
        },
        "latest_settlement_batch": latest_settlement_batch,
        "all_ready": all_ready,
    }
    write_status(output_path, payload)
    return payload


async def main_async(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    manifest["manifest_path"] = str(args.manifest)
    payload = await collect_status(
        database_url=args.database_url,
        manifest=manifest,
        output_path=args.output,
        tail_lines=args.tail_lines,
        forecast_publish_after=_parse_optional_time(args.forecast_publish_after),
        poker_reward_window_id=args.poker_reward_window_id,
        arena_tournament_prefix=args.arena_tournament_prefix,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["all_ready"] else 1


def main() -> int:
    return asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
