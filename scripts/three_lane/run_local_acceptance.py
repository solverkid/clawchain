#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import ExitStack
from pathlib import Path

import asyncpg

from check_status import collect_status
from common import DEFAULT_BUILD_DIR, DEFAULT_MANIFEST_PATH, isoformat_z, load_or_create_manifest, utc_now, write_status


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local three-lane acceptance flow.")
    parser.add_argument("--database-url", default="postgresql://clawchain:clawchain_dev_pw@127.0.0.1:55432/clawchain")
    parser.add_argument("--forecast-base-url", default="http://127.0.0.1:1317")
    parser.add_argument("--arena-base-url", default="http://127.0.0.1:18117")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--miner-count", type=int, default=33)
    parser.add_argument("--namespace", default="three-lane-local-v1")
    parser.add_argument("--arena-target-tournaments", type=int, default=16)
    parser.add_argument("--acceptance-timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--forecast-wait-seconds", type=float, default=1200.0)
    parser.add_argument("--forecast-submit-max-workers", type=int, default=33)
    parser.add_argument("--admin-reconcile-interval-seconds", type=float, default=15.0)
    parser.add_argument("--arena-attempt-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--arena-runner-concurrency", type=int, default=8)
    parser.add_argument("--arena-cycle-delay-ms", type=int, default=75)
    parser.add_argument("--arena-http-timeout-seconds", type=int, default=45)
    parser.add_argument("--leave-stack-running", action="store_true")
    return parser.parse_args()


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(cmd, cwd=ROOT, env=env, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(cmd)}")


def _run_allow_nonzero(cmd: list[str], *, env: dict[str, str] | None = None) -> int:
    result = subprocess.run(cmd, cwd=ROOT, env=env, text=True)
    return result.returncode


def _run_background(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    stdout=None,
    stderr=None,
) -> subprocess.Popen[str]:
    return subprocess.Popen(cmd, cwd=ROOT, env=env, text=True, stdout=stdout, stderr=stderr)


def _pkill(pattern: str) -> None:
    subprocess.run(
        ["pkill", "-f", pattern],
        cwd=ROOT,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _terminate_process(process: subprocess.Popen[str] | None, *, timeout_seconds: float = 10.0) -> int | None:
    if process is None:
        return None
    exit_code = process.poll()
    if exit_code is not None:
        return exit_code
    process.terminate()
    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait(timeout=timeout_seconds)


def _terminate_pid_file_process(pid_path: Path, *, timeout_seconds: float = 10.0) -> bool:
    if not pid_path.exists():
        return False
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError:
        pid_path.unlink(missing_ok=True)
        return False
    if pid <= 0:
        pid_path.unlink(missing_ok=True)
        return False

    def process_running() -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    if not process_running():
        pid_path.unlink(missing_ok=True)
        return False

    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pid_path.unlink(missing_ok=True)
            return False

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not process_running():
            pid_path.unlink(missing_ok=True)
            return True
        time.sleep(0.2)

    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    pid_path.unlink(missing_ok=True)
    return True


def _read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def should_restart_forecast_swarm(summary: dict[str, object]) -> bool:
    if bool(summary.get("forecast_ready")):
        return False
    return not bool(summary.get("forecast_capture_ready"))


def should_admin_reconcile_forecast(summary: dict[str, object]) -> bool:
    return bool(summary.get("forecast_capture_ready")) and not bool(summary.get("forecast_ready"))


def build_poker_round_command(
    *,
    base_url: str,
    manifest: Path,
    tournament_id: str,
    request_timeout_seconds: float = 180.0,
) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT_DIR / "run_poker_round.py"),
        "--base-url",
        base_url,
        "--manifest",
        str(manifest),
        "--tournament-id",
        tournament_id,
        "--request-timeout-seconds",
        str(request_timeout_seconds),
    ]


