#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
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

import forecast_engine
import poker_mtt_evidence
import mq_projector
import release_evidence_replay as replay
import runtime_projection as runtime
from repository import FakeRepository


EMIT_CALLER = "mq/rocketmq.go:185"
ACK_CALLER = "mq/rocketmq.go:196"
CONSUMER_NAME = "donor-log-replay"
COMPLETED_HAND_TOPIC = mq_projector.COMPLETED_HAND_TOPIC
STANDUP_TOPIC = mq_projector.STANDUP_TOPIC
TOPIC_PATTERN = re.compile(r"topic:(POKER_RECORD_TOPIC|POKER_RECORD_STANDUP_TOPIC)")
ACK_ERROR_PATTERN = re.compile(r"^err:(.*?) send mq to key:")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay donor-emitted same-run MQ payloads from the gameserver log through the ClawChain poker MTT projector.",
    )
    parser.add_argument("--summary", type=Path, required=True, help="Path to the runtime summary JSON.")
    parser.add_argument("--evidence", type=Path, required=True, help="Path to the runtime evidence JSON.")
    parser.add_argument("--donor-log", type=Path, required=True, help="Path to the donor gameserver main log.")
    parser.add_argument("--output", type=Path, required=True, help="Path to write the emitted-MQ replay evidence JSON.")
    parser.add_argument("--lane", choices=("poker_mtt_daily", "poker_mtt_weekly"), default="poker_mtt_daily")
    parser.add_argument("--reward-pool-amount", type=int, default=1000)
    parser.add_argument("--started-minutes-before-lock", type=int, default=45)
    parser.add_argument("--late-join-grace-seconds", type=int, default=600)
    parser.add_argument("--runtime-source", default=replay.DEFAULT_RUNTIME_SOURCE)
    parser.add_argument("--final-ranking-source", default=replay.DEFAULT_FINAL_RANKING_SOURCE)
    parser.add_argument("--policy-bundle-version", default=replay.DEFAULT_POLICY_BUNDLE_VERSION)
    parser.add_argument(
        "--reward-window-policy-version",
        default=None,
        help="Reward window policy version. Defaults to the lane-specific Phase 3 policy bundle.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def classify_ack_status(error_text: str) -> str:
    normalized = str(error_text or "").strip()
    if normalized == "<nil>":
        return "success"
    if "DeadlineExceeded" in normalized or "context deadline exceeded" in normalized:
        return "deadline"
    if "rpc error" in normalized or "grpc" in normalized:
        return "grpc_fail"
    if not normalized:
        return "unknown"
    return "error"


def _extract_topic(message: str) -> str | None:
    match = TOPIC_PATTERN.search(message)
    if not match:
        return None
    return match.group(1)


def _extract_payload(message: str) -> dict[str, Any]:
    _, marker, body_text = message.partition("body:")
    if not marker or not body_text:
        raise ValueError("message body not found")
    return json.loads(body_text)


def _extract_ack_error(message: str) -> str:
    match = ACK_ERROR_PATTERN.match(message)
    if not match:
        return "unknown"
    return match.group(1).strip()


def collect_donor_mq_events(*, donor_log_path: Path, tournament_id: str) -> dict[str, Any]:
    emitted_events: list[dict[str, Any]] = []
    broker_acks: list[dict[str, Any]] = []

    with donor_log_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if tournament_id not in line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("mttID") != tournament_id:
                continue
            caller = record.get("caller")
            if caller not in {EMIT_CALLER, ACK_CALLER}:
                continue
            message = str(record.get("msg") or "")
            topic = _extract_topic(message)
            if topic not in {COMPLETED_HAND_TOPIC, STANDUP_TOPIC}:
                continue
            payload = _extract_payload(message)
            timestamp = parse_iso_datetime(str(record["ts"]))
            entry = {
                "ts": forecast_engine.isoformat_z(timestamp),
                "line_number": line_number,
                "topic": topic,
                "biz_id": str(payload.get("bizID") or ""),
                "room_id": record.get("roomID"),
                "trace_id": record.get("trace_id"),
                "payload": payload,
            }
            if caller == EMIT_CALLER:
                emitted_events.append(entry)
                continue
            error_text = _extract_ack_error(message)
            broker_acks.append(
                {
                    **entry,
                    "error_text": error_text,
                    "status": classify_ack_status(error_text),
                }
            )

    emitted_events.sort(key=lambda item: (item["ts"], item["line_number"]))
    broker_acks.sort(key=lambda item: (item["ts"], item["line_number"]))

    ack_counts: dict[str, dict[str, int]] = {
        COMPLETED_HAND_TOPIC: {},
        STANDUP_TOPIC: {},
    }
    for ack in broker_acks:
        counts = ack_counts.setdefault(ack["topic"], {})
        counts[ack["status"]] = int(counts.get(ack["status"], 0) or 0) + 1

    emitted_counts = {
        COMPLETED_HAND_TOPIC: sum(1 for item in emitted_events if item["topic"] == COMPLETED_HAND_TOPIC),
        STANDUP_TOPIC: sum(1 for item in emitted_events if item["topic"] == STANDUP_TOPIC),
    }
    return {
        "emitted_events": emitted_events,
        "broker_acks": broker_acks,
        "metrics": {
            "emitted_count": len(emitted_events),
            "completed_hand_emitted_count": emitted_counts[COMPLETED_HAND_TOPIC],
            "standup_emitted_count": emitted_counts[STANDUP_TOPIC],
            "broker_ack_count": len(broker_acks),
            "broker_ack_counts_by_topic": ack_counts,
        },
    }


async def build_mq_evidence_summary(
    *,
    repo,
    tournament_id: str,
    policy_bundle_version: str,
    accepted_event_count: int,
    generated_at: datetime,
) -> dict[str, Any]:
    hand_rows = await repo.list_poker_mtt_hand_events_for_tournament(tournament_id)
    checkpoints = await repo.list_poker_mtt_mq_checkpoints(tournament_id=tournament_id)
    hand_manifest = (
        poker_mtt_evidence.build_hand_history_manifest(
            tournament_id=tournament_id,
            rows=hand_rows,
            policy_bundle_version=policy_bundle_version,
            generated_at=generated_at,
        )
        if hand_rows
        else None
    )
    checkpoint_manifest = (
        poker_mtt_evidence.build_consumer_checkpoint_manifest(
            tournament_id=tournament_id,
            rows=checkpoints,
            policy_bundle_version=policy_bundle_version,
            generated_at=generated_at,
        )
        if checkpoints
        else None
    )
    freshness_candidates = [
        row.get("updated_at")
        for row in [*hand_rows, *checkpoints]
        if row.get("updated_at") is not None
    ]
    latest_freshness_at = max(freshness_candidates) if freshness_candidates else None
    return {
        "accepted_event_count": accepted_event_count,
        "checkpoint_count": len(checkpoints),
        "hand_history_evidence_root": hand_manifest["manifest_root"] if hand_manifest else None,
        "consumer_checkpoint_root": checkpoint_manifest["manifest_root"] if checkpoint_manifest else None,
        "latest_freshness_at": latest_freshness_at,
    }


async def run_emitted_mq_replay(
    summary: dict[str, Any],
    evidence: dict[str, Any],
    *,
    donor_log_path: Path,
    summary_path: Path | None = None,
    evidence_path: Path | None = None,
    lane: str = "poker_mtt_daily",
    reward_pool_amount: int = 1000,
    started_minutes_before_lock: int = 45,
    late_join_grace_seconds: int = 600,
    runtime_source: str = replay.DEFAULT_RUNTIME_SOURCE,
    final_ranking_source: str = replay.DEFAULT_FINAL_RANKING_SOURCE,
    policy_bundle_version: str = replay.DEFAULT_POLICY_BUNDLE_VERSION,
    reward_window_policy_version: str | None = None,
) -> dict[str, Any]:
    if summary["mtt_id"] != evidence["mtt_id"]:
        raise ValueError("summary and evidence must reference the same tournament")

    donor_log = collect_donor_mq_events(donor_log_path=donor_log_path, tournament_id=summary["mtt_id"])
    if donor_log["metrics"]["emitted_count"] <= 0:
        raise ValueError("no donor-emitted MQ payloads found for tournament")

    locked_at = parse_iso_datetime(evidence["captured_at"]).replace(microsecond=0)
    resolved_reward_window_policy_version = runtime.derive_reward_window_policy_version(lane, reward_window_policy_version)
    apply_payload, wallet_bindings, replay_notes = runtime.build_apply_payload(
        summary,
        evidence,
        locked_at=locked_at,
        started_minutes_before_lock=started_minutes_before_lock,
        late_join_grace_seconds=late_join_grace_seconds,
        runtime_source=runtime_source,
        final_ranking_source=final_ranking_source,
        policy_bundle_version=policy_bundle_version,
    )

    first_emit_at = parse_iso_datetime(donor_log["emitted_events"][0]["ts"])
    clock = replay.FrozenClock(first_emit_at)
    repo = FakeRepository()

    async def fake_typed_broadcaster(plan, now):  # noqa: ANN001
        return {
            "tx_hash": "TYPED-MQ-" + summary["mtt_id"],
            "code": 0,
            "raw_log": "",
            "memo": plan["fallback_memo"],
            "broadcast_at": forecast_engine.isoformat_z(now),
            "account_number": 0,
            "sequence": 1,
            "attempt_count": 1,
            "broadcast_method": "typed_msg",
        }

    async def fake_confirmer(tx_hash, now):  # noqa: ANN001
        return {
            "tx_hash": tx_hash,
            "found": True,
            "confirmed": True,
            "confirmation_status": "confirmed",
            "height": 987655,
            "code": 0,
            "raw_log": "",
        }

    service = forecast_engine.ForecastMiningService(
        repo,
        forecast_engine.ForecastSettings(
            poker_mtt_reward_windows_enabled=True,
            poker_mtt_settlement_anchoring_enabled=True,
            poker_mtt_daily_reward_pool_amount=reward_pool_amount,
            poker_mtt_weekly_reward_pool_amount=reward_pool_amount,
        ),
        chain_typed_broadcaster=fake_typed_broadcaster,
        chain_tx_confirmer=fake_confirmer,
    )

    ingest_status_counts: dict[str, int] = {}
    replay_event_preview: list[dict[str, Any]] = []
    accepted_event_count = 0
    for event in donor_log["emitted_events"]:
        replay_result = await mq_projector.replay_donor_message(
            service=service,
            repo=repo,
            tournament_id=summary["mtt_id"],
            topic=event["topic"],
            message=event["payload"],
            consumer_name=CONSUMER_NAME,
            received_at=parse_iso_datetime(event["ts"]),
        )
        ingest_status_counts[replay_result["status"]] = int(ingest_status_counts.get(replay_result["status"], 0) or 0) + 1
        if replay_result["status"].startswith("accepted"):
            accepted_event_count += 1
        if len(replay_event_preview) < 5:
            replay_event_preview.append(
                {
                    "topic": event["topic"],
                    "biz_id": event["biz_id"],
                    "status": replay_result["status"],
                    "ts": event["ts"],
                }
            )

    evidence_summary = await build_mq_evidence_summary(
        repo=repo,
        tournament_id=summary["mtt_id"],
        policy_bundle_version=policy_bundle_version,
        accepted_event_count=accepted_event_count,
        generated_at=locked_at,
    )

    chain_result = await replay.execute_release_chain(
        summary=summary,
        evidence=evidence,
        apply_payload=apply_payload,
        wallet_bindings=wallet_bindings,
        replay_notes={
            **replay_notes,
            "hand_history_strategy": "same_run_donor_emitted_payload_replay",
            "consumer_name": CONSUMER_NAME,
        },
        locked_at=locked_at,
        lane=lane,
        reward_pool_amount=reward_pool_amount,
        reward_window_policy_version=resolved_reward_window_policy_version,
        hand_history_evidence_root=evidence_summary["hand_history_evidence_root"],
        consumer_checkpoint_root=evidence_summary["consumer_checkpoint_root"],
        summary_path=summary_path,
        evidence_path=evidence_path,
        tx_hash_prefix="TYPED-MQ-",
        repo=repo,
        service=service,
        clock=clock,
    )

    checkpoints = await repo.list_poker_mtt_mq_checkpoints(tournament_id=summary["mtt_id"])
    dlq_entries = await repo.list_poker_mtt_mq_dlq(tournament_id=summary["mtt_id"])

    broker_ack_counts = donor_log["metrics"]["broker_ack_counts_by_topic"]
    broker_success_count = sum(int(topic_counts.get("success", 0) or 0) for topic_counts in broker_ack_counts.values())
    live_projector_complete = (
        broker_success_count >= donor_log["metrics"]["emitted_count"]
        and evidence_summary["accepted_event_count"] >= donor_log["metrics"]["emitted_count"]
        and len(dlq_entries) == 0
    )

    release_chain_complete = chain_result["gate_status"]["release_proof_complete"] is True
    same_run_payload_replay_complete = (
        evidence_summary["accepted_event_count"] > 0
        and chain_result["finalize"]["hand_history_evidence_root"] == evidence_summary["hand_history_evidence_root"]
        and chain_result["finalize"]["consumer_checkpoint_root"] == evidence_summary["consumer_checkpoint_root"]
    )

    return {
        **chain_result,
        "input_paths": {
            **chain_result["input_paths"],
            "donor_log": str(donor_log_path),
        },
        "mq_replay": {
            "consumer_name": CONSUMER_NAME,
            "emitted_count": donor_log["metrics"]["emitted_count"],
            "completed_hand_emitted_count": donor_log["metrics"]["completed_hand_emitted_count"],
            "standup_emitted_count": donor_log["metrics"]["standup_emitted_count"],
            "broker_ack_count": donor_log["metrics"]["broker_ack_count"],
            "broker_ack_counts_by_topic": broker_ack_counts,
            "ingest_status_counts": ingest_status_counts,
            "accepted_event_count": evidence_summary["accepted_event_count"],
            "checkpoint_count": evidence_summary["checkpoint_count"],
            "dlq_count": len(dlq_entries),
            "hand_history_evidence_root": evidence_summary["hand_history_evidence_root"],
            "consumer_checkpoint_root": evidence_summary["consumer_checkpoint_root"],
            "latest_freshness_at": evidence_summary["latest_freshness_at"],
            "event_preview": replay_event_preview,
        },
        "gate_status": {
            "same_run_donor_emitted_payload_replay_complete": same_run_payload_replay_complete,
            "release_chain_complete": release_chain_complete,
            "broker_acked_live_mq_projector_complete": live_projector_complete,
        },
        "known_gap": (
            None
            if live_projector_complete
            else {
                "code": "broker_acked_same_run_live_projector_not_confirmed",
                "message": "The same donor runtime sample emitted replayable MQ payloads, but the donor broker acknowledgements did not prove a successful live projector path for every payload.",
            }
        ),
        "raw_broker_ack_preview": donor_log["broker_acks"][:5],
        "checkpoint_metrics": [
            {
                "consumer_name": checkpoint["consumer_group"],
                "topic": checkpoint["topic"],
                "accepted_count": 1 if str(checkpoint.get("last_ingest_state", "")).startswith("accepted") else 0,
                "stale_ignored_count": 0,
                "conflict_count": 0,
                "dlq_count": 0,
                "last_event_version": checkpoint.get("last_offset"),
            }
            for checkpoint in checkpoints
        ],
    }


def main() -> int:
    args = parse_args()
    summary = load_json(args.summary)
    evidence = load_json(args.evidence)
    payload = asyncio.run(
        run_emitted_mq_replay(
            summary,
            evidence,
            donor_log_path=args.donor_log,
            summary_path=args.summary,
            evidence_path=args.evidence,
            lane=args.lane,
            reward_pool_amount=args.reward_pool_amount,
            started_minutes_before_lock=args.started_minutes_before_lock,
            late_join_grace_seconds=args.late_join_grace_seconds,
            runtime_source=args.runtime_source,
            final_ranking_source=args.final_ranking_source,
            policy_bundle_version=args.policy_bundle_version,
            reward_window_policy_version=args.reward_window_policy_version,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
