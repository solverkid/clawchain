#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import importlib.util
import json
import random
import socket
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import redis
import requests
import websocket

SCRIPT_DIR = Path(__file__).resolve().parent

try:
    from complete_standings import fetch_complete_standings
except ModuleNotFoundError:  # pragma: no cover - import path guard for test loaders
    spec = importlib.util.spec_from_file_location(
        "complete_standings",
        SCRIPT_DIR / "complete_standings.py",
    )
    if spec is None or spec.loader is None:  # pragma: no cover - runtime guard
        raise
    complete_standings = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(complete_standings)
    fetch_complete_standings = complete_standings.fetch_complete_standings


class HarnessFailure(RuntimeError):
    pass


ALLOWED_WS_CLOSE_ERROR_SNIPPETS = (
    "close status: 1000",
    "close status: 1001",
    "connection to remote host was lost",
    "socket is already closed",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run non-mock MTT users through auth-backed join + websocket play.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--outer-port", type=int, default=18082)
    parser.add_argument("--inner-port", type=int, default=18083)
    parser.add_argument("--redis-host", default="127.0.0.1")
    parser.add_argument("--redis-port", type=int, default=36379)
    parser.add_argument("--redis-db", type=int, default=15)
    parser.add_argument("--redis-password", default="")
    parser.add_argument("--mtt-id", default=f"non-mock-play-{int(time.time())}")
    parser.add_argument("--user-count", type=int, default=30)
    parser.add_argument("--table-room-count-at-least", type=int, default=4)
    parser.add_argument("--hold-seconds", type=float, default=60.0)
    parser.add_argument("--wait-seconds", type=float, default=120.0)
    parser.add_argument("--until-finish", action="store_true")
    parser.add_argument("--finish-timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--finish-poll-seconds", type=float, default=1.0)
    parser.add_argument("--request-timeout", type=float, default=5.0)
    parser.add_argument("--max-workers", type=int, default=30)
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def build_token(user_id: str) -> str:
    return f"Bearer local-user:{user_id}"


def sanitize_chip_choices(chips: list[Any] | None) -> list[float]:
    if not chips:
        return []
    normalized = sorted({float(chip) for chip in chips if chip is not None and float(chip) > 0})
    return normalized


def choose_supported_chip(chips: list[Any] | None, rng: random.Random) -> float:
    normalized = sanitize_chip_choices(chips)
    if not normalized:
        return 0.0
    if len(normalized) > 2:
        normalized = normalized[:-1]
    return float(rng.choice(normalized))


def choose_action_plan(supported_actions: list[dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    by_action = {
        str(item.get("action")): item
        for item in supported_actions
        if item.get("action")
    }
    if "check" in by_action:
        if "bet" in by_action and sanitize_chip_choices(by_action["bet"].get("chips")) and rng.random() < 0.35:
            return {
                "action": "bet",
                "chips": choose_supported_chip(by_action["bet"].get("chips"), rng),
            }
        return {"action": "check", "chips": 0}
    if "call" in by_action:
        roll = rng.random()
        if "raise" in by_action and sanitize_chip_choices(by_action["raise"].get("chips")) and roll < 0.30:
            return {
                "action": "raise",
                "chips": choose_supported_chip(by_action["raise"].get("chips"), rng),
            }
        if "fold" in by_action and roll < 0.08:
            return {"action": "fold", "chips": 0}
        if "allIn" in by_action and roll > 0.97:
            return {"action": "allIn", "chips": 0}
        return {"action": "call", "chips": 0}
    if "bet" in by_action and sanitize_chip_choices(by_action["bet"].get("chips")):
        return {
            "action": "bet",
            "chips": choose_supported_chip(by_action["bet"].get("chips"), rng),
        }
    if "raise" in by_action and sanitize_chip_choices(by_action["raise"].get("chips")):
        return {
            "action": "raise",
            "chips": choose_supported_chip(by_action["raise"].get("chips"), rng),
        }
    if "allIn" in by_action:
        return {"action": "allIn", "chips": 0}
    return {"action": "fold", "chips": 0}


def wait_for_port(host: str, port: int, deadline: float) -> None:
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.5)
    raise HarnessFailure(f"timeout waiting for {host}:{port}")


def parse_json_response(response: requests.Response) -> dict[str, Any]:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise HarnessFailure(f"expected JSON object, got: {payload!r}")
    return payload


def require_code_zero(payload: dict[str, Any], context: str) -> None:
    if payload.get("code", 0) != 0:
        raise HarnessFailure(f"{context} failed: {json.dumps(payload, ensure_ascii=False)}")


def start_mtt(args: argparse.Namespace) -> dict[str, Any]:
    response = requests.post(
        f"http://{args.host}:{args.inner_port}/v1/mtt/start",
        json={"ID": args.mtt_id, "type": "mtt"},
        timeout=args.request_timeout,
    )
    payload = parse_json_response(response)
    require_code_zero(payload, "start mtt")
    return payload


def collect_room_assignments(args: argparse.Namespace, deadline: float) -> dict[str, Any]:
    room_by_user: dict[str, str] = {}
    while time.time() < deadline:
        for idx in range(args.user_count):
            user_id = str(idx)
            if user_id in room_by_user:
                continue
            response = requests.get(
                f"http://{args.host}:{args.inner_port}/v1/mtt/getMTTRoomByID",
                params={"userID": user_id, "ID": args.mtt_id},
                timeout=args.request_timeout,
            )
            payload = parse_json_response(response)
            room_id = ((payload.get("data") or {}).get("roomID"))
            if room_id:
                room_by_user[user_id] = room_id
        if len(room_by_user) >= args.user_count:
            counter = collections.Counter(room_by_user.values())
            if len(counter) >= args.table_room_count_at_least:
                return {
                    "room_by_user": dict(sorted(room_by_user.items(), key=lambda item: int(item[0]))),
                    "unique_rooms": len(counter),
                    "room_sizes": dict(sorted(counter.items())),
                }
        time.sleep(0.5)
    raise HarnessFailure(
        "timeout waiting for room assignments "
        f"(users_seen={len(room_by_user)}, expected={args.user_count})"
    )


def join_game(args: argparse.Namespace, user_id: str) -> dict[str, Any]:
    token = build_token(user_id)
    response = requests.post(
        f"http://{args.host}:{args.outer_port}/v1/join_game?id={args.mtt_id}&type=mtt",
        headers={"Authorization": token},
        json={"time": int(time.time()), "playerName": user_id},
        timeout=args.request_timeout,
    )
    payload = parse_json_response(response)
    require_code_zero(payload, f"join game user={user_id}")
    session_id = payload.get("sessionID")
    if not session_id:
        raise HarnessFailure(f"join response missing sessionID for user={user_id}")
    return payload


def wait_for_redis_snapshot(args: argparse.Namespace, deadline: float) -> dict[str, Any]:
    client = redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        db=args.redis_db,
        password=args.redis_password or None,
        decode_responses=True,
    )
    snapshot_key = f"rankingUserInfo:mtt:{args.mtt_id}"
    alive_key = f"rankingNotDiedScore:mtt:{args.mtt_id}"
    died_key = f"rankingUserDiedInfo:mtt:{args.mtt_id}"
    while time.time() < deadline:
        snapshot_count = client.hlen(snapshot_key)
        alive_count = client.zcard(alive_key)
        died_items = client.lrange(died_key, 0, -1)
        if snapshot_count >= args.user_count:
            return {
                "snapshot_key": snapshot_key,
                "alive_key": alive_key,
                "died_key": died_key,
                "snapshot_count": snapshot_count,
                "alive_count": alive_count,
                "died_count": len(died_items),
            }
        time.sleep(0.5)
    raise HarnessFailure(
        "timeout waiting for redis snapshot "
        f"(snapshot_count={snapshot_count}, expected={args.user_count})"
    )


def is_tournament_finished(standings_payload: dict[str, Any], *, expected_players: int) -> bool:
    counts = standings_payload.get("counts") or {}
    snapshot_count = int(counts.get("snapshot_count") or 0)
    alive_count = int(counts.get("alive_count") or 0)
    pending_count = int(counts.get("pending_count") or 0)
    return snapshot_count >= expected_players and pending_count == 0 and alive_count <= 1


def is_allowed_ws_close_error(message: str) -> bool:
    normalized = str(message or "").lower()
    return any(snippet in normalized for snippet in ALLOWED_WS_CLOSE_ERROR_SNIPPETS)


def validate_finish_summary(summary: dict[str, Any], *, expected_players: int) -> None:
    connections = summary.get("connections") or {}
    finish_mode = summary.get("finish_mode") or {}
    standings = summary.get("standings") or {}
    counts = standings.get("counts") or {}
    users = list(summary.get("users") or [])

    expected_died = max(0, expected_players - 1)
    failures: list[str] = []
    required_counts = {
        "joined_users": expected_players,
        "received_current_mtt_ranking": expected_players,
        "users_with_sent_actions": expected_players,
    }
    for field, expected in required_counts.items():
        actual = int(connections.get(field) or 0)
        if actual != expected:
            failures.append(f"{field}={actual}, expected={expected}")
    if int(connections.get("sent_action_total") or 0) < expected_players:
        failures.append(
            f"sent_action_total={connections.get('sent_action_total')}, expected_at_least={expected_players}"
        )
    if finish_mode.get("finished") is not True:
        failures.append("finish_mode.finished=false")

    standings_required = {
        "snapshot_count": expected_players,
        "standings_count": expected_players,
        "alive_count": 1,
        "died_count": expected_died,
        "pending_count": 0,
    }
    for field, expected in standings_required.items():
        actual = int(counts.get(field) or 0)
        if actual != expected:
            failures.append(f"{field}={actual}, expected={expected}")

    if len(users) != expected_players:
        failures.append(f"users={len(users)}, expected={expected_players}")

    users_missing_ranking = []
    users_missing_actions = []
    unexpected_ws_errors = []
    for user in users:
        user_id = str(user.get("user_id") or "")
        ws_summary = user.get("ws") or {}
        if ws_summary.get("received_current_mtt_ranking") is not True:
            users_missing_ranking.append(user_id)
        if not ws_summary.get("sent_actions"):
            users_missing_actions.append(user_id)
        for error in ws_summary.get("errors") or []:
            if not is_allowed_ws_close_error(str(error)):
                unexpected_ws_errors.append({"user_id": user_id, "error": str(error)})

    if users_missing_ranking:
        failures.append(f"users_missing_current_mtt_ranking={users_missing_ranking}")
    if users_missing_actions:
        failures.append(f"users_missing_sent_actions={users_missing_actions}")
    if unexpected_ws_errors:
        failures.append(f"unexpected_ws_errors={unexpected_ws_errors[:5]}")

    statuses = collections.Counter(str(item.get("status") or "") for item in standings.get("standings") or [])
    if statuses.get("alive", 0) != 1 or statuses.get("died", 0) != expected_died or statuses.get("pending", 0) != 0:
        failures.append(f"standing_statuses={dict(sorted(statuses.items()))}")

    if failures:
        raise HarnessFailure("finish gate failed: " + "; ".join(failures))


def wait_for_tournament_finish(
    args: argparse.Namespace,
    redis_client: redis.Redis,
    finish_event: threading.Event,
) -> dict[str, Any]:
    finish_deadline = time.time() + args.finish_timeout_seconds
    last_standings: dict[str, Any] | None = None
    while time.time() < finish_deadline:
        standings = fetch_complete_standings(redis_client, args.mtt_id, game_type="mtt")
        last_standings = standings
        if is_tournament_finished(standings, expected_players=args.user_count):
            finish_event.set()
            return standings
        if finish_event.is_set():
            return standings
        time.sleep(args.finish_poll_seconds)
    finish_event.set()
    if last_standings is None:
        last_standings = fetch_complete_standings(redis_client, args.mtt_id, game_type="mtt")
    counts = last_standings.get("counts") or {}
    raise HarnessFailure(
        "timeout waiting for tournament finish "
        f"(alive_count={counts.get('alive_count')}, pending_count={counts.get('pending_count')}, "
        f"snapshot_count={counts.get('snapshot_count')})"
    )


def update_known_position(user_id: str, payload: dict[str, Any], known_position: int | None) -> int | None:
    players = payload.get("playerStatus") or []
    if not isinstance(players, list):
        return known_position
    for player in players:
        if not isinstance(player, dict):
            continue
        if str(player.get("userID") or "") == user_id and player.get("position") is not None:
            return int(player["position"])
    return known_position


def send_action(ws: websocket.WebSocket, position: int, plan: dict[str, Any]) -> None:
    command = {
        "action": plan["action"],
        "position": position,
    }
    if plan.get("chips"):
        command["chips"] = float(plan["chips"])
    ws.send(json.dumps(command))


def hold_ws_session(
    args: argparse.Namespace,
    user_id: str,
    session_id: str,
    rng_seed: int,
    finish_event: threading.Event | None = None,
) -> dict[str, Any]:
    token = build_token(user_id)
    ws_url = (
        f"ws://{args.host}:{args.outer_port}/v1/ws?"
        + urlencode({"id": args.mtt_id, "type": "mtt"})
    )
    ws = websocket.create_connection(
        ws_url,
        subprotocols=[token, session_id],
        timeout=args.request_timeout,
    )
    ws.settimeout(1.0)

    rng = random.Random(rng_seed)
    session_timeout_seconds = args.finish_timeout_seconds if args.until_finish else args.hold_seconds
    hold_deadline = time.time() + session_timeout_seconds
    actions: list[str] = []
    sent_actions: list[dict[str, Any]] = []
    errors: list[str] = []
    action_counts: collections.Counter[str] = collections.Counter()
    known_position: int | None = None
    received_ranking = False

    try:
        ws.send(json.dumps({"action": "mttRanking"}))
        while time.time() < hold_deadline:
            if finish_event is not None and finish_event.is_set():
                break
            try:
                raw_message = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as exc:  # pragma: no cover - runtime guard
                errors.append(f"recv failed: {exc}")
                break
            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError as exc:
                errors.append(f"json decode failed: {exc}")
                continue
            action = str(payload.get("action") or "")
            actions.append(action)
            action_counts[action] += 1
            known_position = update_known_position(user_id, payload, known_position)
            if action == "currentMTTRanking":
                received_ranking = True
                continue
            if action == "ping":
                ws.send(json.dumps({"action": "pong"}))
                continue
            if action != "readyToAct":
                continue
            next_player = payload.get("nextPlayer") or {}
            next_position = next_player.get("position")
            supported_actions = payload.get("supportedActions") or []
            if known_position is None or next_position is None or int(next_position) != known_position:
                continue
            if not isinstance(supported_actions, list) or not supported_actions:
                continue
            plan = choose_action_plan(supported_actions, rng)
            send_action(ws, known_position, plan)
            sent_actions.append(plan)
        return {
            "user_id": user_id,
            "session_id": session_id,
            "position": known_position,
            "actions": actions,
            "action_counts": dict(sorted(action_counts.items())),
            "sent_actions": sent_actions,
            "errors": errors,
            "received_current_mtt_ranking": received_ranking,
        }
    finally:
        ws.close()
def run_user(
    args: argparse.Namespace,
    user_id: str,
    rng_seed: int,
    finish_event: threading.Event | None = None,
) -> dict[str, Any]:
    join_response = join_game(args, user_id)
    session_id = join_response["sessionID"]
    ws_summary = hold_ws_session(args, user_id, session_id, rng_seed, finish_event=finish_event)
    return {
        "user_id": user_id,
        "join_response": join_response,
        "ws": ws_summary,
    }


def main() -> int:
    args = parse_args()
    deadline = time.time() + args.wait_seconds
    wait_for_port(args.host, args.outer_port, deadline)
    wait_for_port(args.host, args.inner_port, deadline)

    start_response = start_mtt(args)
    assignments = collect_room_assignments(args, deadline)
    redis_state = wait_for_redis_snapshot(args, deadline)
    redis_client = redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        db=args.redis_db,
        password=args.redis_password or None,
        decode_responses=True,
    )

    results: list[dict[str, Any]] = []
    finish_event = threading.Event()
    final_standings: dict[str, Any] | None = None
    delayed_failure: Exception | None = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [
            executor.submit(run_user, args, str(idx), args.seed + idx, finish_event)
            for idx in range(args.user_count)
        ]
        try:
            if args.until_finish:
                final_standings = wait_for_tournament_finish(args, redis_client, finish_event)
        except Exception as exc:
            delayed_failure = exc
        finally:
            finish_event.set()
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    if delayed_failure is not None:
        raise delayed_failure

    results.sort(key=lambda item: int(item["user_id"]))
    ranking_ok = sum(1 for item in results if item["ws"]["received_current_mtt_ranking"])
    sent_action_users = sum(1 for item in results if item["ws"]["sent_actions"])
    sent_action_total = sum(len(item["ws"]["sent_actions"]) for item in results)
    failures = [item for item in results if item["ws"]["errors"]]
    standings = final_standings or fetch_complete_standings(redis_client, args.mtt_id, game_type="mtt")
    summary = {
        "mtt_id": args.mtt_id,
        "start_response": start_response,
        "assignments": {
            "unique_rooms": assignments["unique_rooms"],
            "room_sizes": assignments["room_sizes"],
        },
        "redis_state": redis_state,
        "connections": {
            "joined_users": len(results),
            "received_current_mtt_ranking": ranking_ok,
            "users_with_ws_errors": len(failures),
            "users_with_sent_actions": sent_action_users,
            "sent_action_total": sent_action_total,
        },
        "finish_mode": {
            "until_finish": args.until_finish,
            "finish_timeout_seconds": args.finish_timeout_seconds,
            "finished": is_tournament_finished(standings, expected_players=args.user_count),
        },
        "standings": standings,
        "users": results,
    }
    if args.until_finish:
        validate_finish_summary(summary, expected_players=args.user_count)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HarnessFailure as exc:
        print(f"non-mock play harness failed: {exc}")
        raise SystemExit(1)
