from __future__ import annotations

import asyncio
import json
import sys
import tracemalloc
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine
import server
from repository import FakeRepository


WINDOW_START = datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END = WINDOW_START + timedelta(days=1)
BUILD_NOW = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
POLICY_VERSION = "poker_mtt_daily_policy_v2"


class CountingPokerMTTRepository(FakeRepository):
    def __init__(self):
        super().__init__()
        self.calls: Counter[str] = Counter()
        self.artifact_write_count = 0

    def _count(self, name: str) -> None:
        self.calls[name] += 1

    async def get_miner(self, address: str) -> dict | None:
        self._count("get_miner")
        return await super().get_miner(address)

    async def list_poker_mtt_results(self) -> list[dict]:
        self._count("list_poker_mtt_results")
        return await super().list_poker_mtt_results()

    async def list_poker_mtt_results_for_reward_window(self, **kwargs) -> list[dict]:
        self._count("list_poker_mtt_results_for_reward_window")
        return await super().list_poker_mtt_results_for_reward_window(**kwargs)

    async def load_poker_mtt_reward_window_inputs(self, **kwargs) -> dict:
        self._count("load_poker_mtt_reward_window_inputs")
        return await super().load_poker_mtt_reward_window_inputs(**kwargs)

    async def list_poker_mtt_closed_reward_window_candidates(self, **kwargs) -> list[dict]:
        self._count("list_poker_mtt_closed_reward_window_candidates")
        return await super().list_poker_mtt_closed_reward_window_candidates(**kwargs)

    async def get_poker_mtt_final_ranking(self, final_ranking_id: str) -> dict | None:
        self._count("get_poker_mtt_final_ranking")
        return await super().get_poker_mtt_final_ranking(final_ranking_id)

    async def list_poker_mtt_final_rankings_by_ids(self, final_ranking_ids: list[str]) -> list[dict]:
        self._count("list_poker_mtt_final_rankings_by_ids")
        return await super().list_poker_mtt_final_rankings_by_ids(final_ranking_ids)

    async def list_miners_by_addresses(self, addresses: list[str]) -> list[dict]:
        self._count("list_miners_by_addresses")
        return await super().list_miners_by_addresses(addresses)

    async def list_poker_mtt_rating_snapshots(self, **kwargs) -> list[dict]:
        self._count("list_poker_mtt_rating_snapshots")
        return await super().list_poker_mtt_rating_snapshots(**kwargs)

    async def list_latest_poker_mtt_rating_snapshots_for_miners(self, miner_addresses: list[str]) -> list[dict]:
        self._count("list_latest_poker_mtt_rating_snapshots_for_miners")
        return await super().list_latest_poker_mtt_rating_snapshots_for_miners(miner_addresses)

    async def get_reward_window(self, reward_window_id: str) -> dict | None:
        self._count("get_reward_window")
        return await super().get_reward_window(reward_window_id)

    async def save_reward_window(self, reward_window: dict) -> dict:
        self._count("save_reward_window")
        return await super().save_reward_window(reward_window)

    async def save_artifact(self, artifact: dict) -> dict:
        self._count("save_artifact")
        self.artifact_write_count += 1
        return await super().save_artifact(artifact)

    async def save_artifacts_bulk(self, artifacts: list[dict]) -> list[dict]:
        self._count("save_artifacts_bulk")
        before = self.artifact_write_count
        rows = await super().save_artifacts_bulk(artifacts)
        self.artifact_write_count = before + sum(1 for row in rows if row.get("_write_state") != "unchanged")
        return rows


def test_phase3_reward_window_build_uses_bulk_db_path_for_300_rows():
    async def scenario():
        repo = CountingPokerMTTRepository()
        _seed_reward_ready_rows(repo, 300)
        service = _service(repo)

        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=WINDOW_START,
            window_end_at=WINDOW_END,
            reward_pool_amount=300,
            include_provisional=False,
            policy_bundle_version=POLICY_VERSION,
            now=BUILD_NOW,
        )

        assert reward_window["miner_count"] == 300
        assert reward_window["submission_count"] == 300
        assert repo.calls["get_poker_mtt_final_ranking"] == 0
        assert repo.calls["get_miner"] == 0
        assert repo.calls["list_poker_mtt_rating_snapshots"] == 0
        assert repo.calls["load_poker_mtt_reward_window_inputs"] == 1
        assert _db_call_count(repo) < 30

    asyncio.run(scenario())


