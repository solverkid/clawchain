#!/usr/bin/env python3
"""
ClawChain Mining Script
Connects to ClawChain testnet, fetches challenges, solves them, and submits answers.
"""

import json
import os
import sys
import time
import hashlib
import re

CLAWCHAIN_DIR = os.path.expanduser("~/.clawchain")
WALLET_FILE = os.path.join(CLAWCHAIN_DIR, "wallet.json")
CONFIG_FILE = os.path.join(CLAWCHAIN_DIR, "config.json")
LOG_FILE = os.path.join(CLAWCHAIN_DIR, "mining_log.json")


def load_config():
    if not os.path.exists(CONFIG_FILE):
        print("❌ Config not found. Run: python3 scripts/setup.py")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        return json.load(f)


def load_wallet():
    if not os.path.exists(WALLET_FILE):
        print("❌ Wallet not found. Run: python3 scripts/setup.py")
        sys.exit(1)
    with open(WALLET_FILE) as f:
        return json.load(f)


def solve_math(prompt):
    """Solve math challenges locally."""
    # Extract numbers and operator
    match = re.search(r"(\d+)\s*([+\-*])\s*(\d+)", prompt)
    if match:
        a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
        if op == "+": return str(a + b)
        if op == "-": return str(a - b)
        if op == "*": return str(a * b)
    return None


def solve_sentiment(prompt):
    """Solve sentiment analysis locally with keyword matching."""
    positive = ["突破", "新高", "牛市", "晴朗", "高度评价", "大增", "重大突破", "成功"]
    negative = ["暴跌", "恐慌", "抛售", "延期", "压力", "漏洞", "泄露", "裁员", "低落"]
    text = prompt.lower()
    pos_count = sum(1 for w in positive if w in prompt)
    neg_count = sum(1 for w in negative if w in prompt)
    if pos_count > neg_count: return "正面"
    if neg_count > pos_count: return "负面"
    return "中性"


def solve_classification(prompt):
    """Solve text classification locally with keyword matching."""
    categories = {
        "科技": ["AI", "GPT", "量子", "SpaceX", "算力", "模型", "飞船"],
        "金融": ["美联储", "加息", "股市", "比特币", "道指", "价格"],
        "体育": ["世界杯", "NBA", "奥运", "夺冠", "决赛", "金牌"],
        "娱乐": ["电影", "票房", "奥斯卡", "演唱会", "歌手"],
        "政治": ["联合国", "峰会", "G20", "欧盟", "政策"],
    }
    for cat, keywords in categories.items():
        if any(k in prompt for k in keywords):
            return cat
    return "科技"


def solve_logic(prompt):
    """Solve logic challenges."""
    if "A > B" in prompt and "B > C" in prompt:
        return "A>C"
    return None


def solve_challenge(challenge):
    """Route to appropriate solver based on challenge type."""
    ctype = challenge.get("type", "")
    prompt = challenge.get("prompt", "")

    if ctype == "math":
        return solve_math(prompt)
    elif ctype == "sentiment":
        return solve_sentiment(prompt)
    elif ctype == "classification":
        return solve_classification(prompt)
    elif ctype == "logic":
        return solve_logic(prompt)
    elif ctype == "format_convert":
        # Try basic JSON to CSV
        if "JSON" in prompt and "CSV" in prompt:
            try:
                json_match = re.search(r'\{.*\}', prompt)
                if json_match:
                    data = json.loads(json_match.group())
                    header = ",".join(data.keys())
                    values = ",".join(str(v) for v in data.values())
                    return f"{header}\n{values}"
            except:
                pass
    
    # Fallback: try LLM if available
    return solve_with_llm(prompt)


def solve_with_llm(prompt):
    """Try to solve with available LLM API."""
    # Try OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        try:
            import requests
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
        except:
            pass

    # Try Gemini
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            import requests
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except:
            pass

    return None


def log_result(entry):
    """Append result to mining log."""
    log = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE) as f:
                log = json.load(f)
        except:
            log = []
    log.append(entry)
    # Keep last 1000 entries
    log = log[-1000:]
    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


def main():
    config = load_config()
    wallet = load_wallet()
    rpc = config["rpc_url"]
    address = wallet["address"]

    print(f"⛏️  ClawChain Miner")
    print(f"   Address: {address}")
    print(f"   Node: {rpc}")
    print()

    try:
        import requests
    except ImportError:
        print("❌ requests library required: pip3 install requests")
        sys.exit(1)

    # Check miner registration
    try:
        resp = requests.get(f"{rpc}/clawchain/miner/{address}", timeout=5)
        if resp.status_code != 200:
            print("⚠️  Miner not registered. Registering...")
            requests.post(f"{rpc}/clawchain/miner/register", json={"address": address}, timeout=5)
    except Exception as e:
        print(f"❌ Cannot connect to chain: {e}")
        sys.exit(1)

    # Fetch pending challenges
    try:
        resp = requests.get(f"{rpc}/clawchain/challenges/pending", timeout=5)
        if resp.status_code != 200:
            print("ℹ️  No pending challenges. Will try again next epoch.")
            sys.exit(0)
        challenges = resp.json().get("challenges", [])
    except Exception as e:
        print(f"❌ Failed to fetch challenges: {e}")
        sys.exit(1)

    if not challenges:
        print("ℹ️  No pending challenges. Will try again next epoch.")
        sys.exit(0)

    print(f"📋 Found {len(challenges)} challenge(s)")

    solved = 0
    for ch in challenges:
        ch_id = ch.get("id", "unknown")
        ch_type = ch.get("type", "unknown")
        prompt = ch.get("prompt", "")

        answer = solve_challenge(ch)
        if answer:
            # Submit answer
            try:
                resp = requests.post(
                    f"{rpc}/clawchain/challenge/submit",
                    json={
                        "challenge_id": ch_id,
                        "miner_address": address,
                        "answer": answer,
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    print(f"  ✅ {ch_id} ({ch_type}): submitted")
                    solved += 1
                else:
                    print(f"  ⚠️ {ch_id} ({ch_type}): submit failed ({resp.status_code})")
            except Exception as e:
                print(f"  ❌ {ch_id} ({ch_type}): error ({e})")

            log_result({
                "challenge_id": ch_id,
                "type": ch_type,
                "answer": answer[:100],
                "status": "submitted" if solved else "failed",
                "timestamp": time.time(),
            })
        else:
            print(f"  ⏭️  {ch_id} ({ch_type}): could not solve")

    print(f"\n⛏️  Done: {solved}/{len(challenges)} challenges solved")


if __name__ == "__main__":
    main()
