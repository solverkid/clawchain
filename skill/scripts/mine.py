#!/usr/bin/env python3
"""
ClawChain Mining Script
Query on-chain challenges → Solve with LLM / local compute → Submit answers (supports commit-reveal)
"""

import argparse
import ast
import hashlib
import json
import operator
import os
import re
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("❌ Required: pip install requests")
    sys.exit(1)

MINER_VERSION = "0.2.0"

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
DATA_DIR = SCRIPT_DIR.parent / "data"
LOG_PATH = DATA_DIR / "mining_log.json"
LLM_LOG_PATH = DATA_DIR / "llm_calls.json"

DATA_DIR.mkdir(exist_ok=True)


# ─── Config ───

def load_config():
    """Load configuration with backward compatibility for node_url → rpc_url migration."""
    if not CONFIG_PATH.exists():
        print(f"❌ Config file not found: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        config = json.load(f)

    # Backward compat: migrate node_url → rpc_url
    if "rpc_url" not in config and "node_url" in config:
        print("⚠️  DEPRECATION: 'node_url' is deprecated, migrating to 'rpc_url'. Please update config.json.")
        config["rpc_url"] = config.pop("node_url")
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)

    if "rpc_url" not in config:
        print("❌ 'rpc_url' not set in config.json")
        sys.exit(1)

    return config


def resolve_rpc_url(config):
    """Resolve working RPC URL with fallback support.

    Supports:
      - config["rpc_url"] (single endpoint, backward compat)
      - config["rpc_endpoints"] (array of endpoints with auto-fallback)
    """
    endpoints = config.get("rpc_endpoints", [])
    if not endpoints:
        # Backward compat: single rpc_url
        return config["rpc_url"]

    for ep in endpoints:
        url = ep if isinstance(ep, str) else ep.get("url", "")
        if not url:
            continue
        try:
            resp = requests.get(f"{url}/clawchain/stats", timeout=5)
            if resp.status_code == 200:
                return url
        except Exception:
            continue

    # All endpoints failed, fall back to primary rpc_url
    print("⚠️ All RPC endpoints unreachable, using primary rpc_url")
    return config["rpc_url"]


def warn_insecure_rpc(url):
    """Warn if RPC URL uses plain HTTP on a non-localhost endpoint."""
    parsed = urlparse(url)
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        print(f"⚠️  SECURITY WARNING: RPC endpoint uses plain HTTP ({url}). Use HTTPS for production.")


# ─── Chain API ───

def verify_commitment(challenge_id, revealed_answer, salt, commitment):
    """Verify server commitment: H(challenge_id || expected_answer || salt) == commitment"""
    if not commitment or not salt:
        return None  # No commitment to verify
    payload = f"{challenge_id}{revealed_answer}{salt}"
    computed = hashlib.sha256(payload.encode()).hexdigest()
    return computed == commitment


def check_server_version(rpc_url):
    """Check server version compatibility"""
    try:
        resp = requests.get(f"{rpc_url}/clawchain/version", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            min_ver = data.get("min_miner_version", "0.0.0")
            if MINER_VERSION < min_ver:
                print(f"⚠️ Miner version {MINER_VERSION} is below server minimum {min_ver}. Please upgrade.")
                return False
            return True
    except Exception:
        pass
    return True  # Don't block mining if version check fails


def log_llm_call(provider, model, prompt_preview, success):
    """Log LLM API calls for audit"""
    logs = []
    if LLM_LOG_PATH.exists():
        try:
            with open(LLM_LOG_PATH) as f:
                logs = json.load(f)
        except (json.JSONDecodeError, IOError):
            logs = []

    logs.append({
        "timestamp": datetime.now().isoformat(),
        "provider": provider,
        "model": model,
        "prompt_preview": prompt_preview[:80],
        "success": success,
    })

    # Keep last 500 entries
    if len(logs) > 500:
        logs = logs[-500:]

    with open(LLM_LOG_PATH, "w") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)


