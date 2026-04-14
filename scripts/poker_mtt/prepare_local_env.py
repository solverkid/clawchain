#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "lepoker-gameserver" / "config-dev.yaml"
DEFAULT_BACKUP = ROOT / "build" / "poker-mtt" / "config-dev.yaml.orig"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch donor config-dev.yaml for local poker-mtt sidecar startup.",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--mode", choices=("mock", "auth"), default="mock")
    parser.add_argument("--outer-port", type=int, default=18082)
    parser.add_argument("--inner-port", type=int, default=18083)
    parser.add_argument("--redis-host", default="127.0.0.1:36379")
    parser.add_argument("--redis-db", type=int, default=15)
    parser.add_argument("--mq-endpoint", default="127.0.0.1:38081")
    parser.add_argument("--consume-group", default="GAME_SERVER_LOCAL")
    parser.add_argument("--auth-host", default="http://127.0.0.1:18090")
    parser.add_argument("--mtt-user-count", type=int, default=2)
    parser.add_argument("--table-max-player", type=int, default=2)
    return parser.parse_args()


def read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping at top level: {path}")
    return data


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def ensure_backup(config_path: Path, backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if not backup_path.exists():
        shutil.copy2(config_path, backup_path)


def patch_local_config(data: dict, args: argparse.Namespace) -> dict:
    server = data.setdefault("server", {})
    redis_cfg = data.setdefault("redis", {})
    mq_cfg = data.setdefault("rocket_mq", {})
    auth_cfg = data.setdefault("auth_service", {})

    data["chat_group_available"] = False
    data["mock_mtt_user_number"] = args.mtt_user_count
    data["mock_mtt_table_max_player"] = args.table_max_player

    if args.mode == "mock":
        data["mock"] = True
        data["mock_autoCall"] = True
        data["mock_mtt_valid"] = True
        data["need_login"] = False
    else:
        data["mock"] = False
        data["mock_autoCall"] = False
        data["mock_mtt_valid"] = False
        data["need_login"] = True
        auth_cfg["host"] = args.auth_host

    server["port"] = args.outer_port
    server["inner_port"] = args.inner_port

    redis_cfg["host"] = args.redis_host
    redis_cfg["database"] = args.redis_db
    redis_cfg["password"] = ""

    mq_cfg["endpoint"] = args.mq_endpoint
    mq_cfg["consume_group"] = args.consume_group
    return data


def restore_config(config_path: Path, backup_path: Path) -> int:
    if not backup_path.exists():
        print(f"backup file not found: {backup_path}", file=sys.stderr)
        return 1
    shutil.copy2(backup_path, config_path)
    print(f"restored {config_path} from {backup_path}")
    return 0


def main() -> int:
    args = parse_args()
    config_path = args.config.resolve()
    backup_path = args.backup.resolve()

    if args.restore:
        return restore_config(config_path, backup_path)

    ensure_backup(config_path, backup_path)
    data = read_yaml(config_path)
    patched = patch_local_config(data, args)
    write_yaml(config_path, patched)
    print(f"patched {config_path}")
    print(f"backup: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
