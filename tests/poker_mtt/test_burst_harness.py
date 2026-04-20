from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "poker_mtt" / "burst_harness.py"


def load_module():
    spec = importlib.util.spec_from_file_location("burst_harness", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_burst_messages_counts_completed_hand_and_standup_events() -> None:
    module = load_module()

    messages = module.build_burst_messages(table_count=3, hands_per_table=2)

    topics = [topic for topic, _ in messages]
    assert topics.count("POKER_RECORD_TOPIC") == 6
    assert topics.count("POKER_RECORD_STANDUP_TOPIC") == 3


def test_run_burst_harness_returns_checkpoint_and_reward_metrics() -> None:
    module = load_module()

    summary = asyncio.run(
        module.run_burst_harness(
            tournament_id="burst-test-1",
            user_count=20,
            table_count=2,
            hands_per_table=2,
            event_batch_size=2,
            reward_pool_amount=100,
        )
    )

    assert summary["events"]["completed_hand_processed"] == 4
    assert summary["events"]["standup_processed"] == 2
    assert summary["mq_metrics"]["lag_high_water_mark"] >= 2
    assert summary["dlq_total"] == 0
    assert summary["conflict_total"] == 0
    assert summary["finalize"]["item_count"] == 20
    assert summary["reward_window"]["submission_count"] == 20
    assert summary["reward_window"]["total_reward_amount"] == 100
    assert summary["anchor"]["consumer_checkpoint_root"].startswith("sha256:")