def check_miner_registered(rpc_url, address):
    """Check if miner is registered"""
    try:
        resp = requests.get(f"{rpc_url}/clawchain/miner/{address}", timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def auto_register(rpc_url, address, name):
    """Auto-register miner on chain"""
    try:
        resp = requests.post(
            f"{rpc_url}/clawchain/miner/register",
            headers={"Content-Type": "application/json"},
            json={"address": address, "name": name, "miner_version": MINER_VERSION},
            timeout=10
        )
        if resp.status_code == 409:
            return True  # Already registered
        resp.raise_for_status()
        result = resp.json()
        return result.get("success", False)
    except Exception as e:
        print(f"⚠️ Auto-registration failed: {e}")
        return False


def query_pending_challenges(rpc_url):
    """Query pending challenges"""
    try:
        resp = requests.get(f"{rpc_url}/clawchain/challenges/pending", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("challenges") or []
    except requests.ConnectionError:
        print("⚠️ Cannot connect to chain node, will retry later")
        return []
    except Exception as e:
        print(f"⚠️ Failed to query challenges: {e}")
        return []


def submit_answer(rpc_url, challenge_id, miner_addr, answer):
    """Submit answer (simplified, direct submit in DEV mode)"""
    try:
        resp = requests.post(
            f"{rpc_url}/clawchain/challenge/submit",
            headers={"Content-Type": "application/json"},
            json={
                "challenge_id": challenge_id,
                "miner_address": miner_addr,
                "answer": answer,
            },
            timeout=10
        )
        if resp.status_code == 409:
            return {"success": True, "already_submitted": True}
        if resp.status_code == 410:
            return {"success": False, "expired": True}
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ Failed to submit answer: {e}")
        return None


def submit_commit(rpc_url, challenge_id, miner_addr, commit_hash):
    """Phase 1: Submit commit hash"""
    try:
        resp = requests.post(
            f"{rpc_url}/clawchain/challenge/commit",
            headers={"Content-Type": "application/json"},
            json={
                "challenge_id": challenge_id,
                "miner_address": miner_addr,
                "commit_hash": commit_hash,
            },
            timeout=10
        )
        if resp.status_code == 409:
            return {"success": True, "already_committed": True}
        if resp.status_code == 404:
            return {"success": False, "not_found": True}
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ Failed to submit commit: {e}")
        return None


def submit_reveal(rpc_url, challenge_id, miner_addr, answer, nonce):
    """Phase 2: Submit reveal"""
    try:
        resp = requests.post(
            f"{rpc_url}/clawchain/challenge/reveal",
            headers={"Content-Type": "application/json"},
            json={
                "challenge_id": challenge_id,
                "miner_address": miner_addr,
                "answer": answer,
                "nonce": nonce,
            },
            timeout=10
        )
        if resp.status_code == 409:
            return {"success": True, "already_revealed": True}
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ Failed to submit reveal: {e}")
        return None


def submit_two_phase(rpc_url, challenge_id, miner_addr, answer, delay=3):
    """Two-phase submission: commit → wait → reveal"""
    nonce = secrets.token_hex(16)
    commit_hash = hashlib.sha256((answer + nonce).encode()).hexdigest()

    # Phase 1: Commit
    commit_result = submit_commit(rpc_url, challenge_id, miner_addr, commit_hash)
    if not commit_result or not commit_result.get("success"):
        return commit_result

    print(f"   🔒 Commit done, waiting {delay}s before reveal...")
    time.sleep(delay)

    # Phase 2: Reveal
    reveal_result = submit_reveal(rpc_url, challenge_id, miner_addr, answer, nonce)
    return reveal_result


# ─── Safe Math Evaluator (replaces eval()) ───

# Allowed AST node types for safe math evaluation
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval_node(node):
    """Recursively evaluate an AST node containing only numbers and arithmetic ops."""
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body)
    elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    elif isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        return _SAFE_OPS[type(node.op)](left, right)
    elif isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        operand = _safe_eval_node(node.operand)
        return _SAFE_OPS[type(node.op)](operand)
    else:
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def safe_math_eval(expr: str):
    """Safely evaluate a math expression string. Only supports numbers, +, -, *, /, %, ()."""
    tree = ast.parse(expr.strip(), mode="eval")
    return _safe_eval_node(tree)


# ─── Local Solvers ───

def solve_math(prompt):
    """Local math computation (safe, no eval())"""
    # Chinese format: "计算 123 + 456 的结果"
    match = re.search(r'计算\s*([\d\s+\-*/().%]+)\s*的结果', prompt)
    if match:
        expr = match.group(1).strip()
    else:
        match = re.search(r'[Cc]alculate[:\s]*(.+)', prompt)
        if match:
            expr = match.group(1).strip().rstrip("。.?")
        else:
            match = re.search(r'([\d\s+\-*/().%]+)', prompt)
            if match:
                expr = match.group(1).strip()
            else:
                return None

    try:
        allowed = set("0123456789+-*/().% ")
        if all(c in allowed for c in expr):
            result = safe_math_eval(expr)
            if isinstance(result, float) and result == int(result):
                return str(int(result))
            return str(result)
    except Exception:
        pass
    return None


def solve_hash(prompt):
    """Local hash computation"""
    text_match = re.search(r'["\'](.+?)["\']', prompt)
    if not text_match:
        text_match = re.search(r'of[:\s]+(.+)', prompt, re.IGNORECASE)

    if not text_match:
        return None

    text = text_match.group(1).strip()

    if "sha256" in prompt.lower():
        return hashlib.sha256(text.encode()).hexdigest()
    elif "sha1" in prompt.lower():
        return hashlib.sha1(text.encode()).hexdigest()
    elif "md5" in prompt.lower():
        return hashlib.md5(text.encode()).hexdigest()
    else:
        return hashlib.sha256(text.encode()).hexdigest()


def solve_text_transform(prompt):
    """Local text transformation"""
    text_match = re.search(r'["\'](.+?)["\']', prompt)
    if not text_match:
        return None

    text = text_match.group(1)
    prompt_lower = prompt.lower()

    if "uppercase" in prompt_lower or "大写" in prompt_lower:
        return text.upper()
    elif "lowercase" in prompt_lower or "小写" in prompt_lower:
        return text.lower()
    elif "reverse" in prompt_lower or "反转" in prompt_lower:
        return text[::-1]
    elif "title" in prompt_lower or "首字母大写" in prompt_lower:
        return text.title()
    elif "length" in prompt_lower or "长度" in prompt_lower or "字数" in prompt_lower:
        return str(len(text))
    else:
        return text.upper()


def solve_json_extract(prompt):
    """Local JSON extraction"""
    json_match = re.search(r'\{[^{}]*\}', prompt, re.DOTALL)
    if not json_match:
        json_match = re.search(r'\[.*\]', prompt, re.DOTALL)
    if not json_match:
        return None

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return None

    field_match = re.search(r'(?:extract|get|提取|获取)[:\s]*["\']?(\w+)["\']?', prompt, re.IGNORECASE)
    if field_match:
        field = field_match.group(1)
        if isinstance(data, dict) and field in data:
            val = data[field]
            return json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val

    if isinstance(data, dict):
        key_match = re.search(r'keys|字段|键', prompt, re.IGNORECASE)
        if key_match:
            return ", ".join(data.keys())

    return None


def solve_format_convert(prompt):
    """Local format conversion"""
    if "csv" in prompt.lower() and "json" in prompt.lower():
        lines = [l.strip() for l in prompt.split("\n") if "," in l and l.strip()]
        if len(lines) >= 2:
            headers = [h.strip() for h in lines[0].split(",")]
            rows = []
            for line in lines[1:]:
                vals = [v.strip() for v in line.split(",")]
                if len(vals) == len(headers):
                    rows.append(dict(zip(headers, vals)))
            if rows:
                return json.dumps(rows, ensure_ascii=False)
    return None


def solve_sentiment(prompt):
    """Local sentiment analysis (keyword matching)"""
    positive_kw = ["突破", "新高", "增长", "上涨", "利好", "成功", "超预期", "繁荣", "创新", "领先"]
    negative_kw = ["暴跌", "下跌", "危机", "失败", "亏损", "崩盘", "衰退", "制裁", "裁员", "违约"]
    pos = sum(1 for kw in positive_kw if kw in prompt)
    neg = sum(1 for kw in negative_kw if kw in prompt)
    if pos > neg:
        return "正面"
    elif neg > pos:
        return "负面"
    elif pos == 0 and neg == 0:
        return "中性"
    return None


def solve_classification(prompt):
    """Local text classification (keyword matching)"""
    categories = {
        "科技": ["AI", "人工智能", "芯片", "量子", "5G", "机器人", "算法", "GPU", "模型", "开源"],
        "金融": ["美联储", "加息", "降息", "GDP", "股市", "央行", "通胀", "利率", "债券", "汇率"],
        "体育": ["世界杯", "奥运", "冠军", "联赛", "球员", "比赛", "决赛", "足球", "篮球"],
        "娱乐": ["电影", "票房", "明星", "综艺", "音乐", "演唱会", "导演", "首映"],
        "政治": ["总统", "选举", "国会", "政策", "外交", "峰会", "制裁", "条约"],
    }
    scores = {}
    for cat, keywords in categories.items():
        scores[cat] = sum(1 for kw in keywords if kw in prompt)
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return None


def solve_translation(prompt):
    """Local translation (simple phrase dictionary)"""
    translations = {
        "open source software drives innovation": "开源软件推动创新",
        "artificial intelligence is changing the world": "人工智能正在改变世界",
        "blockchain technology enables trustless transactions": "区块链技术实现无需信任的交易",
    }
    for en, zh in translations.items():
        if en in prompt.lower():
            return zh
    return None


# ─── LLM Solvers ───

SYSTEM_PROMPTS = {
    "text_summary": "You are a text summarization expert. Summarize the given text in no more than 50 characters. Return only the summary.",
    "sentiment": "Determine the sentiment of the text. Return only one of: 正面, 负面, 中性. No explanation.",
    "translation": "Translate the given text accurately. Return only the translation.",
    "classification": "Classify the text into the most appropriate category (科技/金融/体育/娱乐/政治). Return only the category name.",
    "entity_extraction": "Extract key entities (names, organizations) from the text, separated by commas. Return only the entity list.",
    "logic": "Reason through the given conditions and return the most concise answer.",
    "math": "Calculate the given expression. Return only the numeric result.",
    "hash": "Compute the hash of the given text.",
    "text_transform": "Transform the text as instructed. Return only the result.",
    "json_extract": "Extract the specified field from the JSON. Return only the result.",
    "format_convert": "Convert the data format as instructed. Return only the result.",
}


def solve_with_llm(prompt, challenge_type, config):
    """Solve with LLM (auto-detect available provider)"""
    provider = config.get("llm_provider", "auto")
    model = config.get("llm_model", "")
    system_prompt = SYSTEM_PROMPTS.get(challenge_type, "Answer concisely and accurately. Return only the answer.")

    # Auto-detect provider based on available API keys
    if provider == "auto":
        if os.getenv("OPENAI_API_KEY"):
            provider = "openai"
            model = model or "gpt-4o-mini"
        elif os.getenv("GEMINI_API_KEY"):
            provider = "gemini"
            model = model or "gemini-2.0-flash"
        elif os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
            model = model or "claude-3-5-haiku-latest"
        else:
            print("⚠️ No LLM API key found (OPENAI_API_KEY/GEMINI_API_KEY/ANTHROPIC_API_KEY)")
            return None

    result = None
    if provider == "openai":
        result = _call_openai(prompt, system_prompt, model or "gpt-4o-mini")
    elif provider == "anthropic":
        result = _call_anthropic(prompt, system_prompt, model or "claude-3-5-haiku-latest")
    elif provider == "gemini":
        result = _call_gemini(prompt, system_prompt, model or "gemini-2.0-flash")
    else:
        print(f"⚠️ Unsupported LLM provider: {provider}")
        return None

    # Log LLM call for audit
    log_llm_call(provider, model, prompt, result is not None)
    return result


def _call_openai(prompt, system_prompt, model):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️ OPENAI_API_KEY not set")
        return None
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 200,
            },
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"⚠️ OpenAI API failed: {e}")
        return None


