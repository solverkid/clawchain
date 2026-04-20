from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "poker_mtt"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import release_evidence_pack


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def test_build_release_pack_marks_phase3_complete_but_preserves_known_gap(tmp_path: Path):
    runtime_path = write_json(
        tmp_path / "runtime.json",
        {
            "captured_at": "2026-04-20T16:15:34+08:00",
            "mtt_id": "runtime-r4",
            "connections": {"joined_users": 30, "sent_action_total": 393},
            "final_standings": {
                "alive_count": 0,
                "payout_rank_unique": True,
                "winner": {"user_id": "24"},
                "runner_up": {"user_id": "14"},
            },
            "log_truth": {"main_log": {"roomID_not_correct": 0, "onLooker_action": 0}},
        },
    )
    settlement_path = write_json(
        tmp_path / "settlement.json",
        {
            "captured_at": "2026-04-20T08:15:40Z",
            "reward_window": {"id": "rw_daily", "state": "finalized"},
            "settlement_batch": {"id": "sb_daily", "chain_confirmation_state": "confirmed"},
            "anchor_job": {"id": "aj_daily", "state": "anchored"},
            "gate_status": {
                "locked_ranking_complete": True,
                "reward_window_finalized": True,
                "query_confirmed_settlement": True,
            },
        },
    )
    burst_path = write_json(
        tmp_path / "burst.json",
        {
            "user_count": 20000,
            "table_count": 2000,
            "events": {
                "completed_hand_processed": 2000,
                "standup_processed": 2000,
            },
            "dlq_total": 0,
            "conflict_total": 0,
            "anchor": {"consumer_checkpoint_root": "sha256:checkpoint"},
        },
    )

    pack = release_evidence_pack.build_release_pack(
        runtime_evidence_path=runtime_path,
        settlement_evidence_path=settlement_path,
        burst_summary_path=burst_path,
    )

    assert pack["gate_status"]["runtime_realism_complete"] is True
    assert pack["gate_status"]["release_chain_complete"] is True
    assert pack["gate_status"]["scale_burst_complete"] is True
    assert pack["gate_status"]["same_run_live_mq_projector_complete"] is False
    assert pack["gate_status"]["phase3_release_pack_complete"] is True
    assert pack["known_gap"]["code"] == "same_run_live_mq_projector_not_recaptured"
    assert pack["payload_hash"].startswith("sha256:")


def test_build_release_pack_includes_emitted_mq_replay_and_narrows_gap(tmp_path: Path):
    runtime_path = write_json(
        tmp_path / "runtime.json",
        {
            "captured_at": "2026-04-20T16:15:34+08:00",
            "mtt_id": "runtime-r4",
            "connections": {"joined_users": 30, "sent_action_total": 393},
            "final_standings": {
                "alive_count": 0,
                "payout_rank_unique": True,
                "winner": {"user_id": "24"},
                "runner_up": {"user_id": "14"},
            },
            "log_truth": {"main_log": {"roomID_not_correct": 0, "onLooker_action": 0}},
        },
    )
    settlement_path = write_json(
        tmp_path / "settlement.json",
        {
            "captured_at": "2026-04-20T08:15:40Z",
            "reward_window": {"id": "rw_daily", "state": "finalized"},
            "settlement_batch": {"id": "sb_daily", "chain_confirmation_state": "confirmed"},
            "anchor_job": {"id": "aj_daily", "state": "anchored"},
            "gate_status": {
                "locked_ranking_complete": True,
                "reward_window_finalized": True,
                "query_confirmed_settlement": True,
            },
        },
    )
    burst_path = write_json(
        tmp_path / "burst.json",
        {
            "user_count": 20000,
            "table_count": 2000,
            "events": {
                "completed_hand_processed": 2000,
                "standup_processed": 2000,
            },
            "dlq_total": 0,
            "conflict_total": 0,
            "anchor": {"consumer_checkpoint_root": "sha256:checkpoint"},
        },
    )
    emitted_path = write_json(
        tmp_path / "emitted.json",
        {
            "captured_at": "2026-04-20T08:15:38Z",
            "mq_replay": {
                "hand_history_evidence_root": "sha256:hands",
                "consumer_checkpoint_root": "sha256:checkpoint-replay",
            },
            "gate_status": {
                "same_run_donor_emitted_payload_replay_complete": True,
                "release_chain_complete": True,
                "broker_acked_live_mq_projector_complete": False,
            },
            "known_gap": {
                "code": "broker_acked_same_run_live_projector_not_confirmed",
            },
        },
    )

    pack = release_evidence_pack.build_release_pack(
        runtime_evidence_path=runtime_path,
        settlement_evidence_path=settlement_path,
        burst_summary_path=burst_path,
        emitted_mq_replay_path=emitted_path,
    )

    assert pack["gate_status"]["same_run_donor_emitted_payload_replay_complete"] is True
    assert pack["gate_status"]["same_run_live_mq_projector_complete"] is False
    assert pack["gate_status"]["phase3_release_pack_complete"] is True
    assert pack["known_gap"]["code"] == "broker_acked_same_run_live_projector_not_confirmed"
    assert pack["summary"]["emitted_mq_replay_hand_history_root"] == "sha256:hands"
    assert pack["artifacts"]["emitted_mq_replay"]["path"] == str(emitted_path)


