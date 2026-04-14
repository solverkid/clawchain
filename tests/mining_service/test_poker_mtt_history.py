from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import poker_mtt_history


def test_hand_completed_hot_store_is_idempotent_by_version_and_checksum():
    store = poker_mtt_history.InMemoryHandHistoryHotStore()
    event_v1 = hand_event(version=1, pot_amount=120)
    same_event_v1 = hand_event(version=1, pot_amount=120)
    event_v2 = hand_event(version=2, pot_amount=140)
    stale_event = hand_event(version=1, pot_amount=120)
    conflicting_event = hand_event(version=2, pot_amount=160)

    inserted = store.ingest(event_v1)
    duplicate = store.ingest(same_event_v1)
    updated = store.ingest(event_v2)
    stale = store.ingest(stale_event)
    conflict = store.ingest(conflicting_event)

    assert inserted.state == "inserted"
    assert duplicate.state == "duplicate"
    assert updated.state == "updated"
    assert stale.state == "stale"
    assert conflict.state == "conflict"
    assert store.get("mtt-history-1:table-1:42")["version"] == 2
    assert store.get("mtt-history-1:table-1:42")["checksum"] == event_v2["checksum"]


def test_missing_version_hand_event_only_accepts_existing_checksum_match():
    store = poker_mtt_history.InMemoryHandHistoryHotStore()
    versioned = hand_event(version=3, pot_amount=220)
    missing_same_checksum = {k: v for k, v in versioned.items() if k != "version"}
    missing_conflict = hand_event(version=None, pot_amount=260)

    store.ingest(versioned)
    duplicate = store.ingest(missing_same_checksum)
    conflict = store.ingest(missing_conflict)

    assert duplicate.state == "duplicate"
    assert conflict.state == "conflict"
    assert conflict.reason == "missing_version_checksum_mismatch"


def test_hand_completed_event_id_is_deterministic_from_canonical_payload():
    first = hand_event(version=1, pot_amount=120, payload={"actions": [{"seat": 2, "type": "call"}], "pot": 120})
    second = hand_event(version=1, pot_amount=120, payload={"pot": 120, "actions": [{"type": "call", "seat": 2}]})

    assert first["event_type"] == "poker_mtt.hand_completed"
    assert first["schema_version"] == "poker_mtt.hand_completed.v1"
    assert first["identity"]["hand_id"] == "mtt-history-1:table-1:42"
    assert first["checksum"] == second["checksum"]
    assert first["event_id"] == second["event_id"]


def hand_event(*, version: int | None, pot_amount: int, payload: dict | None = None) -> dict:
    payload = payload or {"pot": pot_amount, "actions": [{"seat": 2, "type": "call"}]}
    return poker_mtt_history.build_hand_completed_event(
        tournament_id="mtt-history-1",
        table_id="table-1",
        hand_no=42,
        version=version,
        payload=payload,
        source={
            "transport": "rocketmq",
            "topic": "POKER_RECORD_TOPIC",
            "message_id": f"msg-{pot_amount}",
            "biz_id": "biz-42",
            "record_type": "recordType",
            "source_mtt_id": "donor-mtt-1",
            "source_room_id": "donor-room-1",
        },
    )
