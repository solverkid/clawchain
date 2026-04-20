from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine
import poker_mtt_history
from canonical import canonical_hash


COMPLETED_HAND_TOPIC = "POKER_RECORD_TOPIC"
STANDUP_TOPIC = "POKER_RECORD_STANDUP_TOPIC"
DEFAULT_QUEUE = "rocketmq:0"


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    raise ValueError("message payload must be dict or json string")


def _build_source(
    *,
    tournament_id: str,
    topic: str,
    consumer_name: str,
    received_at: datetime,
    biz_id: str,
    queue: str,
) -> dict[str, Any]:
    return {
        "topic": topic,
        "queue": queue,
        "consumer_group": consumer_name,
        "source_mtt_id": tournament_id,
        "mtt_id": tournament_id,
        "biz_id": biz_id,
        "message_id": biz_id,
        "lag_messages": 0,
        "lag_watermark_at": forecast_engine.isoformat_z(received_at),
    }


def build_hand_event_from_completed_message(
    *,
    tournament_id: str,
    message: dict[str, Any],
    consumer_name: str,
    received_at: datetime,
    queue: str = DEFAULT_QUEUE,
) -> dict[str, Any]:
    biz_id = str(message.get("bizID") or "")
    record_wrapper = _as_dict(message.get("record") or {})
    nested_record = _as_dict(record_wrapper.get("record") or {})
    table_id = str(
        record_wrapper.get("roomID")
        or nested_record.get("tableId")
        or nested_record.get("roomID")
        or nested_record.get("tableID")
        or message.get("gameID")
        or "unknown-table"
    )
    hand_no = int(record_wrapper.get("seq") or record_wrapper.get("version") or 0)
    if hand_no <= 0:
        raise ValueError("completed-hand donor message missing seq/version")
    version = int(record_wrapper.get("version") or hand_no)
    payload = {
        "bizID": biz_id,
        "record": {
            **record_wrapper,
            "record": nested_record,
        },
    }
    return poker_mtt_history.build_hand_completed_event(
        tournament_id=tournament_id,
        table_id=table_id,
        hand_no=hand_no,
        version=version,
        payload=payload,
        source=_build_source(
            tournament_id=tournament_id,
            topic=COMPLETED_HAND_TOPIC,
            consumer_name=consumer_name,
            received_at=received_at,
            biz_id=biz_id,
            queue=queue,
        ),
    )


def build_non_hand_checkpoint_row(
    *,
    tournament_id: str,
    topic: str,
    message: dict[str, Any],
    consumer_name: str,
    received_at: datetime,
    queue: str = DEFAULT_QUEUE,
    ingest_state: str = "accepted_non_hand",
) -> dict[str, Any]:
    biz_id = str(message.get("bizID") or "")
    replay_root = canonical_hash(
        {
            "tournament_id": tournament_id,
            "topic": topic,
            "consumer_group": consumer_name,
            "queue": queue,
            "biz_id": biz_id,
            "payload": message,
            "ingest_state": ingest_state,
        }
    )
    timestamp = forecast_engine.isoformat_z(received_at)
    return {
        "id": f"poker_mtt_mq_checkpoint:{tournament_id}:{topic}:{consumer_name}:{queue}",
        "tournament_id": tournament_id,
        "topic": topic,
        "queue": queue,
        "consumer_group": consumer_name,
        "last_offset": None,
        "last_message_id": biz_id,
        "last_biz_id": biz_id,
        "last_hand_id": None,
        "last_ingest_state": ingest_state,
        "replay_root": replay_root,
        "lag_messages": 0,
        "lag_watermark_at": timestamp,
        "source_json": _build_source(
            tournament_id=tournament_id,
            topic=topic,
            consumer_name=consumer_name,
            received_at=received_at,
            biz_id=biz_id,
            queue=queue,
        ),
        "last_processed_at": timestamp,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


async def replay_donor_message(
    *,
    service,
    repo,
    tournament_id: str,
    topic: str,
    message: dict[str, Any],
    consumer_name: str,
    received_at: datetime,
    queue: str = DEFAULT_QUEUE,
) -> dict[str, Any]:
    if topic == COMPLETED_HAND_TOPIC:
        event = build_hand_event_from_completed_message(
            tournament_id=tournament_id,
            message=message,
            consumer_name=consumer_name,
            received_at=received_at,
            queue=queue,
        )
        result = await service.ingest_poker_mtt_hand_event(event, now=received_at)
        return {
            "status": "accepted" if result["state"] in {"inserted", "updated", "duplicate"} else result["state"],
            "ingest_state": result["state"],
            "topic": topic,
        }
    if topic == STANDUP_TOPIC:
        checkpoint = build_non_hand_checkpoint_row(
            tournament_id=tournament_id,
            topic=topic,
            message=message,
            consumer_name=consumer_name,
            received_at=received_at,
            queue=queue,
        )
        await repo.save_poker_mtt_mq_checkpoint(checkpoint)
        return {
            "status": "accepted",
            "ingest_state": checkpoint["last_ingest_state"],
            "topic": topic,
        }
    raise ValueError(f"unsupported donor topic: {topic}")
