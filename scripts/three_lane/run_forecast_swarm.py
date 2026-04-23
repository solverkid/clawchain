#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPT_DIR = ROOT / "skill" / "scripts"
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(SKILL_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPT_DIR))
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

from forecast_engine import compute_commit_hash  # noqa: E402
from mine import (  # noqa: E402
    compute_heuristic_prediction,
    get_active_tasks,
    get_task_detail,
    parse_time,
    post_commit,
    post_reveal,
    resolve_request_timeout,
    sign_parts,
)

from common import DEFAULT_BUILD_DIR, DEFAULT_MANIFEST_PATH, append_jsonl, isoformat_z, load_manifest, register_manifest_miners, utc_now, write_status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a 33-miner forecast swarm against the local mining service.")
    parser.add_argument("--base-url", default="http://127.0.0.1:1317")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--skip-register-miners", action="store_true")
    parser.add_argument("--wait-seconds", type=float, default=360.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=3.0)
    parser.add_argument("--submit-request-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.1)
    parser.add_argument("--min-commit-time-remaining-seconds", type=float, default=0.2)
    parser.add_argument("--publish-safety-seconds", type=float, default=0.05)
    parser.add_argument("--commit-retry-interval-seconds", type=float, default=0.05)
    parser.add_argument("--reveal-retry-interval-seconds", type=float, default=0.05)
    parser.add_argument("--upcoming-collection-cutoff-seconds", type=float, default=0.75)
    parser.add_argument("--max-workers", type=int, default=64)
    parser.add_argument("--submit-max-workers", type=int, default=33)
    parser.add_argument("--log-file", type=Path, default=DEFAULT_BUILD_DIR / "forecast-swarm.jsonl")
    return parser.parse_args()


def _task_ready(task: dict[str, Any], *, min_commit_time_remaining_seconds: float) -> bool:
    remaining = (parse_time(task["commit_deadline"]) - datetime.now(timezone.utc)).total_seconds()
    return remaining > min_commit_time_remaining_seconds


def _find_ready_tasks(base_url: str, *, min_commit_time_remaining_seconds: float, request_config: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = get_active_tasks(base_url, config=request_config)
    return [
        task for task in tasks
        if task.get("lane") == "forecast_15m" and _task_ready(task, min_commit_time_remaining_seconds=min_commit_time_remaining_seconds)
    ]


def _find_upcoming_tasks(base_url: str, *, request_timeout_seconds: float, limit: int = 8) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            f"{base_url}/v1/forecast/task-runs/upcoming",
            params={"limit": limit},
            timeout=request_timeout_seconds,
        )
        response.raise_for_status()
        items = response.json()["data"]["items"]
    except Exception:
        return []
    return [item for item in items if item.get("lane") == "forecast_15m"]


def _collect_upcoming_tasks(
    base_url: str,
    *,
    initial_tasks: list[dict[str, Any]],
    request_timeout_seconds: float,
    poll_interval_seconds: float,
    collection_cutoff_seconds: float,
) -> list[dict[str, Any]]:
    if not initial_tasks:
        return []
    tasks_by_id = {task["task_run_id"]: task for task in initial_tasks}
    publish_at = min(parse_time(task["publish_at"]) for task in initial_tasks)
    collection_deadline = publish_at.timestamp() - max(0.0, collection_cutoff_seconds)
    while time.time() < collection_deadline:
        next_tasks = _find_upcoming_tasks(
            base_url,
            request_timeout_seconds=request_timeout_seconds,
            limit=max(8, len(tasks_by_id) + 4),
        )
        for task in next_tasks:
            tasks_by_id[task["task_run_id"]] = task
        remaining = collection_deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval_seconds, max(0.05, remaining)))
    return sorted(tasks_by_id.values(), key=lambda item: (item["publish_at"], item["task_run_id"]))