def _call_anthropic(prompt, system_prompt, model):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️ ANTHROPIC_API_KEY not set")
        return None
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model if model.startswith("claude-") else "claude-3-5-haiku-latest",
                "max_tokens": 200,
                "system": system_prompt,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"⚠️ Anthropic API failed: {e}")
        return None


def _call_gemini(prompt, system_prompt, model):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ GEMINI_API_KEY not set")
        return None
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": f"{system_prompt}\n\n{prompt}"}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 200},
            },
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"⚠️ Gemini API failed: {e}")
        return None


# ─── Solver Router ───

LOCAL_SOLVERS = {
    "math": solve_math,
    "hash": solve_hash,
    "text_transform": solve_text_transform,
    "json_extract": solve_json_extract,
    "format_convert": solve_format_convert,
    "sentiment": solve_sentiment,
    "classification": solve_classification,
    "translation": solve_translation,
}

LLM_TYPES = {"text_summary", "sentiment", "translation", "classification", "entity_extraction", "logic"}


def solve_challenge(challenge, config):
    """Solve challenge based on solver_mode config.

    solver_mode:
      - "local_only": Only use local solvers; skip challenges that need LLM.
      - "llm": Always attempt LLM (skip local).
      - "auto" (default): Try local first, fall back to LLM.

    Note: In "auto" and "llm" modes, the challenge prompt text is sent to an
    external LLM provider (OpenAI / Google / Anthropic).
    """
    ctype = challenge["type"]
    prompt = challenge["prompt"]
    solver_mode = config.get("solver_mode", "auto")

    if solver_mode == "local_only":
        # Only local solvers
        if ctype in LOCAL_SOLVERS:
            answer = LOCAL_SOLVERS[ctype](prompt)
            if answer:
                return answer, "local"
        return None, None

    elif solver_mode == "llm":
        # Always try LLM
        answer = solve_with_llm(prompt, ctype, config)
        if answer:
            return answer, "llm"
        return None, None

    else:
        # auto: local first, LLM fallback
        if ctype in LOCAL_SOLVERS:
            answer = LOCAL_SOLVERS[ctype](prompt)
            if answer:
                return answer, "local"

        answer = solve_with_llm(prompt, ctype, config)
        if answer:
            return answer, "llm"

        return None, None


