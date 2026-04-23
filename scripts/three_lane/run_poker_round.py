#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import requests

from common import (
    DEFAULT_BUILD_DIR,
    DEFAULT_MANIFEST_PATH,
    append_jsonl,
    hash_payload,
    isoformat_z,
    load_manifest,
    register_manifest_miners,
    utc_now,
    write_status,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project and settle one Poker MTT round for the shared 33-miner manifest.")
    parser.add_argument("--base-url", default="http://127.0.0.1:1317")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--lane", default="poker_mtt_daily")
    parser.add_argument("--reward-pool-amount", type=int, default=3300)
    parser.add_argument("--policy-bundle-version", default="poker_mtt_v1")
    parser.add_argument("--reward-window-policy-version", default="poker_mtt_daily_policy_v1")
    parser.add_argument("--tournament-id")
    parser.add_argument("--request-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--log-file", type=Path, default=DEFAULT_BUILD_DIR / "poker-round.jsonl")
    return parser.parse_args()


def _post_json(base_url: str, path: str, payload: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
    response = requests.post(f"{base_url}{path}", json=payload, timeout=timeout_seconds)
    if response.status_code >= 400:
        raise RuntimeError(f"{path} failed {response.status_code}: {response.text}")
    return response.json()


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.manifest)
    register_manifest_miners(
        base_url=args.base_url,
        manifest=manifest,
        log_path=args.log_file,
        manifest_path=args.manifest,
    )

    locked_at = utc_now().replace(microsecond=0)
    tournament_id = args.tournament_id or f"local-poker-{locked_at.strftime('%Y%m%d%H%M%S')}"
    source_mtt_id = tournament_id
    standing_snapshot_id = f"standing:{tournament_id}"

    rows: list[dict[str, Any]] = []
    hidden_eval_entries: list[dict[str, Any]] = []
    ranking_root_input: list[dict[str, Any]] = []
    for rank, miner in enumerate(manifest["miners"], start=1):
        final_ranking_id = f"poker_final:{tournament_id}:{miner['address']}"
        evidence_root = hash_payload(
            {
                "tournament_id": tournament_id,
                "miner_address": miner["address"],
                "rank": rank,
            }
        )
        row = {
            "id": final_ranking_id,
            "tournament_id": tournament_id,
            "source_mtt_id": source_mtt_id,
            "source_user_id": miner["address"],
            "miner_address": miner["address"],
            "economic_unit_id": miner["economic_unit_id"],
            "member_id": f"{miner['address']}:1",
            "entry_number": 1,
            "reentry_count": 1,
            "rank": rank,
            "display_rank": rank,
            "rank_state": "ranked",
            "rank_basis": "local_acceptance_harness",
            "rank_tiebreaker": "index",
            "chip": float(max(0, 100000 - (rank * 1000))),
            "chip_delta": float(33 - rank),
            "died_time": isoformat_z(locked_at + timedelta(seconds=rank)),
            "waiting_or_no_show": False,
            "bounty": 0.0,
            "defeat_num": 0,
            "field_size_policy": "exclude_waiting_no_show_from_reward_field_size",
            "standing_snapshot_id": standing_snapshot_id,
            "standing_snapshot_hash": "",
            "evidence_root": evidence_root,
            "evidence_state": "complete",
            "policy_bundle_version": args.policy_bundle_version,
            "snapshot_found": True,
            "status": "completed",
            "player_name": miner["name"],
            "room_id": f"table-{((rank - 1) // 8) + 1:02d}",
            "start_chip": 100000.0,
            "stand_up_status": None,
            "source_rank": str(rank),
            "source_rank_numeric": True,
            "zset_score": None,
            "locked_at": isoformat_z(locked_at),
            "anchorable_at": isoformat_z(locked_at),
            "created_at": isoformat_z(locked_at),
            "updated_at": isoformat_z(locked_at),
        }
        rows.append(row)
        ranking_root_input.append(
            {
                "id": row["id"],
                "miner_address": row["miner_address"],
                "rank": row["rank"],
                "economic_unit_id": row["economic_unit_id"],
            }
        )
        hidden_eval_entries.append(
            {
                "miner_address": miner["address"],
                "final_ranking_id": final_ranking_id,
                "hidden_eval_score": round(max(-1.0, 0.35 - (rank * 0.01)), 4),
                "score_components_json": {
                    "local_acceptance_score": round(max(-1.0, 0.35 - (rank * 0.01)), 4),
                },
                "evidence_root": evidence_root,
            }
        )

    standing_snapshot_hash = hash_payload(ranking_root_input)
    for row in rows:
        row["standing_snapshot_hash"] = standing_snapshot_hash
    final_ranking_root = hash_payload(ranking_root_input)

    hidden_eval_payload = {
        "tournament_id": tournament_id,
        "policy_bundle_version": args.policy_bundle_version,
        "seed_assignment_id": f"seed:{tournament_id}",
        "baseline_sample_id": None,
        "entries": hidden_eval_entries,
    }
    hidden_eval_result = _post_json(
        args.base_url,
        "/admin/poker-mtt/hidden-eval/finalize",
        hidden_eval_payload,
        timeout_seconds=args.request_timeout_seconds,
    )
    append_jsonl(args.log_file, {"at": isoformat_z(utc_now()), "event": "hidden_eval_finalized", "tournament_id": tournament_id, "result": hidden_eval_result})

    projection_payload = {
        "schema_version": "clawchain.poker_mtt_final_ranking_projection.v1",
        "projection_id": f"projection:{tournament_id}",
        "tournament_id": tournament_id,
        "source_mtt_id": source_mtt_id,
        "rated_or_practice": "rated",
        "human_only": True,
        "field_size": manifest["count"],
        "policy_bundle_version": args.policy_bundle_version,
        "standing_snapshot_id": standing_snapshot_id,
        "standing_snapshot_hash": standing_snapshot_hash,
        "final_ranking_root": final_ranking_root,
        "locked_at": isoformat_z(locked_at),
        "rows": rows,
    }
    projection_result = _post_json(
        args.base_url,
        "/admin/poker-mtt/final-rankings/project",
        projection_payload,
        timeout_seconds=args.request_timeout_seconds,
    )
    append_jsonl(args.log_file, {"at": isoformat_z(utc_now()), "event": "final_rankings_projected", "tournament_id": tournament_id, "projection_id": projection_payload["projection_id"]})

    reward_window_payload = {
        "lane": args.lane,
        "window_start_at": isoformat_z(locked_at - timedelta(minutes=5)),
        "window_end_at": isoformat_z(locked_at + timedelta(minutes=5)),
        "reward_pool_amount": args.reward_pool_amount,
        "include_provisional": False,
        "policy_bundle_version": args.reward_window_policy_version,
        "reward_window_id": f"rw:{args.lane}:{tournament_id}",
    }
    reward_window = _post_json(
        args.base_url,
        "/admin/poker-mtt/reward-windows/build",
        reward_window_payload,
        timeout_seconds=args.request_timeout_seconds,
    )
    append_jsonl(
        args.log_file,
        {
            "at": isoformat_z(utc_now()),
            "event": "reward_window_built",
            "tournament_id": tournament_id,
            "reward_window_id": reward_window["id"],
            "settlement_batch_id": reward_window.get("settlement_batch_id"),
            "miner_count": reward_window.get("miner_count"),
            "total_reward_amount": reward_window.get("total_reward_amount"),
        },
    )

    summary = {
        "updated_at": isoformat_z(utc_now()),
        "lane": args.lane,
        "tournament_id": tournament_id,
        "manifest_path": str(args.manifest),
        "log_file": str(args.log_file),
        "projection_id": projection_payload["projection_id"],
        "reward_window_id": reward_window["id"],
        "settlement_batch_id": reward_window.get("settlement_batch_id"),
        "miner_count": reward_window.get("miner_count"),
        "total_reward_amount": reward_window.get("total_reward_amount"),
        "eligible_for_multiplier_count": sum(
            1 for item in projection_result.get("items", []) if item.get("eligible_for_multiplier") is True
        ),
    }
    write_status(DEFAULT_BUILD_DIR / "poker-round.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
