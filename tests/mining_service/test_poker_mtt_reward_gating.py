from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine
from repository import FakeRepository


def test_final_ranking_projection_does_not_lock_incomplete_evidence():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1pendingevidence",
            name="pending-evidence",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await repo.save_poker_mtt_final_ranking(
            final_ranking_row(
                tournament_id="mtt-pending-evidence",
                miner_address="claw1pendingevidence",
                evidence_state="pending",
            )
        )

        projection = await service.project_poker_mtt_final_rankings(
            tournament_id="mtt-pending-evidence",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            locked_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
        )
        stored = (await repo.list_poker_mtt_results_for_miner("claw1pendingevidence"))[0]

        assert projection["items"][0]["eligible_for_multiplier"] is False
        assert stored["evaluation_state"] == "final"
        assert stored["evidence_state"] == "pending"
        assert stored["locked_at"] is None
        assert stored["no_multiplier_reason"] == "evidence_not_reward_ready"
        assert "evidence_not_reward_ready" in stored["risk_flags"]

        try:
            await service.build_poker_mtt_reward_window(
                lane="poker_mtt_daily",
                window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
                window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
                reward_pool_amount=100,
                include_provisional=False,
                now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
            )
        except ValueError as exc:
            assert str(exc) == "no poker mtt results found for reward window"
        else:
            raise AssertionError("reward window should reject unlocked final rows")

    asyncio.run(scenario())


def test_final_ranking_projection_requires_service_hidden_eval_for_complete_evidence():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1missinghidden",
            name="missing-hidden",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await repo.save_poker_mtt_final_ranking(
            final_ranking_row(
                tournament_id="mtt-missing-hidden",
                miner_address="claw1missinghidden",
                evidence_state="complete",
            )
        )

        projection = await service.project_poker_mtt_final_rankings(
            tournament_id="mtt-missing-hidden",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            locked_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
        )
        stored = (await repo.list_poker_mtt_results_for_miner("claw1missinghidden"))[0]

        assert projection["items"][0]["eligible_for_multiplier"] is False
        assert stored["no_multiplier_reason"] == "missing_hidden_eval"
        assert stored["hidden_eval_score"] == 0.0
        assert stored["locked_at"] is None

    asyncio.run(scenario())


def test_reward_window_membership_uses_locked_at_not_created_at():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1lockedpoker",
            name="locked-poker",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await repo.save_poker_mtt_final_ranking(
            final_ranking_row(
                tournament_id="mtt-locked",
                miner_address="claw1lockedpoker",
                created_at="2026-04-08T09:00:00Z",
                evidence_state="complete",
            )
        )
        await finalize_hidden_eval(
            service,
            tournament_id="mtt-locked",
            miner_address="claw1lockedpoker",
            final_ranking_id="poker_mtt_final_ranking:mtt-locked:claw1lockedpoker",
        )

        await service.project_poker_mtt_final_rankings(
            tournament_id="mtt-locked",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            locked_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
        )

        try:
            await service.build_poker_mtt_reward_window(
                lane="poker_mtt_daily",
                window_start_at=datetime(2026, 4, 8, 0, 0, 0, tzinfo=timezone.utc),
                window_end_at=datetime(2026, 4, 9, 0, 0, 0, tzinfo=timezone.utc),
                reward_pool_amount=100,
                include_provisional=False,
                now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
            )
        except ValueError as exc:
            assert str(exc) == "no poker mtt results found for reward window"
        else:
            raise AssertionError("created_at-only membership should not include locked results")

        reward_window = await service.build_poker_mtt_reward_window(
            lane="poker_mtt_daily",
            window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
            reward_pool_amount=100,
            include_provisional=False,
            now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
        )

        stored = (await repo.list_poker_mtt_results_for_miner("claw1lockedpoker"))[0]
        assert stored["locked_at"] == "2026-04-10T10:00:00Z"
        assert stored["eligible_for_multiplier"] is True
        assert stored["multiplier_before"] == 1.0
        assert stored["multiplier_after"] == 1.0
        assert reward_window["task_run_ids"] == ["mtt-locked"]
        assert reward_window["submission_count"] == 1

    asyncio.run(scenario())