def test_phase3_admin_endpoint_builds_300_row_window_on_bulk_path():
    repo = CountingPokerMTTRepository()
    _seed_reward_ready_rows(repo, 300)
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(
            poker_mtt_projection_artifact_page_size=5000,
            poker_mtt_settlement_anchoring_enabled=False,
        ),
        repository=repo,
        now_fn=lambda: BUILD_NOW,
    )

    with TestClient(app) as client:
        response = client.post(
            "/admin/poker-mtt/reward-windows/build",
            json={
                "lane": "poker_mtt_daily",
                "window_start_at": "2026-04-10T00:00:00Z",
                "window_end_at": "2026-04-11T00:00:00Z",
                "reward_pool_amount": 300,
                "include_provisional": False,
                "policy_bundle_version": POLICY_VERSION,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["miner_count"] == 300
    assert payload["submission_count"] == 300
    assert repo.calls["load_poker_mtt_reward_window_inputs"] == 1
    assert repo.calls["get_poker_mtt_final_ranking"] == 0
    assert repo.calls["get_miner"] == 0


def test_phase3_reward_window_build_pages_20k_rows_and_keeps_response_small():
    async def scenario():
        repo = CountingPokerMTTRepository()
        _seed_reward_ready_rows(repo, 20_000)
        service = _service(repo)

        tracemalloc.start()
        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=WINDOW_START,
            window_end_at=WINDOW_END,
            reward_pool_amount=20_000,
            include_provisional=False,
            policy_bundle_version=POLICY_VERSION,
            now=BUILD_NOW,
        )
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        encoded = json.dumps(reward_window, sort_keys=True, default=str).encode("utf-8")
        assert len(encoded) < 256 * 1024
        assert peak_bytes < 512 * 1024 * 1024
        assert reward_window["miner_count"] == 20_000
        assert reward_window["artifact_page_count"] == 4
        assert reward_window["miner_reward_rows_root"].startswith("sha256:")
        assert "miner_addresses" not in reward_window
        assert _db_call_count(repo) < 30

        artifacts = await repo.list_artifacts_for_entity("reward_window", reward_window["id"])
        projection = next(item for item in artifacts if item["kind"] == "poker_mtt_reward_window_projection")
        pages = [item for item in artifacts if item["kind"] == "poker_mtt_reward_window_projection_page"]
        assert len(pages) == 4

        rows = forecast_engine.resolve_poker_mtt_projection_reward_rows(projection["payload_json"], pages)
        assert len(rows) == 20_000
        assert forecast_engine._hash_sequence(rows) == reward_window["miner_reward_rows_root"]

    asyncio.run(scenario())


def test_phase3_reward_window_rebuild_is_idempotent_without_artifact_rewrites():
    async def scenario():
        repo = CountingPokerMTTRepository()
        _seed_reward_ready_rows(repo, 300)
        service = _service(repo)

        first = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=WINDOW_START,
            window_end_at=WINDOW_END,
            reward_pool_amount=300,
            include_provisional=False,
            policy_bundle_version=POLICY_VERSION,
            now=BUILD_NOW,
        )
        first_write_count = repo.artifact_write_count
        repo.calls.clear()

        second = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=WINDOW_START,
            window_end_at=WINDOW_END,
            reward_pool_amount=300,
            include_provisional=False,
            policy_bundle_version=POLICY_VERSION,
            now=BUILD_NOW + timedelta(minutes=1),
        )

        assert second["canonical_root"] == first["canonical_root"]
        assert repo.artifact_write_count == first_write_count
        assert repo.calls["save_reward_window"] == 0
        assert repo.calls["load_poker_mtt_reward_window_inputs"] == 1
        assert _db_call_count(repo) < 5

    asyncio.run(scenario())


