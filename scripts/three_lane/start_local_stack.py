#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from common import DEFAULT_BUILD_DIR, DEFAULT_MANIFEST_PATH, isoformat_z, load_or_create_manifest, utc_now, wait_for_http, write_status


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the local three-lane stack (forecast service + arena runtime).")
    parser.add_argument("--database-url", default="postgresql://clawchain:clawchain_dev_pw@127.0.0.1:55432/clawchain")
    parser.add_argument("--forecast-base-url", default="http://127.0.0.1:1317")
    parser.add_argument("--arena-base-url", default="http://127.0.0.1:18117")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--miner-count", type=int, default=33)
    parser.add_argument("--namespace", default="three-lane-local-v1")
    parser.add_argument("--arena-ready-timeout-seconds", type=float, default=180.0)
    return parser.parse_args()


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _parse_host_port(base_url: str) -> tuple[str, int]:
    host_port = base_url.removeprefix("http://").removeprefix("https://")
    host, port_text = host_port.split(":", 1)
    return host, int(port_text)


def _start_process(*, cmd: list[str], workdir: Path, env: dict[str, str], log_path: Path, pid_path: Path) -> int:
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = 0
        if pid and _pid_is_running(pid):
            return pid
        pid_path.unlink(missing_ok=True)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as handle:
        process = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_path.write_text(f"{process.pid}\n", encoding="utf-8")
    return process.pid


def _stop_process(pid_path: Path) -> None:
    if not pid_path.exists():
        return
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError:
        pid_path.unlink(missing_ok=True)
        return
    if _pid_is_running(pid):
        os.killpg(pid, signal.SIGTERM)
        time.sleep(1)
    pid_path.unlink(missing_ok=True)


def _wait_for_arena_ready(base_url: str, *, timeout_seconds: float) -> None:
    wait_for_http(f"{base_url}/healthz", timeout_seconds=timeout_seconds)
    wait_for_http(f"{base_url}/v1/arena/waves/active", timeout_seconds=timeout_seconds)


def main() -> int:
    args = parse_args()
    build_dir = DEFAULT_BUILD_DIR
    build_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_or_create_manifest(args.manifest, count=args.miner_count, namespace=args.namespace)

    forecast_host, forecast_port = _parse_host_port(args.forecast_base_url)
    arena_host, arena_port = _parse_host_port(args.arena_base_url)

    forecast_pid_path = build_dir / "forecast-service.pid"
    forecast_log_path = build_dir / "forecast-service.log"
    arena_pid_path = build_dir / "arena-runtime.pid"
    arena_log_path = build_dir / "arena-runtime.log"

    if _port_is_open(forecast_host, forecast_port):
        _stop_process(forecast_pid_path)
        time.sleep(1)
    if _port_is_open(forecast_host, forecast_port):
        raise RuntimeError(f"forecast service port still busy after stop: {forecast_host}:{forecast_port}")

    forecast_env = os.environ.copy()
    forecast_env.update(
        {
            "CLAWCHAIN_ENV": "local",
            "CLAWCHAIN_DATABASE_URL": args.database_url,
            "CLAWCHAIN_BIND_HOST": forecast_host,
            "CLAWCHAIN_LIVE_MARKET_DATA_ENABLED": "1",
            "CLAWCHAIN_MARKET_DATA_TIMEOUT_SECONDS": "3.0",
            "CLAWCHAIN_FAST_TASK_LIVE_BUILD_TIMEOUT_SECONDS": "1.0",
            "CLAWCHAIN_FAST_TASK_SECONDS": "300",
            "CLAWCHAIN_FAST_TASK_PREWARM_SECONDS": "90",
            "CLAWCHAIN_COMMIT_WINDOW_SECONDS": "3",
            "CLAWCHAIN_REVEAL_WINDOW_SECONDS": "13",
            "CLAWCHAIN_FORECAST_PROGRESSION_LOOP_ENABLED": "1",
            "CLAWCHAIN_FORECAST_PROGRESSION_LOOP_INTERVAL_SECONDS": "5.0",
            "CLAWCHAIN_POKER_MTT_REWARD_WINDOWS_ENABLED": "1",
            "CLAWCHAIN_POKER_MTT_DAILY_REWARD_POOL_AMOUNT": "3300",
            "CLAWCHAIN_POKER_MTT_WEEKLY_REWARD_POOL_AMOUNT": "23100",
            "CLAWCHAIN_POKER_MTT_SETTLEMENT_ANCHORING_ENABLED": "0",
            "CLAWCHAIN_ADMIN_AUTH_ENABLED": "0",
        }
    )
    _start_process(
        cmd=[sys.executable, "server.py", "--host", forecast_host, "--port", str(forecast_port)],
        workdir=MINING_SERVICE_DIR,
        env=forecast_env,
        log_path=forecast_log_path,
        pid_path=forecast_pid_path,
    )
    wait_for_http(f"{args.forecast_base_url}/clawchain/stats", timeout_seconds=60)

    if _port_is_open(arena_host, arena_port):
        _stop_process(arena_pid_path)
        time.sleep(1)
    if _port_is_open(arena_host, arena_port):
        raise RuntimeError(f"arena runtime port still busy after stop: {arena_host}:{arena_port}")

    arena_env = os.environ.copy()
    arena_env.update(
        {
            "ARENA_DATABASE_URL": args.database_url + "?sslmode=disable" if "?" not in args.database_url else args.database_url,
            "ARENA_HTTP_ADDR": f"{arena_host}:{arena_port}",
        }
    )
    _start_process(
        cmd=["go", "run", "./cmd/arenad"],
        workdir=ROOT,
        env=arena_env,
        log_path=arena_log_path,
        pid_path=arena_pid_path,
    )
    _wait_for_arena_ready(args.arena_base_url, timeout_seconds=args.arena_ready_timeout_seconds)

    status = {
        "updated_at": isoformat_z(utc_now()),
        "manifest_path": str(args.manifest),
        "manifest_root": manifest["manifest_root"],
        "miner_count": manifest["count"],
        "forecast": {
            "base_url": args.forecast_base_url,
            "pid_file": str(forecast_pid_path),
            "log_file": str(forecast_log_path),
            "progression_loop_interval_seconds": 5.0,
            "fast_task_prewarm_seconds": 90,
            "fast_task_live_build_timeout_seconds": 1.0,
            "market_data_timeout_seconds": 3.0,
        },
        "arena": {
            "base_url": args.arena_base_url,
            "pid_file": str(arena_pid_path),
            "log_file": str(arena_log_path),
        },
    }
    write_status(build_dir / "stack.json", status)
    print(f"forecast_base_url={args.forecast_base_url}")
    print(f"arena_base_url={args.arena_base_url}")
    print(f"manifest={args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