def test_final_ranking_projection_folds_duplicate_reentries_to_canonical_row():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1reentry",
            name="reentry",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await repo.save_poker_mtt_final_ranking(
            final_ranking_row(
                row_id="poker_mtt_final_ranking:mtt-reentry:7:1",
                tournament_id="mtt-reentry",
                miner_address="claw1reentry",
                member_id="7:1",
                entry_number=1,
                rank=2,
                rank_state="duplicate_entry_collapsed",
                reentry_count=2,
                evidence_state="complete",
            )
        )
        await repo.save_poker_mtt_final_ranking(
            final_ranking_row(
                row_id="poker_mtt_final_ranking:mtt-reentry:7:2",
                tournament_id="mtt-reentry",
                miner_address="claw1reentry",
                member_id="7:2",
                entry_number=2,
                rank=1,
                rank_state="ranked",
                reentry_count=2,
                evidence_state="complete",
            )
        )
        await finalize_hidden_eval(
            service,
            tournament_id="mtt-reentry",
            miner_address="claw1reentry",
            final_ranking_id="poker_mtt_final_ranking:mtt-reentry:7:2",
        )

        projection = await service.project_poker_mtt_final_rankings(
            tournament_id="mtt-reentry",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            locked_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
        )
        stored = await repo.list_poker_mtt_results_for_miner("claw1reentry")

        assert len(projection["items"]) == 1
        assert len(stored) == 1
        assert stored[0]["final_rank"] == 1
        assert stored[0]["entry_number"] == 2
        assert stored[0]["reentry_count"] == 2
        assert stored[0]["final_ranking_id"] == "poker_mtt_final_ranking:mtt-reentry:7:2"
        assert stored[0]["eligible_for_multiplier"] is True

    asyncio.run(scenario())


def test_poker_mtt_reward_window_never_settles_provisional_rows():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1provisional",
            name="provisional",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await repo.save_poker_mtt_result(
            {
                "id": "poker_mtt:mtt-provisional:claw1provisional",
                "tournament_id": "mtt-provisional",
                "miner_address": "claw1provisional",
                "rated_or_practice": "rated",
                "human_only": True,
                "field_size": 30,
                "final_rank": 1,
                "finish_percentile": 1.0,
                "tournament_result_score": 1.0,
                "hidden_eval_score": 0.0,
                "consistency_input_score": 0.0,
                "total_score": 0.55,
                "eligible_for_multiplier": True,
                "rolling_score": None,
                "multiplier_before": 1.0,
                "multiplier_after": 1.0,
                "evaluation_state": "provisional",
                "evaluation_version": "poker_mtt_v1",
                "economic_unit_id": "claw1provisional",
                "entry_number": 1,
                "reentry_count": 1,
                "final_ranking_id": "poker_mtt_final_ranking:mtt-provisional:1:1",
                "standing_snapshot_id": "poker_mtt_standing_snapshot:mtt-provisional:abc",
                "standing_snapshot_hash": "sha256:abc",
                "evidence_root": "sha256:evidence",
                "evidence_state": "complete",
                "locked_at": "2026-04-10T10:00:00Z",
                "anchor_state": "unanchored",
                "anchor_payload_hash": None,
                "risk_flags": [],
                "no_multiplier_reason": None,
                "created_at": "2026-04-10T10:00:00Z",
                "updated_at": "2026-04-10T10:00:00Z",
            }
        )

        try:
            await service.build_poker_mtt_reward_window(
                lane="poker_mtt_daily",
                window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
                window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
                reward_pool_amount=100,
                include_provisional=True,
                now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
            )
        except ValueError as exc:
            assert str(exc) == "no poker mtt results found for reward window"
        else:
            raise AssertionError("provisional poker mtt rows must never settle")

    asyncio.run(scenario())


def test_legacy_apply_caller_hidden_score_does_not_unlock_reward_readiness():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1hidden",
            name="hidden",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        applied = await service.apply_poker_mtt_results(
            tournament_id="mtt-hidden",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1hidden",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.9,
                    "consistency_input_score": 0.2,
                    "evaluation_state": "final",
                    "evidence_state": "complete",
                    "evidence_root": "sha256:evidence",
                    "locked_at": "2026-04-10T10:00:00Z",
                }
            ],
            completed_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
        )
        stored = applied["items"][0]

        assert stored["hidden_eval_score"] == 0.0
        assert stored["eligible_for_multiplier"] is False
        assert stored["no_multiplier_reason"] in {"missing_hidden_eval", "missing_final_ranking_ref"}

    asyncio.run(scenario())


