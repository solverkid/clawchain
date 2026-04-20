from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "poker_mtt"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import runtime_projection


def test_runtime_projection_excludes_waiting_no_show_cancelled_and_failed_start():
    started_at = datetime(2026, 4, 20, 8, 0, 0, tzinfo=timezone.utc)

    waiting = runtime_projection.evaluate_runtime_entry(
        {"status": "waiting", "waiting_or_no_show": True},
        started_at=started_at,
        late_join_grace_seconds=600,
    )
    cancelled = runtime_projection.evaluate_runtime_entry(
        {"entry_state": "cancelled"},
        started_at=started_at,
        late_join_grace_seconds=600,
    )
    failed = runtime_projection.evaluate_runtime_entry(
        {"entry_state": "failed_to_start"},
        started_at=started_at,
        late_join_grace_seconds=600,
    )

    assert waiting["eligibility_state"] == "excluded"
    assert waiting["exclusion_reason"] == "waiting_or_no_show"
    assert waiting["rank_state"] == "waiting_or_no_show"

    assert cancelled["eligibility_state"] == "excluded"
    assert cancelled["exclusion_reason"] == "cancelled"
    assert cancelled["rank_state"] == "cancelled"

    assert failed["eligibility_state"] == "excluded"
    assert failed["exclusion_reason"] == "failed_to_start"
    assert failed["rank_state"] == "failed_to_start"


def test_runtime_projection_excludes_late_join_after_grace_window():
    started_at = datetime(2026, 4, 20, 8, 0, 0, tzinfo=timezone.utc)

    ontime = runtime_projection.evaluate_runtime_entry(
        {"joined_at": "2026-04-20T08:09:59Z"},
        started_at=started_at,
        late_join_grace_seconds=600,
    )
    late = runtime_projection.evaluate_runtime_entry(
        {"joined_at": "2026-04-20T08:10:01Z"},
        started_at=started_at,
        late_join_grace_seconds=600,
    )

    assert ontime["eligibility_state"] == "eligible"
    assert ontime["exclusion_reason"] is None
    assert ontime["rank_state"] == "ranked"

    assert late["eligibility_state"] == "excluded"
    assert late["exclusion_reason"] == "late_join_after_grace_window"
    assert late["rank_state"] == "late_join_after_grace_window"


def test_build_projection_rows_marks_excluded_entries_as_non_ranked():
    locked_at = datetime(2026, 4, 20, 8, 15, 34, tzinfo=timezone.utc)
    summary = {
        "mtt_id": "guarded-runtime",
        "standings": {
            "standings": [
                {
                    "member_id": "ontime:1",
                    "user_id": "1",
                    "entry_number": 1,
                    "display_rank": 1,
                    "payout_rank": 1,
                    "joined_at": "2026-04-20T08:09:59Z",
                },
                {
                    "member_id": "late:1",
                    "user_id": "2",
                    "entry_number": 1,
                    "display_rank": 2,
                    "payout_rank": 2,
                    "joined_at": "2026-04-20T08:10:35Z",
                },
            ]
        },
    }
    evidence = {
        "captured_at": "2026-04-20T08:15:34Z",
        "mtt_id": "guarded-runtime",
        "connections": {"joined_users": 2},
        "room_assignments": {},
        "final_standings": {},
        "log_truth": {},
    }

    payload, _, _ = runtime_projection.build_apply_payload(
        summary,
        evidence,
        locked_at=locked_at,
        started_minutes_before_lock=15,
        late_join_grace_seconds=600,
        runtime_source="lepoker_gameserver",
        final_ranking_source="donor_redis_rankings",
        policy_bundle_version="poker_mtt_v1",
    )
    projection_rows, _ = runtime_projection.build_projection_rows(payload, locked_at=locked_at)
    rows_by_member_id = {row["member_id"]: row for row in projection_rows}

    assert rows_by_member_id["ontime:1"]["rank"] == 1
    assert rows_by_member_id["ontime:1"]["rank_state"] == "ranked"
    assert rows_by_member_id["ontime:1"]["evidence_state"] == "complete"

    assert rows_by_member_id["late:1"]["rank"] is None
    assert rows_by_member_id["late:1"]["rank_state"] == "late_join_after_grace_window"
    assert rows_by_member_id["late:1"]["evidence_state"] == "pending"
