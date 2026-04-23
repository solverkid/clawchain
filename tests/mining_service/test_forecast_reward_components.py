from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine
from repository import FakeRepository


class StaticTaskProvider:
    def __init__(self, resolutions):
        self.resolutions = list(resolutions)

    async def build_fast_task(self, now, settings, asset):  # noqa: ANN001
        return forecast_engine.build_fast_task(now, settings=settings, asset=asset)

    async def resolve_fast_task(self, task):  # noqa: ANN001
        if self.resolutions:
            return self.resolutions.pop(0)
        return {"outcome": None, "resolution_status": "pending", "commit_close_ref_price": task.get("commit_close_ref_price")}

    async def resolve_daily_task(self, task):  # noqa: ANN001
        return {
            "outcome": 1,
            "resolution_status": "resolved",
            "start_ref_price": 70000.0,
            "end_ref_price": 71000.0,
        }

    async def aclose(self):
        return None


def _expected_submission_components(
    *,
    task: dict,
    miner_before: dict,
    p_yes_bps: int,
    outcome: int,
    settings,
    anti_abuse_discount: float = 1.0,
) -> dict:  # noqa: ANN001
    score = forecast_engine.score_probability(
        p_yes_bps=p_yes_bps,
        baseline_q_bps=task["baseline_q_bps"],
        outcome=outcome,
    )
    fast_direct_score = forecast_engine._reward_from_score(score)
    settled_tasks = int(miner_before["settled_tasks"]) + 1
    edge_score_total = float(miner_before["edge_score_total"]) + score
    model_reliability = forecast_engine.clamp(1.0 + (edge_score_total / settled_tasks) * 0.25, 0.97, 1.03)
    ops_reliability = round(float(miner_before["ops_reliability"]), 6)
    arena_multiplier = round(float(miner_before["arena_multiplier"]), 6)
    quality_envelope = round(
        model_reliability * ops_reliability * arena_multiplier * anti_abuse_discount,
        6,
    )
    reward_amount = max(0, int(round(fast_direct_score * quality_envelope)))
    release_ratio = settings.admission_release_bps / 10_000
    released_reward_amount = int(round(reward_amount * release_ratio))
    held_reward_amount = reward_amount - released_reward_amount
    return {
        "score": score,
        "fast_direct_score": fast_direct_score,
        "model_reliability_component": model_reliability,
        "ops_reliability_component": ops_reliability,
        "arena_multiplier_component": arena_multiplier,
        "anti_abuse_discount": anti_abuse_discount,
        "quality_envelope": quality_envelope,
        "reward_amount": reward_amount,
        "released_reward_amount": released_reward_amount,
        "held_reward_amount": held_reward_amount,
    }


def _expected_reward_row(miner_address: str, component_fields: dict) -> dict:
    fast_direct_score = component_fields["fast_direct_score"]
    final_mining_score = component_fields["reward_amount"]
    quality_envelope = (
        round(final_mining_score / fast_direct_score, 6)
        if fast_direct_score > 0
        else round(component_fields["quality_envelope"], 6)
    )
    return {
        "miner_address": miner_address,
        "submission_count": 1,
        "fast_direct_score": fast_direct_score,
        "slow_direct_score": 0,
        "base_score": fast_direct_score,
        "final_mining_score": final_mining_score,
        "released_reward_amount": component_fields["released_reward_amount"],
        "held_reward_amount": component_fields["held_reward_amount"],
        "gross_reward_amount": final_mining_score,
        "model_reliability": round(component_fields["model_reliability_component"], 6),
        "ops_reliability": round(component_fields["ops_reliability_component"], 6),
        "arena_multiplier": round(component_fields["arena_multiplier_component"], 6),
        "anti_abuse_discount": round(component_fields["anti_abuse_discount"], 6),
        "quality_envelope": quality_envelope,
    }


