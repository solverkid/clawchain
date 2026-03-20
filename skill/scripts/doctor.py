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
WORKSPACE_DIR = Path("~/.openclaw/workspace").expanduser()
REPO_DIR = SCRIPT_DIR.parent.parent  # clawchain repo root

MINER_VERSION = "0.2.0"

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

    # 3. OpenClaw workspace
    ok = WORKSPACE_DIR.exists() and WORKSPACE_DIR.is_dir()
    all_ok &= check("OpenClaw workspace exists", ok, str(WORKSPACE_DIR))

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

    # 6. Solver mode check
    solver_mode = config.get("solver_mode", "auto") if config else "auto"
    if solver_mode == "local_only":
        check("Solver mode", True, f"{solver_mode} (most secure, no external API calls)")
    elif solver_mode == "auto":
        print(f"  ⚠️  Solver mode — {solver_mode} (local first, LLM fallback — challenge text sent to LLM provider)")
    elif solver_mode == "llm":
        print(f"  ⚠️  Solver mode — {solver_mode} (all challenges sent to external LLM)")
    else:
        info("Solver mode", f"{solver_mode} (unknown)")

    # 7. LLM API key (optional)
    has_llm = bool(
        os.getenv("OPENAI_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
    )
    providers = []
    if os.getenv("OPENAI_API_KEY"):
        providers.append("OpenAI")
    if os.getenv("GEMINI_API_KEY"):
        providers.append("Gemini")
    if os.getenv("ANTHROPIC_API_KEY"):
        providers.append("Anthropic")
    detail = ", ".join(providers) if providers else "none set (optional, local-only mining still works)"
    icon = "✅" if has_llm else "⚠️"
    suffix = f" — {detail}"
    print(f"  {icon} LLM API key set (optional){suffix}")

    # 7b. RPC endpoint sanity check
    rpc_url = config.get("rpc_url", "") if config else ""
    if not rpc_url and config:
        rpc_url = config.get("node_url", "")  # legacy fallback
    if rpc_url:
        is_localhost = "localhost" in rpc_url or "127.0.0.1" in rpc_url
        is_tunnel = "trycloudflare" in rpc_url or "ngrok" in rpc_url
        if is_localhost:
            print("  ⚠️  RPC endpoint points to localhost — this won't work for public testnet")
            print("     Check SETUP.md or https://github.com/0xVeryBigOrange/clawchain for the current endpoint")
        elif is_tunnel:
            print("  ⚠️  RPC endpoint points to a temporary tunnel URL — it may expire")
            print("     Check SETUP.md or https://github.com/0xVeryBigOrange/clawchain for the current endpoint")

    # 8. RPC endpoint reachable
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
    all_ok &= check("Miner registered on chain", ok, detail)

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

    # 11. Commitment verification test
    if rpc_url:
        try:
            import requests as req
            # Try to find a completed challenge with commitment data
            resp = req.get(f"{rpc_url}/clawchain/stats", timeout=5)
            if resp.status_code == 200:
                stats = resp.json()
                completed = stats.get("completed_challenges", 0)
                if completed > 0:
                    info("Commitment system", f"{completed} challenges settled (commitment verification available)")
                else:
                    info("Commitment system", "no settled challenges yet to verify")
            else:
                info("Commitment system", "cannot query stats")
        except Exception:
            info("Commitment system", "check unavailable")
    else:
        info("Commitment system", "no RPC to check")

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
