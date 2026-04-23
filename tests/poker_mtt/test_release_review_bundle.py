from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "poker_mtt"
SCRIPT_PATH = SCRIPT_DIR / "build_release_review_bundle.py"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_release_review_bundle


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def test_build_release_review_bundle_accepts_complete_phase3_artifacts_and_metadata(tmp_path: Path):
    artifact_dir = tmp_path / "phase3"
    artifact_dir.mkdir()
    (artifact_dir / "db-load-20k.log").write_text("5 passed in 12.34s\n", encoding="utf-8")
    write_json(
        artifact_dir / "non-mock-30-finish-summary.json",
        {
            "mtt_id": "phase3-finish-1",
            "connections": {
                "joined_users": 30,
                "received_current_mtt_ranking": 30,
                "users_with_sent_actions": 30,
                "sent_action_total": 393,
            },
            "finish_mode": {
                "until_finish": True,
                "finished": True,
            },
            "standings": {
                "counts": {
                    "snapshot_count": 30,
                    "alive_count": 1,
                    "died_count": 29,
                    "pending_count": 0,
                    "standings_count": 30,
                }
            },
        },
    )
    write_json(
        artifact_dir / "local-run-log-check.json",
        {
            "line_count": 100,
            "counts": {
                "tencent_im_external_call": 0,
                "rocketmq_publish_failure": 0,
                "operation_channel_overflow": 0,
            },
            "blocking_findings": [],
        },
    )
    write_json(
        artifact_dir / "settlement-anchor-query-receipt.json",
        {
            "anchor": {
                "settlement_batch_id": "sb-phase3-1",
                "canonical_root": "sha256:" + "a" * 64,
                "anchor_payload_hash": "sha256:" + "b" * 64,
                "lane": "poker_mtt_daily",
                "policy_bundle_version": "poker_mtt_daily_policy_v2",
                "reward_window_ids_root": "sha256:" + "c" * 64,
                "task_run_ids_root": "sha256:" + "d" * 64,
                "miner_reward_rows_root": "sha256:" + "e" * 64,
                "window_end_at": "2026-04-20T00:00:00Z",
                "total_reward_amount": 1200,
            }
        },
    )
    release_pack_path = write_json(
        tmp_path / "release-pack.json",
        {
            "schema_version": "poker_mtt.phase3.release_pack.v1",
            "gate_status": {
                "phase3_release_pack_complete": True,
                "same_run_live_mq_projector_complete": True,
            },
            "payload_hash": "sha256:" + "f" * 64,
        },
    )

    bundle = build_release_review_bundle.build_release_review_bundle(
        artifact_dir=artifact_dir,
        release_pack_path=release_pack_path,
        metadata={
            "budget_source_id": "budget-2026-04",
            "emission_epoch_id": "epoch-2026w17",
            "epoch_cap": 5000,
            "settlement_operator_role": "ops-poker-mtt",
            "chain_submitter": "claw1submitterxyz",
            "fallback_tx_policy": "typed_msg_only",
            "donor_runtime_version": "lepoker-gameserver-dev-sha",
            "admin_auth_mode": "internal-bearer",
            "reward_bound_identity_authority": "clawchain_miner_binding_v1",
            "monitoring_evidence_ref": "grafana:poker-mtt-rollout-2026-04-20",
            "rollback_runbook_ref": "docs/runbooks/poker-mtt-rollout-rollback.md",
        },
        signoffs=[
            {
                "role": "operator",
                "name": "alice",
                "signed_at": "2026-04-20T12:00:00Z",
            }
        ],
    )

    assert bundle["gate_status"]["heavy_artifacts_present"] is True
    assert bundle["gate_status"]["runtime_finish_complete"] is True
    assert bundle["gate_status"]["log_check_clean"] is True
    assert bundle["gate_status"]["settlement_query_complete"] is True
    assert bundle["gate_status"]["release_pack_complete"] is True
    assert bundle["gate_status"]["rollout_metadata_complete"] is True
    assert bundle["gate_status"]["release_review_bundle_complete"] is True
    assert bundle["artifacts"]["release_pack"]["payload_hash"] == "sha256:" + "f" * 64
    assert bundle["runtime_summary"]["joined_users"] == 30
    assert bundle["runtime_summary"]["finished"] is True
    assert bundle["settlement_query_summary"]["settlement_batch_id"] == "sb-phase3-1"
    assert bundle["lineage_roots"]["release_pack_payload_hash"] == "sha256:" + "f" * 64
    assert bundle["lineage_roots"]["canonical_root"] == "sha256:" + "a" * 64
    assert bundle["lineage_roots"]["anchor_payload_hash"] == "sha256:" + "b" * 64
    assert bundle["lineage_roots"]["reward_window_ids_root"] == "sha256:" + "c" * 64
    assert bundle["lineage_roots"]["task_run_ids_root"] == "sha256:" + "d" * 64
    assert bundle["lineage_roots"]["miner_reward_rows_root"] == "sha256:" + "e" * 64
    assert bundle["payload_hash"].startswith("sha256:")


