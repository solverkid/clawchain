#!/usr/bin/env python3
"""
ClawChain Forecast Miner Status
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("❌ Required: pip install requests")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
DATA_DIR = SCRIPT_DIR.parent / "data"
LOG_PATH = DATA_DIR / "mining_log.json"


def load_config():
    if not CONFIG_PATH.exists():
        print(f"❌ Config file not found: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    if "rpc_url" not in config:
        print("❌ 'rpc_url' not set in config.json")
        sys.exit(1)
    return config


def warn_insecure_rpc(url):
    parsed = urlparse(url)
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        print(f"⚠️  SECURITY WARNING: RPC endpoint uses plain HTTP ({url}). Use HTTPS for production.")


def get_miner_status(rpc_url, address):
    resp = requests.get(f"{rpc_url}/v1/miners/{address}/status", timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()["data"]


def get_chain_stats(rpc_url):
    resp = requests.get(f"{rpc_url}/clawchain/stats", timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_local_logs():
    if not LOG_PATH.exists():
        return []
    try:
        with open(LOG_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def build_settlement_status_lines(miner):
    if not miner:
        return [
            "   Released / held:      — / —",
            "   Latest reward window: none",
            "   Latest settlement batch: none",
            "   Latest anchor job:   none",
        ]

    latest_window = miner.get("latest_reward_window") or {}
    latest_batch = miner.get("latest_settlement_batch") or {}
    latest_anchor = miner.get("latest_anchor_job") or {}
    anchor_bits = [latest_anchor.get("id") or "none", latest_anchor.get("state") or "unknown"]
    if latest_anchor.get("broadcast_tx_hash"):
        anchor_bits.append(latest_anchor["broadcast_tx_hash"])

    window_root = latest_window.get("canonical_root") or ""
    batch_root = latest_batch.get("canonical_root") or ""
    return [
        f"   Released / held:      {miner.get('total_rewards', 0)} / {miner.get('held_rewards', 0)}",
        f"   Latest reward window: {latest_window.get('id', 'none')} ({latest_window.get('state', 'unknown')}) {window_root}".rstrip(),
        f"   Latest settlement batch: {latest_batch.get('id', 'none')} ({latest_batch.get('state', 'unknown')}) {batch_root}".rstrip(),
        f"   Latest anchor job:   {' · '.join(anchor_bits)}",
    ]


def main():
    parser = argparse.ArgumentParser(description="ClawChain Forecast Miner Status")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--rpc", default=None, help="RPC URL override")
    parser.add_argument("--logs", type=int, default=10, help="Show last N records")
    args = parser.parse_args()

    config = load_config()
    rpc_url = args.rpc or config["rpc_url"]
    warn_insecure_rpc(rpc_url)
    address = config.get("miner_address", "")
    if not address:
        print("❌ Miner address not configured. Run: python3 skill/scripts/setup.py")
        sys.exit(1)

    miner = get_miner_status(rpc_url, address)
    chain = get_chain_stats(rpc_url)
    logs = get_local_logs()

    if args.json:
        print(json.dumps({"miner": miner, "chain": chain, "recent_logs": logs[-args.logs:]}, indent=2, ensure_ascii=False))
        return

    print("📊 ClawChain Forecast Mining Status")
    print("=" * 44)
    print(f"\n🔗 Miner: {address}")
    if miner:
        print(f"   Rank / ELO:         {miner.get('public_rank')} / {miner.get('public_elo')}")
        print(f"   Total rewards:      {miner.get('total_rewards', 0)}")
        print(f"   Held rewards:       {miner.get('held_rewards', 0)}")
        print(f"   Forecast commits:   {miner.get('forecast_commits', 0)}")
        print(f"   Forecast reveals:   {miner.get('forecast_reveals', 0)}")
        print(f"   Settled tasks:      {miner.get('settled_tasks', 0)}")
        print(f"   Admission state:    {miner.get('admission_state', 'probation')}")
        print(f"   Fast opp / miss:    {miner.get('fast_task_opportunities', 0)} / {miner.get('fast_task_misses', 0)}")
        print(f"   Model reliability:  {miner.get('model_reliability', 1.0)}")
        print(f"   Ops reliability:    {miner.get('ops_reliability', 1.0)}")
        print(f"   Arena multiplier:   {miner.get('arena_multiplier', 1.0)}")
        print(f"   Risk review:        {miner.get('risk_review_state', 'clear')} ({miner.get('open_risk_case_count', 0)})")

        score_explanation = miner.get("score_explanation") or {}
        latest_fast = score_explanation.get("latest_fast")
        latest_daily = score_explanation.get("latest_daily")
        latest_arena = score_explanation.get("latest_arena")
        reward_timeline = miner.get("reward_timeline") or {}

        print("\n🧠 Score Explanation:")
        if latest_fast:
            print(
                f"   Fast:               {latest_fast.get('task_run_id')} "
                f"p={latest_fast.get('p_yes_bps')} baseline={latest_fast.get('baseline_q_bps')} "
                f"outcome={latest_fast.get('outcome')} reward={latest_fast.get('reward_amount')}"
            )
        else:
            print("   Fast:               no resolved forecast yet")
        if latest_daily:
            print(
                f"   Daily:              {latest_daily.get('task_run_id')} "
                f"p={latest_daily.get('p_yes_bps')} outcome={latest_daily.get('outcome')} "
                f"anchor={latest_daily.get('anchor_multiplier')}"
            )
        else:
            print("   Daily:              no resolved daily anchor yet")
        if latest_arena:
            print(
                f"   Arena:              {latest_arena.get('tournament_id')} "
                f"{latest_arena.get('rated_or_practice')} score={latest_arena.get('arena_score')} "
                f"mult={latest_arena.get('arena_multiplier_after')}"
            )
        else:
            print("   Arena:              no arena result yet")

        print("\n⏱️ Reward Timeline:")
        print(f"   Released:           {reward_timeline.get('released_rewards', miner.get('total_rewards', 0))}")
        print(f"   Held:               {reward_timeline.get('held_rewards', miner.get('held_rewards', 0))}")
        print(f"   Open holds:         {reward_timeline.get('open_hold_entry_count', 0)}")
        print(f"   Pending resolve:    {reward_timeline.get('pending_resolution_count', 0)}")
        print(f"   Anti-abuse:         {reward_timeline.get('anti_abuse_discount', miner.get('anti_abuse_discount', 1.0))}")

        print("\n🧾 Settlement:")
        for line in build_settlement_status_lines(miner):
            print(line)
    else:
        print("   ❌ Miner not found")

    print("\n🌐 Network:")
    print(f"   Protocol:           {chain.get('protocol')}")
    print(f"   Active miners:      {chain.get('active_miners', 0)}")
    print(f"   Active fast tasks:  {chain.get('active_fast_tasks', 0)}")
    print(f"   Settled fast tasks: {chain.get('settled_fast_tasks', 0)}")
    print(f"   Total paid:         {chain.get('total_rewards_paid', 0)}")

    recent = logs[-args.logs:] if logs else []
    print(f"\n📝 Last {len(recent)} local records:")
    if not recent:
        print("   No records yet")
    else:
        for idx, item in enumerate(recent, start=1):
            print(
                f"   {idx}. [{item.get('timestamp', '')[:19]}] "
                f"{item.get('task_run_id', '?')} -> {item.get('p_yes_bps', '?')} "
                f"({item.get('reward_eligibility', '?')})"
            )


if __name__ == "__main__":
    main()