def test_build_release_pack_accepts_champion_alive_runtime_and_clears_known_gap(tmp_path: Path):
    runtime_path = write_json(
        tmp_path / "runtime.json",
        {
            "captured_at": "2026-04-20T18:25:34+08:00",
            "mtt_id": "runtime-r5",
            "connections": {"joined_users": 30, "sent_action_total": 297},
            "final_standings": {
                "snapshot_count": 30,
                "alive_count": 1,
                "died_count": 29,
                "pending_count": 0,
                "standings_count": 30,
                "payout_rank_unique": True,
                "winner": {
                    "user_id": "13",
                    "payout_rank": 1,
                    "display_rank": 1,
                    "end_chip": 90000,
                    "died_time": "0",
                },
                "runner_up": {
                    "user_id": "28",
                    "payout_rank": 2,
                    "display_rank": 2,
                    "end_chip": 0,
                    "died_time": "1776680705",
                },
            },
            "log_truth": {"main_log": {"roomID_not_correct": 0, "onLooker_action": 0}},
        },
    )
    settlement_path = write_json(
        tmp_path / "settlement.json",
        {
            "captured_at": "2026-04-20T10:29:04Z",
            "reward_window": {"id": "rw_daily", "state": "finalized"},
            "settlement_batch": {"id": "sb_daily", "chain_confirmation_state": "confirmed"},
            "anchor_job": {"id": "aj_daily", "state": "anchored"},
            "gate_status": {
                "locked_ranking_complete": True,
                "reward_window_finalized": True,
                "query_confirmed_settlement": True,
            },
        },
    )
    burst_path = write_json(
        tmp_path / "burst.json",
        {
            "user_count": 20000,
            "table_count": 2000,
            "events": {
                "completed_hand_processed": 2000,
                "standup_processed": 2000,
            },
            "dlq_total": 0,
            "conflict_total": 0,
            "anchor": {"consumer_checkpoint_root": "sha256:checkpoint"},
        },
    )
    emitted_path = write_json(
        tmp_path / "emitted.json",
        {
            "captured_at": "2026-04-20T10:25:05Z",
            "mq_replay": {
                "hand_history_evidence_root": "sha256:hands-r5",
                "consumer_checkpoint_root": "sha256:checkpoint-r5",
            },
            "gate_status": {
                "same_run_donor_emitted_payload_replay_complete": True,
                "release_chain_complete": True,
                "broker_acked_live_mq_projector_complete": True,
            },
            "known_gap": {
                "code": "broker_acked_same_run_live_projector_not_confirmed",
            },
        },
    )

    pack = release_evidence_pack.build_release_pack(
        runtime_evidence_path=runtime_path,
        settlement_evidence_path=settlement_path,
        burst_summary_path=burst_path,
        emitted_mq_replay_path=emitted_path,
    )

    assert pack["gate_status"]["runtime_realism_complete"] is True
    assert pack["gate_status"]["same_run_donor_emitted_payload_replay_complete"] is True
    assert pack["gate_status"]["same_run_live_mq_projector_complete"] is True
    assert pack["gate_status"]["phase3_release_pack_complete"] is True
    assert pack["known_gap"] is None
