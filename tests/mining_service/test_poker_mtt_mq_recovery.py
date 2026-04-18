from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine
import poker_mtt_history
from repository import FakeRepository


NOW = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)


def hand_event(
    *,
    tournament_id: str = "mtt-mq-1",
    table_id: str = "table-1",
    hand_no: int = 42,
    version: int | None = 1,
    pot: int = 120,
    offset: int = 10,
    message_id: str | None = None,
    lag_messages: int = 0,
) -> dict:
    return poker_mtt_history.build_hand_completed_event(
        tournament_id=tournament_id,
        table_id=table_id,
        hand_no=hand_no,
        version=version,
        payload={"pot": pot, "actions": [{"seat": 2, "type": "call"}]},
        source={
            "transport": "rocketmq",
            "topic": "POKER_RECORD_TOPIC",
            "queue": "queue-a",
            "consumer_group": "clawchain-poker-mtt-hands",
            "offset": offset,
            "message_id": message_id or f"msg-{offset}",
            "biz_id": f"biz-{offset}",
            "record_type": "recordType",
            "source_mtt_id": tournament_id,
            "source_room_id": table_id,
            "lag_messages": lag_messages,
        },
    )


def test_hand_ingest_updates_checkpoint_across_duplicate_update_and_stale_replay():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        event_v1 = hand_event(version=1, pot=120, offset=10)
        duplicate_v1 = hand_event(version=1, pot=120, offset=11)
        event_v2 = hand_event(version=2, pot=160, offset=12)
        stale_v1 = hand_event(version=1, pot=120, offset=13)

        inserted = await service.ingest_poker_mtt_hand_event(event_v1, now=NOW)
        duplicate = await service.ingest_poker_mtt_hand_event(duplicate_v1, now=NOW)
        updated = await service.ingest_poker_mtt_hand_event(event_v2, now=NOW)
        stale = await service.ingest_poker_mtt_hand_event(stale_v1, now=NOW)
        hand = await repo.get_poker_mtt_hand_event("mtt-mq-1:table-1:42")
        checkpoints = await repo.list_poker_mtt_mq_checkpoints(tournament_id="mtt-mq-1")

        assert [inserted["state"], duplicate["state"], updated["state"], stale["state"]] == [
            "inserted",
            "duplicate",
            "updated",
            "stale",
        ]
        assert hand["version"] == 2
        assert len(checkpoints) == 1
        checkpoint = checkpoints[0]
        assert checkpoint["topic"] == "POKER_RECORD_TOPIC"
        assert checkpoint["consumer_group"] == "clawchain-poker-mtt-hands"
        assert checkpoint["queue"] == "queue-a"
        assert checkpoint["last_offset"] == 13
        assert checkpoint["last_message_id"] == "msg-13"
        assert checkpoint["last_biz_id"] == "biz-13"
        assert checkpoint["last_hand_id"] == "mtt-mq-1:table-1:42"
        assert checkpoint["last_ingest_state"] == "stale"
        assert checkpoint["replay_root"].startswith("sha256:")

    asyncio.run(scenario())


def test_crash_after_hand_write_before_checkpoint_is_recovered_by_replay():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        event = hand_event(offset=21)
        await repo.save_poker_mtt_hand_event(event)
        assert await repo.list_poker_mtt_mq_checkpoints(tournament_id="mtt-mq-1") == []

        replay = await service.ingest_poker_mtt_hand_event(event, now=NOW)
        checkpoints = await repo.list_poker_mtt_mq_checkpoints(tournament_id="mtt-mq-1")

        assert replay["state"] == "duplicate"
        assert len(checkpoints) == 1
        assert checkpoints[0]["last_offset"] == 21
        assert checkpoints[0]["last_ingest_state"] == "duplicate"

    asyncio.run(scenario())


def test_same_version_checksum_conflict_is_persisted_for_manual_review():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.ingest_poker_mtt_hand_event(hand_event(version=1, pot=120, offset=30), now=NOW)

        conflict = await service.ingest_poker_mtt_hand_event(hand_event(version=1, pot=220, offset=31), now=NOW)
        conflicts = await repo.list_poker_mtt_mq_conflicts(tournament_id="mtt-mq-1")
        checkpoints = await repo.list_poker_mtt_mq_checkpoints(tournament_id="mtt-mq-1")

        assert conflict["state"] == "conflict"
        assert conflict["reason"] == "same_version_checksum_mismatch"
        assert len(conflicts) == 1
        assert conflicts[0]["state"] == "manual_review"
        assert conflicts[0]["conflict_reason"] == "same_version_checksum_mismatch"
        assert conflicts[0]["hand_id"] == "mtt-mq-1:table-1:42"
        assert conflicts[0]["message_id"] == "msg-31"
        assert conflicts[0]["checksum"] != conflicts[0]["previous_checksum"]
        assert checkpoints[0]["last_ingest_state"] == "conflict"

    asyncio.run(scenario())


def test_malformed_hand_payload_goes_to_dlq_without_crashing_consumer():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        malformed = {
            "schema_version": "bad-schema",
            "event_type": "poker_mtt.hand_completed",
            "event_id": "bad-msg-1",
            "source": {
                "transport": "rocketmq",
                "topic": "POKER_RECORD_TOPIC",
                "queue": "queue-a",
                "consumer_group": "clawchain-poker-mtt-hands",
                "offset": 40,
                "message_id": "bad-msg-1",
                "biz_id": "bad-biz-1",
                "source_mtt_id": "mtt-mq-1",
            },
            "identity": {"tournament_id": "mtt-mq-1", "table_id": "table-1", "hand_no": 42, "hand_id": "mtt-mq-1:table-1:42"},
            "checksum": "sha256:bad",
            "payload": {"pot": 120},
        }

        result = await service.ingest_poker_mtt_hand_event(malformed, now=NOW)
        dlq_rows = await repo.list_poker_mtt_mq_dlq(tournament_id="mtt-mq-1")
        checkpoints = await repo.list_poker_mtt_mq_checkpoints(tournament_id="mtt-mq-1")

        assert result["state"] == "dlq"
        assert result["reason"] == "invalid hand completed schema_version"
        assert len(dlq_rows) == 1
        assert dlq_rows[0]["message_id"] == "bad-msg-1"
        assert dlq_rows[0]["dlq_reason"] == "invalid hand completed schema_version"
        assert checkpoints[0]["last_ingest_state"] == "dlq"

    asyncio.run(scenario())


def test_checkpoint_replay_root_is_deterministic_across_replays():
    async def scenario():
        first_repo = FakeRepository()
        second_repo = FakeRepository()
        first_service = forecast_engine.ForecastMiningService(first_repo, forecast_engine.ForecastSettings())
        second_service = forecast_engine.ForecastMiningService(second_repo, forecast_engine.ForecastSettings())
        event = hand_event(version=1, pot=120, offset=50, message_id="msg-stable")

        await first_service.ingest_poker_mtt_hand_event(event, now=NOW)
        await second_service.ingest_poker_mtt_hand_event(event, now=NOW)

        first_checkpoint = (await first_repo.list_poker_mtt_mq_checkpoints(tournament_id="mtt-mq-1"))[0]
        second_checkpoint = (await second_repo.list_poker_mtt_mq_checkpoints(tournament_id="mtt-mq-1"))[0]

        assert first_checkpoint["replay_root"] == second_checkpoint["replay_root"]

    asyncio.run(scenario())