def post_admin_reconcile(base_url: str, *, timeout_seconds: float = 5.0) -> dict[str, object]:
    request = urllib.request.Request(f"{base_url}/admin/reconcile", data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - local harness URL.
        return json.loads(response.read().decode("utf-8"))


async def _seed_arena_warmup_history(database_url: str, manifest: dict[str, object]) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        addresses = [item["address"] for item in manifest["miners"]]
        registered = int(
            await conn.fetchval("SELECT COUNT(*) FROM miners WHERE address = ANY($1::text[])", addresses) or 0
        )
        if registered != len(addresses):
            raise RuntimeError(f"expected {len(addresses)} shared miners before warmup seed, found {registered}")

        seeded_at = utc_now().replace(microsecond=0)
        warm_tournament_id = f"warm:{manifest['manifest_root']}"
        for address in addresses:
            state_hash = f"warm-state:{address}"
            await conn.execute(
                """
                INSERT INTO rating_state_current (
                    miner_address,
                    mu,
                    sigma,
                    arena_reliability,
                    public_elo,
                    payload,
                    schema_version,
                    policy_bundle_version,
                    state_hash,
                    payload_hash,
                    artifact_ref,
                    updated_at
                ) VALUES ($1, 25, 8.333333, 1, 1200, '{}'::jsonb, 1, 'v1', $2, $2, '', $3)
                ON CONFLICT (miner_address) DO UPDATE
                SET updated_at = EXCLUDED.updated_at
                """,
                address,
                state_hash,
                seeded_at,
            )

            for index in range(15):
                snapshot_id = f"warm-mult:{address}:{index:02d}"
                await conn.execute(
                    """
                    INSERT INTO arena_multiplier_snapshot (
                        snapshot_id,
                        tournament_id,
                        miner_address,
                        eligible_for_multiplier,
                        tournament_score,
                        confidence_weight,
                        multiplier_before,
                        multiplier_after,
                        payload,
                        schema_version,
                        policy_bundle_version,
                        state_hash,
                        payload_hash,
                        artifact_ref,
                        created_at
                    ) VALUES (
                        $1, $2, $3, TRUE, 0.6, 1.0, 1.0, 1.0, '{}'::jsonb, 1, 'v1', $1, $1, '', $4
                    )
                    ON CONFLICT (snapshot_id) DO NOTHING
                    """,
                    snapshot_id,
                    warm_tournament_id,
                    address,
                    seeded_at,
                )
    finally:
        await conn.close()


def main() -> int:
    args = parse_args()
    manifest = load_or_create_manifest(args.manifest, count=args.miner_count, namespace=args.namespace)
    run_started_at = utc_now().replace(microsecond=0)
    run_id = run_started_at.strftime("%Y%m%d%H%M%S")
    poker_tournament_id = f"local-poker-{run_id}"
    arena_tournament_prefix = f"tour:wave-three-lane-{run_id}-"
    acceptance_log_path = DEFAULT_BUILD_DIR / "local-acceptance.log"
    forecast_stdout_path = DEFAULT_BUILD_DIR / "forecast-swarm.stdout.log"
    DEFAULT_BUILD_DIR.mkdir(parents=True, exist_ok=True)

    with ExitStack() as stack:
        acceptance_log = stack.enter_context(acceptance_log_path.open("a", encoding="utf-8"))
        forecast_stdout = stack.enter_context(forecast_stdout_path.open("a", encoding="utf-8"))
        acceptance_log.write(f"{isoformat_z(run_started_at)} run_start run_id={run_id}\n")
        acceptance_log.flush()

        _run(
            [
                sys.executable,
                str(SCRIPT_DIR / "start_local_stack.py"),
                "--database-url",
                args.database_url,
                "--forecast-base-url",
                args.forecast_base_url,
                "--arena-base-url",
                args.arena_base_url,
                "--manifest",
                str(args.manifest),
                "--miner-count",
                str(args.miner_count),
                "--namespace",
                args.namespace,
            ]
        )
        if not args.leave_stack_running:
            stack.callback(_terminate_pid_file_process, DEFAULT_BUILD_DIR / "forecast-service.pid")
            stack.callback(_terminate_pid_file_process, DEFAULT_BUILD_DIR / "arena-runtime.pid")
        acceptance_log.write(f"{isoformat_z(utc_now())} stack_ready\n")
        acceptance_log.flush()

        _run(
            build_poker_round_command(
                base_url=args.forecast_base_url,
                manifest=args.manifest,
                tournament_id=poker_tournament_id,
            )
        )
        poker_summary = _read_json(DEFAULT_BUILD_DIR / "poker-round.json") or {}
        poker_reward_window_id = str(poker_summary.get("reward_window_id") or f"rw:poker_mtt_daily:{poker_tournament_id}")
        acceptance_log.write(f"{isoformat_z(utc_now())} poker_round_done\n")
        acceptance_log.flush()

        asyncio.run(_seed_arena_warmup_history(args.database_url, manifest))
        acceptance_log.write(f"{isoformat_z(utc_now())} arena_warmup_seeded\n")
        acceptance_log.flush()

        _pkill("scripts/three_lane/run_forecast_swarm.py")
        _pkill("cmd/arena-swarm")

        forecast_proc: subprocess.Popen[str] | None = None
        forecast_exit_code: int | None = None
        arena_proc: subprocess.Popen[str] | None = None
        arena_exit_code: int | None = None
        arena_started_at = 0.0
        arena_attempt = 0
        deadline = time.time() + args.acceptance_timeout_seconds
        last_heartbeat_at = 0.0
        last_admin_reconcile_at = 0.0
        all_ready = False

        def start_forecast_swarm() -> subprocess.Popen[str]:
            forecast_cmd = [
                sys.executable,
                str(SCRIPT_DIR / "run_forecast_swarm.py"),
                "--base-url",
                args.forecast_base_url,
                "--manifest",
                str(args.manifest),
                "--skip-register-miners",
                "--wait-seconds",
                str(args.forecast_wait_seconds),
                "--request-timeout-seconds",
                "3",
                "--submit-request-timeout-seconds",
                "8",
                "--poll-interval-seconds",
                "0.1",
                "--min-commit-time-remaining-seconds",
                "0.2",
                "--upcoming-collection-cutoff-seconds",
                "0.75",
                "--max-workers",
                "64",
                "--submit-max-workers",
                str(args.forecast_submit_max_workers),
            ]
            return _run_background(
                forecast_cmd,
                env=os.environ.copy(),
                stdout=forecast_stdout,
                stderr=subprocess.STDOUT,
            )

        def start_arena_attempt(attempt: int) -> subprocess.Popen[str]:
            log_file = DEFAULT_BUILD_DIR / f"arena-swarm-{run_id}-{attempt:02d}.jsonl"
            acceptance_log.write(
                f"{isoformat_z(utc_now())} arena_attempt_start attempt={attempt} log_file={log_file.name}\n"
            )
            acceptance_log.flush()
            return _run_background(
                [
                    "go",
                    "run",
                    "./cmd/arena-swarm",
                    "--base-url",
                    args.arena_base_url,
                    "--policy",
                    "heuristic",
                    "--miner-ids-file",
                    str(args.manifest),
                    "--log-file",
                    str(log_file),
                    "--wave-id",
                    f"wave-three-lane-{run_id}-{attempt:02d}",
                    "--max-steps",
                    "5000",
                    "--max-idle-cycles",
                    "20",
                    "--arm-time-cap",
                    "--runner-concurrency",
                    str(args.arena_runner_concurrency),
                    "--cycle-delay-ms",
                    str(args.arena_cycle_delay_ms),
                    "--http-timeout-seconds",
                    str(args.arena_http_timeout_seconds),
                ],
                env=os.environ.copy(),
                stdout=acceptance_log,
                stderr=subprocess.STDOUT,
            )

        try:
            forecast_proc = start_forecast_swarm()
            acceptance_log.write(f"{isoformat_z(utc_now())} forecast_swarm_started\n")
            acceptance_log.flush()

            while time.time() < deadline:
                scoped_status = asyncio.run(
                    collect_status(
                        database_url=args.database_url,
                        manifest={**manifest, "manifest_path": str(args.manifest)},
                        output_path=DEFAULT_BUILD_DIR / "status.json",
                        tail_lines=20,
                        forecast_publish_after=run_started_at,
                        poker_reward_window_id=poker_reward_window_id,
                        arena_tournament_prefix=arena_tournament_prefix,
                    )
                )
                summary = {
                    "forecast_submission_count": int(scoped_status["forecast"]["submission_count"]),
                    "forecast_reward_total": int(
                        ((scoped_status["forecast"]["latest_reward_window"] or {}).get("total_reward_amount") or 0)
                    ),
                    "forecast_ready": bool(scoped_status["forecast"]["ready"]),
                    "forecast_capture_ready": bool(scoped_status["forecast"]["latest_fully_revealed_bucket"]),
                    "forecast_revealed_count": int(
                        ((scoped_status["forecast"]["latest_bucket"] or {}).get("revealed_count") or 0)
                    ),
                    "forecast_expected_revealed_count": int(scoped_status["forecast"]["expected_revealed_count"] or 0),
                    "forecast_capture_publish_at": (
                        (scoped_status["forecast"]["latest_fully_revealed_bucket"] or {}).get("publish_at")
                    ),
                    "poker_ready": bool(scoped_status["poker"]["ready"]),
                    "arena_ready": bool(scoped_status["arena"]["ready"]),
                    "arena_result_count": int(((scoped_status["arena"]["current_run"] or {}).get("result_count") or 0)),
                    "arena_nondefault_count": int(
                        ((scoped_status["arena"]["current_run"] or {}).get("nondefault_multiplier_count") or 0)
                    ),
                }
                now = time.time()
                if now - last_heartbeat_at >= args.poll_interval_seconds:
                    acceptance_log.write(
                        (
                            f"{isoformat_z(utc_now())} heartbeat "
                            f"forecast_submissions={summary['forecast_submission_count']} "
                            f"forecast_revealed={summary['forecast_revealed_count']}/{summary['forecast_expected_revealed_count']} "
                            f"forecast_reward_total={summary['forecast_reward_total']} "
                            f"forecast_capture_ready={summary['forecast_capture_ready']} "
                            f"forecast_capture_publish_at={summary['forecast_capture_publish_at'] or '-'} "
                            f"arena_results={summary['arena_result_count']} "
                            f"arena_nondefault={summary['arena_nondefault_count']} "
                            f"poker_ready={summary['poker_ready']}\n"
                        )
                    )
                    acceptance_log.flush()
                    last_heartbeat_at = now

                all_ready = bool(summary["forecast_ready"] and summary["poker_ready"] and summary["arena_ready"])
                if all_ready:
                    break

                if should_admin_reconcile_forecast(summary) and (
                    now - last_admin_reconcile_at >= args.admin_reconcile_interval_seconds
                ):
                    try:
                        result = post_admin_reconcile(args.forecast_base_url)
                    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
                        acceptance_log.write(
                            f"{isoformat_z(utc_now())} admin_reconcile_failed error={type(exc).__name__}:{exc}\n"
                        )
                    else:
                        acceptance_log.write(
                            (
                                f"{isoformat_z(utc_now())} admin_reconcile_done "
                                f"task_count={result.get('task_count')} "
                                f"reward_window_count={result.get('reward_window_count')} "
                                f"settlement_batch_count={result.get('settlement_batch_count')}\n"
                            )
                        )
                    acceptance_log.flush()
                    last_admin_reconcile_at = now

                if forecast_proc is not None:
                    forecast_exit_code = forecast_proc.poll()
                    if forecast_exit_code is not None:
                        acceptance_log.write(
                            f"{isoformat_z(utc_now())} forecast_exit exit_code={forecast_exit_code}\n"
                        )
                        acceptance_log.flush()
                        forecast_proc = None

                if forecast_proc is None and should_restart_forecast_swarm(summary):
                    forecast_proc = start_forecast_swarm()
                    forecast_exit_code = None
                    acceptance_log.write(f"{isoformat_z(utc_now())} forecast_swarm_restarted\n")
                    acceptance_log.flush()

                if arena_proc is not None:
                    arena_exit_code = arena_proc.poll()
                    if arena_exit_code is not None:
                        acceptance_log.write(
                            f"{isoformat_z(utc_now())} arena_attempt_done attempt={arena_attempt} exit_code={arena_exit_code}\n"
                        )
                        acceptance_log.flush()
                        arena_proc = None
                    elif now - arena_started_at >= args.arena_attempt_timeout_seconds:
                        arena_exit_code = _terminate_process(arena_proc, timeout_seconds=10)
                        arena_proc = None
                        acceptance_log.write(
                            f"{isoformat_z(utc_now())} arena_attempt_timeout attempt={arena_attempt} exit_code={arena_exit_code}\n"
                        )
                        acceptance_log.flush()

                if arena_proc is None and not summary["arena_ready"] and arena_attempt < args.arena_target_tournaments:
                    arena_attempt += 1
                    arena_proc = start_arena_attempt(arena_attempt)
                    arena_started_at = time.time()
                    arena_exit_code = None

                time.sleep(min(args.poll_interval_seconds, max(0.1, deadline - time.time())))
        finally:
            forecast_exit_code = _terminate_process(forecast_proc, timeout_seconds=10)
            arena_exit_code = _terminate_process(arena_proc, timeout_seconds=10)
            if forecast_exit_code is not None:
                acceptance_log.write(f"{isoformat_z(utc_now())} forecast_exit exit_code={forecast_exit_code}\n")
            if arena_exit_code is not None:
                acceptance_log.write(
                    f"{isoformat_z(utc_now())} arena_attempt_done attempt={arena_attempt} exit_code={arena_exit_code}\n"
                )
            acceptance_log.flush()

    status_path = DEFAULT_BUILD_DIR / "acceptance.json"
    status = {
        "updated_at": isoformat_z(utc_now()),
        "manifest_path": str(args.manifest),
        "miner_count": manifest["count"],
        "forecast_base_url": args.forecast_base_url,
        "arena_base_url": args.arena_base_url,
        "database_url": args.database_url,
        "run_id": run_id,
        "forecast_publish_after": isoformat_z(run_started_at),
        "poker_reward_window_id": poker_reward_window_id,
        "arena_tournament_prefix": arena_tournament_prefix,
        "acceptance_log_path": str(acceptance_log_path),
        "forecast_stdout_path": str(forecast_stdout_path),
    }
    write_status(status_path, status)

    env = os.environ.copy()
    check_exit = _run_allow_nonzero(
        [
            sys.executable,
            str(SCRIPT_DIR / "check_status.py"),
            "--database-url",
            args.database_url,
            "--manifest",
            str(args.manifest),
            "--forecast-publish-after",
            isoformat_z(run_started_at),
            "--poker-reward-window-id",
            poker_reward_window_id,
            "--arena-tournament-prefix",
            arena_tournament_prefix,
        ],
        env=env,
    )
    if check_exit not in {0, 1}:
        raise RuntimeError(f"check_status failed with exit code {check_exit}")
    if check_exit != 0 or not all_ready:
        raise RuntimeError("three-lane acceptance did not reach all-ready state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