def test_phase3_auto_reconcile_uses_bounded_closed_window_query():
    async def scenario():
        repo = CountingPokerMTTRepository()
        _seed_reward_ready_rows(repo, 12)
        service = _service(
            repo,
            poker_mtt_reward_windows_enabled=True,
            poker_mtt_daily_reward_pool_amount=12,
            poker_mtt_weekly_reward_pool_amount=0,
        )

        await service.reconcile(now=WINDOW_END + timedelta(hours=1))

        assert repo.calls["list_poker_mtt_results"] == 0
        assert repo.calls["list_poker_mtt_closed_reward_window_candidates"] == 1
        assert repo.calls["load_poker_mtt_reward_window_inputs"] == 1

    asyncio.run(scenario())


def test_phase3_models_expose_reward_window_scale_indexes():
    import models

    assert _index_names(models.poker_mtt_result_entries) >= {
        "ix_poker_mtt_results_locked_reward_window",
        "ix_poker_mtt_results_reward_window_ready",
    }
    assert _index_names(models.artifacts) >= {"ix_artifacts_entity_kind_id"}
    assert _index_names(models.poker_mtt_rating_snapshots) >= {"ix_poker_mtt_rating_miner_window"}
    assert _index_names(models.poker_mtt_final_rankings) >= {"ix_poker_mtt_final_rankings_window_join"}


def _service(repo: FakeRepository, **settings_overrides) -> forecast_engine.ForecastMiningService:
    return forecast_engine.ForecastMiningService(
        repo,
        forecast_engine.ForecastSettings(
            poker_mtt_projection_artifact_page_size=5000,
            poker_mtt_settlement_anchoring_enabled=False,
            **settings_overrides,
        ),
    )


def _db_call_count(repo: CountingPokerMTTRepository) -> int:
    counted_prefixes = (
        "get_",
        "list_",
        "save_",
    )
    return sum(count for name, count in repo.calls.items() if name.startswith(counted_prefixes))


def _seed_reward_ready_rows(repo: CountingPokerMTTRepository, count: int) -> None:
    locked_at = "2026-04-10T10:00:00Z"
    for index in range(count):
        miner_address = f"claw1phase3load{index:05d}"
        tournament_id = "mtt-phase3-load"
        final_ranking_id = f"poker_mtt_final_ranking:{tournament_id}:{miner_address}"
        repo._miners[miner_address] = {
            "address": miner_address,
            "name": miner_address,
            "registration_index": index + 1,
            "public_key": "pubkey",
            "miner_version": "0.4.0",
            "status": "active",
            "economic_unit_id": miner_address,
            "total_rewards": 0,
            "held_rewards": 0,
            "forecast_commits": 0,
            "forecast_reveals": 0,
            "fast_task_opportunities": 0,
            "fast_task_misses": 0,
            "fast_window_start_at": "2026-04-01T00:00:00Z",
            "settled_tasks": 0,
            "correct_direction_count": 0,
            "edge_score_total": 0.0,
            "admission_state": "probation",
            "model_reliability": 1.0,
            "ops_reliability": 1.0,
            "arena_multiplier": 1.0,
            "poker_mtt_multiplier": 1.0,
            "poker_mtt_user_id": f"user-{index:05d}",
            "poker_mtt_auth_source": "donor_token",
            "poker_mtt_reward_bound": True,
            "poker_mtt_reward_bound_at": "2026-04-01T00:00:00Z",
            "poker_mtt_is_synthetic": False,
            "poker_mtt_identity_expires_at": None,
            "poker_mtt_identity_revoked_at": None,
            "public_rank": None,
            "public_elo": 1200,
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
        }
        repo._poker_mtt_final_rankings[final_ranking_id] = _final_ranking_row(
            tournament_id=tournament_id,
            miner_address=miner_address,
            final_ranking_id=final_ranking_id,
            rank=index + 1,
            locked_at=locked_at,
        )
        repo._poker_mtt_results[f"poker_mtt_result:{tournament_id}:{miner_address}"] = _result_row(
            tournament_id=tournament_id,
            miner_address=miner_address,
            final_ranking_id=final_ranking_id,
            rank=index + 1,
            locked_at=locked_at,
        )
        repo._poker_mtt_rating_snapshots[f"poker_mtt_rating:{miner_address}:latest"] = {
            "id": f"poker_mtt_rating:{miner_address}:latest",
            "miner_address": miner_address,
            "window_start_at": "2026-04-01T00:00:00Z",
            "window_end_at": "2026-04-10T00:00:00Z",
            "public_rating": 1500.0 + (index % 100),
            "public_rank": index + 1,
            "confidence": 0.9,
            "policy_bundle_version": "poker_mtt_v1",
            "created_at": "2026-04-10T00:00:00Z",
            "updated_at": "2026-04-10T00:00:00Z",
        }


