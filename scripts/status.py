#!/usr/bin/env python3
"""
ClawChain Status Script
Shows miner status, balance, and chain statistics.
"""

import json
import os
import sys

CLAWCHAIN_DIR = os.path.expanduser("~/.clawchain")
WALLET_FILE = os.path.join(CLAWCHAIN_DIR, "wallet.json")
CONFIG_FILE = os.path.join(CLAWCHAIN_DIR, "config.json")
LOG_FILE = os.path.join(CLAWCHAIN_DIR, "mining_log.json")


def main():
    # Parse args
    show_chain = "--chain" in sys.argv
    show_json = "--json" in sys.argv

    if not os.path.exists(WALLET_FILE):
        print("❌ Wallet not found. Run: python3 scripts/setup.py")
        sys.exit(1)

    with open(WALLET_FILE) as f:
        wallet = json.load(f)

    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            config = json.load(f)

    rpc = config.get("rpc_url", "http://localhost:1317")
    address = wallet["address"]

    # Local stats from mining log
    log = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE) as f:
                log = json.load(f)
        except:
            log = []

    submitted = [e for e in log if e.get("status") == "submitted"]
    total_tasks = len(submitted)

    if show_json:
        result = {
            "address": address,
            "rpc": rpc,
            "local_tasks_completed": total_tasks,
        }

        # Try chain query
        try:
            import requests
            resp = requests.get(f"{rpc}/clawchain/miner/{address}", timeout=5)
            if resp.status_code == 200:
                result["chain_data"] = resp.json()
        except:
            result["chain_data"] = None

        if show_chain:
            try:
                import requests
                resp = requests.get(f"{rpc}/clawchain/stats", timeout=5)
                if resp.status_code == 200:
                    result["chain_stats"] = resp.json()
            except:
                result["chain_stats"] = None

        print(json.dumps(result, indent=2))
        return

    # Human-readable output
    print("🦞 ClawChain Miner Status")
    print("=" * 40)
    print(f"  Address:     {address}")
    print(f"  Node:        {rpc}")
    print(f"  Local tasks: {total_tasks} completed")
    print()

    # Try chain query
    try:
        import requests
        resp = requests.get(f"{rpc}/clawchain/miner/{address}", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            miner = data.get("miner", data)
            print("📊 On-Chain Data:")
            print(f"  Status:      {miner.get('status', 'unknown')}")
            print(f"  Reputation:  {miner.get('reputation', 'N/A')}")
            print(f"  Challenges:  {miner.get('challenges_completed', 0)}")
            print(f"  Rewards:     {miner.get('total_rewards', 0)} uclaw")
            print()
        else:
            print(f"⚠️  Cannot fetch miner data (HTTP {resp.status_code})")
            print()
    except Exception as e:
        print(f"⚠️  Cannot connect to chain: {e}")
        print()

    if show_chain:
        try:
            import requests
            resp = requests.get(f"{rpc}/clawchain/stats", timeout=5)
            if resp.status_code == 200:
                stats = resp.json()
                print("🔗 Chain Statistics:")
                for k, v in stats.items():
                    print(f"  {k}: {v}")
                print()
        except Exception as e:
            print(f"⚠️  Cannot fetch chain stats: {e}")


if __name__ == "__main__":
    main()