def _prepare_submission(miner: dict[str, Any], task: dict[str, Any], task_detail: dict[str, Any]) -> dict[str, Any]:
    prediction = compute_heuristic_prediction(task_detail)
    nonce = secrets.token_hex(16)
    commit_request_id = f"{task['task_run_id']}:{miner['address']}:commit:{secrets.token_hex(8)}"
    commit_hash = compute_commit_hash(task["task_run_id"], miner["address"], prediction["p_yes_bps"], nonce)
    commit_signature = sign_parts(
        miner["private_key"],
        [task["task_run_id"], commit_hash, nonce, miner["address"], commit_request_id],
    )
    reveal_request_id = f"{task['task_run_id']}:{miner['address']}:{secrets.token_hex(8)}"
    reveal_signature = sign_parts(
        miner["private_key"],
        [task["task_run_id"], str(prediction["p_yes_bps"]), nonce, miner["address"], reveal_request_id],
    )
    return {
        "miner_address": miner["address"],
        "economic_unit_id": miner["economic_unit_id"],
        "task_run_id": task["task_run_id"],
        "publish_at": task["publish_at"],
        "commit_deadline": task["commit_deadline"],
        "reveal_deadline": task["reveal_deadline"],
        "prediction": prediction,
        "commit_payload": {
            "request_id": commit_request_id,
            "task_run_id": task["task_run_id"],
            "miner_id": miner["address"],
            "economic_unit_id": miner["economic_unit_id"],
            "commit_hash": commit_hash,
            "nonce": nonce,
            "client_version": "three-lane-local-v1",
            "signature": commit_signature,
        },
        "reveal_payload": {
            "request_id": reveal_request_id,
            "task_run_id": task["task_run_id"],
            "miner_id": miner["address"],
            "economic_unit_id": miner["economic_unit_id"],
            "p_yes_bps": prediction["p_yes_bps"],
            "nonce": nonce,
            "schema_version": "v1",
            "signature": reveal_signature,
        },
    }


def _sleep_until_publish(tasks: list[dict[str, Any]], *, publish_safety_seconds: float) -> None:
    if not tasks:
        return
    publish_at = min(parse_time(task["publish_at"]) for task in tasks)
    sleep_seconds = (publish_at - datetime.now(timezone.utc)).total_seconds() + publish_safety_seconds
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)


