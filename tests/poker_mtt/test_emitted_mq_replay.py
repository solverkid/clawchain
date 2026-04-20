from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "poker_mtt"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import emitted_mq_replay


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def build_completed_payload(*, mtt_id: str, biz_id: str, room_id: str, seq: int, end_time: int) -> dict:
    return {
        "bizID": biz_id,
        "record": {
            "roomID": room_id,
            "seq": seq,
            "version": seq,
            "recordType": "recordType",
            "beginTime": end_time - 10,
            "endTime": end_time,
            "record": json.dumps(
                {
                    "gameType": "mtt",
                    "gameID": mtt_id,
                    "roomID": room_id,
                    "beginTime": end_time - 10,
                    "endTime": end_time,
                    "version": seq,
                }
            ),
        },
    }


def build_standup_payload(*, mtt_id: str, biz_id: str, user_id: str, hub_sequence: int) -> dict:
    return {
        "bizID": biz_id,
        "gameID": mtt_id,
        "IDType": "mtt",
        "subIDType": "",
        "userID": user_id,
        "hubSequence": hub_sequence,
        "player": {
            "userID": user_id,
            "stack": 0,
            "standUpReason": "standUpDieStatus",
        },
    }


def build_log_line(*, ts: str, caller: str, msg: str, mtt_id: str, room_id: str = "room-1") -> str:
    return json.dumps(
        {
            "level": "INFO",
            "ts": ts,
            "caller": caller,
            "msg": msg,
            "trace_id": "trace-1",
            "local_ip": "127.0.0.1",
            "session_id": "<nil>",
            "mttID": mtt_id,
            "roomID": room_id,
            "userInfo": "<nil>",
            "connectionInfoID": "<nil>",
            "goID": "1",
        },
        ensure_ascii=False,
    )


def test_collect_donor_mq_events_parses_emits_and_ack_statuses(tmp_path: Path):
    mtt_id = "phase3-log-1"
    completed_payload = build_completed_payload(
        mtt_id=mtt_id,
        biz_id="biz-completed",
        room_id="room-1",
        seq=1,
        end_time=1776671716,
    )
    standup_payload = build_standup_payload(mtt_id=mtt_id, biz_id="biz-standup", user_id="2", hub_sequence=1)
    lines = [
        build_log_line(
            ts="2026-04-20T15:55:16.000+08:00",
            caller="mq/rocketmq.go:185",
            msg=f"send mq to key:biz-completed topic:POKER_RECORD_TOPIC,tag:,body:{json.dumps(completed_payload)}",
            mtt_id=mtt_id,
        ),
        build_log_line(
            ts="2026-04-20T15:55:17.000+08:00",
            caller="mq/rocketmq.go:196",
            msg=f"err:<nil> send mq to key:biz-completed msgID:1 topic:POKER_RECORD_TOPIC tag: body:{json.dumps(completed_payload)}",
            mtt_id=mtt_id,
        ),
        build_log_line(
            ts="2026-04-20T15:55:18.000+08:00",
            caller="mq/rocketmq.go:185",
            msg=f"send mq to key:biz-standup topic:POKER_RECORD_STANDUP_TOPIC,tag:mtt,body:{json.dumps(standup_payload)}",
            mtt_id=mtt_id,
        ),
        build_log_line(
            ts="2026-04-20T15:55:19.000+08:00",
            caller="mq/rocketmq.go:196",
            msg=(
                "err:rpc error: code = DeadlineExceeded desc = context deadline exceeded "
                f"send mq to key:biz-standup msgID: topic:POKER_RECORD_STANDUP_TOPIC tag: body:{json.dumps(standup_payload)}"
            ),
            mtt_id=mtt_id,
        ),
    ]
    log_path = tmp_path / "donor.log"
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    collected = emitted_mq_replay.collect_donor_mq_events(donor_log_path=log_path, tournament_id=mtt_id)

    assert collected["metrics"]["emitted_count"] == 2
    assert collected["metrics"]["completed_hand_emitted_count"] == 1
    assert collected["metrics"]["standup_emitted_count"] == 1
    assert collected["metrics"]["broker_ack_counts_by_topic"]["POKER_RECORD_TOPIC"]["success"] == 1
    assert collected["metrics"]["broker_ack_counts_by_topic"]["POKER_RECORD_STANDUP_TOPIC"]["deadline"] == 1
    assert collected["emitted_events"][0]["biz_id"] == "biz-completed"
    assert collected["broker_acks"][1]["status"] == "deadline"


