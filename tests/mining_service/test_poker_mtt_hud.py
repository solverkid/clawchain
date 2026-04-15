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