def _commit_submission(
    base_url: str,
    prepared: dict[str, Any],
    *,
    commit_retry_interval_seconds: float,
    request_config: dict[str, Any],
) -> dict[str, Any]:
    commit_deadline = parse_time(prepared["commit_deadline"])
    base_timeout = resolve_request_timeout(request_config)
    timeout_floor = max(0.1, min(base_timeout, 1.0))
    timeout_cap = max(timeout_floor, min(base_timeout, 2.0))
    last_exc: Exception | None = None
    while True:
        remaining = (commit_deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise last_exc or RuntimeError("commit window closed")
        attempt_timeout = max(timeout_floor, min(timeout_cap, remaining - 0.05))
        try:
            commit_result = post_commit(
                base_url,
                prepared["task_run_id"],
                prepared["commit_payload"],
                config={**request_config, "request_timeout_seconds": attempt_timeout},
            )
            break
        except Exception as exc:
            last_exc = exc
            if datetime.now(timezone.utc) >= commit_deadline:
                raise
            time.sleep(max(0.01, commit_retry_interval_seconds))
    return {
        **prepared,
        "commit": commit_result,
    }


def _retryable_submission_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if response is not None and 400 <= response.status_code < 500:
        return False
    return isinstance(exc, (requests.Timeout, requests.ConnectionError)) or response is None or response.status_code >= 500


def _reveal_submission(
    base_url: str,
    committed: dict[str, Any],
    *,
    reveal_retry_interval_seconds: float,
    request_config: dict[str, Any],
) -> dict[str, Any]:
    reveal_deadline = parse_time(committed["reveal_deadline"])
    base_timeout = resolve_request_timeout(request_config)
    timeout_floor = max(0.1, min(base_timeout, 1.0))
    timeout_cap = max(timeout_floor, min(base_timeout, 2.0))
    last_exc: Exception | None = None
    while True:
        remaining = (reveal_deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise last_exc or RuntimeError("reveal window closed")
        attempt_timeout = max(timeout_floor, min(timeout_cap, remaining - 0.05))
        try:
            reveal_result = post_reveal(
                base_url,
                committed["task_run_id"],
                committed["reveal_payload"],
                config={**request_config, "request_timeout_seconds": attempt_timeout},
            )
            return {
                **committed,
                "reveal": reveal_result,
            }
        except Exception as exc:
            last_exc = exc
            if not _should_retry_reveal_error(exc):
                raise
            if datetime.now(timezone.utc) >= reveal_deadline:
                raise
            time.sleep(max(0.01, reveal_retry_interval_seconds))


def _build_submission_event(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "at": isoformat_z(utc_now()),
        "event": "forecast_submission",
        "task_run_id": result["task_run_id"],
        "miner_address": result["miner_address"],
        "p_yes_bps": result["prediction"]["p_yes_bps"],
        "provider": result["prediction"]["provider"],
        "commit_already": bool(result["commit"].get("already")),
        "reveal_already": bool(result["reveal"].get("already")),
        "commit_validation": result["commit"].get("data", {}).get("validation_status"),
        "reveal_validation": result["reveal"].get("data", {}).get("validation_status"),
        "reward_eligibility": result["reveal"].get("data", {}).get("reward_eligibility"),
    }


def _error_message(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if response is None:
        return str(exc)
    body = (getattr(response, "text", "") or "").strip()
    detail = body[:500] if body else str(exc)
    return f"http {response.status_code}: {detail}"


def _build_error_event(*, phase: str, prepared: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "at": isoformat_z(utc_now()),
        "event": "forecast_submission_error",
        "phase": phase,
        "task_run_id": prepared["task_run_id"],
        "miner_address": prepared["miner_address"],
        "p_yes_bps": prepared["prediction"]["p_yes_bps"],
        "provider": prepared["prediction"]["provider"],
        "error": _error_message(exc),
    }


def _should_attempt_reveal_after_commit_error(exc: Exception) -> bool:
    if _retryable_submission_error(exc):
        return True
    response = getattr(exc, "response", None)
    if response is None:
        return False
    if response.status_code != 400:
        return False
    body = (getattr(response, "text", "") or "").lower()
    return "commit window closed" in body


def _should_retry_reveal_error(exc: Exception) -> bool:
    return _retryable_submission_error(exc)


def _submission_worker_count(*, configured_max: int, submission_count: int, task_count: int) -> int:
    if submission_count <= 0:
        return max(1, configured_max)
    scaled_limit = max(1, configured_max) * max(1, task_count)
    return max(1, min(128, min(submission_count, scaled_limit)))


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.manifest)
    if not args.skip_register_miners:
        register_manifest_miners(
            base_url=args.base_url,
            manifest=manifest,
            log_path=args.log_file,
            manifest_path=args.manifest,
        )

    deadline = time.time() + args.wait_seconds
    ready_tasks: list[dict[str, Any]] = []
    task_details: dict[str, dict[str, Any]] = {}
    using_upcoming_preview = False
    poll_request_config = {"request_timeout_seconds": args.request_timeout_seconds}
    submit_request_config = {"request_timeout_seconds": args.submit_request_timeout_seconds}
    request_timeout_seconds = resolve_request_timeout(poll_request_config)
    while time.time() < deadline:
        ready_tasks = _find_ready_tasks(
            args.base_url,
            min_commit_time_remaining_seconds=args.min_commit_time_remaining_seconds,
            request_config=poll_request_config,
        )
        if ready_tasks:
            task_details = {
                task["task_run_id"]: get_task_detail(args.base_url, task["task_run_id"], config=poll_request_config)
                for task in ready_tasks
            }
            break
        upcoming_tasks = _find_upcoming_tasks(
            args.base_url,
            request_timeout_seconds=request_timeout_seconds,
        )
        if upcoming_tasks:
            ready_tasks = _collect_upcoming_tasks(
                args.base_url,
                initial_tasks=upcoming_tasks,
                request_timeout_seconds=request_timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
                collection_cutoff_seconds=args.upcoming_collection_cutoff_seconds,
            )
            task_details = {task["task_run_id"]: task for task in ready_tasks}
            using_upcoming_preview = True
            break
        time.sleep(args.poll_interval_seconds)
    if not ready_tasks:
        raise SystemExit("no forecast_15m tasks with enough commit time remaining")

    prepared_submissions: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as pool:
        futures = []
        for task in ready_tasks:
            detail = task_details[task["task_run_id"]]
            for miner in manifest["miners"]:
                futures.append(pool.submit(_prepare_submission, miner, task, detail))
        for future in as_completed(futures):
            prepared_submissions.append(future.result())

    if using_upcoming_preview:
        _sleep_until_publish(ready_tasks, publish_safety_seconds=args.publish_safety_seconds)

    committed_submissions: list[dict[str, Any]] = []
    reveal_candidate_submissions: list[dict[str, Any]] = []
    commit_error_count = 0
    ambiguous_commit_count = 0
    submit_worker_count = _submission_worker_count(
        configured_max=args.submit_max_workers,
        submission_count=len(prepared_submissions),
        task_count=len(ready_tasks),
    )
    with ThreadPoolExecutor(max_workers=submit_worker_count) as pool:
        futures = {
            pool.submit(
                _commit_submission,
                args.base_url,
                prepared,
                commit_retry_interval_seconds=args.commit_retry_interval_seconds,
                request_config=submit_request_config,
            ): prepared
            for prepared in prepared_submissions
        }
        for future in as_completed(futures):
            prepared = futures[future]
            try:
                committed = future.result()
                committed_submissions.append(committed)
                reveal_candidate_submissions.append(committed)
            except Exception as exc:
                commit_error_count += 1
                append_jsonl(args.log_file, _build_error_event(phase="commit", prepared=prepared, exc=exc))
                if _should_attempt_reveal_after_commit_error(exc):
                    ambiguous_commit_count += 1
                    reveal_candidate_submissions.append(
                        {
                            **prepared,
                            "commit": {
                                "already": False,
                                "data": {"validation_status": "unknown"},
                            },
                            "commit_uncertain": True,
                        }
                    )

    events: list[dict[str, Any]] = []
    reveal_error_count = 0
    with ThreadPoolExecutor(max_workers=submit_worker_count) as pool:
        futures = {
            pool.submit(
                _reveal_submission,
                args.base_url,
                committed,
                reveal_retry_interval_seconds=args.reveal_retry_interval_seconds,
                request_config=submit_request_config,
            ): committed
            for committed in reveal_candidate_submissions
        }
        for future in as_completed(futures):
            committed = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                reveal_error_count += 1
                append_jsonl(args.log_file, _build_error_event(phase="reveal", prepared=committed, exc=exc))
                continue
            event = _build_submission_event(result)
            events.append(event)
            append_jsonl(args.log_file, event)

    summary = {
        "updated_at": isoformat_z(utc_now()),
        "lane": "forecast_15m",
        "manifest_path": str(args.manifest),
        "log_file": str(args.log_file),
        "task_run_ids": [task["task_run_id"] for task in ready_tasks],
        "prepared_submission_count": len(prepared_submissions),
        "submit_worker_count": submit_worker_count,
        "commit_success_count": len(committed_submissions),
        "commit_error_count": commit_error_count,
        "ambiguous_commit_count": ambiguous_commit_count,
        "submission_count": len(events),
        "reveal_error_count": reveal_error_count,
        "miner_count": manifest["count"],
        "reward_eligible_count": sum(1 for item in events if item.get("reward_eligibility") == "eligible"),
        "used_upcoming_preview": using_upcoming_preview,
    }
    write_status(DEFAULT_BUILD_DIR / "forecast-swarm.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