def test_poker_mtt_reward_window_requires_saved_canonical_final_ranking():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1nofinalranking",
            name="no-final-ranking",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await repo.save_poker_mtt_result(
            {
                "id": "poker_mtt:mtt-no-final-ranking:claw1nofinalranking",
                "tournament_id": "mtt-no-final-ranking",
                "miner_address": "claw1nofinalranking",
                "rated_or_practice": "rated",
                "human_only": True,
                "field_size": 30,
                "final_rank": 1,
                "rank_state": "ranked",
                "chip_delta": 6000.0,
                "finish_percentile": 1.0,
                "tournament_result_score": 1.0,
                "hidden_eval_score": 0.0,
                "consistency_input_score": 0.0,
                "total_score": 0.55,
                "eligible_for_multiplier": True,
                "rolling_score": None,
                "multiplier_before": 1.0,
                "multiplier_after": 1.0,
                "evaluation_state": "final",
                "evaluation_version": "poker_mtt_v1",
                "economic_unit_id": "claw1nofinalranking",
                "entry_number": 1,
                "reentry_count": 1,
                "final_ranking_id": "poker_mtt_final_ranking:mtt-no-final-ranking:1:1",
                "standing_snapshot_id": "poker_mtt_standing_snapshot:mtt-no-final-ranking:abc",
                "standing_snapshot_hash": "sha256:abc",
                "evidence_root": "sha256:evidence",
                "evidence_state": "complete",
                "locked_at": "2026-04-10T10:00:00Z",
                "anchorable_at": "2026-04-10T10:00:00Z",
                "anchor_state": "unanchored",
                "anchor_payload_hash": None,
                "risk_flags": [],
                "no_multiplier_reason": None,
                "created_at": "2026-04-10T10:00:00Z",
                "updated_at": "2026-04-10T10:00:00Z",
            }
        )

        try:
            await service.build_poker_mtt_reward_window(
                lane="poker_mtt_daily",
                window_start_at=datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc),
                window_end_at=datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
                reward_pool_amount=100,
                include_provisional=False,
                now=datetime(2026, 4, 11, 0, 5, 0, tzinfo=timezone.utc),
            )
        except ValueError as exc:
            assert str(exc) == "no poker mtt results found for reward window"
        else:
            raise AssertionError("reward window must reject rows without saved canonical final ranking")

    asyncio.run(scenario())


def test_legacy_apply_requires_final_ranking_refs_before_multiplier():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1missingrefs",
            name="missing-refs",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        for index in range(16):
            await service.apply_poker_mtt_results(
                tournament_id=f"mtt-missing-refs-{index}",
                rated_or_practice="rated",
                human_only=True,
                field_size=30,
                policy_bundle_version="poker_mtt_v1",
                results=[
                    {
                        "miner_id": "claw1missingrefs",
                        "final_rank": 1,
                        "tournament_result_score": 1.0,
                        "hidden_eval_score": 0.0,
                        "consistency_input_score": 0.0,
                        "evaluation_state": "final",
                        "evidence_state": "complete",
                        "evidence_root": f"sha256:evidence:{index}",
                        "locked_at": "2026-04-10T10:00:00Z",
                    }
                ],
                completed_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
            )

        miner = await repo.get_miner("claw1missingrefs")
        stored = (await repo.list_poker_mtt_results_for_miner("claw1missingrefs"))[0]

        assert miner["poker_mtt_multiplier"] == 1.0
        assert stored["eligible_for_multiplier"] is False
        assert stored["no_multiplier_reason"] == "missing_final_ranking_ref"

    asyncio.run(scenario())


def test_legacy_apply_rejects_fabricated_final_ranking_refs_before_multiplier():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1fakerefs",
            name="fake-refs",
            public_key="pubkey",
            miner_version="0.4.0",
        )

        await service.apply_poker_mtt_results(
            tournament_id="mtt-fake-refs",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1fakerefs",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    "evidence_state": "complete",
                    "evidence_root": "sha256:evidence",
                    "final_ranking_id": "poker_mtt_final_ranking:mtt-fake-refs:7:1",
                    "standing_snapshot_id": "poker_mtt_standing_snapshot:mtt-fake-refs:abc",
                    "standing_snapshot_hash": "sha256:abc",
                    "locked_at": "2026-04-10T10:00:00Z",
                }
            ],
            completed_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
        )

        miner = await repo.get_miner("claw1fakerefs")
        stored = (await repo.list_poker_mtt_results_for_miner("claw1fakerefs"))[0]

        assert miner["poker_mtt_multiplier"] == 1.0
        assert stored["eligible_for_multiplier"] is False
        assert stored["no_multiplier_reason"] == "canonical_final_ranking_not_found"

    asyncio.run(scenario())