def _final_ranking_row(
    *,
    tournament_id: str,
    miner_address: str,
    final_ranking_id: str,
    rank: int,
    locked_at: str,
) -> dict:
    return {
        "id": final_ranking_id,
        "tournament_id": tournament_id,
        "source_mtt_id": tournament_id,
        "source_user_id": miner_address,
        "miner_address": miner_address,
        "economic_unit_id": miner_address,
        "member_id": f"{miner_address}:1",
        "entry_number": 1,
        "reentry_count": 1,
        "rank": rank,
        "rank_state": "ranked",
        "chip": float(100_000 - rank),
        "chip_delta": float(100_000 - rank),
        "died_time": None,
        "waiting_or_no_show": False,
        "bounty": 0.0,
        "defeat_num": max(0, 20_000 - rank),
        "field_size_policy": "exclude_waiting_no_show_from_reward_field_size",
        "standing_snapshot_id": f"poker_mtt_standing_snapshot:{tournament_id}:locked",
        "standing_snapshot_hash": "sha256:" + "b" * 64,
        "evidence_root": "sha256:" + "c" * 64,
        "evidence_state": "complete",
        "policy_bundle_version": "poker_mtt_v1",
        "snapshot_found": True,
        "status": "alive" if rank == 1 else "died",
        "player_name": miner_address,
        "room_id": "room-1",
        "start_chip": 3000.0,
        "stand_up_status": "",
        "source_rank": str(rank),
        "source_rank_numeric": True,
        "zset_score": float(100_000 - rank),
        "locked_at": locked_at,
        "anchorable_at": locked_at,
        "created_at": "2026-04-10T09:00:00Z",
        "updated_at": "2026-04-10T09:00:00Z",
    }


def _result_row(
    *,
    tournament_id: str,
    miner_address: str,
    final_ranking_id: str,
    rank: int,
    locked_at: str,
) -> dict:
    score = round(max(0.01, 1.0 - ((rank - 1) / 20_000)), 6)
    return {
        "id": f"poker_mtt_result:{tournament_id}:{miner_address}",
        "tournament_id": tournament_id,
        "miner_address": miner_address,
        "economic_unit_id": miner_address,
        "rated_or_practice": "rated",
        "human_only": True,
        "field_size": 20_000,
        "final_rank": rank,
        "entry_number": 1,
        "reentry_count": 1,
        "finish_percentile": score,
        "tournament_result_score": score,
        "hidden_eval_score": 0.0,
        "consistency_input_score": 0.0,
        "total_score": score,
        "eligible_for_multiplier": True,
        "rolling_score": None,
        "multiplier_before": 1.0,
        "multiplier_after": 1.0,
        "evaluation_state": "final",
        "evaluation_version": "poker_mtt_v1",
        "rank_state": "ranked",
        "chip_delta": float(100_000 - rank),
        "final_ranking_id": final_ranking_id,
        "standing_snapshot_id": f"poker_mtt_standing_snapshot:{tournament_id}:locked",
        "standing_snapshot_hash": "sha256:" + "b" * 64,
        "evidence_root": "sha256:" + "c" * 64,
        "evidence_state": "complete",
        "locked_at": locked_at,
        "anchorable_at": locked_at,
        "anchor_state": "unanchored",
        "anchor_payload_hash": None,
        "risk_flags": [],
        "no_multiplier_reason": None,
        "created_at": "2026-04-10T09:00:00Z",
        "updated_at": "2026-04-10T09:00:00Z",
    }


def _index_names(table) -> set[str]:
    return {index.name for index in table.indexes}
