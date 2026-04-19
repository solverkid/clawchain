#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

import redis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build full MTT standings from donor Redis ranking keys.",
    )
    parser.add_argument("--redis-host", default="127.0.0.1")
    parser.add_argument("--redis-port", type=int, default=36379)
    parser.add_argument("--redis-db", type=int, default=15)
    parser.add_argument("--redis-password", default="")
    parser.add_argument("--mtt-id", required=True)
    parser.add_argument("--game-type", default="mtt")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def to_display_rank(zero_based_rank: int | None) -> int | None:
    if zero_based_rank is None:
        return None
    return int(zero_based_rank) + 1


def decode_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        payload = json.loads(value)
        if isinstance(payload, dict):
            return payload
    raise ValueError(f"expected JSON object, got: {value!r}")


def parse_member_id(member_id: str | None) -> tuple[str | None, int | None]:
    if not member_id:
        return None, None
    user_id, _, entry_part = str(member_id).partition(":")
    return normalize_string(user_id), to_int(entry_part)


def build_member_id(user_id: Any, entry_number: Any) -> str | None:
    normalized_user = normalize_string(user_id)
    normalized_entry = to_int(entry_number)
    if normalized_user is None or normalized_entry is None:
        return None
    return f"{normalized_user}:{normalized_entry}"


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def to_number(value: Any) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    text = str(value).strip()
    if not text:
        return None
    try:
        integer = int(text)
        return integer
    except ValueError:
        try:
            number = float(text)
        except ValueError:
            return None
        return int(number) if number.is_integer() else number


def normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    text = str(value)
    return text if text else None


def normalize_entry(
    entry: dict[str, Any],
    *,
    member_id: str | None,
    status: str,
    display_rank: int | None,
    rank: int | None = None,
    alive_rank_zero_based: int | None = None,
    died_rank_internal: int | None = None,
    zset_score: float | None = None,
    snapshot_found: bool = True,
) -> dict[str, Any]:
    parsed_user_id, parsed_entry_number = parse_member_id(member_id)
    user_id = normalize_string(entry.get("userID")) or parsed_user_id
    entry_number = to_int(entry.get("entryNumber"))
    if entry_number is None:
        entry_number = parsed_entry_number
    normalized_member_id = member_id or build_member_id(user_id, entry_number)
    return {
        "rank": rank,
        "display_rank": display_rank,
        "status": status,
        "member_id": normalized_member_id,
        "user_id": user_id,
        "entry_number": entry_number,
        "player_name": normalize_string(entry.get("playerName")),
        "room_id": normalize_string(entry.get("roomID")),
        "start_chip": to_number(entry.get("startChip")),
        "end_chip": to_number(entry.get("endChip")),
        "died_time": normalize_string(entry.get("diedTime")),
        "stand_up_status": normalize_string(entry.get("standUpStatus")),
        "alive_rank_zero_based": alive_rank_zero_based,
        "died_rank_internal": died_rank_internal,
        "zset_score": zset_score,
        "snapshot_found": snapshot_found,
    }


def member_sort_key(member_id: str) -> tuple[int, int, str]:
    user_id, entry_number = parse_member_id(member_id)
    user_order = to_int(user_id)
    return (
        user_order if user_order is not None else 10**12,
        entry_number if entry_number is not None else 10**12,
        member_id,
    )


def assign_unique_payout_ranks(standings: list[dict[str, Any]]) -> None:
    for item in standings:
        item["rank"] = None
    ranked = [
        item
        for item in standings
        if item.get("status") in {"alive", "died"} and item.get("display_rank") is not None
    ]

    def sort_key(item: dict[str, Any]) -> tuple[int, float, tuple[int, int, str]]:
        display_rank = to_int(item.get("display_rank")) or 10**12
        start_chip = to_number(item.get("start_chip")) or 0
        died_start_chip_order = -float(start_chip) if item.get("status") == "died" else 0.0
        member_id = normalize_string(item.get("member_id")) or ""
        return (display_rank, died_start_chip_order, member_sort_key(member_id))

    for payout_rank, item in enumerate(sorted(ranked, key=sort_key), start=1):
        item["rank"] = payout_rank


def final_standing_sort_key(item: dict[str, Any]) -> tuple[int, int, int, int, str]:
    rank = to_int(item.get("rank"))
    member_id = normalize_string(item.get("member_id")) or ""
    user_order, entry_order, member_order = member_sort_key(member_id)
    if rank is not None:
        return (0, rank, user_order, entry_order, member_order)
    display_rank = to_int(item.get("display_rank")) or 10**12
    return (1, display_rank, user_order, entry_order, member_order)


