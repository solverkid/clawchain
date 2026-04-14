#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local auth/upstream mock for donor non-mock MTT startup and join flow.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18090)
    parser.add_argument("--user-count", type=int, default=30)
    parser.add_argument("--table-max-player", type=int, default=9)
    parser.add_argument("--start-delay-seconds", type=int, default=5)
    parser.add_argument("--late-registration-seconds", type=int, default=1800)
    parser.add_argument("--client-act-timeout", type=int, default=4)
    parser.add_argument("--init-stack", type=int, default=3000)
    return parser.parse_args()


def parse_user_id_from_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    token = authorization.strip()
    if not token:
        return None
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        return None
    if ":" in token:
        return token.rsplit(":", 1)[-1]
    return token


def build_participants(user_count: int, init_stack: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    participants: list[dict[str, Any]] = []
    users_init_config: list[dict[str, Any]] = []
    for idx in range(user_count):
        user_id = str(idx)
        participants.append(
            {
                "userID": user_id,
                "playerName": user_id,
                "entryNumber": 1,
                "ID": "",
            }
        )
        users_init_config.append(
            {
                "initStack": init_stack,
                "users": [
                    {
                        "userID": user_id,
                        "playerName": user_id,
                    }
                ],
            }
        )
    return participants, users_init_config


def build_blind_structure() -> list[dict[str, int]]:
    return [
        {"smallBlind": 15, "bigBlind": 30, "ante": 3, "duration": 60},
        {"smallBlind": 20, "bigBlind": 40, "ante": 4, "duration": 60},
        {"smallBlind": 30, "bigBlind": 60, "ante": 6, "duration": 60},
        {"smallBlind": 40, "bigBlind": 80, "ante": 8, "duration": 60},
        {"smallBlind": 50, "bigBlind": 100, "ante": 10, "duration": 60},
        {"smallBlind": 75, "bigBlind": 150, "ante": 15, "duration": 60},
        {"smallBlind": 100, "bigBlind": 200, "ante": 20, "duration": 60},
        {"smallBlind": 150, "bigBlind": 300, "ante": 30, "duration": 60},
        {"smallBlind": 200, "bigBlind": 400, "ante": 40, "duration": 60},
        {"smallBlind": 300, "bigBlind": 600, "ante": 60, "duration": 60},
    ]


def build_mtt_detail(args: argparse.Namespace, mtt_id: str, game_type: str) -> dict[str, Any]:
    start_time = int(time.time()) + args.start_delay_seconds
    participants, users_init_config = build_participants(args.user_count, args.init_stack)
    participants = [{**item, "ID": mtt_id} for item in participants]
    return {
        "participants": participants,
        "userExtraInfo": {
            "usersInitConfig": users_init_config,
        },
        "mttDetails": {
            "mttID": mtt_id,
            "MttName": f"Local {game_type.upper()} {mtt_id}",
            "description": "local auth-backed poker mtt test",
            "logo": "local",
            "startTime": start_time,
            "prizePoolSize": args.user_count,
            "lateRegistrationTime": args.late_registration_seconds,
            "reEntryLimits": 0,
            "autoReEntry": 0,
            "breakTime": 0,
            "minPlayers": 2,
            "maxPlayers": args.user_count,
            "allowQuit": False,
            "observeMode": True,
            "tableBackgroundUrl": "local",
            "verticalTableBackgroundUrl": "local",
            "type": game_type,
            "subType": "",
            "gameMode": "NLH",
            "voiceChat": False,
            "videoChat": False,
            "enableRabbitHunting": False,
            "vdfShuffle": False,
            "vdfChain": "",
            "autoKnockoutAfterRound": 20,
            "blindStructure": build_blind_structure(),
            "clientActTimeOut": args.client_act_timeout,
            "maxPlayerNumber": args.table_max_player,
            "initBlind": 100,
            "timeBank": {
                "duration": 15,
                "number": 1,
                "addPolicy": 5,
            },
        },
    }


def ok_response(data: Any = None) -> dict[str, Any]:
    response: dict[str, Any] = {
        "code": 0,
        "msg": "ok",
        "success": True,
    }
    if data is not None:
        response["data"] = data
    return response


class LocalAuthHandler(BaseHTTPRequestHandler):
    server: "LocalAuthServer"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        raw_body = self.rfile.read(content_length)
        if not raw_body:
            return {}
        return json.loads(raw_body)

    def _write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/token_verify":
            user_id = parse_user_id_from_token(self.headers.get("Authorization"))
            if not user_id:
                self._write_json(
                    {
                        "code": 401,
                        "msg": "missing token",
                        "success": False,
                        "data": {},
                    }
                )
                return
            self._write_json(
                ok_response(
                    {
                        "userID": user_id,
                        "playerName": user_id,
                    }
                )
            )
            return
        if parsed.path == "/v1/user/seed":
            query = parse_qs(parsed.query)
            user_ids = query.get("userIdList", [])
            self._write_json(ok_response([{"userId": user_id, "seed": f"seed-{user_id}"} for user_id in user_ids]))
            return
        self._write_json(ok_response({}))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self._read_json()
        if parsed.path == "/v1/mtt/player/show_player_details":
            mtt_id = str(payload.get("ID") or "local-mtt")
            game_type = str(payload.get("type") or "mtt").lower()
            self._write_json(ok_response(build_mtt_detail(self.server.args, mtt_id, game_type)))
            return
        self._write_json(ok_response({}))


class LocalAuthServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls: type[LocalAuthHandler], args: argparse.Namespace):
        super().__init__(server_address, handler_cls)
        self.args = args


def main() -> int:
    args = parse_args()
    server = LocalAuthServer((args.host, args.port), LocalAuthHandler, args)
    print(f"local auth mock listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