# ─── Logging ───

def log_result(challenge, answer, result, method):
    """Record mining result"""
    logs = []
    if LOG_PATH.exists():
        try:
            with open(LOG_PATH) as f:
                logs = json.load(f)
        except (json.JSONDecodeError, IOError):
            logs = []

    logs.append({
        "timestamp": datetime.now().isoformat(),
        "challenge_id": challenge["id"],
        "type": challenge["type"],
        "tier": challenge.get("tier", 1),
        "prompt_preview": challenge["prompt"][:100],
        "answer": answer,
        "method": method,
        "status": result.get("status", "unknown") if result else "failed",
        "submission_count": result.get("submission_count", 0) if result else 0,
    })

    # Keep last 200 entries
    if len(logs) > 200:
        logs = logs[-200:]

    with open(LOG_PATH, "w") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)


# ─── Main ───

def main():
    parser = argparse.ArgumentParser(description="ClawChain Mining — Query challenges, solve, and submit answers")
    parser.add_argument("--max", type=int, default=None, help="Max challenges to process this run")
    parser.add_argument("--dry-run", action="store_true", help="Solve only, do not submit")
    parser.add_argument("--type", default=None, help="Only process challenges of this type")
    parser.add_argument("--two-phase", action="store_true", help="Force commit-reveal two-phase submission")
    parser.add_argument("--reveal-delay", type=int, default=3, help="Seconds to wait between commit and reveal (default: 3)")
    args = parser.parse_args()

    config = load_config()
    rpc_url = resolve_rpc_url(config)
    warn_insecure_rpc(rpc_url)

    miner_addr = config.get("miner_address", "")
    miner_name = config.get("miner_name", "openclaw-miner")
    max_challenges = args.max or config.get("max_challenges_per_run", 5)
    use_two_phase = args.two_phase or config.get("use_two_phase", False)

    if not miner_addr:
        print("❌ Miner address not configured. Run first: python3 scripts/setup.py")
        sys.exit(1)

    # Version check
    print(f"🔧 Miner version: {MINER_VERSION}")
    if not check_server_version(rpc_url):
        print("❌ Miner version incompatible. Please upgrade.")
        sys.exit(1)

    # Check registration
    if not check_miner_registered(rpc_url, miner_addr):
        print("📝 Miner not registered, auto-registering...")
        if not auto_register(rpc_url, miner_addr, miner_name):
            print("❌ Registration failed, exiting")
            sys.exit(1)
        print("✅ Registration successful")

    # Query challenges
    print("🔍 Querying pending challenges...")
    challenges = query_pending_challenges(rpc_url)

    if not challenges:
        print("📭 No pending challenges")
        return

    # Filter by type
    if args.type:
        challenges = [c for c in challenges if c["type"] == args.type]

    # Filter already submitted
    challenges = [c for c in challenges if miner_addr not in (c.get("reveals") or {})]

    if not challenges:
        print("📭 No processable challenges (all already submitted)")
        return

    # Limit count
    challenges = challenges[:max_challenges]

    print(f"📦 Processing {len(challenges)} challenge(s)")

    solved = 0
    failed = 0

    for ch in challenges:
        cid = ch["id"]
        ctype = ch["type"]
        tier = ch.get("tier", 1)
        tier_label = {1: "⭐ Basic", 2: "⭐⭐ Intermediate", 3: "⭐⭐⭐ Advanced"}.get(tier, f"T{tier}")

        print(f"\n🎯 [{cid}] {ctype} ({tier_label})")
        prompt_preview = ch["prompt"][:80] + "..." if len(ch["prompt"]) > 80 else ch["prompt"]
        print(f"   Prompt: {prompt_preview}")

        # Solve
        answer, method = solve_challenge(ch, config)

        if not answer:
            print("   ❌ Failed to solve")
            failed += 1
            log_result(ch, None, None, None)
            continue

        print(f"   💡 Answer: {answer[:60]}{'...' if len(answer) > 60 else ''} ({method})")

        if args.dry_run:
            print("   🏷️ Dry-run mode, not submitting")
            continue

        # Submit: try direct first, fall back to two-phase if needed
        result = None
        if use_two_phase:
            print("   🔐 Using commit-reveal two-phase submission")
            result = submit_two_phase(rpc_url, cid, miner_addr, answer, args.reveal_delay)
        else:
            result = submit_answer(rpc_url, cid, miner_addr, answer)
            if result is None:
                print("   🔐 Direct submit failed, trying commit-reveal")
                result = submit_two_phase(rpc_url, cid, miner_addr, answer, args.reveal_delay)

        if result:
            if result.get("already_submitted") or result.get("already_revealed"):
                print("   ⏭️ Already submitted")
            elif result.get("expired"):
                print("   ⏰ Challenge expired")
            elif result.get("success"):
                status = result.get("status", "")
                count = result.get("submission_count", 0)
                required = result.get("required_submissions", 3)
                print(f"   ✅ Submitted ({count}/{required}) Status: {status}")
                solved += 1

                # Verify commitment if settlement happened
                verification = result.get("verification")
                if verification:
                    mode = verification.get("verification_mode", "unknown")
                    commitment = verification.get("commitment", "")
                    revealed = verification.get("revealed_answer", "")
                    salt = verification.get("salt", "")
                    if commitment and salt:
                        valid = verify_commitment(cid, revealed, salt, commitment)
                        if valid:
                            print(f"   🔒 Commitment verified ✓ (mode: {mode})")
                        elif valid is False:
                            print(f"   ⚠️ COMMITMENT VERIFICATION FAILED! Server may be dishonest.")
                    else:
                        print(f"   ℹ️ Verification mode: {mode}")
            else:
                print("   ❌ Submission failed")
                failed += 1
        else:
            failed += 1

        log_result(ch, answer, result, method)

    # Summary
    print(f"\n{'='*40}")
    print(f"✅ Done | Solved: {solved} | Failed: {failed} | Total: {len(challenges)}")


if __name__ == "__main__":
    main()
