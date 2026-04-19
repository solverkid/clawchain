from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "poker_mtt" / "complete_standings.py"


def load_module():
    spec = importlib.util.spec_from_file_location("complete_standings", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_complete_standings_alive_then_died() -> None:
    module = load_module()
    snapshot_map = {
        "0:1": {"userID": "0", "playerName": "0", "entryNumber": 1, "endChip": 3200, "startChip": 3000},
        "1:1": {"userID": "1", "playerName": "1", "entryNumber": 1, "endChip": 2800, "startChip": 3000},
        "2:1": {"userID": "2", "playerName": "2", "entryNumber": 1, "endChip": 0, "startChip": 3000},
        "3:1": {"userID": "3", "playerName": "3", "entryNumber": 1, "endChip": 0, "startChip": 3000},
    }
    alive_members = ["0:1", "1:1"]
    died_entries = [
        {"rank": 2, "userID": "3", "playerName": "3", "entryNumber": 1, "endChip": 0, "startChip": 3000},
        {"rank": 1, "userID": "2", "playerName": "2", "entryNumber": 1, "endChip": 0, "startChip": 3000},
    ]

    standings = module.build_complete_standings(snapshot_map, alive_members, died_entries)

    assert [(item["user_id"], item["display_rank"], item["status"]) for item in standings] == [
        ("0", 1, "alive"),
        ("1", 2, "alive"),
        ("3", 3, "died"),
        ("2", 4, "died"),
    ]
    assert [(item["user_id"], item["rank"]) for item in standings] == [
        ("0", 1),
        ("1", 2),
        ("3", 3),
        ("2", 4),
    ]


def test_build_complete_standings_preserves_tied_died_rank_groups() -> None:
    module = load_module()
    snapshot_map = {
        "0:1": {"userID": "0", "playerName": "0", "entryNumber": 1, "endChip": 1200, "startChip": 3000},
        "1:1": {"userID": "1", "playerName": "1", "entryNumber": 1, "endChip": 0, "startChip": 1900},
        "2:1": {"userID": "2", "playerName": "2", "entryNumber": 1, "endChip": 0, "startChip": 2200},
        "3:1": {"userID": "3", "playerName": "3", "entryNumber": 1, "endChip": 0, "startChip": 500},
    }
    alive_members = ["0:1"]
    died_entries = [
        {"rank": 3, "userID": "2", "playerName": "2", "entryNumber": 1, "endChip": 0, "startChip": 2200},
        {"rank": 3, "userID": "1", "playerName": "1", "entryNumber": 1, "endChip": 0, "startChip": 1900},
        {"rank": 1, "userID": "3", "playerName": "3", "entryNumber": 1, "endChip": 0, "startChip": 500},
    ]

    standings = module.build_complete_standings(snapshot_map, alive_members, died_entries)

    assert [(item["user_id"], item["display_rank"]) for item in standings] == [
        ("0", 1),
        ("2", 2),
        ("1", 2),
        ("3", 4),
    ]
    assert [(item["user_id"], item["rank"]) for item in standings] == [
        ("0", 1),
        ("2", 2),
        ("1", 3),
        ("3", 4),
    ]
    assert [item["rank"] for item in standings] == sorted(item["rank"] for item in standings)


def test_build_complete_standings_sorts_output_by_unique_payout_rank() -> None:
    module = load_module()
    snapshot_map = {
        "0:1": {"userID": "0", "playerName": "0", "entryNumber": 1, "endChip": 9000, "startChip": 3000},
        "1:1": {"userID": "1", "playerName": "1", "entryNumber": 1, "endChip": 0, "startChip": 900},
        "2:1": {"userID": "2", "playerName": "2", "entryNumber": 1, "endChip": 0, "startChip": 2200},
        "3:1": {"userID": "3", "playerName": "3", "entryNumber": 1, "endChip": 0, "startChip": 1500},
    }
    alive_members = ["0:1"]
    died_entries = [
        {"rank": 3, "userID": "1", "playerName": "1", "entryNumber": 1, "endChip": 0, "startChip": 900},
        {"rank": 3, "userID": "2", "playerName": "2", "entryNumber": 1, "endChip": 0, "startChip": 2200},
        {"rank": 3, "userID": "3", "playerName": "3", "entryNumber": 1, "endChip": 0, "startChip": 1500},
    ]

    standings = module.build_complete_standings(snapshot_map, alive_members, died_entries)

    assert [(item["user_id"], item["display_rank"], item["rank"]) for item in standings] == [
        ("0", 1, 1),
        ("2", 2, 2),
        ("3", 2, 3),
        ("1", 2, 4),
    ]


def test_build_complete_standings_leaves_pending_without_payout_rank() -> None:
    module = load_module()
    snapshot_map = {
        "0:1": {"userID": "0", "playerName": "0", "entryNumber": 1, "endChip": 3200, "startChip": 3000},
        "1:1": {"userID": "1", "playerName": "1", "entryNumber": 1, "endChip": 3000, "startChip": 3000},
    }
    alive_members = ["0:1"]

    standings = module.build_complete_standings(snapshot_map, alive_members, [])

    assert [(item["user_id"], item["status"], item["rank"], item["display_rank"]) for item in standings] == [
        ("0", "alive", 1, 1),
        ("1", "pending", None, None),
    ]


def test_to_display_rank_converts_zero_based_alive_rank() -> None:
    module = load_module()

    assert module.to_display_rank(0) == 1
    assert module.to_display_rank(4) == 5
    assert module.to_display_rank(None) is None
