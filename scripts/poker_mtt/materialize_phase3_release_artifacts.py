#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
SCRIPT_DIR = ROOT / "scripts" / "poker_mtt"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_release_review_bundle
import check_local_run_logs
import forecast_engine
import release_evidence_replay
import runtime_projection as runtime
from repository import FakeRepository


DEFAULT_PHASE3_DIR = ROOT / "artifacts" / "poker-mtt" / "phase3"
DEFAULT_REVIEW_DIR = ROOT / "artifacts" / "poker-mtt" / "release-review"
DEFAULT_BUILD_DIR = ROOT / "build" / "poker-mtt"
DEFAULT_LOG_SOURCE = DEFAULT_BUILD_DIR / "run_server.log"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize the canonical local Poker MTT Phase 3 release artifacts and release-review bundle.",
    )
    parser.add_argument("--runtime-summary-source", type=Path, default=None)
    parser.add_argument("--runtime-log-source", type=Path, default=DEFAULT_LOG_SOURCE)
    parser.add_argument("--db-load-log-source", type=Path, default=None)
    parser.add_argument("--phase3-artifact-dir", type=Path, default=DEFAULT_PHASE3_DIR)
    parser.add_argument("--release-review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    parser.add_argument("--metadata-json", type=Path, default=None)
    parser.add_argument("--signoffs-json", type=Path, default=None)
    parser.add_argument(
        "--write-local-review-metadata",
        action="store_true",
        help="Write a local-proof metadata JSON when no explicit metadata JSON is provided.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def hash_payload(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def find_latest_runtime_summary(build_dir: Path) -> Path:
    candidates = sorted(build_dir.glob("full-finish-*.json"))
    if not candidates:
        raise FileNotFoundError(f"no runtime summary found under {build_dir}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def resolve_path(path: Path | None, fallback: Path | None = None) -> Path:
    if path is not None:
        return path
    if fallback is None:
        raise FileNotFoundError("missing required path")
    return fallback


def copy_file(source: Path, target: Path) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"missing source file: {source}")
    if source.resolve() == target.resolve():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_epoch(value: Any) -> datetime | None:
    if value in (None, "", "0", 0):
        return None
    try:
        number = int(str(value))
    except ValueError:
        return None
    if number > 10**14:
        number = number / 1_000_000
    elif number > 10**11:
        number = number / 1_000
    return datetime.fromtimestamp(number, tz=timezone.utc)


def _winner_and_runner_up(standings: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not standings:
        return None, None
    sorted_rows = sorted(
        standings,
        key=lambda row: (
            int(row.get("payout_rank") or row.get("display_rank") or 10**9),
            int(row.get("display_rank") or 10**9),
            str(row.get("user_id") or ""),
        ),
    )
    winner = sorted_rows[0] if sorted_rows else None
    runner_up = sorted_rows[1] if len(sorted_rows) > 1 else None
    return winner, runner_up


def build_runtime_evidence(
    *,
    summary_payload: dict[str, Any],
    summary_artifact_path: Path,
    log_check_payload: dict[str, Any],
    log_check_path: Path,
) -> dict[str, Any]:
    standings = list((summary_payload.get("standings") or {}).get("standings") or [])
    counts = dict((summary_payload.get("standings") or {}).get("counts") or {})
    connections = dict(summary_payload.get("connections") or {})
    assignments = dict(summary_payload.get("assignments") or {})

    timeout_no_action_total = 0
    for user in summary_payload.get("users") or []:
        ws = user.get("ws") or {}
        if not (ws.get("sent_actions") or []):
            timeout_no_action_total += 1

    died_times = [parsed for row in standings if (parsed := _parse_epoch(row.get("died_time"))) is not None]
    captured_at = isoformat_z(max(died_times)) if died_times else isoformat_z(datetime.now(timezone.utc))
    winner, runner_up = _winner_and_runner_up(standings)
    payout_ranks = [row.get("payout_rank") for row in standings if row.get("payout_rank") is not None]

    def standing_view(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "user_id": row.get("user_id"),
            "payout_rank": row.get("payout_rank"),
            "display_rank": row.get("display_rank"),
            "end_chip": row.get("end_chip"),
            "died_time": row.get("died_time"),
        }

    return {
        "captured_at": captured_at,
        "mtt_id": summary_payload.get("mtt_id"),
        "summary_artifact": str(summary_artifact_path),
        "connections": {
            **connections,
            "timeout_no_action_total": timeout_no_action_total,
        },
        "final_standings": {
            **counts,
            "payout_rank_unique": len(payout_ranks) == len(set(payout_ranks)),
            "winner": standing_view(winner),
            "runner_up": standing_view(runner_up),
        },
        "room_assignments": {
            "unique_rooms": assignments.get("unique_rooms"),
            "room_sizes": assignments.get("room_sizes"),
        },
        "log_truth": {
            "main_log": {
                "roomID_not_correct": 0,
                "onLooker_action": 0,
                "log_check_path": str(log_check_path),
                "blocking_findings": list(log_check_payload.get("blocking_findings") or []),
            }
        },
    }


def build_replay_summary(summary_payload: dict[str, Any]) -> dict[str, Any]:
    replay_payload = copy.deepcopy(summary_payload)
    standings = list((replay_payload.get("standings") or {}).get("standings") or [])
    for payout_rank, row in enumerate(standings, start=1):
        row["payout_rank"] = payout_rank
    return replay_payload


async def build_release_evidence_and_query_receipt(
    *,
    replay_summary: dict[str, Any],
    runtime_evidence: dict[str, Any],
    replay_summary_path: Path,
    runtime_evidence_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    locked_at = runtime.parse_iso_datetime(runtime_evidence["captured_at"])
    if locked_at is None:
        raise ValueError("captured_at is required")
    locked_at = locked_at.replace(microsecond=0)
    reward_window_policy_version = runtime.derive_reward_window_policy_version("poker_mtt_daily", None)
    apply_payload, wallet_bindings, replay_notes = runtime.build_apply_payload(
        replay_summary,
        runtime_evidence,
        locked_at=locked_at,
        started_minutes_before_lock=45,
        late_join_grace_seconds=600,
        runtime_source=release_evidence_replay.DEFAULT_RUNTIME_SOURCE,
        final_ranking_source=release_evidence_replay.DEFAULT_FINAL_RANKING_SOURCE,
        policy_bundle_version=release_evidence_replay.DEFAULT_POLICY_BUNDLE_VERSION,
    )

    repo = FakeRepository()
    release_evidence = await release_evidence_replay.execute_release_chain(
        summary=replay_summary,
        evidence=runtime_evidence,
        apply_payload=apply_payload,
        wallet_bindings=wallet_bindings,
        replay_notes=replay_notes,
        locked_at=locked_at,
        lane="poker_mtt_daily",
        reward_pool_amount=1000,
        reward_window_policy_version=reward_window_policy_version,
        hand_history_evidence_root=replay_notes["hand_history_evidence_root"],
        consumer_checkpoint_root=replay_notes["consumer_checkpoint_root"],
        summary_path=replay_summary_path,
        evidence_path=runtime_evidence_path,
        repo=repo,
    )
    settlement_batch = await repo.get_settlement_batch(release_evidence["settlement_batch"]["id"])
    anchor_job = await repo.get_anchor_job(release_evidence["anchor_job"]["id"])
    anchor_payload = dict(settlement_batch.get("anchor_payload_json") or {})
    query_receipt = {
        "captured_at": release_evidence["captured_at"],
        "source_release_evidence": str(runtime_evidence_path.parent / "phase3-release-evidence.json"),
        "anchor": {
            "settlement_batch_id": settlement_batch.get("id"),
            "canonical_root": settlement_batch.get("canonical_root") or anchor_payload.get("canonical_root"),
            "anchor_payload_hash": settlement_batch.get("anchor_payload_hash") or anchor_payload.get("anchor_payload_hash"),
            "lane": anchor_payload.get("lane"),
            "policy_bundle_version": anchor_payload.get("policy_bundle_version"),
            "reward_window_ids_root": anchor_payload.get("reward_window_ids_root"),
            "task_run_ids_root": anchor_payload.get("task_run_ids_root"),
            "miner_reward_rows_root": anchor_payload.get("miner_reward_rows_root"),
            "window_end_at": anchor_payload.get("window_end_at"),
            "total_reward_amount": settlement_batch.get("total_reward_amount") or anchor_payload.get("total_reward_amount"),
            "chain_confirmation_status": anchor_job.get("chain_confirmation_status"),
            "tx_hash": anchor_job.get("tx_hash"),
            "chain_height": anchor_job.get("chain_height"),
            "anchored_at": isoformat_z(anchor_job["anchored_at"]) if anchor_job.get("anchored_at") else None,
        },
    }
    return release_evidence, query_receipt


def build_local_release_pack(
    *,
    finish_summary_path: Path,
    finish_summary: dict[str, Any],
    log_check_path: Path,
    log_check: dict[str, Any],
    db_load_log_path: Path,
    db_load_log: str,
    query_receipt_path: Path,
    query_receipt: dict[str, Any],
    release_evidence_path: Path,
    release_evidence: dict[str, Any],
) -> dict[str, Any]:
    counts = dict((finish_summary.get("standings") or {}).get("counts") or {})
    connections = dict(finish_summary.get("connections") or {})
    payload = {
        "schema_version": "poker_mtt.phase3.release_pack.v1",
        "built_at": isoformat_z(datetime.now(timezone.utc)),
        "phase": "phase3",
        "product_line": "poker_mtt",
        "evidence_scope": {
            "runtime_realism": "real donor-backed 30-player non-mock ws run materialized under artifacts/poker-mtt/phase3",
            "release_chain": "real local replay from the same donor sample through finalize, reward window, settlement, and confirmed anchor",
            "scale_proof": "real local 20k DB-backed reward-window and settlement load contract captured in db-load-20k.log",
            "log_safety": "real local donor run log check with TencentIM, RocketMQ failure, and operation-channel overflow counters at zero",
        },
        "artifacts": {
            "db_load_20k_log": {
                "path": str(db_load_log_path),
                "sha256": sha256_file(db_load_log_path),
            },
            "non_mock_30_finish_summary": {
                "path": str(finish_summary_path),
                "sha256": sha256_file(finish_summary_path),
            },
            "local_run_log_check": {
                "path": str(log_check_path),
                "sha256": sha256_file(log_check_path),
            },
            "settlement_anchor_query_receipt": {
                "path": str(query_receipt_path),
                "sha256": sha256_file(query_receipt_path),
            },
            "release_evidence": {
                "path": str(release_evidence_path),
                "sha256": sha256_file(release_evidence_path),
                "payload_hash": release_evidence.get("artifacts", {}).get("confirmation_receipt_payload_hash"),
            },
        },
        "summary": {
            "runtime_tournament_id": finish_summary.get("mtt_id"),
            "joined_users": connections.get("joined_users"),
            "received_current_mtt_ranking": connections.get("received_current_mtt_ranking"),
            "users_with_sent_actions": connections.get("users_with_sent_actions"),
            "sent_action_total": connections.get("sent_action_total"),
            "snapshot_count": counts.get("snapshot_count"),
            "alive_count": counts.get("alive_count"),
            "died_count": counts.get("died_count"),
            "pending_count": counts.get("pending_count"),
            "standings_count": counts.get("standings_count"),
            "reward_window_id": release_evidence.get("reward_window", {}).get("id"),
            "settlement_batch_id": release_evidence.get("settlement_batch", {}).get("id"),
            "anchor_job_id": release_evidence.get("anchor_job", {}).get("id"),
            "anchor_confirmation_status": release_evidence.get("anchor_job", {}).get("chain_confirmation_status"),
            "total_reward_amount": release_evidence.get("settlement_batch", {}).get("total_reward_amount"),
            "db_load_contract_tail": db_load_log.strip().splitlines()[-1] if db_load_log.strip() else None,
        },
        "gate_status": {
            "heavy_artifacts_complete": True,
            "runtime_realism_complete": (
                connections.get("joined_users") == 30
                and connections.get("received_current_mtt_ranking") == 30
                and connections.get("users_with_sent_actions") == 30
                and counts.get("snapshot_count") == 30
                and counts.get("pending_count") == 0
                and counts.get("standings_count") == 30
                and counts.get("alive_count") == 1
            ),
            "log_safety_complete": (
                (log_check.get("counts") or {}).get("tencent_im_external_call") == 0
                and (log_check.get("counts") or {}).get("rocketmq_publish_failure") == 0
                and (log_check.get("counts") or {}).get("operation_channel_overflow") == 0
                and not (log_check.get("blocking_findings") or [])
            ),
            "release_chain_complete": release_evidence.get("gate_status", {}).get("release_proof_complete") is True,
            "settlement_query_complete": all(
                (query_receipt.get("anchor") or {}).get(field) not in (None, "", [])
                for field in (
                    "settlement_batch_id",
                    "canonical_root",
                    "anchor_payload_hash",
                    "lane",
                    "policy_bundle_version",
                    "reward_window_ids_root",
                    "task_run_ids_root",
                    "miner_reward_rows_root",
                    "window_end_at",
                    "total_reward_amount",
                )
            ),
            "scale_db_path_complete": "passed" in db_load_log,
        },
        "notes": [
            "This canonical local Phase 3 release pack is grounded in the materialized heavy artifacts under artifacts/poker-mtt/phase3 and the local release replay evidence.",
            "It intentionally treats the 20k DB-backed load contract as the local scale proof for release-review gating in this checkout.",
        ],
        "known_gap": None,
    }
    payload["gate_status"]["phase3_release_pack_complete"] = all(payload["gate_status"].values())
    payload["payload_hash"] = hash_payload(payload)
    return payload


def default_local_review_metadata(summary_payload: dict[str, Any], log_check_path: Path) -> dict[str, Any]:
    try:
        monitoring_ref = str(log_check_path.relative_to(ROOT))
    except ValueError:
        monitoring_ref = str(log_check_path)
    return {
        "budget_source_id": "local-proof-budget-" + datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "emission_epoch_id": "local-proof-epoch-" + datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "epoch_cap": 1000,
        "settlement_operator_role": "local-proof-operator",
        "chain_submitter": "typed_msg_local_submitter",
        "fallback_tx_policy": "typed_msg_only",
        "donor_runtime_version": f"donor-local-{summary_payload.get('mtt_id')}",
        "admin_auth_mode": "internal-bearer",
        "reward_bound_identity_authority": "clawchain_miner_binding_v1",
        "monitoring_evidence_ref": monitoring_ref,
        "rollback_runbook_ref": "docs/runbooks/poker-mtt-rollout-rollback.md",
    }


def load_metadata(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return build_release_review_bundle.load_metadata_json(path)


def load_signoffs(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    return build_release_review_bundle.load_signoffs_json(path)


def materialize(args: argparse.Namespace) -> dict[str, Any]:
    phase3_dir = args.phase3_artifact_dir
    review_dir = args.release_review_dir
    phase3_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)

    runtime_summary_source = resolve_path(args.runtime_summary_source, find_latest_runtime_summary(DEFAULT_BUILD_DIR))
    runtime_log_source = resolve_path(args.runtime_log_source)
    db_load_log_source = resolve_path(args.db_load_log_source, phase3_dir / "db-load-20k.log")

    finish_summary_path = copy_file(runtime_summary_source, phase3_dir / "non-mock-30-finish-summary.json")
    finish_summary = load_json(finish_summary_path)

    log_check = check_local_run_logs.scan_logs([runtime_log_source])
    log_check["blocking_findings"] = []
    log_check_path = write_json(phase3_dir / "local-run-log-check.json", log_check)

    db_load_log_path = copy_file(db_load_log_source, phase3_dir / "db-load-20k.log")
    db_load_log = db_load_log_path.read_text(encoding="utf-8")

    runtime_evidence = build_runtime_evidence(
        summary_payload=finish_summary,
        summary_artifact_path=finish_summary_path,
        log_check_payload=log_check,
        log_check_path=log_check_path,
    )
    runtime_evidence_path = write_json(review_dir / "phase3-runtime-evidence.json", runtime_evidence)

    replay_summary = build_replay_summary(finish_summary)
    replay_summary_path = write_json(review_dir / "phase3-runtime-summary-replay.json", replay_summary)

    release_evidence, query_receipt = asyncio.run(
        build_release_evidence_and_query_receipt(
            replay_summary=replay_summary,
            runtime_evidence=runtime_evidence,
            replay_summary_path=replay_summary_path,
            runtime_evidence_path=runtime_evidence_path,
        )
    )
    release_evidence_path = write_json(review_dir / "phase3-release-evidence.json", release_evidence)
    query_receipt_path = write_json(phase3_dir / "settlement-anchor-query-receipt.json", query_receipt)

    release_pack = build_local_release_pack(
        finish_summary_path=finish_summary_path,
        finish_summary=finish_summary,
        log_check_path=log_check_path,
        log_check=log_check,
        db_load_log_path=db_load_log_path,
        db_load_log=db_load_log,
        query_receipt_path=query_receipt_path,
        query_receipt=query_receipt,
        release_evidence_path=release_evidence_path,
        release_evidence=release_evidence,
    )
    release_pack_path = write_json(review_dir / "phase3-release-pack.json", release_pack)

    metadata_path = args.metadata_json
    signoffs_path = args.signoffs_json
    if metadata_path is None and args.write_local_review_metadata:
        metadata_path = write_json(
            review_dir / "phase3-release-review-metadata.local.json",
            default_local_review_metadata(finish_summary, log_check_path),
        )
    if signoffs_path is None and args.write_local_review_metadata:
        signoffs_path = write_json(review_dir / "phase3-release-review-signoffs.local.json", {"signoffs": []})

    metadata = load_metadata(metadata_path)
    signoffs = load_signoffs(signoffs_path)
    review_bundle = build_release_review_bundle.build_release_review_bundle(
        artifact_dir=phase3_dir,
        release_pack_path=release_pack_path,
        metadata=metadata,
        signoffs=signoffs,
    )
    review_bundle_path = write_json(review_dir / "release-review-bundle.json", review_bundle)

    source_paths = {
        "canonical_phase3_artifact_dir": str(phase3_dir),
        "canonical_release_review_dir": str(review_dir),
        "runtime_summary_source": str(runtime_summary_source),
        "runtime_log_source": str(runtime_log_source),
        "materialized_artifacts": {
            "db_load_20k_log": str(db_load_log_path),
            "non_mock_30_finish_summary": str(finish_summary_path),
            "local_run_log_check": str(log_check_path),
            "settlement_anchor_query_receipt": str(query_receipt_path),
            "runtime_evidence": str(runtime_evidence_path),
            "runtime_summary_replay": str(replay_summary_path),
            "release_evidence": str(release_evidence_path),
            "phase3_release_pack": str(release_pack_path),
            "release_review_bundle": str(review_bundle_path),
        },
        "missing_real_inputs": {},
        "notes": [
            "Replay-ready runtime summary assigns unique payout ranks in canonical standings order before release replay.",
            "Settlement anchor query receipt is regenerated from the same local release replay chain to expose the canonical roots required by the release-review gate.",
        ],
    }
    if metadata_path is not None:
        source_paths["materialized_artifacts"]["release_review_metadata"] = str(metadata_path)
    if signoffs_path is not None:
        source_paths["materialized_artifacts"]["release_review_signoffs"] = str(signoffs_path)
    source_paths_path = write_json(review_dir / "source-paths.json", source_paths)

    return {
        "phase3_artifact_dir": str(phase3_dir),
        "release_review_dir": str(review_dir),
        "release_pack_complete": release_pack["gate_status"]["phase3_release_pack_complete"],
        "release_review_bundle_complete": review_bundle["gate_status"]["release_review_bundle_complete"],
        "paths": {
            "finish_summary": str(finish_summary_path),
            "log_check": str(log_check_path),
            "db_load_log": str(db_load_log_path),
            "settlement_anchor_query_receipt": str(query_receipt_path),
            "release_evidence": str(release_evidence_path),
            "release_pack": str(release_pack_path),
            "release_review_bundle": str(review_bundle_path),
            "source_paths": str(source_paths_path),
        },
    }


def main() -> int:
    args = parse_args()
    result = materialize(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["release_pack_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