def test_run_emitted_mq_replay_reuses_same_run_payloads_but_preserves_broker_gap(tmp_path: Path):
    mtt_id = "phase3-log-replay"
    summary_path = write_json(
        tmp_path / "summary.json",
        {
            "mtt_id": mtt_id,
            "standings": {
                "standings": [
                    {
                        "display_rank": 1,
                        "payout_rank": 1,
                        "status": "died",
                        "member_id": "1:1",
                        "user_id": "1",
                        "entry_number": 1,
                        "player_name": "1",
                        "room_id": None,
                        "start_chip": 6000,
                        "end_chip": 6000,
                        "died_time": "1776672906",
                        "stand_up_status": "standUpDieStatus",
                        "alive_rank_zero_based": None,
                        "died_rank_internal": 2,
                        "zset_score": None,
                        "snapshot_found": True,
                    },
                    {
                        "display_rank": 2,
                        "payout_rank": 2,
                        "status": "died",
                        "member_id": "2:1",
                        "user_id": "2",
                        "entry_number": 1,
                        "player_name": "2",
                        "room_id": None,
                        "start_chip": 0,
                        "end_chip": 0,
                        "died_time": "1776672905",
                        "stand_up_status": "standUpDieStatus",
                        "alive_rank_zero_based": None,
                        "died_rank_internal": 1,
                        "zset_score": None,
                        "snapshot_found": True,
                    },
                ]
            },
        },
    )
    evidence_path = write_json(
        tmp_path / "runtime.json",
        {
            "captured_at": "2026-04-20T08:15:34Z",
            "mtt_id": mtt_id,
            "summary_artifact": str(summary_path),
            "connections": {
                "joined_users": 2,
                "sent_action_total": 8,
                "timeout_no_action_total": 1,
            },
            "final_standings": {
                "alive_count": 0,
                "winner": {"user_id": "1"},
                "runner_up": {"user_id": "2"},
            },
            "room_assignments": [],
            "log_truth": {"main_log": {"roomID_not_correct": 0, "onLooker_action": 0}},
        },
    )
    completed_payload = build_completed_payload(
        mtt_id=mtt_id,
        biz_id="biz-completed",
        room_id="room-1",
        seq=1,
        end_time=1776671716,
    )
    standup_payload = build_standup_payload(mtt_id=mtt_id, biz_id="biz-standup", user_id="2", hub_sequence=1)
    log_lines = [
        build_log_line(
            ts="2026-04-20T15:55:16.000+08:00",
            caller="mq/rocketmq.go:185",
            msg=f"send mq to key:biz-completed topic:POKER_RECORD_TOPIC,tag:,body:{json.dumps(completed_payload)}",
            mtt_id=mtt_id,
        ),
        build_log_line(
            ts="2026-04-20T15:55:17.000+08:00",
            caller="mq/rocketmq.go:196",
            msg=f"err:<nil> send mq to key:biz-completed msgID:1 topic:POKER_RECORD_TOPIC tag: body:{json.dumps(completed_payload)}",
            mtt_id=mtt_id,
        ),
        build_log_line(
            ts="2026-04-20T15:55:18.000+08:00",
            caller="mq/rocketmq.go:185",
            msg=f"send mq to key:biz-standup topic:POKER_RECORD_STANDUP_TOPIC,tag:mtt,body:{json.dumps(standup_payload)}",
            mtt_id=mtt_id,
        ),
        build_log_line(
            ts="2026-04-20T15:55:19.000+08:00",
            caller="mq/rocketmq.go:196",
            msg=(
                "err:rpc error: code = DeadlineExceeded desc = context deadline exceeded "
                f"send mq to key:biz-standup msgID: topic:POKER_RECORD_STANDUP_TOPIC tag: body:{json.dumps(standup_payload)}"
            ),
            mtt_id=mtt_id,
        ),
    ]
    log_path = tmp_path / "donor.log"
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    result = emitted_mq_replay.asyncio.run(
        emitted_mq_replay.run_emitted_mq_replay(
            json.loads(summary_path.read_text(encoding="utf-8")),
            json.loads(evidence_path.read_text(encoding="utf-8")),
            donor_log_path=log_path,
            summary_path=summary_path,
            evidence_path=evidence_path,
            reward_pool_amount=1000,
        )
    )

    assert result["mq_replay"]["emitted_count"] == 2
    assert result["mq_replay"]["accepted_event_count"] == 2
    assert result["mq_replay"]["broker_ack_counts_by_topic"]["POKER_RECORD_TOPIC"]["success"] == 1
    assert result["mq_replay"]["broker_ack_counts_by_topic"]["POKER_RECORD_STANDUP_TOPIC"]["deadline"] == 1
    assert result["finalize"]["hand_history_evidence_root"] == result["mq_replay"]["hand_history_evidence_root"]
    assert result["finalize"]["consumer_checkpoint_root"] == result["mq_replay"]["consumer_checkpoint_root"]
    assert result["reward_window"]["state"] == "finalized"
    assert result["settlement_batch"]["chain_confirmation_state"] == "confirmed"
    assert result["anchor_job"]["state"] == "anchored"
    assert result["gate_status"]["same_run_donor_emitted_payload_replay_complete"] is True
    assert result["gate_status"]["release_chain_complete"] is True
    assert result["gate_status"]["broker_acked_live_mq_projector_complete"] is False
    assert result["known_gap"]["code"] == "broker_acked_same_run_live_projector_not_confirmed"


