from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "poker_mtt"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import release_evidence_replay as replay


def sample_summary() -> dict:
    return {
        "mtt_id": "sample-runtime-mtt",
        "standings": {
            "standings": [
                {
                    "member_id": "7:1",
                    "user_id": "7",
                    "entry_number": 1,
                    "display_rank": 1,
                    "payout_rank": 1,
                },
                {
                    "member_id": "1:1",
                    "user_id": "1",
                    "entry_number": 1,
                    "display_rank": 2,
                    "payout_rank": 2,
                },
                {
                    "member_id": "4:1",
                    "user_id": "4",
                    "entry_number": 1,
                    "display_rank": 3,
                    "payout_rank": 3,
                },
            ]
        },
        "users": [
            {"user_id": "7", "ws": {"sent_actions": [{"action": "raise", "chips": 90.0}], "timeout_no_action_count": 0}},
            {"user_id": "1", "ws": {"sent_actions": [{"action": "call", "chips": 0}], "timeout_no_action_count": 1}},
            {"user_id": "4", "ws": {"sent_actions": [{"action": "fold", "chips": 0}], "timeout_no_action_count": 0}},
        ],
    }


def sample_evidence() -> dict:
    return {
        "captured_at": "2026-04-20T16:15:34+08:00",
        "mtt_id": "sample-runtime-mtt",
        "summary_artifact": "/tmp/sample-runtime-summary.json",
        "connections": {
            "joined_users": 3,
            "sent_action_total": 3,
            "timeout_no_action_total": 1,
        },
        "room_assignments": {"unique_rooms": 1, "room_sizes": {"table-a": 3}},
        "final_standings": {
            "winner": {"user_id": "7", "payout_rank": 1},
            "runner_up": {"user_id": "1", "payout_rank": 2},
        },
        "log_truth": {
            "main_log": {"roomID_not_correct": 0, "onLooker_action": 0},
            "record_log": {"roomID_not_correct": 0},
        },
    }


def test_build_apply_payload_preserves_runtime_order_and_phase3_contract():
    locked_at = datetime(2026, 4, 20, 8, 15, 34, tzinfo=timezone.utc)
    payload, wallet_bindings, replay_notes = replay.build_apply_payload(
        sample_summary(),
        sample_evidence(),
        locked_at=locked_at,
        started_minutes_before_lock=45,
        late_join_grace_seconds=600,
        runtime_source="lepoker_gameserver",
        final_ranking_source="donor_redis_rankings",
        policy_bundle_version="poker_mtt_v1",
    )

    assert payload["tournament_id"] == "sample-runtime-mtt"
    assert payload["late_join_grace_seconds"] == 600
    assert payload["started_at"] == "2026-04-20T07:30:34Z"
    assert [item["source_user_id"] for item in payload["results"]] == ["7", "1", "4"]
    assert payload["results"][0]["final_rank"] == 1
    assert payload["results"][0]["display_rank"] == 1
    assert payload["results"][0]["source_rank"] == 1
    assert payload["results"][0]["reward_identity_state"] == "bound"
    assert payload["results"][0]["hand_history_evidence_root"].startswith("sha256:")
    assert payload["results"][0]["hidden_eval_score"] == 0.0
    assert payload["results"][0]["consistency_input_score"] == 0.0
    assert wallet_bindings["7"]["address"].startswith("claw")
    assert replay_notes["joined_at_strategy"].startswith("omitted")


def test_run_release_evidence_confirms_anchor_chain_and_writes_artifact(tmp_path: Path):
    output_path = tmp_path / "release-proof.json"

    result = replay.run_release_evidence(
        sample_summary(),
        sample_evidence(),
        lane="poker_mtt_daily",
        reward_pool_amount=120,
    )

    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    assert result["apply"]["status_code"] == 200
    assert result["finalize"]["item_count"] == 3
    assert result["finalize"]["eligible_count"] == 3
    assert result["finalize"]["payout_rank_unique"] is True
    assert result["reward_window"]["state"] == "finalized"
    assert result["settlement_batch"]["chain_confirmation_state"] == "confirmed"
    assert result["anchor_job"]["chain_confirmation_status"] == "confirmed"
    assert result["anchor_job"]["state"] == "anchored"
    assert result["gate_status"]["release_proof_complete"] is True
    assert output_path.exists() is True
