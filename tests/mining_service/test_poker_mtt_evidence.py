from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import canonical
import forecast_engine
import poker_mtt_evidence
import poker_mtt_history
from repository import FakeRepository


def test_canonical_rows_root_normalizes_utc_timestamps_and_fixed_decimals():
    rows = [
        {
            "member_id": "2:1",
            "created_at": "2026-04-10T10:00:00+00:00",
            "chip": canonical.fixed_decimal(Decimal("3000.1000"), places=4),
            "rank": 2,
        },
        {
            "member_id": "1:1",
            "created_at": datetime(2026, 4, 10, 5, 0, 0, tzinfo=timezone.utc),
            "chip": canonical.fixed_decimal(Decimal("4000.5"), places=4),
            "rank": 1,
        },
    ]
    same_rows_different_order_and_key_order = [
        {
            "rank": 1,
            "chip": "4000.5000",
            "created_at": "2026-04-10T05:00:00Z",
            "member_id": "1:1",
        },
        {
            "rank": 2,
            "chip": "3000.1000",
            "created_at": "2026-04-10T06:00:00-04:00",
            "member_id": "2:1",
        },
    ]

    assert canonical.rows_root(rows, sort_keys=("member_id",)) == canonical.rows_root(
        same_rows_different_order_and_key_order,
        sort_keys=("member_id",),
    )
    assert canonical.canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_final_ranking_manifest_has_stable_root_with_explicit_row_sort_keys():
    generated_at = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    rows = [
        final_ranking_row("2:1", rank=2, chip=Decimal("2000.25")),
        final_ranking_row("1:1", rank=1, chip=Decimal("7000.75")),
    ]
    shuffled = list(reversed(rows))
    fixed_decimal_rows = [
        {
            **final_ranking_row("1:1", rank=1, chip=Decimal("7000.75")),
            "chip": "7000.750000",
            "chip_delta": "4000.750000",
            "bounty": "0.000000",
            "start_chip": "3000.000000",
            "zset_score": "7000.750000",
        },
        {
            **final_ranking_row("2:1", rank=2, chip=Decimal("2000.25")),
            "chip": "2000.250000",
            "chip_delta": "-999.750000",
            "bounty": "0.000000",
            "start_chip": "3000.000000",
            "zset_score": "2000.250000",
        },
    ]

    first = poker_mtt_evidence.build_final_ranking_manifest(
        tournament_id="mtt-evidence-1",
        rows=rows,
        policy_bundle_version="poker_mtt_v1",
        generated_at=generated_at,
    )
    second = poker_mtt_evidence.build_final_ranking_manifest(
        tournament_id="mtt-evidence-1",
        rows=shuffled,
        policy_bundle_version="poker_mtt_v1",
        generated_at="2026-04-10T12:00:00Z",
    )
    third = poker_mtt_evidence.build_final_ranking_manifest(
        tournament_id="mtt-evidence-1",
        rows=fixed_decimal_rows,
        policy_bundle_version="poker_mtt_v1",
        generated_at="2026-04-10T12:00:00Z",
    )

    assert first["kind"] == "poker_mtt_final_ranking_manifest"
    assert first["row_count"] == 2
    assert first["row_sort_keys"] == ["tournament_id", "member_id"]
    assert first["rows_root"] == second["rows_root"]
    assert first["manifest_root"] == second["manifest_root"]
    assert first["rows_root"] == third["rows_root"]
    assert first["manifest_root"] == third["manifest_root"]


