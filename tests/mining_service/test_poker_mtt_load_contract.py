from __future__ import annotations

import sys
import json
import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine


GENERATOR = ROOT / "scripts" / "poker_mtt" / "generate_hand_history_load.py"
HARNESS = ROOT / "scripts" / "poker_mtt" / "non_mock_play_harness.py"


def load_non_mock_harness_module():
    spec = importlib.util.spec_from_file_location("non_mock_play_harness", HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_large_window_for_test(player_count: int) -> dict:
    miner_reward_rows = [
        {
            "miner_address": f"claw1load{i:05d}",
            "gross_reward_amount": 1,
            "submission_count": 1,
        }
        for i in range(player_count)
    ]
    payload = {
        "reward_window_id": "rw-load",
        "lane": "poker_mtt_daily",
        "miner_reward_rows": miner_reward_rows,
    }
    return forecast_engine.build_paged_poker_mtt_projection_payload(payload, page_size=5000)[0]


def test_large_poker_mtt_reward_window_returns_page_references_not_full_payload():
    window = build_large_window_for_test(player_count=20000)

    assert window["artifact_page_count"] > 1
    assert "miner_reward_rows_root" in window
    assert "miner_reward_rows" not in window


def test_phase2_load_generator_emits_required_shapes():
    completed = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--players",
            "30",
            "--hands",
            "4",
            "--synthetic-projection-players",
            "20000",
            "--medium-players",
            "300",
            "--early-table-count",
            "2000",
        ],
        cwd=ROOT,
        text=True,
        check=True,
        capture_output=True,
    )

    summary = json.loads(completed.stdout)

    assert summary["smoke_mtt"]["player_count"] == 30
    assert summary["smoke_mtt"]["hand_event_count"] == 4
    assert summary["medium_check"]["player_count"] == 300
    assert summary["synthetic_projection"]["player_count"] == 20000
    assert summary["synthetic_projection"]["artifact_page_count"] > 1
    assert summary["early_table_burst"]["table_count"] == 2000
    assert summary["early_table_burst"]["completed_hand_event_count"] == 2000
    assert summary["early_table_burst"]["hand_event_checksum_root"].startswith("sha256:")


def test_poker_mtt_observability_contract_lists_required_fields():
    assert set(forecast_engine.POKER_MTT_OBSERVABILITY_FIELDS) >= {
        "poker_mtt.hand_ingest.count",
        "poker_mtt.hand_ingest.conflict_count",
        "poker_mtt.hud.project.duration_ms",
        "poker_mtt.reward_window.query.duration_ms",
        "poker_mtt.settlement_anchor.confirmation_state",
        "poker_mtt.reward_window.selected_count",
        "poker_mtt.reward_window.omitted_count",
        "poker_mtt.reward_window.artifact_page_count",
        "poker_mtt.mq.lag",
        "poker_mtt.mq.dlq_count",
    }


def test_non_mock_finish_harness_validates_hard_30_player_finish_gate():
    harness = load_non_mock_harness_module()
    summary = build_finish_summary(player_count=30)

    harness.validate_finish_summary(summary, expected_players=30)


def test_non_mock_finish_harness_rejects_missing_actions_and_pending_players():
    harness = load_non_mock_harness_module()
    summary = build_finish_summary(player_count=30)
    summary["connections"]["users_with_sent_actions"] = 29
    summary["users"][17]["ws"]["sent_actions"] = []
    summary["standings"]["counts"]["alive_count"] = 2
    summary["standings"]["counts"]["died_count"] = 27
    summary["standings"]["counts"]["pending_count"] = 1
    summary["standings"]["standings"][29]["status"] = "pending"

    try:
        harness.validate_finish_summary(summary, expected_players=30)
    except harness.HarnessFailure as exc:
        message = str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected finish summary validation to fail")

    assert "users_with_sent_actions" in message
    assert "alive_count" in message
    assert "pending_count" in message


def test_non_mock_finish_harness_rejects_unexpected_ws_errors():
    harness = load_non_mock_harness_module()
    summary = build_finish_summary(player_count=30)
    summary["connections"]["users_with_ws_errors"] = 1
    summary["users"][5]["ws"]["errors"] = ["recv failed: protocol violation"]

    try:
        harness.validate_finish_summary(summary, expected_players=30)
    except harness.HarnessFailure as exc:
        message = str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected finish summary validation to fail")

    assert "unexpected_ws_errors" in message


def build_finish_summary(*, player_count: int) -> dict:
    standings = [{"status": "alive", "user_id": "0", "member_id": "0:1"}]
    standings.extend(
        {"status": "died", "user_id": str(index), "member_id": f"{index}:1"}
        for index in range(1, player_count)
    )
    return {
        "connections": {
            "joined_users": player_count,
            "received_current_mtt_ranking": player_count,
            "users_with_ws_errors": 0,
            "users_with_sent_actions": player_count,
            "sent_action_total": player_count * 3,
        },
        "finish_mode": {
            "until_finish": True,
            "finished": True,
        },
        "standings": {
            "counts": {
                "snapshot_count": player_count,
                "alive_count": 1,
                "died_count": player_count - 1,
                "pending_count": 0,
                "standings_count": player_count,
            },
            "standings": standings,
        },
        "users": [
            {
                "user_id": str(index),
                "ws": {
                    "received_current_mtt_ranking": True,
                    "sent_actions": [{"action": "check", "chips": 0}],
                    "errors": [],
                },
            }
            for index in range(player_count)
        ],
    }
