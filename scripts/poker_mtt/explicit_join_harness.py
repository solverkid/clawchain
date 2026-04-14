#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import json
import socket
import threading
import time
from typing import Any
from urllib.parse import urlencode

import redis
import requests
import websocket


class HarnessFailure(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Explicitly join N mock MTT users and hold N WebSocket sessions open.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--outer-port", type=int, default=18082)
    parser.add_argument("--inner-port", type=int, default=18083)
    parser.add_argument("--redis-host", default="127.0.0.1")
    parser.add_argument("--redis-port", type=int, default=36379)
    parser.add_argument("--redis-db", type=int, default=15)
    parser.add_argument("--redis-password", default="")
    parser.add_argument("--mtt-id", default=f"explicit-join-{int(time.time())}")
    parser.add_argument("--user-count", type=int, default=30)
    parser.add_argument("--table-room-count-at-least", type=int, default=4)
    parser.add_argument("--hold-seconds", type=float, default=20.0)
    parser.add_argument("--wait-seconds", type=float, default=120.0)
    parser.add_argument("--request-timeout", type=float, default=5.0)
    parser.add_argument("--max-workers", type=int, default=10)
    return parser.parse_args()


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
    response = requests.post(
        f"http://{args.host}:{args.outer_port}/v1/join_game?id={args.mtt_id}&type=mtt",
        headers={"Mock-Userid": user_id},
        json={"time": int(time.time()), "playerName": user_id},
        timeout=args.request_timeout,
    )
    payload = parse_json_response(response)
    require_code_zero(payload, f"join game user={user_id}")
    session_id = payload.get("sessionID")
    if not session_id:
        raise HarnessFailure(f"join response missing sessionID for user={user_id}")
    return payload


def hold_ws_session(
    args: argparse.Namespace,
    user_id: str,
    session_id: str,
    hold_deadline: float,
) -> dict[str, Any]:
    ws_url = (
        f"ws://{args.host}:{args.outer_port}/v1/ws?"
        + urlencode({"id": args.mtt_id, "type": "mtt"})
    )
    ws = websocket.create_connection(
        ws_url,
        header=[f"Mock-Userid: {user_id}"],
        subprotocols=["-1", session_id],
        timeout=args.request_timeout,
    )
    actions: list[str] = []
    action_counts: collections.Counter[str] = collections.Counter()
    errors: list[str] = []
    lock = threading.Lock()

    def record_action(action: str) -> None:
        with lock:
            actions.append(action)
            action_counts[action] += 1

    try:
        ws.send(json.dumps({"action": "mttRanking"}))
        while time.time() < hold_deadline:
            try:
                raw_message = ws.recv()
            except websocket.WebSocketTimeoutException:
                try:
                    ws.send(json.dumps({"action": "ping"}))
                except Exception as exc:  # pragma: no cover - runtime guard
                    errors.append(f"ping failed: {exc}")
                    break
                continue
            payload = json.loads(raw_message)
            action = payload.get("action", "")
            record_action(action)
            if action == "ping":
                ws.send(json.dumps({"action": "pong"}))
        return {
            "user_id": user_id,
            "session_id": session_id,
            "actions": actions,
            "action_counts": dict(sorted(action_counts.items())),
            "errors": errors,
            "received_current_mtt_ranking": action_counts["currentMTTRanking"] > 0,
        }
    finally:
        ws.close()


def explicit_join_user(
    args: argparse.Namespace,
    user_id: str,
    hold_deadline: float,
) -> dict[str, Any]:
    join_response = join_game(args, user_id)
    session_id = join_response["sessionID"]
    ws_summary = hold_ws_session(args, user_id, session_id, hold_deadline)
    return {
        "user_id": user_id,
        "join_response": join_response,
        "ws": ws_summary,
    }


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


def main() -> int:
    args = parse_args()
    deadline = time.time() + args.wait_seconds
    hold_deadline = time.time() + args.hold_seconds

    wait_for_port(args.host, args.outer_port, deadline)
    wait_for_port(args.host, args.inner_port, deadline)

    start_response = start_mtt(args)
    assignments = collect_room_assignments(args, deadline)
    redis_state = wait_for_redis_snapshot(args, deadline)

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [
            executor.submit(explicit_join_user, args, str(idx), hold_deadline)
            for idx in range(args.user_count)
        ]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: int(item["user_id"]))
    ranking_ok = sum(1 for item in results if item["ws"]["received_current_mtt_ranking"])
    failures = [item for item in results if item["ws"]["errors"]]
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
        },
        "users": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HarnessFailure as exc:
        print(f"explicit join harness failed: {exc}")
        raise SystemExit(1)