def test_legacy_apply_rejects_mismatched_final_ranking_ref_before_multiplier():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(
            address="claw1mismatchrefs",
            name="mismatch-refs",
            public_key="pubkey",
            miner_version="0.4.0",
        )
        await repo.save_poker_mtt_final_ranking(
            final_ranking_row(
                row_id="poker_mtt_final_ranking:mtt-mismatch-refs:7:1",
                tournament_id="mtt-mismatch-refs",
                miner_address="claw1mismatchrefs",
                rank=2,
                evidence_state="complete",
            )
        )

        await service.apply_poker_mtt_results(
            tournament_id="mtt-mismatch-refs",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_id": "claw1mismatchrefs",
                    "final_rank": 1,
                    "tournament_result_score": 1.0,
                    "hidden_eval_score": 0.0,
                    "consistency_input_score": 0.0,
                    "evaluation_state": "final",
                    "evidence_state": "complete",
                    "evidence_root": "sha256:evidence",
                    "final_ranking_id": "poker_mtt_final_ranking:mtt-mismatch-refs:7:1",
                    "standing_snapshot_id": "poker_mtt_standing_snapshot:mtt-mismatch-refs:abc",
                    "standing_snapshot_hash": "sha256:abc",
                    "locked_at": "2026-04-10T10:00:00Z",
                }
            ],
            completed_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
        )

        miner = await repo.get_miner("claw1mismatchrefs")
        stored = (await repo.list_poker_mtt_results_for_miner("claw1mismatchrefs"))[0]

        assert miner["poker_mtt_multiplier"] == 1.0
        assert stored["eligible_for_multiplier"] is False
        assert stored["no_multiplier_reason"] == "canonical_final_ranking_mismatch"

    asyncio.run(scenario())


async def finalize_hidden_eval(
    service: forecast_engine.ForecastMiningService,
    *,
    tournament_id: str,
    miner_address: str,
    final_ranking_id: str,
    hidden_eval_score: float = 0.0,
) -> None:
    await service.finalize_poker_mtt_hidden_eval(
        tournament_id=tournament_id,
        policy_bundle_version="poker_mtt_v1",
        seed_assignment_id=f"hidden-seed:{tournament_id}",
        baseline_sample_id=None,
        entries=[
            {
                "miner_address": miner_address,
                "final_ranking_id": final_ranking_id,
                "hidden_eval_score": hidden_eval_score,
                "score_components_json": {"test_fixture": True},
                "evidence_root": "sha256:hidden_eval",
            }
        ],
        now=datetime(2026, 4, 10, 9, 30, 0, tzinfo=timezone.utc),
    )


def final_ranking_row(
    *,
    row_id: str | None = None,
    tournament_id: str,
    miner_address: str,
    member_id: str | None = None,
    entry_number: int = 1,
    reentry_count: int = 1,
    created_at: str = "2026-04-10T09:00:00Z",
    evidence_state: str = "complete",
    rank_state: str = "ranked",
    rank: int | None = None,
) -> dict:
    if rank is None and rank_state == "ranked":
        rank = 1
    resolved_member_id = member_id or f"{miner_address}:{entry_number}"
    return {
        "id": row_id or f"poker_mtt_final_ranking:{tournament_id}:{miner_address}",
        "tournament_id": tournament_id,
        "source_mtt_id": tournament_id,
        "source_user_id": miner_address,
        "miner_address": miner_address,
        "economic_unit_id": miner_address,
        "member_id": resolved_member_id,
        "entry_number": entry_number,
        "reentry_count": reentry_count,
        "rank": rank,
        "rank_state": rank_state,
        "chip": 9000.0,
        "chip_delta": 6000.0,
        "died_time": None,
        "waiting_or_no_show": rank is None,
        "bounty": 0.0,
        "defeat_num": 0,
        "field_size_policy": "exclude_waiting_no_show_from_reward_field_size",
        "standing_snapshot_id": f"poker_mtt_standing_snapshot:{tournament_id}:abc",
        "standing_snapshot_hash": "sha256:abc",
        "evidence_root": "sha256:evidence",
        "evidence_state": evidence_state,
        "policy_bundle_version": "poker_mtt_v1",
        "snapshot_found": True,
        "status": "alive",
        "player_name": miner_address,
        "room_id": "room-1",
        "start_chip": 3000.0,
        "stand_up_status": "",
        "source_rank": "1" if rank is not None else "",
        "source_rank_numeric": rank is not None,
        "zset_score": 9000.0,
        "created_at": created_at,
        "updated_at": created_at,
    }
