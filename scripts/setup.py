#!/usr/bin/env python3
"""
ClawChain Setup Script
Generates wallet, registers miner, and configures environment.
"""

import json
import os
import sys
import hashlib
import secrets

CLAWCHAIN_DIR = os.path.expanduser("~/.clawchain")
WALLET_FILE = os.path.join(CLAWCHAIN_DIR, "wallet.json")
CONFIG_FILE = os.path.join(CLAWCHAIN_DIR, "config.json")

DEFAULT_CONFIG = {
    "rpc_url": "http://localhost:1317",
    "chain_id": "clawchain-testnet-1",
    "auto_mine": True,
    "max_cpu": 50,
    "task_types": "all",
    "idle_threshold": 60,
    "log_level": "info",
    "auto_stake": False,
    "reward_notify": True,
}


def generate_address():
    """Generate a simple testnet address (placeholder for real crypto)."""
    raw = secrets.token_bytes(20)
    return "claw1" + raw.hex()


def generate_seed_phrase():
    """Generate a 24-word placeholder seed phrase."""
    # In production, use BIP-39. This is a testnet placeholder.
    words = [
        "abandon", "ability", "able", "about", "above", "absent",
        "absorb", "abstract", "absurd", "abuse", "access", "accident",
        "account", "accuse", "achieve", "acid", "acoustic", "acquire",
        "across", "act", "action", "actor", "actress", "actual",
    ]
    return " ".join(words)


def main():
    print("🦞 ClawChain Setup")
    print("=" * 40)

    # Create config directory
    os.makedirs(CLAWCHAIN_DIR, exist_ok=True)

    # Generate wallet
    if os.path.exists(WALLET_FILE):
        with open(WALLET_FILE, "r") as f:
            wallet = json.load(f)
        print(f"✅ Wallet already exists: {wallet['address']}")
    else:
        address = generate_address()
        seed = generate_seed_phrase()
        wallet = {
            "address": address,
            "seed_phrase": seed,
            "created_at": __import__("datetime").datetime.now().isoformat(),
        }
        with open(WALLET_FILE, "w") as f:
            json.dump(wallet, f, indent=2)
        os.chmod(WALLET_FILE, 0o600)
        print(f"🔑 Wallet created: {address}")
        print(f"⚠️  SAVE YOUR SEED PHRASE:")
        print(f"    {seed}")
        print()

    # Write default config
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"⚙️  Config written to {CONFIG_FILE}")
    else:
        print(f"✅ Config already exists: {CONFIG_FILE}")

    # Try to register miner on chain
    try:
        import requests
        config = json.load(open(CONFIG_FILE))
        rpc = config["rpc_url"]
        resp = requests.post(
            f"{rpc}/clawchain/miner/register",
            json={"address": wallet["address"]},
            timeout=5,
        )
        if resp.status_code == 200:
            print(f"✅ Miner registered on chain")
        else:
            print(f"⚠️  Chain registration failed (chain may not be running): {resp.status_code}")
    except Exception as e:
        print(f"⚠️  Could not connect to chain ({e}). Register when chain is running.")

    print()
    print("💰 Setup complete!")
    print(f"   Next: python3 scripts/mine.py")


if __name__ == "__main__":
    main()
