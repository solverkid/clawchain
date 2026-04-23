from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

import asyncpg
import pytest

ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine
from pg_repository import PostgresRepository


def _shared_db_url() -> str:
    return os.environ.get(
        "CLAWCHAIN_SHARED_TEST_DATABASE_URL",
        "postgresql://clawchain:clawchain_dev_pw@127.0.0.1:55432/clawchain_integration_test?sslmode=disable",
    )


def _python_db_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    return parsed._replace(query="").geturl()


async def _ensure_database_exists(database_url: str) -> None:
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/")
    assert db_name
    safe_name = db_name.replace("_", "")
    assert safe_name.isalnum()
    admin_url = parsed._replace(path="/postgres").geturl()
    conn = await asyncpg.connect(admin_url)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


def test_arena_runtime_writeback_is_visible_to_mining_service_status():
    database_url = _shared_db_url()
    asyncio.run(_ensure_database_exists(database_url))

    env = os.environ.copy()
    env["ARENA_TEST_DATABASE_URL"] = database_url
    result = subprocess.run(
        ["go", "test", "-p", "1", "./arena/integration/...", "-run", "TestWarmMultiplierSharedMinerWriteback", "-count=1"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"go test failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

    async def scenario():
        repo = PostgresRepository(_python_db_url(database_url))
        try:
            await repo.init_schema()
            miners = await repo.list_miners()
            bridged = [
                miner
                for miner in miners
                if abs(float(miner.get("arena_multiplier", 1.0) or 1.0) - 1.0) > 1e-9
            ]
            assert bridged, "expected at least one shared miner row with a non-default arena_multiplier"

            target = bridged[0]
            service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
            status = await service.get_miner_status(target["address"])

            assert status["miner_id"] == target["address"]
            assert status["arena_multiplier"] == pytest.approx(round(float(target["arena_multiplier"]), 4))
            assert status["public_rank"] == target.get("public_rank")
            assert status["public_elo"] == target.get("public_elo")
            assert status["total_rewards"] == 0
            assert status["forecast_commits"] == 0
            assert status["forecast_reveals"] == 0
            assert status["risk_review_state"] == "clear"
            assert status["open_risk_case_count"] == 0
        finally:
            await repo.engine.dispose()

    asyncio.run(scenario())
