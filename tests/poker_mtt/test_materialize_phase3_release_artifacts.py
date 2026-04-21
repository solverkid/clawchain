from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "poker_mtt" / "materialize_phase3_release_artifacts.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_phase3_release_artifacts", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def build_runtime_summary(user_count: int = 30) -> dict:
    standings = []
    users = []
    room_ids = ["room-a", "room-b", "room-c", "room-d"]
    for index in range(user_count):
        payout_rank = index + 1
        standings.append(
            {
                "display_rank": payout_rank,
                "status": "alive" if payout_rank == 1 else "died",
                "member_id": f"{index}:1",
                "user_id": str(index),
                "entry_number": 1,
                "player_name": str(index),
                "room_id": room_ids[index % len(room_ids)] if payout_rank == 1 else None,
                "start_chip": 1000,
                "end_chip": 30000 if payout_rank == 1 else 0,
                "died_time": "0" if payout_rank == 1 else str(1710000000 + payout_rank),
                "stand_up_status": None if payout_rank == 1 else "standUpDieStatus",
                "snapshot_found": True,
                "payout_rank": payout_rank,
            }
        )
        users.append(
            {
                "user_id": str(index),
                "ws": {
                    "sent_actions": [{"action": "call", "chips": 0}],
                },
            }
        )
    return {
        "mtt_id": "phase3-test-mtt",
        "connections": {
            "joined_users": user_count,
            "received_current_mtt_ranking": user_count,
            "users_with_ws_errors": 0,
            "users_with_sent_actions": user_count,
            "sent_action_total": user_count * 2,
        },
        "finish_mode": {
            "until_finish": True,
            "finished": True,
        },
        "assignments": {
            "unique_rooms": 4,
            "room_sizes": {
                "room-a": 8,
                "room-b": 8,
                "room-c": 7,
                "room-d": 7,
            },
        },
        "standings": {
            "counts": {
                "snapshot_count": user_count,
                "alive_count": 1,
                "died_count": user_count - 1,
                "pending_count": 0,
                "standings_count": user_count,
            },
            "standings": standings,
        },
        "users": users,
    }


def test_build_replay_summary_reassigns_unique_payout_ranks() -> None:
    module = load_module()
    summary = build_runtime_summary()
    summary["standings"]["standings"][5]["payout_rank"] = 4
    summary["standings"]["standings"][6]["payout_rank"] = 4

    replay = module.build_replay_summary(summary)

    payout_ranks = [row["payout_rank"] for row in replay["standings"]["standings"]]
    assert payout_ranks == list(range(1, 31))


def test_materialize_script_builds_complete_local_release_artifacts(tmp_path: Path) -> None:
    runtime_summary_source = write_json(tmp_path / "full-finish-test.json", build_runtime_summary())
    runtime_log_source = tmp_path / "run_server.log"
    runtime_log_source.write_text("clean local run\n", encoding="utf-8")
    db_load_log_source = tmp_path / "db-load-20k.log"
    db_load_log_source.write_text("7 passed in 19.57s\n", encoding="utf-8")

    artifact_dir = tmp_path / "artifacts" / "phase3"
    review_dir = tmp_path / "artifacts" / "release-review"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--runtime-summary-source",
            str(runtime_summary_source),
            "--runtime-log-source",
            str(runtime_log_source),
            "--db-load-log-source",
            str(db_load_log_source),
            "--phase3-artifact-dir",
            str(artifact_dir),
            "--release-review-dir",
            str(review_dir),
            "--write-local-review-metadata",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["release_pack_complete"] is True
    assert payload["release_review_bundle_complete"] is True

    release_pack = json.loads((review_dir / "phase3-release-pack.json").read_text(encoding="utf-8"))
    assert release_pack["gate_status"]["phase3_release_pack_complete"] is True

    bundle = json.loads((review_dir / "release-review-bundle.json").read_text(encoding="utf-8"))
    assert bundle["gate_status"]["release_review_bundle_complete"] is True

    query_receipt = json.loads((artifact_dir / "settlement-anchor-query-receipt.json").read_text(encoding="utf-8"))
    assert query_receipt["anchor"]["chain_confirmation_status"] == "confirmed"
    assert query_receipt["anchor"]["miner_reward_rows_root"].startswith("sha256:")

    source_paths = json.loads((review_dir / "source-paths.json").read_text(encoding="utf-8"))
    assert source_paths["materialized_artifacts"]["phase3_release_pack"].endswith("phase3-release-pack.json")
    assert source_paths["materialized_artifacts"]["release_review_bundle"].endswith("release-review-bundle.json")