async def _build_reward_component_fixture(
    *,
    anti_abuse_discount: float = 1.0,
    open_risk_cases: list[dict] | None = None,
) -> dict:
    repo = FakeRepository()
    settings = forecast_engine.ForecastSettings(
        fast_task_seconds=60,
        commit_window_seconds=5,
        reveal_window_seconds=10,
    )
    provider = StaticTaskProvider(
        [{"outcome": 1, "resolution_status": "resolved", "commit_close_ref_price": 70000.5, "end_ref_price": None}]
    )
    service = forecast_engine.ForecastMiningService(repo, settings, task_provider=provider)

    miner_address = "claw1componentminer"
    p_yes_bps = 8500
    task_time = datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc)
    reconcile_time = datetime(2026, 4, 10, 9, 1, 5, tzinfo=timezone.utc)

    await service.register_miner(
        address=miner_address,
        name="component-miner",
        public_key="pubkey",
        miner_version="0.4.0",
    )
    await repo.update_miner(
        miner_address,
        {
            "economic_unit_id": "eu:component-miner",
            "created_at": "2026-04-10T08:55:00Z",
            "forecast_commits": 7,
            "forecast_reveals": 7,
            "fast_task_opportunities": 7,
            "fast_task_misses": 1,
            "settled_tasks": 4,
            "correct_direction_count": 3,
            "edge_score_total": 0.5,
            "model_reliability": 1.0,
            "ops_reliability": 1.012345,
            "arena_multiplier": 1.031234,
            "updated_at": "2026-04-10T08:55:00Z",
        },
    )
    miner_before = await repo.get_miner(miner_address)

    task = forecast_engine.build_fast_task(task_time, settings, asset="BTCUSDT")
    task["commit_close_ref_price"] = 70000.5
    await repo.upsert_task(task)
    await repo.save_submission(
        {
            "id": f"sub:{task['task_run_id']}:{miner_address}",
            "task_run_id": task["task_run_id"],
            "miner_address": miner_address,
            "economic_unit_id": "eu:component-miner",
            "commit_request_id": "req-commit",
            "reveal_request_id": "req-reveal",
            "commit_hash": "hash",
            "commit_nonce": "nonce",
            "p_yes_bps": p_yes_bps,
            "eligibility_status": "eligible",
            "state": "revealed",
            "score": 0.0,
            "reward_amount": 0,
            "accepted_commit_at": "2026-04-10T09:00:02Z",
            "accepted_reveal_at": "2026-04-10T09:00:06Z",
            "created_at": "2026-04-10T09:00:02Z",
            "updated_at": "2026-04-10T09:00:06Z",
        }
    )
    for risk_case in open_risk_cases or []:
        await repo.save_risk_case(risk_case)

    expected_submission = _expected_submission_components(
        task=task,
        miner_before=miner_before,
        p_yes_bps=p_yes_bps,
        outcome=1,
        settings=settings,
        anti_abuse_discount=anti_abuse_discount,
    )
    expected_row = _expected_reward_row(miner_address, expected_submission)

    await service.reconcile(reconcile_time)

    saved_submission = await repo.get_submission(task["task_run_id"], miner_address)
    reward_window = next(iter(await repo.list_reward_windows()))
    reward_window_artifacts = await repo.list_artifacts_for_entity("reward_window", reward_window["id"])
    reward_window_artifact = next(
        artifact for artifact in reward_window_artifacts if artifact["kind"] == "reward_window_membership"
    )
    settlement_batch = next(iter(await repo.list_settlement_batches()))

    return {
        "repo": repo,
        "service": service,
        "settings": settings,
        "task": task,
        "saved_submission": saved_submission,
        "reward_window": reward_window,
        "reward_window_artifact": reward_window_artifact,
        "reward_window_artifacts": reward_window_artifacts,
        "settlement_batch": settlement_batch,
        "expected_submission": expected_submission,
        "expected_row": expected_row,
    }


def test_resolved_fast_task_persists_deterministic_reward_component_fields():
    async def scenario():
        fixture = await _build_reward_component_fixture()
        saved_submission = fixture["saved_submission"]
        expected = fixture["expected_submission"]

        assert saved_submission["state"] == "resolved"
        assert saved_submission["fast_direct_score"] == expected["fast_direct_score"]
        assert saved_submission["reward_amount"] == expected["reward_amount"]
        assert saved_submission["released_reward_amount"] == expected["released_reward_amount"]
        assert saved_submission["held_reward_amount"] == expected["held_reward_amount"]
        assert saved_submission["anti_abuse_discount"] == expected["anti_abuse_discount"]
        assert saved_submission["model_reliability_component"] == pytest.approx(expected["model_reliability_component"])
        assert saved_submission["ops_reliability_component"] == pytest.approx(expected["ops_reliability_component"])
        assert saved_submission["arena_multiplier_component"] == pytest.approx(expected["arena_multiplier_component"])
        assert saved_submission["quality_envelope"] == pytest.approx(expected["quality_envelope"])

    asyncio.run(scenario())


