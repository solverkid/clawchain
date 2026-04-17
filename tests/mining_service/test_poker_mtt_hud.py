from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import poker_mtt_history
import poker_mtt_hud


def test_hud_hot_store_is_disabled_by_default():
    store = poker_mtt_hud.InMemoryHUDHotStore()
    result = store.project_hand(hand_event(), settings=poker_mtt_hud.HUDProjectionSettings(enabled=False))

    assert result.state == "disabled"
    assert store.snapshot_rows(tournament_id="mtt-hud-1") == []


def test_hud_hot_store_projects_basic_short_term_actions_idempotently():
    store = poker_mtt_hud.InMemoryHUDHotStore()
    settings = poker_mtt_hud.HUDProjectionSettings(enabled=True)
    event = hand_event()

    first = store.project_hand(event, settings=settings)
    duplicate = store.project_hand(event, settings=settings)
    rows = store.snapshot_rows(tournament_id="mtt-hud-1")
    manifest = poker_mtt_hud.build_hud_manifest(
        tournament_id="mtt-hud-1",
        rows=list(reversed(rows)),
        policy_bundle_version="poker_mtt_policy_v1",
        generated_at="2026-04-10T12:00:00Z",
    )
    same_manifest = poker_mtt_hud.build_hud_manifest(
        tournament_id="mtt-hud-1",
        rows=rows,
        policy_bundle_version="poker_mtt_policy_v1",
        generated_at="2026-04-10T12:00:00+00:00",
    )

    assert first.state == "projected"
    assert duplicate.state == "duplicate"
    assert len(rows) == 2
    assert rows[0]["miner_address"] == "claw1alice"
    assert rows[0]["hands_seen"] == 1
    assert rows[0]["vpip_count"] == 1
    assert rows[0]["pfr_count"] == 1
    assert rows[0]["three_bet_count"] == 1
    assert rows[1]["miner_address"] == "claw1bob"
    assert rows[1]["hands_seen"] == 1
    assert rows[1]["vpip_count"] == 1
    assert rows[1]["pfr_count"] == 0
    assert manifest["kind"] == "poker_mtt_short_term_hud_manifest"
    assert manifest["rows_root"] == same_manifest["rows_root"]
    assert manifest["manifest_root"] == same_manifest["manifest_root"]


def test_short_term_hud_projects_cbet_showdown_and_won_showdown_idempotently():
    store = poker_mtt_hud.InMemoryHUDHotStore()
    settings = poker_mtt_hud.HUDProjectionSettings(enabled=True, window="short_term")
    event = hand_event_with_showdown()

    first = store.project_hand(event, settings=settings)
    duplicate = store.project_hand(event, settings=settings)
    rows = store.snapshot_rows(tournament_id="mtt-hud-1")
    alice = next(row for row in rows if row["miner_address"] == "claw1alice")

    assert first.state == "projected"
    assert duplicate.state == "duplicate"
    assert alice["cbet_count"] == 1
    assert alice["went_to_showdown_count"] == 1
    assert alice["won_showdown_count"] == 1


def test_long_term_hud_manifest_is_separate_from_short_term_manifest():
    rows = [
        {
            "tournament_id": "mtt-hud-1",
            "miner_address": "claw1alice",
            "hud_window": "long_term",
            "hands_seen": 100,
            "itm_count": 18,
            "win_count": 3,
            "profitable_count": 41,
            "confidence": 0.8,
        }
    ]

    manifest = poker_mtt_hud.build_hud_manifest(
        tournament_id="mtt-hud-1",
        rows=rows,
        policy_bundle_version="poker_mtt_policy_v1",
        generated_at="2026-04-10T12:00:00Z",
        kind=poker_mtt_hud.LONG_TERM_HUD_MANIFEST_KIND,
    )

    assert manifest["kind"] == "poker_mtt_long_term_hud_manifest"
    assert manifest["row_count"] == 1


