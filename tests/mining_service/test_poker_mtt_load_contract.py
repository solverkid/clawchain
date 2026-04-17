from __future__ import annotations

import sys
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine


GENERATOR = ROOT / "scripts" / "poker_mtt" / "generate_hand_history_load.py"


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


def test_poker_mtt_observability_contract_lists_required_fields():
    assert set(forecast_engine.POKER_MTT_OBSERVABILITY_FIELDS) >= {
        "poker_mtt.hand_ingest.count",
        "poker_mtt.hand_ingest.conflict_count",
        "poker_mtt.hud.project.duration_ms",
        "poker_mtt.reward_window.query.duration_ms",
        "poker_mtt.settlement_anchor.confirmation_state",
    }
