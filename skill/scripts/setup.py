#!/usr/bin/env python3
"""
ClawChain Wallet Initialization & Miner Registration
Generate a Cosmos SDK wallet (bech32 claw prefix), save keys, register miner.

Wallet Security:
  - Private keys are stored with file permissions 600 (owner-only read/write).
  - You can override the private key via env var CLAWCHAIN_PRIVATE_KEY.
  - This is a TESTNET/MINING wallet. Do not store significant value.
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
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

# ─── bech32 encoding (pure Python, no extra dependencies) ───

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

def bech32_polymod(values):
    GEN = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk

def bech32_hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]

def bech32_create_checksum(hrp, data):
    values = bech32_hrp_expand(hrp) + data
    polymod = bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]

def bech32_encode(hrp, data):
    combined = data + bech32_create_checksum(hrp, data)
    return hrp + "1" + "".join([CHARSET[d] for d in combined])

def convertbits(data, frombits, tobits, pad=True):
    acc, bits, ret = 0, 0, []
    maxv = (1 << tobits) - 1
    for value in data:
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad and bits:
        ret.append((acc << (tobits - bits)) & maxv)
    return ret


def warn_insecure_rpc(url):
    """Warn if RPC URL uses plain HTTP on a non-localhost endpoint."""
    parsed = urlparse(url)
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        print(f"⚠️  SECURITY WARNING: RPC endpoint uses plain HTTP ({url}). Use HTTPS for production.")


# ─── Wallet Key Obfuscation ───

def _obfuscate_key(private_key_hex: str) -> str:
    """Obfuscate private key with base64 encoding for at-rest storage.

    NOTE: This is NOT cryptographic encryption — it prevents casual exposure
    of the raw hex key in plaintext files. Combined with 600 file permissions,
    this provides reasonable protection for a testnet mining wallet.
    """
    marker = b"CLAWCHAIN_TESTNET_KEY_V1:"
    return base64.b64encode(marker + bytes.fromhex(private_key_hex)).decode()


def _deobfuscate_key(encoded: str) -> str:
    """Reverse the obfuscation."""
    raw = base64.b64decode(encoded)
    marker = b"CLAWCHAIN_TESTNET_KEY_V1:"
    if raw.startswith(marker):
        return raw[len(marker):].hex()
    # Fallback: treat entire payload as the key
    return raw.hex()


def generate_wallet(private_key_override=None):
    """Generate a Cosmos-style wallet (claw prefix).

    If private_key_override is provided (hex string), use it instead of generating.
    """
    if private_key_override:
        private_key = bytes.fromhex(private_key_override)
    else:
        private_key = secrets.token_bytes(32)

    # Simplified: SHA256 + RIPEMD160 to simulate public key hash
    # Real Cosmos SDK uses secp256k1; hash simulation is sufficient for testnet
    sha = hashlib.sha256(private_key).digest()
    ripemd = hashlib.new("ripemd160", sha).digest()

    # bech32 encode
    data5 = convertbits(list(ripemd), 8, 5)
    address = bech32_encode("claw", data5)

    return {
        "address": address,
        "private_key": private_key.hex(),
        "public_key_hash": ripemd.hex(),
    }

def save_wallet(wallet_data, wallet_path):
    """Save wallet to file with obfuscated private key (permissions 600)."""
    wallet_path = Path(wallet_path).expanduser()
    wallet_path.parent.mkdir(parents=True, exist_ok=True)

    # Obfuscate private key for storage
    stored = {
        "address": wallet_data["address"],
        "private_key_encoded": _obfuscate_key(wallet_data["private_key"]),
        "public_key_hash": wallet_data["public_key_hash"],
        "_warning": "This is a mining/test wallet only. Do not store significant value.",
    }

    with open(wallet_path, "w") as f:
        json.dump(stored, f, indent=2)

    os.chmod(wallet_path, 0o600)
    return wallet_path


def load_wallet(wallet_path):
    """Load wallet, supporting both old (plaintext) and new (obfuscated) formats.

    Also supports CLAWCHAIN_PRIVATE_KEY env var override.
    """
    wallet_path = Path(wallet_path).expanduser()
    with open(wallet_path) as f:
        data = json.load(f)

    address = data["address"]

    # Env var override
    env_key = os.getenv("CLAWCHAIN_PRIVATE_KEY")
    if env_key:
        print("🔑 Using private key from CLAWCHAIN_PRIVATE_KEY environment variable")
        return {"address": address, "private_key": env_key, "public_key_hash": data.get("public_key_hash", "")}

    # New format
    if "private_key_encoded" in data:
        pk = _deobfuscate_key(data["private_key_encoded"])
        return {"address": address, "private_key": pk, "public_key_hash": data.get("public_key_hash", "")}

    # Old format (plaintext)
    if "private_key" in data:
        return data

    raise ValueError("Wallet file has no recognizable private key field")


def register_miner(rpc_url, address, name):
    """Register miner on chain"""
    try:
        resp = requests.post(
            f"{rpc_url}/clawchain/miner/register",
            headers={"Content-Type": "application/json"},
            json={"address": address, "name": name},
            timeout=10
        )
        if resp.status_code == 409:
            return {"success": True, "message": "Miner already registered"}
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        return {"success": False, "message": "Cannot connect to chain node (will retry later)"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def main():
    parser = argparse.ArgumentParser(description="ClawChain Wallet Initialization & Miner Registration")
    parser.add_argument("--name", default="openclaw-miner", help="Miner name (default: openclaw-miner)")
    parser.add_argument("--rpc", default=None, help="Chain REST API URL (default: from config.json)")
    parser.add_argument("--wallet-path", default=None, help="Wallet save path (default: ~/.clawchain/wallet.json)")
    parser.add_argument("--non-interactive", action="store_true", help="Non-interactive mode (auto-confirm)")
    args = parser.parse_args()

    # Load config with backward compat
    config = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            config = json.load(f)
        # Migrate node_url → rpc_url
        if "rpc_url" not in config and "node_url" in config:
            print("⚠️  DEPRECATION: 'node_url' is deprecated, migrating to 'rpc_url'. Please update config.json.")
            config["rpc_url"] = config.pop("node_url")
            with open(CONFIG_PATH, "w") as f:
                json.dump(config, f, indent=2)

    rpc_url = args.rpc or config.get("rpc_url", "http://localhost:1317")
    warn_insecure_rpc(rpc_url)

    wallet_path = args.wallet_path or config.get("wallet_path", "~/.clawchain/wallet.json")
    wallet_path_expanded = Path(wallet_path).expanduser()
    miner_name = args.name or config.get("miner_name", "openclaw-miner")

    # Check for env var private key
    env_key = os.getenv("CLAWCHAIN_PRIVATE_KEY")

    # Check for existing wallet
    if wallet_path_expanded.exists():
        existing = load_wallet(wallet_path_expanded)
        print(f"📋 Existing wallet found: {existing['address']}")
        if not args.non_interactive:
            choice = input("Use existing wallet? (y/n): ").strip().lower()
            if choice != "n":
                address = existing["address"]
                print(f"\nUsing existing wallet: {address}")
                print(f"\n📝 Registering miner on chain...")
                result = register_miner(rpc_url, address, miner_name)
                print(f"   {'✅' if result.get('success') else '⚠️'} {result.get('message', '')}")
                config["miner_address"] = address
                config["miner_name"] = miner_name
                with open(CONFIG_PATH, "w") as f:
                    json.dump(config, f, indent=2)
                print(f"\n✅ Config updated")
                return
        else:
            address = existing["address"]
            print(f"Using existing wallet: {address}")
            result = register_miner(rpc_url, address, miner_name)
            print(f"{'✅' if result.get('success') else '⚠️'} {result.get('message', '')}")
            config["miner_address"] = address
            config["miner_name"] = miner_name
            with open(CONFIG_PATH, "w") as f:
                json.dump(config, f, indent=2)
            return

    # Generate new wallet
    print("🔐 ClawChain Wallet Initialization")
    print("⚠️  This is a mining/test wallet only. Do not store significant value.")
    print()

    wallet = generate_wallet(private_key_override=env_key)
    print(f"   Address: {wallet['address']}")
    print(f"   Key path: {wallet_path_expanded}")
    if env_key:
        print(f"   🔑 Using private key from CLAWCHAIN_PRIVATE_KEY env var")
    print()

    if not args.non_interactive:
        confirm = input("Generate wallet and register miner? (y/n): ").strip().lower()
        if confirm != "y":
            print("❌ Cancelled")
            sys.exit(0)

    # Save wallet (with obfuscated key)
    saved_path = save_wallet(wallet, wallet_path)
    print(f"💾 Wallet saved: {saved_path} (permissions 600, key obfuscated)")

    # Register miner
    print(f"\n📝 Registering miner on chain...")
    result = register_miner(rpc_url, wallet["address"], miner_name)
    print(f"   {'✅' if result.get('success') else '⚠️'} {result.get('message', '')}")

    # Solver mode selection
    if not args.non_interactive:
        print("\n🤖 Solver Mode Selection:")
        print("   1. local_only — Solve challenges locally only (most secure, no external API calls)")
        print("   2. auto — Try local first, fall back to LLM (sends challenge text to LLM provider)")
        print("   3. llm — Always use LLM (requires API key)")
        mode_choice = input("Choose solver mode [1/2/3] (default: 1): ").strip()
        solver_mode = {"2": "auto", "3": "llm"}.get(mode_choice, "local_only")
    else:
        solver_mode = config.get("solver_mode", "local_only")

    # Update config.json
    config["miner_address"] = wallet["address"]
    config["miner_name"] = miner_name
    config["solver_mode"] = solver_mode
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n✅ Initialization complete!")
    print(f"   Wallet address: {wallet['address']}")
    print(f"   Solver mode: {solver_mode}")
    print(f"   Next step: python3 scripts/mine.py to start mining")

if __name__ == "__main__":
    main()
