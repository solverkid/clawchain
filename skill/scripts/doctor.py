#!/usr/bin/env python3
"""
ClawChain Doctor — Pre-flight checks for mining setup.

Usage: python3 scripts/doctor.py
"""

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
DATA_DIR = SCRIPT_DIR.parent / "data"
REPO_DIR = SCRIPT_DIR.parent.parent  # clawchain repo root

MINER_VERSION = "0.4.0"

# Import wallet crypto
sys.path.insert(0, str(SCRIPT_DIR))
from wallet_crypto import detect_wallet_version, HAS_CRYPTO


def check(label, ok, detail=""):
    icon = "✅" if ok else "❌"
    suffix = f" — {detail}" if detail else ""
    print(f"  {icon} {label}{suffix}")
    return ok


def info(label, detail=""):
    suffix = f" — {detail}" if detail else ""
    print(f"  ℹ️  {label}{suffix}")


def get_chain_preflight(rpc_url):
    import requests as req

    resp = req.get(f"{rpc_url}/admin/chain/preflight", timeout=10)
    resp.raise_for_status()
    return resp.json()


def summarize_anchor_readiness(preflight):
    warnings = [str(item) for item in (preflight.get("warnings") or []) if item]
    if preflight.get("ready"):
        return {
            "ok": True,
            "status": "ready",
            "detail": "typed and fallback anchor path ready",
        }
    if preflight.get("rpc", {}).get("reachable"):
        return {
            "ok": False,
            "status": "degraded",
            "detail": "; ".join(warnings) or "service reachable but anchor path is not ready",
        }
    return {
        "ok": False,
        "status": "unreachable",
        "detail": "; ".join(warnings) or "anchor path unavailable",
    }


