#!/usr/bin/env python3
"""
ClawChain Settlement Verification Tool

Fetches epoch settlement data from the mining service API,
recomputes the settlement root, and compares it against the
anchored value (on-chain or local).

Usage:
    python3 scripts/verify_settlement.py --epoch 5
    python3 scripts/verify_settlement.py --epoch 5 --rpc http://localhost:1317
"""

import argparse
import hashlib
import json
import sys

try:
    import requests
except ImportError:
    print("❌ Required: pip install requests")
    sys.exit(1)


def verify_epoch(rpc_url: str, epoch_id: int) -> bool:
    """Verify settlement integrity for a given epoch."""
    print(f"🔍 Verifying epoch {epoch_id} settlement...")
    print(f"   RPC: {rpc_url}")

    # 1. Fetch settlement data
    try:
        resp = requests.get(f"{rpc_url}/clawchain/epoch/{epoch_id}/settlement", timeout=10)
        if resp.status_code == 404:
            print(f"   ❌ No settlement data found for epoch {epoch_id}")
            return False
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"   ❌ Failed to fetch settlement: {e}")
        return False

    stored_root = data.get("settlement_root", "")
    anchor_type = data.get("anchor_type", "unknown")
    tx_hash = data.get("tx_hash")
    records = data.get("records", [])

    print(f"   📋 Records: {len(records)} miners")
    print(f"   🔗 Anchor type: {anchor_type}")
    if tx_hash:
        print(f"   📝 TX hash: {tx_hash}")

    if not records:
        print(f"   ⚠️ No records to verify")
        return True

    # 2. Recompute settlement root
    # Sort by miner address (same as server-side)
    sorted_records = sorted(records, key=lambda x: x["miner"])
    canonical = json.dumps(sorted_records, sort_keys=True, separators=(",", ":"))
    computed_root = hashlib.sha256(canonical.encode()).hexdigest()

    print(f"   📊 Stored root:   {stored_root}")
    print(f"   📊 Computed root: {computed_root}")

    # 3. Compare
    if computed_root == stored_root:
        print(f"   ✅ Settlement root matches — epoch {epoch_id} is valid")
        return True
    else:
        print(f"   ❌ SETTLEMENT ROOT MISMATCH — epoch {epoch_id} may be tampered!")
        print(f"      Expected: {stored_root}")
        print(f"      Got:      {computed_root}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Verify ClawChain epoch settlement")
    parser.add_argument("--epoch", type=int, required=True, help="Epoch ID to verify")
    parser.add_argument("--rpc", default="http://localhost:1317", help="Mining service RPC URL")
    parser.add_argument("--all-anchors", action="store_true", help="List all anchored epochs")
    args = parser.parse_args()

    if args.all_anchors:
        try:
            resp = requests.get(f"{args.rpc}/clawchain/anchors", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            anchors = data.get("anchors", [])
            print(f"📋 {len(anchors)} anchored epoch(s):")
            for a in anchors:
                print(f"   Epoch {a['epoch_id']}: {a['settlement_root'][:16]}... ({a['anchor_type']})")
        except Exception as e:
            print(f"❌ Failed to fetch anchors: {e}")
            sys.exit(1)
        return

    success = verify_epoch(args.rpc, args.epoch)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