def build_complete_standings(
    snapshot_map: dict[str, Any],
    alive_members: list[str],
    died_entries: list[Any],
    *,
    alive_scores: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    decoded_snapshot_map = {
        str(member_id): decode_json_object(value)
        for member_id, value in snapshot_map.items()
    }
    alive_scores = alive_scores or {}
    standings: list[dict[str, Any]] = []
    seen_members: set[str] = set()

    for alive_rank_zero_based, member_id in enumerate(alive_members):
        snapshot = decoded_snapshot_map.get(member_id, {})
        standings.append(
            normalize_entry(
                snapshot,
                member_id=member_id,
                status="alive",
                display_rank=to_display_rank(alive_rank_zero_based),
                alive_rank_zero_based=alive_rank_zero_based,
                zset_score=alive_scores.get(member_id),
                snapshot_found=member_id in decoded_snapshot_map,
            )
        )
        seen_members.add(member_id)

    died_rank = len(alive_members)
    same_count = 1
    last_internal_rank: int | None = None
    fallback_rank = len(alive_members)
    for raw_entry in died_entries:
        died_entry = decode_json_object(raw_entry)
        member_id = build_member_id(died_entry.get("userID"), died_entry.get("entryNumber"))
        if member_id and member_id in seen_members:
            continue

        internal_rank = to_int(died_entry.get("rank"))
        if internal_rank is None:
            fallback_rank += 1
            display_rank = fallback_rank
        elif last_internal_rank is not None and internal_rank == last_internal_rank:
            display_rank = died_rank
            same_count += 1
        else:
            last_internal_rank = internal_rank
            died_rank += same_count
            display_rank = died_rank
            same_count = 1
            fallback_rank = max(fallback_rank, display_rank)

        snapshot = decoded_snapshot_map.get(member_id or "", {})
        merged_entry = {**snapshot, **died_entry}
        standings.append(
            normalize_entry(
                merged_entry,
                member_id=member_id,
                status="died",
                display_rank=display_rank,
                died_rank_internal=internal_rank,
                snapshot_found=member_id in decoded_snapshot_map if member_id else False,
            )
        )
        if member_id:
            seen_members.add(member_id)

    for member_id in sorted(decoded_snapshot_map, key=member_sort_key):
        if member_id in seen_members:
            continue
        standings.append(
            normalize_entry(
                decoded_snapshot_map[member_id],
                member_id=member_id,
                status="pending",
                display_rank=None,
                snapshot_found=True,
            )
        )
    assign_unique_payout_ranks(standings)
    return sorted(standings, key=final_standing_sort_key)


def fetch_complete_standings(
    redis_client: redis.Redis,
    mtt_id: str,
    *,
    game_type: str = "mtt",
) -> dict[str, Any]:
    snapshot_key = f"rankingUserInfo:{game_type}:{mtt_id}"
    alive_key = f"rankingNotDiedScore:{game_type}:{mtt_id}"
    died_key = f"rankingUserDiedInfo:{game_type}:{mtt_id}"

    snapshot_map = redis_client.hgetall(snapshot_key)
    alive_items = redis_client.zrevrange(alive_key, 0, -1, withscores=True)
    alive_members = [member for member, _ in alive_items]
    alive_scores = {member: float(score) for member, score in alive_items}
    died_entries = redis_client.lrange(died_key, 0, -1)

    standings = build_complete_standings(
        snapshot_map,
        alive_members,
        died_entries,
        alive_scores=alive_scores,
    )
    return {
        "mtt_id": mtt_id,
        "game_type": game_type,
        "keys": {
            "snapshot_key": snapshot_key,
            "alive_key": alive_key,
            "died_key": died_key,
        },
        "counts": {
            "snapshot_count": len(snapshot_map),
            "alive_count": len(alive_members),
            "died_count": len(died_entries),
            "pending_count": sum(1 for item in standings if item["status"] == "pending"),
            "standings_count": len(standings),
        },
        "standings": standings,
    }


def main() -> int:
    args = parse_args()
    redis_client = redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        db=args.redis_db,
        password=args.redis_password or None,
        decode_responses=True,
    )
    payload = fetch_complete_standings(redis_client, args.mtt_id, game_type=args.game_type)
    if args.pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
