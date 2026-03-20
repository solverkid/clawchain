#!/usr/bin/env python3
"""
ClawChain Doctor — Pre-flight checks for mining setup.

Usage: python3 scripts/doctor.py
"""

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
WORKSPACE_DIR = Path("~/.openclaw/workspace").expanduser()

MINER_VERSION = "0.2.0"


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
            has_rpc = "rpc_url" in config or "node_url" in config
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

    # 6. Solver mode check
    solver_mode = config.get("solver_mode", "auto") if config else "auto"
    if solver_mode == "local_only":
        info("Solver mode", f"{solver_mode} (most secure, no external API calls)")
    elif solver_mode == "auto":
        info("Solver mode", f"{solver_mode} (local first, LLM fallback — challenge text sent to LLM provider)")
    elif solver_mode == "llm":
        info("Solver mode", f"{solver_mode} (⚠️ all challenges sent to external LLM)")
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

    # 8. RPC endpoint reachable
    rpc_url = config.get("rpc_url", config.get("node_url", "")) if config else ""
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

    print()
    if all_ok:
        print("🎉 All checks passed! Ready to mine.")
    else:
        print("⚠️  Some checks failed. Fix the issues above before mining.")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