def test_run_emitted_mq_replay_clears_known_gap_once_broker_ack_is_confirmed(tmp_path: Path):
    mtt_id = "phase3-log-replay-acked"
    summary_path = write_json(
        tmp_path / "summary.json",
        {
            "mtt_id": mtt_id,
            "standings": {
                "standings": [
                    {
                        "display_rank": 1,
                        "payout_rank": 1,
                        "status": "alive",
                        "member_id": "1:1",
                        "user_id": "1",
                        "entry_number": 1,
                        "player_name": "1",
                        "room_id": None,
                        "start_chip": 6000,
                        "end_chip": 12000,
                        "died_time": "0",
                        "stand_up_status": None,
                        "alive_rank_zero_based": 0,
                        "died_rank_internal": None,
                        "zset_score": None,
                        "snapshot_found": True,
                    },
                    {
                        "display_rank": 2,
                        "payout_rank": 2,
                        "status": "died",
                        "member_id": "2:1",
                        "user_id": "2",
                        "entry_number": 1,
                        "player_name": "2",
                        "room_id": None,
                        "start_chip": 0,
                        "end_chip": 0,
                        "died_time": "1776672905",
                        "stand_up_status": "standUpDieStatus",
                        "alive_rank_zero_based": None,
                        "died_rank_internal": 1,
                        "zset_score": None,
                        "snapshot_found": True,
                    },
                ]
            },
        },
    )
    evidence_path = write_json(
        tmp_path / "runtime.json",
        {
            "captured_at": "2026-04-20T08:15:34Z",
            "mtt_id": mtt_id,
            "summary_artifact": str(summary_path),
            "connections": {
                "joined_users": 2,
                "sent_action_total": 8,
                "timeout_no_action_total": 1,
            },
            "final_standings": {
                "alive_count": 1,
                "payout_rank_unique": True,
                "winner": {"user_id": "1", "payout_rank": 1, "died_time": "0"},
                "runner_up": {"user_id": "2", "payout_rank": 2, "died_time": "1776672905"},
            },
            "room_assignments": [],
            "log_truth": {"main_log": {"roomID_not_correct": 0, "onLooker_action": 0}},
        },
    )
    completed_payload = build_completed_payload(
        mtt_id=mtt_id,
        biz_id="biz-completed",
        room_id="room-1",
        seq=1,
        end_time=1776671716,
    )
    standup_payload = build_standup_payload(mtt_id=mtt_id, biz_id="biz-standup", user_id="2", hub_sequence=1)
    log_lines = [
        build_log_line(
            ts="2026-04-20T15:55:16.000+08:00",
            caller="mq/rocketmq.go:185",
            msg=f"send mq to key:biz-completed topic:POKER_RECORD_TOPIC,tag:,body:{json.dumps(completed_payload)}",
            mtt_id=mtt_id,
        ),
        build_log_line(
            ts="2026-04-20T15:55:17.000+08:00",
            caller="mq/rocketmq.go:196",
            msg=f"err:<nil> send mq to key:biz-completed msgID:1 topic:POKER_RECORD_TOPIC tag: body:{json.dumps(completed_payload)}",
            mtt_id=mtt_id,
        ),
        build_log_line(
            ts="2026-04-20T15:55:18.000+08:00",
            caller="mq/rocketmq.go:185",
            msg=f"send mq to key:biz-standup topic:POKER_RECORD_STANDUP_TOPIC,tag:mtt,body:{json.dumps(standup_payload)}",
            mtt_id=mtt_id,
        ),
        build_log_line(
            ts="2026-04-20T15:55:19.000+08:00",
            caller="mq/rocketmq.go:196",
            msg=f"err:<nil> send mq to key:biz-standup msgID:2 topic:POKER_RECORD_STANDUP_TOPIC tag: body:{json.dumps(standup_payload)}",
            mtt_id=mtt_id,
        ),
    ]
    log_path = tmp_path / "donor.log"
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    result = emitted_mq_replay.asyncio.run(
        emitted_mq_replay.run_emitted_mq_replay(
            json.loads(summary_path.read_text(encoding="utf-8")),
            json.loads(evidence_path.read_text(encoding="utf-8")),
            donor_log_path=log_path,
            summary_path=summary_path,
            evidence_path=evidence_path,
            reward_pool_amount=1000,
        )
    )

    assert result["mq_replay"]["broker_ack_counts_by_topic"]["POKER_RECORD_TOPIC"]["success"] == 1
    assert result["mq_replay"]["broker_ack_counts_by_topic"]["POKER_RECORD_STANDUP_TOPIC"]["success"] == 1
    assert result["gate_status"]["broker_acked_live_mq_projector_complete"] is True
    assert result["known_gap"] is None
