#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine
import poker_mtt_history


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate local Poker MTT Phase 2 load-contract shapes.")
    parser.add_argument("--players", type=int, default=30, help="Smoke MTT player count.")
    parser.add_argument("--hands", type=int, default=30, help="Completed-hand events to synthesize.")
    parser.add_argument("--table-size", type=int, default=9, help="Seats per table for synthetic room shape.")
    parser.add_argument("--medium-players", type=int, default=300, help="Medium synthetic field size.")
    parser.add_argument(
        "--synthetic-projection-players",
        type=int,
        default=20000,
        help="Large projection field size for paged artifact contract.",
    )
    parser.add_argument(
        "--early-table-count",
        type=int,
        default=2000,
        help="Synthetic early-stage table burst count.",
    )
    parser.add_argument("--page-size", type=int, default=5000, help="Reward projection artifact page size.")
    parser.add_argument("--output", type=Path, help="Optional path to write the JSON summary.")
    return parser.parse_args()


def require_positive(name: str, value: int) -> None:
    if value <= 0:
        raise SystemExit(f"{name} must be positive")


def table_count_for_players(player_count: int, table_size: int) -> int:
    return max(1, math.ceil(player_count / table_size))


def miner_address(index: int) -> str:
    return f"claw1load{index:05d}"


def build_hand_event(*, tournament_id: str, hand_no: int, player_count: int, table_size: int) -> dict[str, Any]:
    table_index = (hand_no - 1) % max(1, table_count_for_players(player_count, table_size))
    table_id = f"table-{table_index:04d}"
    small_blind = 50 + ((hand_no - 1) // 10) * 25
    big_blind = small_blind * 2
    payload = {
        "hand_no": hand_no,
        "table_id": table_id,
        "blind_level": {
            "small_blind": small_blind,
            "big_blind": big_blind,
            "ante": 0,
        },
        "button_seat": ((hand_no - 1) % table_size) + 1,
        "pot": big_blind * 3,
        "actions": [
            {"street": "preflop", "seat": 1, "type": "small_blind", "amount": small_blind},
            {"street": "preflop", "seat": 2, "type": "big_blind", "amount": big_blind},
            {"street": "preflop", "seat": 3, "type": "raise", "amount": big_blind * 3},
            {"street": "preflop", "seat": 4, "type": "fold"},
            {"street": "showdown", "seat": 3, "type": "win", "amount": big_blind * 3},
        ],
        "winners": [{"seat": 3, "amount": big_blind * 3}],
    }
    source = {
        "transport": "synthetic_load",
        "topic": "POKER_RECORD_TOPIC",
        "message_id": f"load-msg-{tournament_id}-{hand_no}",
        "record_type": "recordType",
        "source_mtt_id": tournament_id,
        "source_room_id": table_id,
    }
    return poker_mtt_history.build_hand_completed_event(
        tournament_id=tournament_id,
        table_id=table_id,
        hand_no=hand_no,
        version=1,
        payload=payload,
        source=source,
    )


def build_projection_summary(*, player_count: int, page_size: int) -> dict[str, Any]:
    miner_reward_rows = [
        {
            "miner_address": miner_address(index),
            "gross_reward_amount": 1,
            "submission_count": 1,
        }
        for index in range(player_count)
    ]
    projection, pages = forecast_engine.build_paged_poker_mtt_projection_payload(
        {
            "reward_window_id": "rw-load",
            "lane": "poker_mtt_daily",
            "miner_reward_rows": miner_reward_rows,
        },
        page_size=page_size,
    )
    return {
        "player_count": player_count,
        "artifact_page_count": projection["artifact_page_count"],
        "miner_reward_rows_root": projection["miner_reward_rows_root"],
        "page_roots": [page["page_root"] for page in pages],
        "inline_rows_in_main_payload": "miner_reward_rows" in projection,
    }


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    for name in (
        "players",
        "hands",
        "table_size",
        "medium_players",
        "synthetic_projection_players",
        "early_table_count",
        "page_size",
    ):
        require_positive(name, int(getattr(args, name)))

    tournament_id = "phase2-load-smoke"
    hand_events = [
        build_hand_event(
            tournament_id=tournament_id,
            hand_no=hand_no,
            player_count=args.players,
            table_size=args.table_size,
        )
        for hand_no in range(1, args.hands + 1)
    ]
    smoke_table_count = table_count_for_players(args.players, args.table_size)
    medium_table_count = table_count_for_players(args.medium_players, args.table_size)

    return {
        "schema_version": "poker_mtt.phase2_load.v1",
        "smoke_mtt": {
            "tournament_id": tournament_id,
            "player_count": args.players,
            "table_count": smoke_table_count,
            "table_size": args.table_size,
            "hand_event_count": len(hand_events),
            "first_hand_id": hand_events[0]["identity"]["hand_id"],
            "last_hand_id": hand_events[-1]["identity"]["hand_id"],
            "hand_event_checksum_root": forecast_engine._hash_sequence(
                [{"hand_id": event["identity"]["hand_id"], "checksum": event["checksum"]} for event in hand_events]
            ),
        },
        "medium_check": {
            "player_count": args.medium_players,
            "table_count": medium_table_count,
            "expected_room_assignment_shape": "multi_table",
        },
        "synthetic_projection": build_projection_summary(
            player_count=args.synthetic_projection_players,
            page_size=args.page_size,
        ),
        "early_table_burst": {
            "table_count": args.early_table_count,
            "shape": "one_completed_hand_per_table_burst",
            "expected_min_hand_events": args.early_table_count,
            "estimated_players_at_nine_max": args.early_table_count * args.table_size,
        },
        "observability_fields": list(forecast_engine.POKER_MTT_OBSERVABILITY_FIELDS),
    }


def main() -> int:
    args = parse_args()
    summary = build_summary(args)
    encoded = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
