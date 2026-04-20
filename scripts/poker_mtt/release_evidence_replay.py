from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
SCRIPT_DIR = ROOT / "scripts" / "poker_mtt"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import forecast_engine
import runtime_projection as runtime
from repository import FakeRepository


DEFAULT_RUNTIME_SOURCE = runtime.DEFAULT_RUNTIME_SOURCE
DEFAULT_FINAL_RANKING_SOURCE = runtime.DEFAULT_FINAL_RANKING_SOURCE
DEFAULT_POLICY_BUNDLE_VERSION = runtime.DEFAULT_POLICY_BUNDLE_VERSION
DEFAULT_DAILY_POLICY_VERSION = runtime.DEFAULT_DAILY_POLICY_VERSION
DEFAULT_WEEKLY_POLICY_VERSION = runtime.DEFAULT_WEEKLY_POLICY_VERSION
build_apply_payload = runtime.build_apply_payload
derive_reward_window_bounds = runtime.derive_reward_window_bounds
derive_reward_window_policy_version = runtime.derive_reward_window_policy_version


class FrozenClock:
    def __init__(self, current: datetime):
        self.current = current

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay a donor non-mock runtime sample through the ClawChain poker MTT release chain.",
    )
    parser.add_argument("--summary", type=Path, required=True, help="Path to the runtime summary JSON.")
    parser.add_argument("--evidence", type=Path, required=True, help="Path to the runtime evidence JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Path to write the release-evidence JSON.")
    parser.add_argument("--lane", choices=("poker_mtt_daily", "poker_mtt_weekly"), default="poker_mtt_daily")
    parser.add_argument("--reward-pool-amount", type=int, default=1000)
    parser.add_argument("--started-minutes-before-lock", type=int, default=45)
    parser.add_argument("--late-join-grace-seconds", type=int, default=600)
    parser.add_argument("--runtime-source", default=DEFAULT_RUNTIME_SOURCE)
    parser.add_argument("--final-ranking-source", default=DEFAULT_FINAL_RANKING_SOURCE)
    parser.add_argument("--policy-bundle-version", default=DEFAULT_POLICY_BUNDLE_VERSION)
    parser.add_argument(
        "--reward-window-policy-version",
        default=None,
        help="Reward window policy version. Defaults to the lane-specific Phase 3 policy bundle.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


async def execute_release_chain(
    *,
    summary: dict[str, Any],
    evidence: dict[str, Any],
    apply_payload: dict[str, Any],
    wallet_bindings: dict[str, dict[str, str]],
    replay_notes: dict[str, Any],
    locked_at: datetime,
    lane: str,
    reward_pool_amount: int,
    reward_window_policy_version: str,
    hand_history_evidence_root: str | None,
    consumer_checkpoint_root: str | None,
    summary_path: Path | None = None,
    evidence_path: Path | None = None,
    tx_hash_prefix: str = "TYPED-",
    repo: FakeRepository | None = None,
    service=None,  # noqa: ANN001
    clock: FrozenClock | None = None,
) -> dict[str, Any]:
    window_start_at, window_end_at = runtime.derive_reward_window_bounds(lane, locked_at)
    if clock is None:
        clock = FrozenClock(locked_at)
    elif clock.now() < locked_at:
        clock.current = locked_at
    if repo is None:
        repo = FakeRepository()
    if service is None:
        async def fake_typed_broadcaster(plan, now):  # noqa: ANN001
            return {
                "tx_hash": tx_hash_prefix + summary["mtt_id"],
                "code": 0,
                "raw_log": "",
                "memo": plan["fallback_memo"],
                "broadcast_at": forecast_engine.isoformat_z(now),
                "account_number": 0,
                "sequence": 1,
                "attempt_count": 1,
                "broadcast_method": "typed_msg",
            }

        async def fake_confirmer(tx_hash, now):  # noqa: ANN001
            return {
                "tx_hash": tx_hash,
                "found": True,
                "confirmed": True,
                "confirmation_status": "confirmed",
                "height": 987654,
                "code": 0,
                "raw_log": "",
            }

        service = forecast_engine.ForecastMiningService(
            repo,
            forecast_engine.ForecastSettings(
                poker_mtt_reward_windows_enabled=True,
                poker_mtt_settlement_anchoring_enabled=True,
                poker_mtt_daily_reward_pool_amount=reward_pool_amount,
                poker_mtt_weekly_reward_pool_amount=reward_pool_amount,
            ),
            chain_typed_broadcaster=fake_typed_broadcaster,
            chain_tx_confirmer=fake_confirmer,
        )

    for source_user_id, wallet in sorted(wallet_bindings.items(), key=lambda item: int(item[0])):
        await service.register_miner(
            address=wallet["address"],
            name=f"poker-mtt-{source_user_id}",
            public_key=wallet["public_key"],
            miner_version="0.4.0",
        )

    projection_rows, final_ranking_root = runtime.build_projection_rows(apply_payload, locked_at=locked_at)
    hidden_eval_entries = runtime.build_hidden_eval_entries(
        projection_rows,
        tournament_id=summary["mtt_id"],
        policy_bundle_version=apply_payload["policy_bundle_version"],
    )
    if hidden_eval_entries:
        await service.finalize_poker_mtt_hidden_eval(
            tournament_id=summary["mtt_id"],
            policy_bundle_version=apply_payload["policy_bundle_version"],
            seed_assignment_id=f"hidden-seed:{summary['mtt_id']}",
            baseline_sample_id=None,
            entries=hidden_eval_entries,
            now=locked_at,
        )

    for row in projection_rows:
        await repo.save_poker_mtt_final_ranking(row)

    project_response = await service.project_poker_mtt_final_rankings(
        tournament_id=apply_payload["tournament_id"],
        rated_or_practice=apply_payload["rated_or_practice"],
        human_only=apply_payload["human_only"],
        field_size=apply_payload["field_size"],
        policy_bundle_version=apply_payload["policy_bundle_version"],
        locked_at=locked_at,
    )

    clock.advance(1)
    reward_window_response = await service.build_poker_mtt_reward_window(
        lane=lane,
        window_start_at=window_start_at,
        window_end_at=window_end_at,
        reward_pool_amount=reward_pool_amount,
        include_provisional=False,
        policy_bundle_version=reward_window_policy_version,
        projection_metadata={
            "hand_history_evidence_root": hand_history_evidence_root,
            "consumer_checkpoint_root": consumer_checkpoint_root,
        },
        now=clock.now(),
    )
    settlement_batch = await repo.get_settlement_batch(reward_window_response["settlement_batch_id"])
    if settlement_batch is None:
        raise ValueError("settlement batch missing after reward window build")

    clock.advance(1)
    anchor_ready_response = await service.retry_anchor_settlement_batch(settlement_batch["id"], now=clock.now())
    clock.advance(1)
    submit_response = await service.submit_anchor_job(settlement_batch["id"], now=clock.now())
    anchor_job_id = submit_response.get("anchor_job_id")
    if not anchor_job_id:
        raise ValueError("anchor job id missing after submit")
    chain_tx_plan = await service.build_chain_tx_plan(anchor_job_id, now=clock.now())
    clock.advance(1)
    broadcast_response = await service.broadcast_chain_tx_typed(anchor_job_id, now=clock.now())
    clock.advance(1)
    confirm_response = await service.confirm_anchor_job_on_chain(anchor_job_id, now=clock.now())

    settlement_batch_after_confirm = await repo.get_settlement_batch(settlement_batch["id"])
    anchor_job_after_confirm = await repo.get_anchor_job(anchor_job_id)
    reward_window_artifacts = await repo.list_artifacts_for_entity("reward_window", reward_window_response["id"])
    anchor_job_artifacts = await repo.list_artifacts_for_entity("anchor_job", anchor_job_id)
    settlement_artifacts = await repo.list_artifacts_for_entity("settlement_batch", settlement_batch["id"])
    projection_artifact = next(
        (artifact for artifact in reward_window_artifacts if artifact.get("kind") == "poker_mtt_reward_window_projection"),
        None,
    )
    membership_artifact = next(
        (artifact for artifact in reward_window_artifacts if artifact.get("kind") == "reward_window_membership"),
        None,
    )
    settlement_anchor_artifact = next(
        (artifact for artifact in settlement_artifacts if artifact.get("kind") == "settlement_anchor_payload"),
        None,
    )
    confirmation_receipt_artifact = next(
        (artifact for artifact in anchor_job_artifacts if artifact.get("kind") == "chain_confirmation_receipt"),
        None,
    )

    ranked_projection_rows = [row for row in projection_rows if row.get("rank") is not None]
    ranked_projection_rows.sort(key=lambda row: int(row["rank"]))
    project_items = list(project_response["items"])
    eligible_count = sum(1 for item in project_items if item.get("eligible_for_multiplier") is True)

    return {
        "captured_at": forecast_engine.isoformat_z(clock.now()),
        "source_runtime_summary": summary["mtt_id"],
        "input_paths": {
            "summary_artifact": str(summary_path) if summary_path else evidence.get("summary_artifact"),
            "runtime_evidence_artifact": str(evidence_path) if evidence_path else None,
        },
        "replay_notes": replay_notes,
        "runtime_sample": {
            "tournament_id": summary["mtt_id"],
            "field_size": len(summary["standings"]["standings"]),
            "winner": evidence.get("final_standings", {}).get("winner"),
            "runner_up": evidence.get("final_standings", {}).get("runner_up"),
            "joined_users": evidence.get("connections", {}).get("joined_users"),
            "sent_action_total": evidence.get("connections", {}).get("sent_action_total"),
            "timeout_no_action_total": evidence.get("connections", {}).get("timeout_no_action_total"),
        },
        "wallet_bindings": [
            {
                "source_user_id": source_user_id,
                "miner_address": wallet["address"],
                "economic_unit_id": f"eu:poker-mtt:{summary['mtt_id']}:{source_user_id}",
            }
            for source_user_id, wallet in sorted(wallet_bindings.items(), key=lambda item: int(item[0]))
        ],
        "apply": {
            "status_code": 200,
            "item_count": len(apply_payload["results"]),
            "results_preview": apply_payload["results"][:3],
        },
        "finalize": {
            "status_code": 200,
            "item_count": len(project_items),
            "eligible_count": eligible_count,
            "locked_at": forecast_engine.isoformat_z(locked_at),
            "final_ranking_root": final_ranking_root,
            "hand_history_evidence_root": hand_history_evidence_root,
            "consumer_checkpoint_root": consumer_checkpoint_root,
            "payout_rank_unique": len({row["rank"] for row in ranked_projection_rows}) == len(ranked_projection_rows),
            "top_three": [
                {
                    "source_user_id": row.get("source_user_id"),
                    "canonical_entry_id": row.get("member_id"),
                    "payout_rank": row.get("rank"),
                    "eligibility_state": "eligible" if row.get("rank") is not None else "excluded",
                }
                for row in ranked_projection_rows[:3]
            ],
        },
        "reward_window": {
            "status_code": 200,
            "id": reward_window_response["id"],
            "lane": reward_window_response["lane"],
            "state": reward_window_response["state"],
            "task_run_ids": reward_window_response["task_run_ids"],
            "miner_count": reward_window_response["miner_count"],
            "submission_count": reward_window_response["submission_count"],
            "total_reward_amount": reward_window_response["total_reward_amount"],
            "policy_bundle_version": reward_window_response["policy_bundle_version"],
            "canonical_root": reward_window_response["canonical_root"],
        },
        "settlement_batch": {
            "id": settlement_batch_after_confirm["id"] if settlement_batch_after_confirm else settlement_batch["id"],
            "state": settlement_batch_after_confirm["state"] if settlement_batch_after_confirm else None,
            "chain_confirmation_state": (
                (
                    settlement_batch_after_confirm.get("chain_confirmation_state")
                    or settlement_batch_after_confirm.get("chain_confirmation_status")
                    or (confirm_response.get("chain_confirmation_status") if anchor_job_after_confirm else None)
                )
                if settlement_batch_after_confirm
                else None
            ),
            "anchor_payload_hash": settlement_batch_after_confirm.get("anchor_payload_hash")
            if settlement_batch_after_confirm
            else None,
            "canonical_root": settlement_batch_after_confirm.get("canonical_root") if settlement_batch_after_confirm else None,
            "total_reward_amount": settlement_batch_after_confirm.get("total_reward_amount")
            if settlement_batch_after_confirm
            else None,
        },
        "anchor_job": {
            "id": anchor_job_after_confirm["id"] if anchor_job_after_confirm else anchor_job_id,
            "state": anchor_job_after_confirm["state"] if anchor_job_after_confirm else None,
            "broadcast_status": broadcast_response["broadcast_status"],
            "tx_hash": broadcast_response["tx_hash"],
            "chain_confirmation_status": confirm_response["chain_confirmation_status"],
            "chain_height": confirm_response["chain_height"],
            "anchored_at": confirm_response["anchored_at"],
        },
        "chain_tx_plan": {
            "settlement_batch_id": chain_tx_plan["future_msg"]["value"]["settlement_batch_id"],
            "canonical_root": chain_tx_plan["future_msg"]["value"]["canonical_root"],
            "anchor_payload_hash": chain_tx_plan["future_msg"]["value"]["anchor_payload_hash"],
            "total_reward_amount": chain_tx_plan["future_msg"]["value"]["total_reward_amount"],
        },
        "artifacts": {
            "final_ranking_payload_hash": final_ranking_root,
            "reward_window_membership_payload_hash": membership_artifact["payload_hash"] if membership_artifact else None,
            "reward_window_projection_payload_hash": projection_artifact["payload_hash"] if projection_artifact else None,
            "settlement_anchor_payload_hash": settlement_anchor_artifact["payload_hash"]
            if settlement_anchor_artifact
            else None,
            "confirmation_receipt_payload_hash": confirmation_receipt_artifact["payload_hash"]
            if confirmation_receipt_artifact
            else None,
        },
        "gate_status": {
            "locked_ranking_complete": eligible_count == len(project_items),
            "reward_window_finalized": reward_window_response["state"] == "finalized",
            "query_confirmed_settlement": confirm_response["chain_confirmation_status"] == "confirmed"
            and anchor_job_after_confirm is not None
            and anchor_job_after_confirm.get("state") == "anchored",
            "release_proof_complete": reward_window_response["state"] == "finalized"
            and confirm_response["chain_confirmation_status"] == "confirmed"
            and anchor_job_after_confirm is not None
            and anchor_job_after_confirm.get("state") == "anchored",
        },
    }


def run_release_evidence(
    summary: dict[str, Any],
    evidence: dict[str, Any],
    *,
    summary_path: Path | None = None,
    evidence_path: Path | None = None,
    lane: str = "poker_mtt_daily",
    reward_pool_amount: int = 1000,
    started_minutes_before_lock: int = 45,
    late_join_grace_seconds: int = 600,
    runtime_source: str = DEFAULT_RUNTIME_SOURCE,
    final_ranking_source: str = DEFAULT_FINAL_RANKING_SOURCE,
    policy_bundle_version: str = DEFAULT_POLICY_BUNDLE_VERSION,
    reward_window_policy_version: str | None = None,
) -> dict[str, Any]:
    locked_at = runtime.parse_iso_datetime(evidence["captured_at"])
    if locked_at is None:
        raise ValueError("captured_at is required")
    locked_at = locked_at.replace(microsecond=0)
    resolved_reward_window_policy_version = runtime.derive_reward_window_policy_version(lane, reward_window_policy_version)
    apply_payload, wallet_bindings, replay_notes = runtime.build_apply_payload(
        summary,
        evidence,
        locked_at=locked_at,
        started_minutes_before_lock=started_minutes_before_lock,
        late_join_grace_seconds=late_join_grace_seconds,
        runtime_source=runtime_source,
        final_ranking_source=final_ranking_source,
        policy_bundle_version=policy_bundle_version,
    )
    return asyncio.run(
        execute_release_chain(
            summary=summary,
            evidence=evidence,
            apply_payload=apply_payload,
            wallet_bindings=wallet_bindings,
            replay_notes=replay_notes,
            locked_at=locked_at,
            lane=lane,
            reward_pool_amount=reward_pool_amount,
            reward_window_policy_version=resolved_reward_window_policy_version,
            hand_history_evidence_root=replay_notes["hand_history_evidence_root"],
            consumer_checkpoint_root=replay_notes["consumer_checkpoint_root"],
            summary_path=summary_path,
            evidence_path=evidence_path,
        )
    )


def main() -> int:
    args = parse_args()
    summary = load_json(args.summary)
    evidence = load_json(args.evidence)
    output = run_release_evidence(
        summary,
        evidence,
        summary_path=args.summary,
        evidence_path=args.evidence,
        lane=args.lane,
        reward_pool_amount=args.reward_pool_amount,
        started_minutes_before_lock=args.started_minutes_before_lock,
        late_join_grace_seconds=args.late_join_grace_seconds,
        runtime_source=args.runtime_source,
        final_ranking_source=args.final_ranking_source,
        policy_bundle_version=args.policy_bundle_version,
        reward_window_policy_version=args.reward_window_policy_version,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