def test_build_release_review_bundle_reports_missing_gates_and_metadata(tmp_path: Path):
    artifact_dir = tmp_path / "phase3"
    artifact_dir.mkdir()
    (artifact_dir / "db-load-20k.log").write_text("5 passed in 12.34s\n", encoding="utf-8")
    write_json(
        artifact_dir / "non-mock-30-finish-summary.json",
        {
            "mtt_id": "phase3-finish-2",
            "connections": {
                "joined_users": 30,
                "received_current_mtt_ranking": 28,
                "users_with_sent_actions": 27,
                "sent_action_total": 120,
            },
            "finish_mode": {
                "until_finish": True,
                "finished": False,
            },
            "standings": {
                "counts": {
                    "snapshot_count": 30,
                    "alive_count": 2,
                    "died_count": 28,
                    "pending_count": 1,
                    "standings_count": 29,
                }
            },
        },
    )
    write_json(
        artifact_dir / "local-run-log-check.json",
        {
            "line_count": 100,
            "counts": {
                "tencent_im_external_call": 0,
                "rocketmq_publish_failure": 0,
                "operation_channel_overflow": 1,
            },
            "blocking_findings": ["operation_channel_overflow"],
        },
    )
    write_json(
        artifact_dir / "settlement-anchor-query-receipt.json",
        {
            "anchor": {
                "settlement_batch_id": "sb-phase3-2",
                "canonical_root": "sha256:" + "a" * 64,
                "lane": "poker_mtt_daily",
            }
        },
    )
    release_pack_path = write_json(
        tmp_path / "release-pack.json",
        {
            "gate_status": {
                "phase3_release_pack_complete": False,
            }
        },
    )

    bundle = build_release_review_bundle.build_release_review_bundle(
        artifact_dir=artifact_dir,
        release_pack_path=release_pack_path,
        metadata={
            "budget_source_id": "budget-2026-04",
        },
    )

    assert bundle["gate_status"]["heavy_artifacts_present"] is True
    assert bundle["gate_status"]["runtime_finish_complete"] is False
    assert bundle["gate_status"]["log_check_clean"] is False
    assert bundle["gate_status"]["settlement_query_complete"] is False
    assert bundle["gate_status"]["release_pack_complete"] is False
    assert bundle["gate_status"]["rollout_metadata_complete"] is False
    assert bundle["gate_status"]["release_review_bundle_complete"] is False
    assert "runtime_finish_incomplete" in bundle["known_gaps"]
    assert "local_run_log_check_blocking_findings" in bundle["known_gaps"]
    assert "settlement_query_missing_fields" in bundle["known_gaps"]
    assert "release_pack_incomplete" in bundle["known_gaps"]
    assert "rollout_metadata_incomplete" in bundle["known_gaps"]


def test_release_review_bundle_cli_accepts_metadata_and_signoff_json_files(tmp_path: Path):
    artifact_dir = tmp_path / "phase3"
    artifact_dir.mkdir()
    (artifact_dir / "db-load-20k.log").write_text("5 passed in 12.34s\n", encoding="utf-8")
    write_json(
        artifact_dir / "non-mock-30-finish-summary.json",
        {
            "mtt_id": "phase3-cli-finish",
            "connections": {
                "joined_users": 30,
                "received_current_mtt_ranking": 30,
                "users_with_sent_actions": 30,
                "sent_action_total": 228,
            },
            "finish_mode": {"until_finish": True, "finished": True},
            "standings": {
                "counts": {
                    "snapshot_count": 30,
                    "alive_count": 1,
                    "died_count": 29,
                    "pending_count": 0,
                    "standings_count": 30,
                }
            },
        },
    )
    write_json(
        artifact_dir / "local-run-log-check.json",
        {
            "line_count": 50,
            "counts": {
                "tencent_im_external_call": 0,
                "rocketmq_publish_failure": 0,
                "operation_channel_overflow": 0,
            },
            "blocking_findings": [],
        },
    )
    write_json(
        artifact_dir / "settlement-anchor-query-receipt.json",
        {
            "anchor": {
                "settlement_batch_id": "sb-cli-json",
                "canonical_root": "sha256:" + "1" * 64,
                "anchor_payload_hash": "sha256:" + "2" * 64,
                "lane": "poker_mtt_daily",
                "policy_bundle_version": "poker_mtt_daily_policy_v2",
                "reward_window_ids_root": "sha256:" + "3" * 64,
                "task_run_ids_root": "sha256:" + "4" * 64,
                "miner_reward_rows_root": "sha256:" + "5" * 64,
                "window_end_at": "2026-04-21T00:00:00Z",
                "total_reward_amount": 3000,
            }
        },
    )
    release_pack = write_json(
        tmp_path / "release-pack.json",
        {
            "gate_status": {"phase3_release_pack_complete": True},
            "payload_hash": "sha256:" + "6" * 64,
        },
    )
    metadata_path = write_json(
        tmp_path / "metadata.json",
        {
            "budget_source_id": "budget-2026-04",
            "emission_epoch_id": "epoch-2026w17",
            "epoch_cap": 5000,
            "settlement_operator_role": "ops-poker-mtt",
            "chain_submitter": "claw1submitterxyz",
            "fallback_tx_policy": "typed_msg_only",
            "donor_runtime_version": "lepoker-gameserver-dev-sha",
            "admin_auth_mode": "internal-bearer",
            "reward_bound_identity_authority": "clawchain_miner_binding_v1",
            "monitoring_evidence_ref": "grafana:poker-mtt-rollout-2026-04-21",
            "rollback_runbook_ref": "docs/runbooks/poker-mtt-rollout-rollback.md",
        },
    )
    signoffs_path = write_json(
        tmp_path / "signoffs.json",
        {
            "signoffs": [
                {
                    "role": "operator",
                    "name": "alice",
                    "signed_at": "2026-04-21T10:00:00Z",
                }
            ]
        },
    )
    output_path = tmp_path / "bundle.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--artifact-dir",
            str(artifact_dir),
            "--release-pack",
            str(release_pack),
            "--metadata-json",
            str(metadata_path),
            "--signoffs-json",
            str(signoffs_path),
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    bundle = json.loads(output_path.read_text(encoding="utf-8"))
    assert bundle["gate_status"]["release_review_bundle_complete"] is True
    assert bundle["rollout_review"]["budget_source_id"] == "budget-2026-04"
    assert bundle["rollout_review"]["signoffs"][0]["name"] == "alice"
