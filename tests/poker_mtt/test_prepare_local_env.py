from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "poker_mtt" / "prepare_local_env.py"


def write_sample_config(path: Path) -> dict:
    data = {
        "mock": False,
        "mock_autoCall": False,
        "mock_mtt_valid": False,
        "chat_group_available": True,
        "need_login": True,
        "server": {
            "port": 8082,
            "inner_port": 8083,
        },
        "redis": {
            "host": "10.0.0.1:6379",
            "database": 2,
            "password": "secret",
        },
        "rocket_mq": {
            "endpoint": "10.0.0.2:8081",
            "consume_group": "GAME_SERVER",
        },
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return data


def run_prepare(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_prepare_local_env_patches_expected_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config-dev.yaml"
    backup_path = tmp_path / "config-dev.yaml.orig"
    write_sample_config(config_path)

    result = run_prepare(
        "--config",
        str(config_path),
        "--backup",
        str(backup_path),
        "--outer-port",
        "18082",
        "--inner-port",
        "18083",
        "--redis-host",
        "127.0.0.1:36379",
        "--redis-db",
        "15",
        "--mq-endpoint",
        "127.0.0.1:38081",
        "--consume-group",
        "GAME_SERVER_LOCAL",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert backup_path.exists()

    patched = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert patched["mock"] is True
    assert patched["mock_autoCall"] is True
    assert patched["mock_mtt_valid"] is True
    assert patched["chat_group_available"] is False
    assert patched["need_login"] is False
    assert patched["server"]["port"] == 18082
    assert patched["server"]["inner_port"] == 18083
    assert patched["redis"]["host"] == "127.0.0.1:36379"
    assert patched["redis"]["database"] == 15
    assert patched["redis"]["password"] == ""
    assert patched["rocket_mq"]["endpoint"] == "127.0.0.1:38081"
    assert patched["rocket_mq"]["consume_group"] == "GAME_SERVER_LOCAL"


def test_prepare_local_env_restore_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / "config-dev.yaml"
    backup_path = tmp_path / "config-dev.yaml.orig"
    original = write_sample_config(config_path)

    apply_result = run_prepare(
        "--config",
        str(config_path),
        "--backup",
        str(backup_path),
    )
    assert apply_result.returncode == 0, apply_result.stderr or apply_result.stdout

    restore_result = run_prepare(
        "--config",
        str(config_path),
        "--backup",
        str(backup_path),
        "--restore",
    )
    assert restore_result.returncode == 0, restore_result.stderr or restore_result.stdout

    restored = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert restored == original


def test_prepare_local_env_patches_mock_mtt_sizes(tmp_path: Path) -> None:
    config_path = tmp_path / "config-dev.yaml"
    backup_path = tmp_path / "config-dev.yaml.orig"
    write_sample_config(config_path)

    result = run_prepare(
        "--config",
        str(config_path),
        "--backup",
        str(backup_path),
        "--mtt-user-count",
        "30",
        "--table-max-player",
        "9",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    patched = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert patched["mock_mtt_user_number"] == 30
    assert patched["mock_mtt_table_max_player"] == 9


def test_prepare_local_env_patches_auth_mode_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config-dev.yaml"
    backup_path = tmp_path / "config-dev.yaml.orig"
    write_sample_config(config_path)

    result = run_prepare(
        "--config",
        str(config_path),
        "--backup",
        str(backup_path),
        "--mode",
        "auth",
        "--auth-host",
        "http://127.0.0.1:18090",
        "--mtt-user-count",
        "30",
        "--table-max-player",
        "9",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    patched = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert patched["mock"] is False
    assert patched["mock_autoCall"] is False
    assert patched["mock_mtt_valid"] is False
    assert patched["need_login"] is True
    assert patched["chat_group_available"] is False
    assert patched["mock_mtt_user_number"] == 30
    assert patched["mock_mtt_table_max_player"] == 9
    assert patched["auth_service"]["host"] == "http://127.0.0.1:18090"