def main():
    print("🩺 ClawChain Doctor")
    print("=" * 50)
    all_ok = True

    # 1. Python version
    v = sys.version_info
    ok = v >= (3, 9)
    all_ok &= check(f"Python >= 3.9", ok, f"current: {v.major}.{v.minor}.{v.micro}")

    # 2. requests installed
    try:
        import requests
        ok = True
        detail = f"v{requests.__version__}"
    except ImportError:
        ok = False
        detail = "pip install requests"
    all_ok &= check("requests library installed", ok, detail)

    # 3. local miner data directory
    try:
        DATA_DIR.mkdir(exist_ok=True)
        ok = DATA_DIR.exists() and DATA_DIR.is_dir()
        detail = str(DATA_DIR)
    except Exception as e:
        ok = False
        detail = str(e)
    all_ok &= check("Miner data directory ready", ok, detail)

    # 4. config.json valid
    config = None
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                config = json.load(f)
            has_rpc = "rpc_url" in config
            if "node_url" in config and "rpc_url" not in config:
                print("  ⚠️  Config uses deprecated 'node_url' — please rename to 'rpc_url'")
                print("     Run: python3 scripts/setup.py to auto-migrate")
                has_rpc = True  # still usable via backward compat
            ok = has_rpc
            detail = "valid JSON" + ("" if has_rpc else ", but missing rpc_url")
        except (json.JSONDecodeError, IOError) as e:
            ok = False
            detail = str(e)
    else:
        ok = False
        detail = f"not found: {CONFIG_PATH}"
    all_ok &= check("config.json format correct", ok, detail)

    # 5. wallet.json exists with correct permissions
    wallet_path = None
    if config:
        wallet_path = Path(config.get("wallet_path", "~/.clawchain/wallet.json")).expanduser()
    else:
        wallet_path = Path("~/.clawchain/wallet.json").expanduser()

    if wallet_path.exists():
        mode = oct(wallet_path.stat().st_mode & 0o777)
        ok = mode == "0o600"
        detail = f"{wallet_path} (permissions: {mode})"
        if not ok:
            detail += " — should be 0o600"
    else:
        ok = False
        detail = f"not found: {wallet_path}"
    all_ok &= check("wallet.json exists with correct permissions (600)", ok, detail)

    # 5b. Wallet encryption status
    if wallet_path and wallet_path.exists():
        wallet_info = detect_wallet_version(wallet_path)
        if wallet_info.get("encrypted"):
            check("Wallet encryption", True, "v2 encrypted (PBKDF2 + Fernet)")
        elif wallet_info.get("format") == "obfuscated":
            print("  ⚠️  Wallet encryption — v1 obfuscated only (not real encryption)")
            print("     Run: python3 scripts/setup.py --migrate-wallet")
        elif wallet_info.get("format") == "plaintext":
            print("  ⚠️  Wallet encryption — v0 plaintext (NOT encrypted)")
            print("     Run: python3 scripts/setup.py --migrate-wallet")
    if not HAS_CRYPTO:
        print("  ⚠️  `cryptography` library not installed — wallet encryption unavailable")
        print("     Install: pip install cryptography")

    # 6. RPC endpoint sanity check
    rpc_url = config.get("rpc_url", "") if config else ""
    if not rpc_url and config:
        rpc_url = config.get("node_url", "")  # legacy fallback
    if rpc_url:
        is_localhost = "localhost" in rpc_url or "127.0.0.1" in rpc_url
        is_tunnel = "trycloudflare" in rpc_url or "ngrok" in rpc_url
        if is_localhost:
            print("  ⚠️  RPC endpoint points to localhost — this won't work for public testnet")
            print("     Check SETUP.md or your current deployed mining-service endpoint")
        elif is_tunnel:
            print("  ⚠️  RPC endpoint points to a temporary tunnel URL — it may expire")
            print("     Check SETUP.md or your current deployed mining-service endpoint")

    # 7. RPC endpoint reachable
    if rpc_url:
        try:
            import requests as req
            resp = req.get(f"{rpc_url}/clawchain/stats", timeout=10)
            ok = resp.status_code == 200
            detail = f"{rpc_url} → HTTP {resp.status_code}"
        except Exception as e:
            ok = False
            detail = f"{rpc_url} → {e}"
    else:
        ok = False
        detail = "no rpc_url in config"
    all_ok &= check("RPC endpoint reachable", ok, detail)

    # 8. anchor readiness
    if rpc_url:
        try:
            readiness = summarize_anchor_readiness(get_chain_preflight(rpc_url))
            if readiness["status"] == "ready":
                all_ok &= check("Anchor readiness", True, readiness["detail"])
            elif readiness["status"] == "degraded":
                print(f"  ⚠️  Anchor readiness — degraded ({readiness['detail']})")
            else:
                print(f"  ⚠️  Anchor readiness — unavailable ({readiness['detail']})")
        except Exception as e:
            print(f"  ⚠️  Anchor readiness — unavailable ({e})")
    else:
        info("Anchor readiness", "no RPC to check")

    # 9. Miner registered
    miner_addr = config.get("miner_address", "") if config else ""
    if miner_addr and rpc_url:
        try:
            import requests as req
            resp = req.get(f"{rpc_url}/clawchain/miner/{miner_addr}", timeout=10)
            ok = resp.status_code == 200
            detail = f"{miner_addr[:20]}..." if ok else "not registered"
        except Exception as e:
            ok = False
            detail = str(e)
    elif not miner_addr:
        ok = False
        detail = "miner_address not in config — run setup.py first"
    else:
        ok = False
        detail = "cannot check (no RPC)"
    all_ok &= check("Miner registered in forecast service", ok, detail)

    # 10. Miner version check
    if rpc_url:
        try:
            import requests as req
            resp = req.get(f"{rpc_url}/clawchain/version", timeout=5)
            if resp.status_code == 200:
                ver_data = resp.json()
                server_ver = ver_data.get("server_version", "unknown")
                min_ver = ver_data.get("min_miner_version", "0.0.0")
                ok = MINER_VERSION >= min_ver
                detail = f"miner={MINER_VERSION}, server={server_ver}, min_required={min_ver}"
            else:
                ok = True
                detail = f"version endpoint not available (HTTP {resp.status_code})"
        except Exception:
            ok = True
            detail = "version check unavailable"
    else:
        ok = True
        detail = "no RPC to check"
    all_ok &= check("Miner version compatible", ok, detail)

    # 11. forecast settlement visibility
    if rpc_url:
        try:
            import requests as req
            resp = req.get(f"{rpc_url}/clawchain/stats", timeout=5)
            if resp.status_code == 200:
                stats = resp.json()
                settled_fast = stats.get("settled_fast_tasks", 0)
                if settled_fast > 0:
                    info("Forecast settlement", f"{settled_fast} fast tasks settled")
                else:
                    info("Forecast settlement", "no settled fast tasks yet")
            else:
                info("Forecast settlement", "cannot query stats")
        except Exception:
            info("Forecast settlement", "check unavailable")
    else:
        info("Forecast settlement", "no RPC to check")

    # 12. RPC fallback endpoints
    endpoints = config.get("rpc_endpoints", []) if config else []
    if endpoints:
        info("RPC fallback", f"{len(endpoints)} endpoints configured")
    else:
        info("RPC fallback", "no fallback endpoints (single rpc_url only)")

    # 13. Release tag check
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            capture_output=True, text=True, cwd=str(REPO_DIR), timeout=5
        )
        if result.returncode == 0:
            tag = result.stdout.strip()
            check("On stable release tag", True, tag)
        else:
            result2 = subprocess.run(
                ["git", "describe", "--tags"],
                capture_output=True, text=True, cwd=str(REPO_DIR), timeout=5
            )
            desc = result2.stdout.strip() if result2.returncode == 0 else "unknown"
            print(f"  ⚠️  Not on a release tag — {desc}")
            print("     Consider using a tagged release for stability")
    except Exception:
        info("Release tag", "git not available or not a git repo")

    # 14. CHECKSUMS.txt verification
    checksums_path = REPO_DIR / "CHECKSUMS.txt"
    if checksums_path.exists():
        try:
            result = subprocess.run(
                ["shasum", "-a", "256", "-c", "CHECKSUMS.txt"],
                capture_output=True, text=True, cwd=str(REPO_DIR), timeout=30
            )
            if result.returncode == 0:
                lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
                check("CHECKSUMS.txt verification", True, f"{len(lines)} files verified")
            else:
                failed_lines = [l for l in result.stdout.strip().split("\n") if "FAILED" in l]
                check("CHECKSUMS.txt verification", False, f"{len(failed_lines)} file(s) failed")
                all_ok = False
        except Exception as e:
            info("CHECKSUMS.txt verification", f"check failed: {e}")
    else:
        info("CHECKSUMS.txt", "not found (run scripts/gen_checksums.sh to generate)")

    print()
    if all_ok:
        print("🎉 All checks passed! Ready to mine.")
    else:
        print("⚠️  Some checks failed. Fix the issues above before mining.")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
