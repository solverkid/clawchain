from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine
import schemas
import server


FIXTURE = ROOT / "tests" / "fixtures" / "poker_mtt" / "final_ranking_projection_from_go.json"


class FrozenClock:
    def __init__(self, now: datetime):
        self.current = now

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def test_go_final_ranking_projection_fixture_matches_fastapi_schema_contract():
    payload = json.loads(FIXTURE.read_text())

    request = schemas.ApplyPokerMTTFinalRankingProjectionRequest(**payload)

    assert request.schema_version == "poker_mtt.final_ranking_apply.v1"
    assert request.projection_id == "poker_mtt_projection:mtt-phase3-contract:poker_mtt_policy_v1:sha256:final-root"
    assert request.source_mtt_id == "donor-mtt-phase3-contract"
    assert request.standing_snapshot_id == "poker_mtt_standing_snapshot:mtt-phase3-contract:abc"
    assert request.standing_snapshot_hash == "sha256:snapshot"
    assert request.final_ranking_root == "sha256:final-root"
    assert request.locked_at.isoformat() == "2026-04-10T12:00:00+00:00"
    assert [row.member_id for row in request.rows] == ["8:1", "19:1", "27:1"]
    assert request.rows[0].status == "alive"
    assert request.rows[0].created_at.isoformat() == "2026-04-10T12:00:00+00:00"
    assert request.rows[2].rank_state == "waiting_no_show"


def test_final_ranking_projection_endpoint_is_idempotent_and_uses_payload_locked_at():
    payload = json.loads(FIXTURE.read_text())
    repo = server.create_fake_repository()
    _seed_fixture_miners(repo, payload)
    clock = FrozenClock(datetime(2026, 4, 11, 9, 0, 0, tzinfo=timezone.utc))
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(),
        repository=repo,
        now_fn=clock.now,
    )

    with TestClient(app) as client:
        first = client.post("/admin/poker-mtt/final-rankings/project", json=payload)
        clock.advance(3600)
        second = client.post("/admin/poker-mtt/final-rankings/project", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["projection_id"] == payload["projection_id"]
    assert first.json()["final_ranking_root"] == payload["final_ranking_root"]
    assert first.json()["standing_snapshot_id"] == payload["standing_snapshot_id"]
    assert first.json()["standing_snapshot_hash"] == payload["standing_snapshot_hash"]
    assert first.json()["locked_at"] == payload["locked_at"]
    tournament = asyncio.run(repo.get_poker_mtt_tournament(payload["tournament_id"]))
    assert tournament["completed_at"] == payload["locked_at"]


def test_final_ranking_projection_endpoint_rejects_same_projection_id_with_different_root():
    payload = json.loads(FIXTURE.read_text())
    repo = server.create_fake_repository()
    _seed_fixture_miners(repo, payload)
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(),
        repository=repo,
        now_fn=lambda: datetime(2026, 4, 11, 9, 0, 0, tzinfo=timezone.utc),
    )
    conflicting_payload = {**payload, "final_ranking_root": "sha256:tampered-final-root"}

    with TestClient(app) as client:
        first = client.post("/admin/poker-mtt/final-rankings/project", json=payload)
        conflict = client.post("/admin/poker-mtt/final-rankings/project", json=conflicting_payload)

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert "projection root conflict" in conflict.json()["detail"]


def _seed_fixture_miners(repo, payload: dict) -> None:  # noqa: ANN001
    async def seed() -> None:
        for row in payload["rows"]:
            miner_address = row["miner_address"]
            await repo.register_miner(
                {
                    "address": miner_address,
                    "name": row.get("player_name") or miner_address,
                    "public_key": f"test-public-key:{miner_address}",
                    "miner_version": "test",
                    "status": "active",
                    "economic_unit_id": row.get("economic_unit_id") or miner_address,
                    "poker_mtt_user_id": miner_address,
                    "poker_mtt_auth_source": "fixture",
                    "poker_mtt_reward_bound": True,
                    "poker_mtt_reward_bound_at": payload["locked_at"],
                    "poker_mtt_is_synthetic": False,
                    "poker_mtt_identity_expires_at": None,
                    "poker_mtt_identity_revoked_at": None,
                    "public_elo": 1500.0,
                    "poker_mtt_multiplier": 1.0,
                    "created_at": payload["locked_at"],
                    "updated_at": payload["locked_at"],
                }
            )

    asyncio.run(seed())
