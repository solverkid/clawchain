#!/usr/bin/env python3
"""
ClawChain Wallet Initialization & Miner Registration
Generate a Cosmos SDK wallet (bech32 claw prefix), save keys, register miner.

Wallet Security:
  - Private keys are encrypted with PBKDF2 + Fernet (requires `cryptography` library).
  - Falls back to base64 obfuscation if `cryptography` is not installed (with warning).
  - File permissions are set to 600 (owner-only read/write).
  - You can override the private key via env var CLAWCHAIN_PRIVATE_KEY.
  - Passphrase can be provided via env var CLAWCHAIN_WALLET_PASSPHRASE.
  - Use --insecure flag for plaintext storage (not recommended).
  - This is a TESTNET/MINING wallet. Do not store significant value.
"""

import argparse
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

# Import wallet crypto module
from wallet_crypto import (
    save_wallet as crypto_save_wallet,
    load_wallet as crypto_load_wallet,
    detect_wallet_version,
    migrate_wallet,
    HAS_CRYPTO,
)

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


def generate_wallet(private_key_override=None):
    """Generate a Cosmos-style wallet (claw prefix) with secp256k1 keypair.

    Address derivation (Cosmos SDK compatible):
      1. Generate 32-byte secp256k1 private key
      2. Derive uncompressed public key (64 bytes)
      3. Compress to 33 bytes (02/03 prefix)
      4. address = bech32("claw", RIPEMD160(SHA256(compressed_pubkey)))

    If private_key_override is provided (hex string), use it instead of generating.
    """
    from eth_keys import keys as eth_keys

    if private_key_override:
        private_key = bytes.fromhex(private_key_override)
    else:
        private_key = secrets.token_bytes(32)

    # Derive secp256k1 public key
    pk = eth_keys.PrivateKey(private_key)
    pubkey_uncompressed = pk.public_key.to_bytes()  # 64 bytes, no 04 prefix

    # Compress: 33 bytes (02 if y is even, 03 if odd)
    x = pubkey_uncompressed[:32]
    y = pubkey_uncompressed[32:]
    prefix = b'\x02' if y[-1] % 2 == 0 else b'\x03'
    compressed = prefix + x

    # Cosmos SDK address: RIPEMD160(SHA256(compressed_pubkey))
    sha = hashlib.sha256(compressed).digest()
    ripemd = hashlib.new("ripemd160", sha).digest()

    # bech32 encode
    data5 = convertbits(list(ripemd), 8, 5)
    address = bech32_encode("claw", data5)

    # Public key hex (uncompressed, for registration)
    public_key_hex = pubkey_uncompressed.hex()

    # Generate HMAC auth secret for legacy fallback
    auth_secret = secrets.token_hex(32)

    return {
        "address": address,
        "private_key": private_key.hex(),
        "public_key": public_key_hex,
        "public_key_hash": ripemd.hex(),
        "auth_secret": auth_secret,
    }


# Backward-compatible wrappers
def save_wallet(wallet_data, wallet_path, passphrase=None, insecure=False):
    return crypto_save_wallet(wallet_data, wallet_path, passphrase=passphrase, insecure=insecure)

def load_wallet(wallet_path, passphrase=None):
    return crypto_load_wallet(wallet_path, passphrase=passphrase)


