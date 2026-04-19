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


def test_choose_supported_chip_can_use_max_legal_chip() -> None:
    module = load_module()
    rng = random.Random(17)

    seen = {
        module.choose_supported_chip([120.0, 180.0, 240.0, 480.0], rng)
        for _ in range(200)
    }

    assert 480.0 in seen


def test_choose_action_plan_can_take_legal_all_in_when_free_to_act() -> None:
    module = load_module()
    supported_actions = [
        {"action": "check"},
        {"action": "bet", "chips": [30.0, 45.0, 60.0, 1000.0]},
        {"action": "allIn"},
    ]

    seen = {
        module.choose_action_plan(supported_actions, random.Random(seed))["action"]
        for seed in range(250)
    }

    assert "allIn" in seen


def test_choose_action_plan_can_fold_when_facing_action() -> None:
    module = load_module()
    supported_actions = [
        {"action": "fold"},
        {"action": "call"},
        {"action": "raise", "chips": [120.0, 240.0, 480.0]},
        {"action": "allIn"},
    ]

    seen = {
        module.choose_action_plan(supported_actions, random.Random(seed))["action"]
        for seed in range(400)
    }

    assert "fold" in seen


def test_choose_action_plan_can_timeout_without_sending() -> None:
    module = load_module()
    supported_actions = [
        {"action": "fold"},
        {"action": "call"},
    ]

    plan = module.choose_action_plan(
        supported_actions,
        random.Random(1),
        timeout_action_rate=1.0,
    )

    assert plan == {"action": "timeout", "chips": 0, "send": False}


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


def test_update_known_position_tracks_own_player_status() -> None:
    module = load_module()

    assert module.update_known_position(
        "12",
        {"playerStatus": [{"userID": "12", "position": 7}]},
        None,
    ) == 7


def test_update_known_position_does_not_clear_on_other_player_status() -> None:
    module = load_module()

    assert module.update_known_position(
        "12",
        {
            "action": "status",
            "playerStatus": [
                {"userID": "28", "position": 1},
                {"userID": "9", "position": 4},
            ],
        },
        7,
    ) == 7


def test_update_known_position_keeps_position_when_payload_has_no_identity() -> None:
    module = load_module()

    assert module.update_known_position(
        "12",
        {"playerStatus": [{"position": 1, "action": "fold"}]},
        7,
    ) == 7


def test_update_known_position_clears_on_server_rejection_msg() -> None:
    module = load_module()

    payload = {
        "action": "Msg",
        "msg": "client is onLooker action:check is not permited",
    }

    assert module.is_server_action_rejection(payload)
    assert module.update_known_position("12", payload, 7) is None


def test_actor_position_prefers_current_payload_position_over_stale_position() -> None:
    module = load_module()

    payload = {
        "action": "readyToAct",
        "currentPosition": 11,
        "nextPlayer": {"position": 1},
    }

    assert module.actor_position_for_payload(payload, known_position=1) == 11
