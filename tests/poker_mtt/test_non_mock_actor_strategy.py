from __future__ import annotations

import importlib.util
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "poker_mtt" / "non_mock_play_harness.py"


def load_module():
    spec = importlib.util.spec_from_file_location("non_mock_play_harness", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_choose_action_plan_uses_supported_chips() -> None:
    module = load_module()
    rng = random.Random(7)
    supported_actions = [
        {"action": "fold"},
        {"action": "call", "chips": [60.0]},
        {"action": "raise", "chips": [120.0, 180.0, 240.0, 480.0], "currentCallChips": 60.0},
    ]

    plan = module.choose_action_plan(supported_actions, rng)

    assert plan["action"] in {"call", "raise", "fold"}
    if plan["action"] == "raise":
        assert plan["chips"] in {120.0, 180.0, 240.0, 480.0}
    elif plan["action"] == "call":
        assert plan["chips"] == 0
    else:
        assert plan["chips"] == 0


def test_choose_action_plan_prefers_check_over_fold_when_free() -> None:
    module = load_module()
    rng = random.Random(11)
    supported_actions = [
        {"action": "fold"},
        {"action": "check"},
        {"action": "bet", "chips": [30.0, 45.0, 60.0]},
    ]

    plan = module.choose_action_plan(supported_actions, rng)

    assert plan["action"] != "fold"
    if plan["action"] == "bet":
        assert plan["chips"] in {30.0, 45.0, 60.0}
    else:
        assert plan["action"] == "check"
        assert plan["chips"] == 0


def test_is_tournament_finished_requires_single_alive_and_no_pending() -> None:
    module = load_module()

    assert module.is_tournament_finished(
        {
            "counts": {
                "snapshot_count": 30,
                "alive_count": 1,
                "pending_count": 0,
            }
        },
        expected_players=30,
    )
    assert module.is_tournament_finished(
        {
            "counts": {
                "snapshot_count": 30,
                "alive_count": 0,
                "pending_count": 0,
            }
        },
        expected_players=30,
    )


def test_is_tournament_finished_rejects_incomplete_states() -> None:
    module = load_module()

    assert not module.is_tournament_finished(
        {
            "counts": {
                "snapshot_count": 29,
                "alive_count": 1,
                "pending_count": 0,
            }
        },
        expected_players=30,
    )
    assert not module.is_tournament_finished(
        {
            "counts": {
                "snapshot_count": 30,
                "alive_count": 2,
                "pending_count": 0,
            }
        },
        expected_players=30,
    )
    assert not module.is_tournament_finished(
        {
            "counts": {
                "snapshot_count": 30,
                "alive_count": 1,
                "pending_count": 1,
            }
        },
        expected_players=30,
    )