def register_miner(rpc_url, address, name, auth_secret=None, public_key=None):
    """Register miner on chain"""
    try:
        payload = {"address": address, "name": name}
        if public_key:
            payload["public_key"] = public_key
        if auth_secret:
            payload["auth_secret"] = auth_secret
        resp = requests.post(
            f"{rpc_url}/clawchain/miner/register",
            headers={"Content-Type": "application/json"},
            json=payload,
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


def derive_public_key(private_key_hex):
    """Derive 64-byte uncompressed secp256k1 public key hex from private key hex."""
    from eth_keys import keys as eth_keys

    private_key = bytes.fromhex(private_key_hex)
    return eth_keys.PrivateKey(private_key).public_key.to_bytes().hex()

def main():
    parser = argparse.ArgumentParser(description="ClawChain Wallet Initialization & Miner Registration")
    parser.add_argument("--name", default="openclaw-miner", help="Miner name (default: openclaw-miner)")
    parser.add_argument("--rpc", default=None, help="Chain REST API URL (default: from config.json)")
    parser.add_argument("--wallet-path", default=None, help="Wallet save path (default: ~/.clawchain/wallet.json)")
    parser.add_argument("--non-interactive", action="store_true", help="Non-interactive mode (auto-confirm)")
    parser.add_argument("--insecure", action="store_true", help="Store wallet without encryption (not recommended)")
    parser.add_argument("--migrate-wallet", action="store_true", help="Migrate existing wallet to v2 encrypted format")
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

    # Show encryption status
    if not HAS_CRYPTO:
        print("⚠️  `cryptography` library not installed. Wallet encryption unavailable.")
        print("   Install: pip install cryptography")
    elif not args.insecure:
        print("🔐 Wallet encryption enabled (PBKDF2 + Fernet)")

    # Handle --migrate-wallet
    if args.migrate_wallet:
        if wallet_path_expanded.exists():
            info = detect_wallet_version(wallet_path_expanded)
            if info.get("needs_migration"):
                print(f"🔄 Migrating wallet from v{info.get('version', 0)} ({info.get('format', 'unknown')}) to v2 encrypted...")
                if migrate_wallet(wallet_path_expanded):
                    print("✅ Wallet migration complete.")
                else:
                    print("❌ Wallet migration failed.")
                    sys.exit(1)
            else:
                print("ℹ️  Wallet is already v2 encrypted.")
        else:
            print("❌ No wallet found to migrate.")
            sys.exit(1)
        return

    # Check for env var private key
    env_key = os.getenv("CLAWCHAIN_PRIVATE_KEY")

    # Check for existing wallet
    if wallet_path_expanded.exists():
        # Detect and warn about unencrypted wallets
        wallet_info = detect_wallet_version(wallet_path_expanded)
        if wallet_info.get("needs_migration") and HAS_CRYPTO and not args.insecure:
            print(f"⚠️  Wallet is in {wallet_info.get('format', 'legacy')} format (not encrypted).")
            if not args.non_interactive:
                migrate_choice = input("   Migrate to encrypted format now? (y/n): ").strip().lower()
                if migrate_choice == "y":
                    if migrate_wallet(wallet_path_expanded):
                        print("✅ Wallet migrated to v2 encrypted format.")
                    else:
                        print("⚠️  Migration failed. Continuing with existing format.")

        existing = load_wallet(wallet_path_expanded)
        print(f"📋 Existing wallet found: {existing['address']}")
        if not args.non_interactive:
            choice = input("Use existing wallet? (y/n): ").strip().lower()
            if choice != "n":
                address = existing["address"]
                print(f"\nUsing existing wallet: {address}")
                print(f"\n📝 Registering miner on chain...")
                # Generate auth_secret if missing from existing wallet
                existing_auth = existing.get("auth_secret")
                if not existing_auth:
                    existing_auth = secrets.token_hex(32)
                    existing["auth_secret"] = existing_auth
                    save_wallet(existing, wallet_path, insecure=args.insecure)
                    print("   🔑 Generated auth_secret for existing wallet (upgrade)")
                result = register_miner(
                    rpc_url,
                    address,
                    miner_name,
                    auth_secret=existing_auth,
                    public_key=derive_public_key(existing["private_key"]),
                )
                print(f"   {'✅' if result.get('success') else '⚠️'} {result.get('message', '')}")
                config["miner_address"] = address
                config["miner_name"] = miner_name
                with open(CONFIG_PATH, "w") as f:
                    json.dump(config, f, indent=2)
                print(f"\n✅ Config updated")
                return
        else:
            address = existing["address"]
            existing_auth = existing.get("auth_secret")
            if not existing_auth:
                existing_auth = secrets.token_hex(32)
                existing["auth_secret"] = existing_auth
                save_wallet(existing, wallet_path, insecure=args.insecure)
            print(f"Using existing wallet: {address}")
            result = register_miner(
                rpc_url,
                address,
                miner_name,
                auth_secret=existing_auth,
                public_key=derive_public_key(existing["private_key"]),
            )
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

    # Save wallet (encrypted if possible)
    saved_path = save_wallet(wallet, wallet_path, insecure=args.insecure)
    if args.insecure:
        print(f"💾 Wallet saved: {saved_path} (permissions 600, ⚠️ NOT encrypted)")
    elif HAS_CRYPTO:
        print(f"💾 Wallet saved: {saved_path} (permissions 600, 🔐 encrypted)")
    else:
        print(f"💾 Wallet saved: {saved_path} (permissions 600, key obfuscated)")

    # Register miner
    print(f"\n📝 Registering miner on chain...")
    result = register_miner(
        rpc_url,
        wallet["address"],
        miner_name,
        auth_secret=wallet.get("auth_secret"),
        public_key=wallet.get("public_key"),
    )
    print(f"   {'✅' if result.get('success') else '⚠️'} {result.get('message', '')}")

    # Forecast mode selection
    if not args.non_interactive:
        print("\n📈 Forecast Mode Selection:")
        print("   1. heuristic_v1 — Use built-in heuristic forecast model")
        print("   2. codex_v1     — Use Codex CLI for live probability forecasts")
        mode_choice = input("Choose forecast mode [1] (default: 1): ").strip()
        forecast_mode = "codex_v1" if mode_choice == "2" else "heuristic_v1"
    else:
        forecast_mode = config.get("forecast_mode", "heuristic_v1")

    # Update config.json
    config["miner_address"] = wallet["address"]
    config["miner_name"] = miner_name
    config["forecast_mode"] = forecast_mode
    config["codex_binary"] = config.get("codex_binary", "codex")
    config["codex_model"] = config.get("codex_model", "gpt-5.4-mini")
    config["codex_timeout_seconds"] = config.get("codex_timeout_seconds", 120)
    config["parallel_tasks"] = config.get("parallel_tasks", 2 if config.get("forecast_mode") == "codex_v1" else 1)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n✅ Initialization complete!")
    print(f"   Wallet address: {wallet['address']}")
    print(f"   Forecast mode: {forecast_mode}")
    print(f"   Next step: python3 skill/scripts/mine.py --once to run a forecast mining cycle")

if __name__ == "__main__":
    main()
