#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import json
import socket
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import redis
import requests
import websocket


ROOT = Path(__file__).resolve().parents[2]


class SmokeFailure(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local smoke test against the donor poker-mtt sidecar.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--outer-port", type=int, default=18082)
    parser.add_argument("--inner-port", type=int, default=18083)
    parser.add_argument("--redis-host", default="127.0.0.1")
    parser.add_argument("--redis-port", type=int, default=36379)
    parser.add_argument("--redis-db", type=int, default=15)
    parser.add_argument("--redis-password", default="")
    parser.add_argument("--mtt-id", default=f"local-smoke-{int(time.time())}")
    parser.add_argument("--user-id", default="0")
    parser.add_argument("--expected-users", type=int, default=2)
    parser.add_argument("--expected-room-count-at-least", type=int, default=1)
    parser.add_argument("--wait-seconds", type=float, default=45.0)
    parser.add_argument("--request-timeout", type=float, default=5.0)
    return parser.parse_args()


def wait_for_port(host: str, port: int, deadline: float) -> None:
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.5)
    raise SmokeFailure(f"timeout waiting for {host}:{port}")


def parse_json_response(response: requests.Response) -> dict[str, Any]:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise SmokeFailure(f"expected JSON object, got: {payload!r}")
    return payload


def require_code_zero(payload: dict[str, Any], context: str) -> None:
    if payload.get("code", 0) != 0:
        raise SmokeFailure(f"{context} failed: {json.dumps(payload, ensure_ascii=False)}")


def start_mtt(args: argparse.Namespace) -> dict[str, Any]:
    response = requests.post(
        f"http://{args.host}:{args.inner_port}/v1/mtt/start",
        json={"ID": args.mtt_id, "type": "mtt"},
        timeout=args.request_timeout,
    )
    payload = parse_json_response(response)
    require_code_zero(payload, "start mtt")
    return payload


def wait_for_room_id(args: argparse.Namespace, deadline: float) -> str:
    while time.time() < deadline:
        response = requests.get(
            f"http://{args.host}:{args.inner_port}/v1/mtt/getMTTRoomByID",
            params={"userID": args.user_id, "ID": args.mtt_id},
            timeout=args.request_timeout,
        )
        payload = parse_json_response(response)
        room_id = ((payload.get("data") or {}).get("roomID"))
        if room_id:
            return room_id
        time.sleep(0.5)
    raise SmokeFailure(f"timeout waiting for roomID for mtt {args.mtt_id}")


def collect_room_assignments(args: argparse.Namespace, deadline: float) -> dict[str, Any]:
    room_by_user: dict[str, str] = {}
    while time.time() < deadline:
        for idx in range(args.expected_users):
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
        if len(room_by_user) >= args.expected_users:
            counter = collections.Counter(room_by_user.values())
            if len(counter) >= args.expected_room_count_at_least:
                return {
                    "users_seen": len(room_by_user),
                    "unique_rooms": len(counter),
                    "room_sizes": dict(sorted(counter.items())),
                }
        time.sleep(0.5)
    raise SmokeFailure(
        "timeout waiting for full room assignment "
        f"(users_seen={len(room_by_user)}, expected_users={args.expected_users})"
    )


def join_game(args: argparse.Namespace) -> dict[str, Any]:
    response = requests.post(
        f"http://{args.host}:{args.outer_port}/v1/join_game?id={args.mtt_id}&type=mtt",
        headers={"Mock-Userid": args.user_id},
        json={"time": int(time.time()), "playerName": args.user_id},
        timeout=args.request_timeout,
    )
    payload = parse_json_response(response)
    require_code_zero(payload, "join game")
    if not payload.get("sessionID"):
        raise SmokeFailure(f"join response missing sessionID: {json.dumps(payload, ensure_ascii=False)}")
    return payload


def request_ranking_over_ws(args: argparse.Namespace, session_id: str, deadline: float) -> list[str]:
    ws_url = (
        f"ws://{args.host}:{args.outer_port}/v1/ws?"
        + urlencode({"id": args.mtt_id, "type": "mtt"})
    )
    actions: list[str] = []
    ws = websocket.create_connection(
        ws_url,
        header=[f"Mock-Userid: {args.user_id}"],
        subprotocols=["-1", session_id],
        timeout=args.request_timeout,
    )
    try:
        ws.send(json.dumps({"action": "mttRanking"}))
        while time.time() < deadline:
            raw_message = ws.recv()
            payload = json.loads(raw_message)
            action = payload.get("action", "")
            actions.append(action)
            if action == "ping":
                ws.send(json.dumps({"action": "pong"}))
                continue
            if action == "currentMTTRanking":
                return actions
        raise SmokeFailure(f"timeout waiting for currentMTTRanking, saw actions={actions}")
    finally:
        ws.close()


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
        if snapshot_count >= args.expected_users and alive_count >= 1:
            return {
                "snapshot_key": snapshot_key,
                "alive_key": alive_key,
                "died_key": died_key,
                "snapshot_count": snapshot_count,
                "alive_count": alive_count,
                "died_count": len(died_items),
            }
        time.sleep(0.5)
    raise SmokeFailure(
        "timeout waiting for redis ranking snapshot "
        f"(snapshot={snapshot_count}, alive={alive_count})"
    )


def main() -> int:
    args = parse_args()
    deadline = time.time() + args.wait_seconds

    wait_for_port(args.host, args.outer_port, deadline)
    wait_for_port(args.host, args.inner_port, deadline)

    start_response = start_mtt(args)
    room_id = wait_for_room_id(args, deadline)
    assignments = collect_room_assignments(args, deadline)
    join_response = join_game(args)
    ws_actions = request_ranking_over_ws(args, join_response["sessionID"], deadline)
    redis_state = wait_for_redis_snapshot(args, deadline)

    summary = {
        "mtt_id": args.mtt_id,
        "room_id": room_id,
        "session_id": join_response["sessionID"],
        "start_response": start_response,
        "join_response": join_response,
        "assignments": assignments,
        "ws_actions": ws_actions,
        "redis_state": redis_state,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        print(f"smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