def test_hud_snapshot_tables_and_repository_surface_are_separate_by_window():
    async def scenario():
        from models import TABLES
        from pg_repository import PostgresRepository
        from repository import FakeRepository

        short_table = TABLES["poker_mtt_short_term_hud_snapshots"]
        long_table = TABLES["poker_mtt_long_term_hud_snapshots"]
        assert {"id", "tournament_id", "miner_address", "hud_window", "metrics_json"}.issubset(short_table.c.keys())
        assert {"id", "tournament_id", "miner_address", "hud_window", "metrics_json"}.issubset(long_table.c.keys())
        assert callable(getattr(PostgresRepository, "save_poker_mtt_hud_snapshot"))
        assert callable(getattr(PostgresRepository, "list_poker_mtt_hud_snapshots"))

        repo = FakeRepository()
        await repo.save_poker_mtt_hud_snapshot(
            {
                "tournament_id": "mtt-hud-1",
                "miner_address": "claw1alice",
                "hud_window": "short_term",
                "hands_seen": 1,
                "vpip_count": 1,
                "policy_bundle_version": "poker_mtt_policy_v1",
            }
        )
        await repo.save_poker_mtt_hud_snapshot(
            {
                "tournament_id": "mtt-hud-1",
                "miner_address": "claw1alice",
                "hud_window": "long_term",
                "hands_seen": 100,
                "itm_count": 18,
                "policy_bundle_version": "poker_mtt_policy_v1",
            }
        )

        short_rows = await repo.list_poker_mtt_hud_snapshots(
            tournament_id="mtt-hud-1",
            miner_address="claw1alice",
            hud_window="short_term",
        )
        long_rows = await repo.list_poker_mtt_hud_snapshots(
            tournament_id="mtt-hud-1",
            miner_address="claw1alice",
            hud_window="long_term",
        )

        assert [row["hud_window"] for row in short_rows] == ["short_term"]
        assert [row["hud_window"] for row in long_rows] == ["long_term"]
        assert short_rows[0]["metrics_json"]["vpip_count"] == 1
        assert long_rows[0]["metrics_json"]["itm_count"] == 18

    import asyncio

    asyncio.run(scenario())


def hand_event() -> dict:
    return poker_mtt_history.build_hand_completed_event(
        tournament_id="mtt-hud-1",
        table_id="table-1",
        hand_no=7,
        version=1,
        payload={
            "players": [
                {"miner_address": "claw1alice", "source_user_id": "alice"},
                {"miner_address": "claw1bob", "source_user_id": "bob"},
            ],
            "actions": [
                {"miner_address": "claw1bob", "street": "preflop", "action": "call"},
                {"miner_address": "claw1alice", "street": "preflop", "action": "raise", "raise_number": 1},
                {"miner_address": "claw1alice", "street": "preflop", "action": "raise", "raise_number": 3},
                {"miner_address": "claw1bob", "street": "flop", "action": "fold"},
            ],
        },
        source={
            "transport": "rocketmq",
            "topic": "POKER_RECORD_TOPIC",
            "message_id": "msg-hud-7",
            "biz_id": "biz-hud-7",
            "record_type": "recordType",
            "source_mtt_id": "donor-mtt-hud-1",
            "source_room_id": "donor-room-hud-1",
        },
    )


def hand_event_with_showdown() -> dict:
    return poker_mtt_history.build_hand_completed_event(
        tournament_id="mtt-hud-1",
        table_id="table-1",
        hand_no=8,
        version=1,
        payload={
            "players": [
                {"miner_address": "claw1alice", "source_user_id": "alice"},
                {"miner_address": "claw1bob", "source_user_id": "bob"},
            ],
            "actions": [
                {"miner_address": "claw1alice", "street": "preflop", "action": "raise", "raise_number": 1},
                {"miner_address": "claw1bob", "street": "preflop", "action": "call"},
                {"miner_address": "claw1alice", "street": "flop", "action": "bet"},
                {"miner_address": "claw1bob", "street": "flop", "action": "call"},
            ],
            "showdown": [
                {"miner_address": "claw1alice", "won": True},
                {"miner_address": "claw1bob", "won": False},
            ],
        },
        source={
            "transport": "rocketmq",
            "topic": "POKER_RECORD_TOPIC",
            "message_id": "msg-hud-8",
            "biz_id": "biz-hud-8",
            "record_type": "recordType",
            "source_mtt_id": "donor-mtt-hud-1",
            "source_room_id": "donor-room-hud-1",
        },
    )