def test_reward_window_membership_artifact_materializes_reward_component_rows():
    async def scenario():
        fixture = await _build_reward_component_fixture()
        reward_window = fixture["reward_window"]
        artifact = fixture["reward_window_artifact"]
        artifacts = fixture["reward_window_artifacts"]
        expected_row = fixture["expected_row"]

        payload = artifact["payload_json"]
        assert reward_window["miner_reward_rows"] == [expected_row]
        assert reward_window["total_reward_amount"] == expected_row["gross_reward_amount"]
        assert payload["reward_window_id"] == reward_window["id"]
        assert payload["miner_reward_rows"] == [expected_row]
        assert payload["miner_reward_rows_count"] == 1
        assert payload["miner_reward_rows_root"] == forecast_engine._hash_sequence([expected_row])
        assert forecast_engine.resolve_reward_window_membership_rows(payload, artifacts) == [expected_row]

    asyncio.run(scenario())


def test_open_cluster_risk_case_discount_flows_into_reward_components():
    async def scenario():
        fixture = await _build_reward_component_fixture(
            anti_abuse_discount=0.25,
            open_risk_cases=[
                {
                    "id": "risk:cluster:eu:component-miner",
                    "case_type": "economic_unit_cluster",
                    "severity": "medium",
                    "state": "open",
                    "economic_unit_id": "eu:component-miner",
                    "miner_address": "claw1componentminer",
                    "task_run_id": None,
                    "submission_id": None,
                    "evidence_json": {"member_addresses": ["claw1componentminer", "claw1shadowminer"]},
                    "created_at": "2026-04-10T09:00:04Z",
                    "updated_at": "2026-04-10T09:00:04Z",
                }
            ],
        )
        saved_submission = fixture["saved_submission"]
        reward_window = fixture["reward_window"]
        expected_submission = fixture["expected_submission"]
        expected_row = fixture["expected_row"]

        assert saved_submission["anti_abuse_discount"] == 0.25
        assert saved_submission["reward_amount"] == expected_submission["reward_amount"]
        assert saved_submission["quality_envelope"] == pytest.approx(expected_submission["quality_envelope"])
        assert reward_window["miner_reward_rows"] == [expected_row]
        assert reward_window["miner_reward_rows"][0]["anti_abuse_discount"] == 0.25
        assert reward_window["miner_reward_rows"][0]["quality_envelope"] == pytest.approx(expected_row["quality_envelope"])

    asyncio.run(scenario())


def test_settlement_anchor_payload_consumes_materialized_reward_window_rows():
    async def scenario():
        fixture = await _build_reward_component_fixture()
        repo = fixture["repo"]
        service = fixture["service"]
        reward_window_artifact = fixture["reward_window_artifact"]
        settlement_batch = fixture["settlement_batch"]
        task = fixture["task"]
        saved_submission = fixture["saved_submission"]
        expected_submission = fixture["expected_submission"]

        mutated_row = deepcopy(fixture["expected_row"])
        mutated_row["released_reward_amount"] -= 1
        mutated_row["held_reward_amount"] += 1

        mutated_payload = {
            **reward_window_artifact["payload_json"],
            "miner_reward_rows": [mutated_row],
            "miner_reward_rows_root": forecast_engine._hash_sequence([mutated_row]),
            "miner_reward_rows_count": 1,
        }
        await repo.save_artifact(
            {
                **reward_window_artifact,
                "payload_json": mutated_payload,
                "payload_hash": forecast_engine._hash_payload(mutated_payload),
                "updated_at": "2026-04-10T09:01:06Z",
            }
        )

        async def noop_reconcile(now=None):  # noqa: ANN001
            return None

        service.reconcile = noop_reconcile  # type: ignore[method-assign]

        anchored = await service.retry_anchor_settlement_batch(
            settlement_batch["id"],
            now=datetime(2026, 4, 10, 9, 1, 7, tzinfo=timezone.utc),
        )
        anchor_artifacts = await repo.list_artifacts_for_entity("settlement_batch", settlement_batch["id"])
        anchor_artifact = next(
            artifact for artifact in anchor_artifacts if artifact["kind"] == "settlement_anchor_payload"
        )

        assert saved_submission["task_run_id"] == task["task_run_id"]
        assert saved_submission["released_reward_amount"] == expected_submission["released_reward_amount"]
        assert saved_submission["held_reward_amount"] == expected_submission["held_reward_amount"]
        assert anchored["anchor_payload_json"]["miner_reward_rows"] == [mutated_row]
        assert anchored["anchor_payload_json"]["miner_reward_rows_root"] == mutated_payload["miner_reward_rows_root"]
        assert forecast_engine.resolve_settlement_anchor_reward_rows(
            anchor_artifact["payload_json"],
            anchor_artifacts,
        ) == [mutated_row]

    asyncio.run(scenario())
