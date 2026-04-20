from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bundle poker MTT runtime, settlement replay, and burst evidence into one Phase 3 release pack.",
    )
    parser.add_argument("--runtime-evidence", type=Path, required=True)
    parser.add_argument("--settlement-evidence", type=Path, required=True)
    parser.add_argument("--burst-summary", type=Path, required=True)
    parser.add_argument("--emitted-mq-replay", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def hash_file(path: Path) -> str:
    return hash_bytes(path.read_bytes())


def hash_payload(payload: dict[str, Any]) -> str:
    return hash_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def as_iso(value: str | None) -> str | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def as_int(value: Any) -> int:
    if value is None:
        return 0
    return int(value)


def runtime_has_terminal_ranking(runtime: dict[str, Any]) -> bool:
    connections = runtime.get("connections", {})
    final_standings = runtime.get("final_standings", {})
    joined_users = as_int(connections.get("joined_users"))
    standings_count_raw = final_standings.get("standings_count")
    snapshot_count_raw = final_standings.get("snapshot_count")
    standings_count = as_int(standings_count_raw or snapshot_count_raw)
    pending_count = as_int(final_standings.get("pending_count"))
    alive_count = as_int(final_standings.get("alive_count"))
    winner = final_standings.get("winner") or {}
    standings_complete = (
        standings_count == joined_users if standings_count_raw is not None or snapshot_count_raw is not None else True
    )

    champion_survivor_row = (
        alive_count == 1
        and winner.get("user_id") is not None
        and as_int(winner.get("payout_rank") or winner.get("display_rank")) == 1
        and str(winner.get("died_time")) == "0"
    )

    return (
        joined_users == 30
        and standings_complete
        and pending_count == 0
        and final_standings.get("payout_rank_unique") is True
        and (alive_count == 0 or champion_survivor_row)
    )


def build_release_pack(
    *,
    runtime_evidence_path: Path,
    settlement_evidence_path: Path,
    burst_summary_path: Path,
    emitted_mq_replay_path: Path | None = None,
) -> dict[str, Any]:
    runtime = load_json(runtime_evidence_path)
    settlement = load_json(settlement_evidence_path)
    burst = load_json(burst_summary_path)
    emitted_replay = load_json(emitted_mq_replay_path) if emitted_mq_replay_path else None

    runtime_gate = (
        runtime_has_terminal_ranking(runtime)
        and runtime.get("log_truth", {}).get("main_log", {}).get("roomID_not_correct") == 0
        and runtime.get("log_truth", {}).get("main_log", {}).get("onLooker_action") == 0
    )
    settlement_gate = (
        settlement.get("gate_status", {}).get("locked_ranking_complete") is True
        and settlement.get("gate_status", {}).get("reward_window_finalized") is True
        and settlement.get("gate_status", {}).get("query_confirmed_settlement") is True
    )
    burst_gate = (
        int(burst.get("events", {}).get("completed_hand_processed") or 0) > 0
        and int(burst.get("events", {}).get("standup_processed") or 0) > 0
        and int(burst.get("dlq_total") or 0) == 0
        and int(burst.get("conflict_total") or 0) == 0
        and int(burst.get("user_count") or 0) >= 20000
        and int(burst.get("table_count") or 0) >= 2000
    )
    emitted_replay_gate = (
        emitted_replay is not None
        and emitted_replay.get("gate_status", {}).get("same_run_donor_emitted_payload_replay_complete") is True
        and emitted_replay.get("gate_status", {}).get("release_chain_complete") is True
    )
    live_projector_complete = (
        emitted_replay.get("gate_status", {}).get("broker_acked_live_mq_projector_complete") is True
        if emitted_replay
        else False
    )

    summary = {
        "runtime_tournament_id": runtime.get("mtt_id"),
        "runtime_winner_user_id": runtime.get("final_standings", {}).get("winner", {}).get("user_id"),
        "runtime_runner_up_user_id": runtime.get("final_standings", {}).get("runner_up", {}).get("user_id"),
        "runtime_joined_users": runtime.get("connections", {}).get("joined_users"),
        "runtime_sent_action_total": runtime.get("connections", {}).get("sent_action_total"),
        "settlement_reward_window_id": settlement.get("reward_window", {}).get("id"),
        "settlement_batch_id": settlement.get("settlement_batch", {}).get("id"),
        "settlement_anchor_job_id": settlement.get("anchor_job", {}).get("id"),
        "settlement_anchor_state": settlement.get("anchor_job", {}).get("state"),
        "burst_users": burst.get("user_count"),
        "burst_tables": burst.get("table_count"),
        "burst_completed_hand_count": burst.get("events", {}).get("completed_hand_processed"),
        "burst_standup_count": burst.get("events", {}).get("standup_processed"),
        "burst_checkpoint_root": burst.get("anchor", {}).get("consumer_checkpoint_root"),
        "emitted_mq_replay_path": str(emitted_mq_replay_path) if emitted_mq_replay_path else None,
        "emitted_mq_replay_hand_history_root": (
            emitted_replay.get("mq_replay", {}).get("hand_history_evidence_root") if emitted_replay else None
        ),
        "emitted_mq_replay_checkpoint_root": (
            emitted_replay.get("mq_replay", {}).get("consumer_checkpoint_root") if emitted_replay else None
        ),
    }

    payload = {
        "built_at": as_iso(datetime.now(timezone.utc).isoformat()),
        "phase": "phase3",
        "product_line": "poker_mtt",
        "evidence_scope": {
            "runtime_realism": "donor non-mock 30-player explicit join and ws sample",
            "release_chain": "clawchain replay of the same runtime sample through finalize, reward window, settlement, and query-confirmed anchor",
            "scale_and_projector": "donor-shaped synthetic 20k-user burst for completed-hand ingest, checkpointing, and settlement prep",
            "same_run_emitted_replay": "same donor runtime sample parsed from donor main log and replayed through the ClawChain hand-history projector",
        },
        "artifacts": {
            "runtime_evidence": {
                "path": str(runtime_evidence_path),
                "file_hash": hash_file(runtime_evidence_path),
            },
            "settlement_evidence": {
                "path": str(settlement_evidence_path),
                "file_hash": hash_file(settlement_evidence_path),
            },
            "burst_summary": {
                "path": str(burst_summary_path),
                "file_hash": hash_file(burst_summary_path),
            },
        },
        "summary": summary,
        "gate_status": {
            "runtime_realism_complete": runtime_gate,
            "release_chain_complete": settlement_gate,
            "scale_burst_complete": burst_gate,
            "same_run_donor_emitted_payload_replay_complete": emitted_replay_gate,
            "same_run_live_mq_projector_complete": live_projector_complete,
            "phase3_release_pack_complete": runtime_gate
            and settlement_gate
            and burst_gate
            and (emitted_replay_gate if emitted_mq_replay_path else True),
        },
        "known_gap": (
            None
            if live_projector_complete
            else {
                "code": (
                    "broker_acked_same_run_live_projector_not_confirmed"
                    if emitted_replay
                    else "same_run_live_mq_projector_not_recaptured"
                ),
                "message": (
                    "The same donor runtime sample emitted replayable MQ payloads, but donor broker acknowledgements still did not prove a successful live projector path for every payload."
                    if emitted_replay
                    else "The donor non-mock runtime sample and the MQ/projector evidence are still proven in two linked artifacts, not one identical live run."
                ),
            }
        ),
        "runtime_snapshot": {
            "captured_at": runtime.get("captured_at"),
            "winner": runtime.get("final_standings", {}).get("winner"),
            "runner_up": runtime.get("final_standings", {}).get("runner_up"),
            "log_truth": runtime.get("log_truth"),
        },
        "settlement_snapshot": {
            "captured_at": settlement.get("captured_at"),
            "reward_window": settlement.get("reward_window"),
            "settlement_batch": settlement.get("settlement_batch"),
            "anchor_job": settlement.get("anchor_job"),
            "gate_status": settlement.get("gate_status"),
        },
        "burst_snapshot": {
            "scale": {
                "users": burst.get("user_count"),
                "tables": burst.get("table_count"),
                "hands_per_table": burst.get("hands_per_table"),
            },
            "history": {
                "total": burst.get("events", {}).get("total"),
                "completed_hand_count": burst.get("events", {}).get("completed_hand_processed"),
                "standup_count": burst.get("events", {}).get("standup_processed"),
                "dlq_count": burst.get("dlq_total"),
                "conflict_count": burst.get("conflict_total"),
            },
            "reward_window": burst.get("reward_window"),
            "anchor": burst.get("anchor"),
        },
    }
    if emitted_replay:
        payload["artifacts"]["emitted_mq_replay"] = {
            "path": str(emitted_mq_replay_path),
            "file_hash": hash_file(emitted_mq_replay_path),
        }
        payload["emitted_mq_snapshot"] = {
            "captured_at": emitted_replay.get("captured_at"),
            "mq_replay": emitted_replay.get("mq_replay"),
            "gate_status": emitted_replay.get("gate_status"),
            "known_gap": emitted_replay.get("known_gap"),
        }
    payload["payload_hash"] = hash_payload(payload)
    return payload


def main() -> int:
    args = parse_args()
    pack = build_release_pack(
        runtime_evidence_path=args.runtime_evidence,
        settlement_evidence_path=args.settlement_evidence,
        burst_summary_path=args.burst_summary,
        emitted_mq_replay_path=args.emitted_mq_replay,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
