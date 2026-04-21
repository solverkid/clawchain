#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_ARTIFACTS = {
    "db_load_20k": "db-load-20k.log",
    "non_mock_30_finish_summary": "non-mock-30-finish-summary.json",
    "local_run_log_check": "local-run-log-check.json",
    "settlement_anchor_query_receipt": "settlement-anchor-query-receipt.json",
}
REQUIRED_METADATA_FIELDS = (
    "budget_source_id",
    "emission_epoch_id",
    "epoch_cap",
    "settlement_operator_role",
    "chain_submitter",
    "fallback_tx_policy",
    "donor_runtime_version",
    "admin_auth_mode",
    "reward_bound_identity_authority",
    "monitoring_evidence_ref",
    "rollback_runbook_ref",
)
REQUIRED_SETTLEMENT_QUERY_FIELDS = (
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


def isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def hash_payload(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_any(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_runtime_finish(payload: dict[str, Any]) -> dict[str, Any]:
    connections = payload.get("connections") or {}
    finish_mode = payload.get("finish_mode") or {}
    standings = payload.get("standings") or {}
    counts = standings.get("counts") or payload.get("final_standings") or {}
    return {
        "mtt_id": payload.get("mtt_id"),
        "joined_users": int(connections.get("joined_users") or 0),
        "received_current_mtt_ranking": int(connections.get("received_current_mtt_ranking") or 0),
        "users_with_sent_actions": int(connections.get("users_with_sent_actions") or 0),
        "sent_action_total": int(connections.get("sent_action_total") or 0),
        "finished": finish_mode.get("finished") is True or int(counts.get("alive_count") or 0) <= 1,
        "snapshot_count": int(counts.get("snapshot_count") or 0),
        "alive_count": int(counts.get("alive_count") or 0),
        "died_count": int(counts.get("died_count") or 0),
        "pending_count": int(counts.get("pending_count") or 0),
        "standings_count": int(counts.get("standings_count") or 0),
    }


def runtime_finish_complete(summary: dict[str, Any]) -> bool:
    joined_users = int(summary.get("joined_users") or 0)
    return (
        joined_users > 0
        and int(summary.get("received_current_mtt_ranking") or 0) == joined_users
        and int(summary.get("users_with_sent_actions") or 0) == joined_users
        and bool(summary.get("finished"))
        and int(summary.get("snapshot_count") or 0) == joined_users
        and int(summary.get("pending_count") or 0) == 0
        and int(summary.get("standings_count") or 0) == joined_users
    )


def summarize_log_check(payload: dict[str, Any]) -> dict[str, Any]:
    counts = payload.get("counts") or {}
    blockers = list(payload.get("blocking_findings") or [])
    return {
        "line_count": int(payload.get("line_count") or 0),
        "tencent_im_external_call": int(counts.get("tencent_im_external_call") or 0),
        "rocketmq_publish_failure": int(counts.get("rocketmq_publish_failure") or 0),
        "operation_channel_overflow": int(counts.get("operation_channel_overflow") or 0),
        "blocking_findings": blockers,
    }


def log_check_clean(summary: dict[str, Any]) -> bool:
    return (
        int(summary.get("tencent_im_external_call") or 0) == 0
        and int(summary.get("rocketmq_publish_failure") or 0) == 0
        and int(summary.get("operation_channel_overflow") or 0) == 0
        and not summary.get("blocking_findings")
    )


def summarize_settlement_query(payload: dict[str, Any]) -> dict[str, Any]:
    anchor = payload.get("anchor") or payload
    return {field: anchor.get(field) for field in REQUIRED_SETTLEMENT_QUERY_FIELDS}


def settlement_query_complete(summary: dict[str, Any]) -> bool:
    return all(summary.get(field) not in (None, "", []) for field in REQUIRED_SETTLEMENT_QUERY_FIELDS)


def metadata_complete(metadata: dict[str, Any]) -> bool:
    return all(metadata.get(field) not in (None, "", []) for field in REQUIRED_METADATA_FIELDS)


def build_release_review_bundle(
    *,
    artifact_dir: Path,
    release_pack_path: Path | None = None,
    metadata: dict[str, Any] | None = None,
    signoffs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    metadata = dict(metadata or {})
    signoffs = list(signoffs or [])
    artifacts: dict[str, Any] = {}
    known_gaps: list[str] = []

    heavy_artifacts_present = True
    runtime_summary: dict[str, Any] = {}
    log_check_summary: dict[str, Any] = {}
    settlement_query_summary: dict[str, Any] = {}

    for artifact_key, filename in REQUIRED_ARTIFACTS.items():
        path = artifact_dir / filename
        if not path.exists():
            heavy_artifacts_present = False
            known_gaps.append(f"missing_artifact:{filename}")
            continue
        artifacts[artifact_key] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        if path.suffix == ".json":
            payload = load_json(path)
            if artifact_key == "non_mock_30_finish_summary":
                runtime_summary = summarize_runtime_finish(payload)
                artifacts[artifact_key]["summary"] = runtime_summary
            elif artifact_key == "local_run_log_check":
                log_check_summary = summarize_log_check(payload)
                artifacts[artifact_key]["summary"] = log_check_summary
            elif artifact_key == "settlement_anchor_query_receipt":
                settlement_query_summary = summarize_settlement_query(payload)
                artifacts[artifact_key]["summary"] = settlement_query_summary

    runtime_complete = runtime_finish_complete(runtime_summary) if runtime_summary else False
    if not runtime_complete:
        known_gaps.append("runtime_finish_incomplete")

    logs_clean = log_check_clean(log_check_summary) if log_check_summary else False
    if not logs_clean:
        known_gaps.append("local_run_log_check_blocking_findings")

    settlement_complete = settlement_query_complete(settlement_query_summary) if settlement_query_summary else False
    if not settlement_complete:
        known_gaps.append("settlement_query_missing_fields")

    release_pack_complete = False
    if release_pack_path is not None:
        if release_pack_path.exists():
            release_pack_payload = load_json(release_pack_path)
            artifacts["release_pack"] = {
                "path": str(release_pack_path),
                "sha256": sha256_file(release_pack_path),
                "bytes": release_pack_path.stat().st_size,
                "payload_hash": release_pack_payload.get("payload_hash"),
                "gate_status": release_pack_payload.get("gate_status") or {},
            }
            release_pack_complete = bool((release_pack_payload.get("gate_status") or {}).get("phase3_release_pack_complete"))
        else:
            known_gaps.append(f"missing_artifact:{release_pack_path.name}")
    if release_pack_path is None or not release_pack_complete:
        known_gaps.append("release_pack_incomplete")

    rollout_metadata_complete = metadata_complete(metadata)
    if not rollout_metadata_complete:
        known_gaps.append("rollout_metadata_incomplete")

    bundle = {
        "schema_version": "poker_mtt.release_review_bundle.v1",
        "generated_at": isoformat_z(datetime.now(timezone.utc)),
        "artifact_dir": str(artifact_dir),
        "artifacts": artifacts,
        "runtime_summary": runtime_summary,
        "log_check_summary": log_check_summary,
        "settlement_query_summary": settlement_query_summary,
        "rollout_review": {
            **{field: metadata.get(field) for field in REQUIRED_METADATA_FIELDS},
            "signoffs": signoffs,
        },
        "gate_status": {
            "heavy_artifacts_present": heavy_artifacts_present,
            "runtime_finish_complete": runtime_complete,
            "log_check_clean": logs_clean,
            "settlement_query_complete": settlement_complete,
            "release_pack_complete": release_pack_complete,
            "rollout_metadata_complete": rollout_metadata_complete,
            "release_review_bundle_complete": (
                heavy_artifacts_present
                and runtime_complete
                and logs_clean
                and settlement_complete
                and release_pack_complete
                and rollout_metadata_complete
            ),
        },
        "known_gaps": sorted(set(known_gaps)),
    }
    bundle["payload_hash"] = hash_payload(bundle)
    return bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a Poker MTT reward-bearing release review bundle from Phase 3 artifacts.",
    )
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--release-pack", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--metadata-json", type=Path, default=None)
    parser.add_argument("--signoffs-json", type=Path, default=None)
    parser.add_argument("--budget-source-id")
    parser.add_argument("--emission-epoch-id")
    parser.add_argument("--epoch-cap", type=int)
    parser.add_argument("--settlement-operator-role")
    parser.add_argument("--chain-submitter")
    parser.add_argument("--fallback-tx-policy")
    parser.add_argument("--donor-runtime-version")
    parser.add_argument("--admin-auth-mode")
    parser.add_argument("--reward-bound-identity-authority")
    parser.add_argument("--monitoring-evidence-ref")
    parser.add_argument("--rollback-runbook-ref")
    parser.add_argument(
        "--signoff",
        action="append",
        default=[],
        help="Format: role:name:signed_at",
    )
    return parser.parse_args()


def parse_signoffs(values: list[str]) -> list[dict[str, str]]:
    signoffs = []
    for value in values:
        parts = value.split(":", 2)
        if len(parts) != 3:
            raise ValueError(f"invalid signoff format: {value}")
        role, name, signed_at = parts
        signoffs.append(
            {
                "role": role,
                "name": name,
                "signed_at": signed_at,
            }
        )
    return signoffs


def load_metadata_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = load_json(path)
    return {field: payload.get(field) for field in REQUIRED_METADATA_FIELDS}


def load_signoffs_json(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = load_json_any(path)
    if isinstance(payload, dict):
        items = payload.get("signoffs") or []
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError("signoffs json must be an object with signoffs or a list")
    signoffs = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each signoff must be an object")
        signoffs.append(
            {
                "role": item.get("role"),
                "name": item.get("name"),
                "signed_at": item.get("signed_at"),
            }
        )
    return signoffs


def main() -> int:
    args = parse_args()
    cli_metadata = {
        "budget_source_id": args.budget_source_id,
        "emission_epoch_id": args.emission_epoch_id,
        "epoch_cap": args.epoch_cap,
        "settlement_operator_role": args.settlement_operator_role,
        "chain_submitter": args.chain_submitter,
        "fallback_tx_policy": args.fallback_tx_policy,
        "donor_runtime_version": args.donor_runtime_version,
        "admin_auth_mode": args.admin_auth_mode,
        "reward_bound_identity_authority": args.reward_bound_identity_authority,
        "monitoring_evidence_ref": args.monitoring_evidence_ref,
        "rollback_runbook_ref": args.rollback_runbook_ref,
    }
    metadata = {
        **load_metadata_json(args.metadata_json),
        **{key: value for key, value in cli_metadata.items() if value not in (None, "", [])},
    }
    signoffs = load_signoffs_json(args.signoffs_json)
    signoffs.extend(parse_signoffs(args.signoff))
    bundle = build_release_review_bundle(
        artifact_dir=args.artifact_dir,
        release_pack_path=args.release_pack,
        metadata=metadata,
        signoffs=signoffs,
    )
    encoded = json.dumps(bundle, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if bundle["gate_status"]["release_review_bundle_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
