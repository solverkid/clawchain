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


def test_repository_persists_hand_event_by_hand_id_version_and_checksum():
    async def scenario():
        from repository import FakeRepository

        repo = FakeRepository()
        event = hand_event(version=1, pot_amount=120)

        inserted = await repo.save_poker_mtt_hand_event(event)
        duplicate = await repo.save_poker_mtt_hand_event(hand_event(version=1, pot_amount=120))
        loaded = await repo.get_poker_mtt_hand_event("mtt-history-1:table-1:42")

        assert inserted["state"] == "inserted"
        assert duplicate["state"] == "duplicate"
        assert loaded["hand_id"] == "mtt-history-1:table-1:42"
        assert loaded["version"] == 1
        assert loaded["checksum"] == event["checksum"]
        assert loaded["payload_json"]["pot"] == 120

    import asyncio

    asyncio.run(scenario())


def test_hand_event_table_has_operational_indexes():
    from models import TABLES

    table = TABLES["poker_mtt_hand_events"]
    columns = set(table.c.keys())
    indexes = {index.name: tuple(column.name for column in index.columns) for index in table.indexes}

    assert {
        "hand_id",
        "tournament_id",
        "table_id",
        "hand_no",
        "version",
        "checksum",
        "event_id",
        "source_json",
        "payload_json",
        "ingest_state",
        "conflict_reason",
        "created_at",
        "updated_at",
    }.issubset(columns)
    assert indexes["ix_poker_mtt_hand_events_tournament_hand_no"] == ("tournament_id", "hand_no")
    assert indexes["ix_poker_mtt_hand_events_tournament_ingest_state"] == ("tournament_id", "ingest_state")
    assert indexes["ix_poker_mtt_hand_events_table_hand_no"] == ("table_id", "hand_no")


def test_postgres_repository_exposes_hand_event_methods():
    from pg_repository import PostgresRepository

    assert callable(getattr(PostgresRepository, "save_poker_mtt_hand_event"))
    assert callable(getattr(PostgresRepository, "get_poker_mtt_hand_event"))
    assert callable(getattr(PostgresRepository, "list_poker_mtt_hand_events_for_tournament"))


def test_repository_backed_hand_history_store_ingests_and_lists_tournament_hands():
    async def scenario():
        from repository import FakeRepository

        store = poker_mtt_history.RepositoryHandHistoryStore(FakeRepository())
        first = await store.ingest(hand_event(version=1, pot_amount=120))
        second = await store.ingest(hand_event(version=1, pot_amount=120))
        rows = await store.list_for_tournament("mtt-history-1")

        assert first.state == "inserted"
        assert second.state == "duplicate"
        assert [row["hand_id"] for row in rows] == ["mtt-history-1:table-1:42"]

    import asyncio

    asyncio.run(scenario())


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