def test_accepted_degraded_stub_manifests_are_empty_and_hashable():
    manifest = poker_mtt_evidence.build_stub_manifest(
        kind="poker_mtt_hidden_eval_manifest",
        tournament_id="mtt-evidence-1",
        policy_bundle_version="poker_mtt_v1",
        evidence_state="accepted_degraded",
        degraded_reason="phase1_hidden_eval_deferred",
        generated_at=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert manifest["evidence_state"] == "accepted_degraded"
    assert manifest["degraded_reason"] == "phase1_hidden_eval_deferred"
    assert manifest["row_count"] == 0
    assert manifest["rows_root"] == canonical.rows_root([], sort_keys=())
    assert manifest["manifest_root"].startswith("sha256:")


def test_hand_history_manifest_uses_persisted_hand_event_rows():
    generated_at = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    rows = [
        {
            "tournament_id": "mtt-evidence-1",
            "hand_id": "mtt-evidence-1:table-2:9",
            "table_id": "table-2",
            "hand_no": 9,
            "version": 1,
            "checksum": "sha256:" + "a" * 64,
            "ingest_state": "inserted",
        }
    ]

    manifest = poker_mtt_evidence.build_hand_history_manifest(
        tournament_id="mtt-evidence-1",
        rows=rows,
        policy_bundle_version="poker_mtt_v1",
        generated_at=generated_at,
    )

    assert manifest["kind"] == "poker_mtt_hand_history_manifest"
    assert manifest["evidence_state"] == "complete"
    assert manifest["row_count"] == 1
    assert manifest["row_sort_keys"] == ["tournament_id", "table_id", "hand_no", "hand_id"]
    assert manifest["manifest_root"].startswith("sha256:")


def test_service_persists_stable_tournament_evidence_manifests():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await repo.save_poker_mtt_final_ranking(
            {
                "id": "poker_mtt_final_ranking:mtt-evidence-1:1:1",
                **final_ranking_row("1:1", rank=1, chip=Decimal("7000.75")),
            }
        )
        await repo.save_poker_mtt_final_ranking(
            {
                "id": "poker_mtt_final_ranking:mtt-evidence-1:2:1",
                **final_ranking_row("2:1", rank=2, chip=Decimal("2000.25")),
            }
        )

        first = await service.build_poker_mtt_evidence_manifests(
            tournament_id="mtt-evidence-1",
            policy_bundle_version="poker_mtt_v1",
            accepted_degraded_kinds=[
                "poker_mtt_hidden_eval_manifest",
                "poker_mtt_short_term_hud_manifest",
                "poker_mtt_long_term_hud_manifest",
            ],
            now=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
        )
        second = await service.build_poker_mtt_evidence_manifests(
            tournament_id="mtt-evidence-1",
            policy_bundle_version="poker_mtt_v1",
            accepted_degraded_kinds=[
                "poker_mtt_long_term_hud_manifest",
                "poker_mtt_short_term_hud_manifest",
                "poker_mtt_hidden_eval_manifest",
            ],
            now="2026-04-10T12:05:00Z",
        )
        artifacts = await repo.list_artifacts_for_entity("poker_mtt_tournament", "mtt-evidence-1")

        assert first["evidence_root"] == second["evidence_root"]
        assert sorted(artifact["kind"] for artifact in artifacts) == [
            "poker_mtt_final_ranking_manifest",
            "poker_mtt_hidden_eval_manifest",
            "poker_mtt_long_term_hud_manifest",
            "poker_mtt_short_term_hud_manifest",
        ]
        assert len(artifacts) == 4
        assert all(artifact["payload_hash"].startswith("sha256:") for artifact in artifacts)

    import asyncio

    asyncio.run(scenario())


def test_service_uses_real_hand_history_manifest_when_hand_events_exist():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await repo.save_poker_mtt_final_ranking(
            {
                "id": "poker_mtt_final_ranking:mtt-evidence-1:1:1",
                **final_ranking_row("1:1", rank=1, chip=Decimal("7000.75")),
            }
        )
        await repo.save_poker_mtt_hand_event(completed_hand_event("mtt-evidence-1", "table-1", 1))

        result = await service.build_poker_mtt_evidence_manifests(
            tournament_id="mtt-evidence-1",
            policy_bundle_version="poker_mtt_v1",
            accepted_degraded_kinds=[
                "poker_mtt_hidden_eval_manifest",
                "poker_mtt_short_term_hud_manifest",
                "poker_mtt_long_term_hud_manifest",
            ],
            now=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
        )
        artifacts = await repo.list_artifacts_for_entity("poker_mtt_tournament", "mtt-evidence-1")
        hand_manifest = next(artifact for artifact in artifacts if artifact["kind"] == "poker_mtt_hand_history_manifest")

        assert result["evidence_state"] == "accepted_degraded"
        assert hand_manifest["payload_json"]["evidence_state"] == "complete"
        assert hand_manifest["payload_json"]["row_count"] == 1

    import asyncio

    asyncio.run(scenario())


def test_service_finalizes_hidden_eval_entries_with_clamped_scores_and_manifest():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())

        result = await service.finalize_poker_mtt_hidden_eval(
            tournament_id="mtt-hidden-eval-1",
            policy_bundle_version="poker_mtt_v1",
            seed_assignment_id="hidden-seed-1",
            baseline_sample_id="baseline-1",
            entries=[
                {
                    "miner_address": "claw1hiddeneval",
                    "final_ranking_id": "poker_mtt_final_ranking:mtt-hidden-eval-1:1:1",
                    "hidden_eval_score": 1.8,
                    "score_components_json": {"baseline_delta": 1.8},
                    "evidence_root": "sha256:" + "b" * 64,
                }
            ],
            now=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
        )
        stored = await repo.list_poker_mtt_hidden_eval_entries_for_tournament("mtt-hidden-eval-1")

        assert result["manifest"]["kind"] == "poker_mtt_hidden_eval_manifest"
        assert result["manifest"]["evidence_state"] == "complete"
        assert result["manifest"]["row_count"] == 1
        assert stored[0]["hidden_eval_score"] == 1.0
        assert stored[0]["manifest_root"] == result["manifest"]["manifest_root"]
        assert stored[0]["visibility_state"] == "service_internal"

    import asyncio

    asyncio.run(scenario())


def final_ranking_row(member_id: str, *, rank: int, chip: Decimal) -> dict:
    return {
        "tournament_id": "mtt-evidence-1",
        "member_id": member_id,
        "rank": rank,
        "rank_state": "ranked",
        "miner_address": f"claw1{member_id.replace(':', '')}",
        "economic_unit_id": f"eu:{member_id.replace(':', '')}",
        "chip": float(chip),
        "chip_delta": float(chip - Decimal("3000")),
        "bounty": 0.0,
        "start_chip": 3000.0,
        "zset_score": float(chip),
        "updated_at": "2026-04-10T12:00:00Z",
    }


def completed_hand_event(tournament_id: str, table_id: str, hand_no: int) -> dict:
    return poker_mtt_history.build_hand_completed_event(
        tournament_id=tournament_id,
        table_id=table_id,
        hand_no=hand_no,
        version=1,
        payload={"pot": 120, "actions": [{"seat": 2, "type": "call"}]},
        source={
            "transport": "rocketmq",
            "topic": "POKER_RECORD_TOPIC",
            "message_id": f"msg-{tournament_id}-{table_id}-{hand_no}",
            "biz_id": f"biz-{tournament_id}-{table_id}-{hand_no}",
            "record_type": "recordType",
            "source_mtt_id": tournament_id,
            "source_room_id": table_id,
        },
    )
