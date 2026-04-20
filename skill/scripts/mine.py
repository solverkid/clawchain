#!/usr/bin/env python3
"""
ClawChain Forecast Miner
Fetch active forecast tasks → commit probability → reveal probability.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("❌ Required: pip install requests")
    sys.exit(1)

from eth_keys import keys as eth_keys

SCRIPT_DIR = Path(__file__).parent
ROOT = SCRIPT_DIR.parent.parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
DATA_DIR = SCRIPT_DIR.parent / "data"
LOG_PATH = DATA_DIR / "mining_log.json"

sys.path.insert(0, str(SCRIPT_DIR))
from wallet_crypto import load_wallet as crypto_load_wallet

sys.path.insert(0, str(ROOT / "mining-service"))
from forecast_engine import build_signature_hash, clamp_bps, compute_commit_hash, ForecastSettings

MINER_VERSION = "0.4.0"
DEFAULT_CODEX_MODEL = "gpt-5.4-mini"
DEFAULT_CODEX_TIMEOUT_SECONDS = 120
DEFAULT_CODEX_PARALLEL_TASKS = 2
DEFAULT_REQUEST_TIMEOUT_SECONDS = 35
DEFAULT_CODEX_MIN_COMMIT_TIME_REMAINING_SECONDS = 90
DEFAULT_MIN_COMMIT_TIME_REMAINING_SECONDS = 1

DATA_DIR.mkdir(exist_ok=True)
LOG_LOCK = threading.Lock()


def load_config():
    if not CONFIG_PATH.exists():
        print(f"❌ Config file not found: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    if "rpc_url" not in config:
        print("❌ 'rpc_url' not set in config.json")
        sys.exit(1)
    return config


def warn_insecure_rpc(url):
    parsed = urlparse(url)
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        print(f"⚠️  SECURITY WARNING: RPC endpoint uses plain HTTP ({url}). Use HTTPS for production.")


def derive_public_key(private_key_hex):
    return eth_keys.PrivateKey(bytes.fromhex(private_key_hex)).public_key.to_bytes().hex()


def sign_parts(private_key_hex, parts):
    msg_hash = build_signature_hash(parts)
    signature = eth_keys.PrivateKey(bytes.fromhex(private_key_hex)).sign_msg_hash(msg_hash)
    return signature.to_bytes().hex()


def load_wallet(wallet_path, passphrase=None):
    return crypto_load_wallet(wallet_path, passphrase=passphrase)


def resolve_request_timeout(config=None):
    config = config or {}
    return int(
        config.get("request_timeout_seconds")
        or os.getenv("CLAWCHAIN_MINER_REQUEST_TIMEOUT_SECONDS")
        or DEFAULT_REQUEST_TIMEOUT_SECONDS
    )


def resolve_min_commit_time_remaining(config=None):
    config = config or {}
    if config.get("min_commit_time_remaining_seconds") is not None:
        return max(0, int(config["min_commit_time_remaining_seconds"]))
    if os.getenv("CLAWCHAIN_MINER_MIN_COMMIT_TIME_REMAINING_SECONDS"):
        return max(0, int(os.environ["CLAWCHAIN_MINER_MIN_COMMIT_TIME_REMAINING_SECONDS"]))
    if str(config.get("forecast_mode") or "heuristic_v1").strip() == "codex_v1":
        return DEFAULT_CODEX_MIN_COMMIT_TIME_REMAINING_SECONDS
    return DEFAULT_MIN_COMMIT_TIME_REMAINING_SECONDS


def commit_time_remaining_seconds(task, now=None):
    current = now or datetime.now(timezone.utc)
    return (parse_time(task["commit_deadline"]) - current).total_seconds()


def check_miner_registered(rpc_url, address, config=None):
    try:
        resp = requests.get(f"{rpc_url}/clawchain/miner/{address}", timeout=resolve_request_timeout(config))
        return resp.status_code == 200
    except Exception:
        return False


def auto_register(rpc_url, wallet, name, config=None):
    payload = {
        "address": wallet["address"],
        "name": name,
        "public_key": derive_public_key(wallet["private_key"]),
        "miner_version": MINER_VERSION,
    }
    try:
        resp = requests.post(
            f"{rpc_url}/clawchain/miner/register",
            json=payload,
            timeout=resolve_request_timeout(config),
        )
        if resp.status_code == 409:
            return True
        resp.raise_for_status()
        return True
    except Exception as exc:
        print(f"⚠️ Auto-registration failed: {exc}")
        return False


def get_active_tasks(rpc_url, config=None):
    try:
        resp = requests.get(f"{rpc_url}/v1/task-runs/active", timeout=resolve_request_timeout(config))
        resp.raise_for_status()
        return resp.json()["data"]["items"]
    except Exception as exc:
        print(f"⚠️ Failed to fetch active tasks: {exc}")
        return []


def get_task_detail(rpc_url, task_run_id, config=None):
    try:
        resp = requests.get(
            f"{rpc_url}/v1/forecast/task-runs/{task_run_id}",
            timeout=resolve_request_timeout(config),
        )
        resp.raise_for_status()
        return resp.json()["data"]
    except Exception as exc:
        print(f"⚠️ Failed to fetch task detail {task_run_id}: {exc}")
        return None


def post_commit(rpc_url, task_run_id, payload, config=None):
    resp = requests.post(
        f"{rpc_url}/v1/task-runs/{task_run_id}/commit",
        json=payload,
        timeout=resolve_request_timeout(config),
    )
    if resp.status_code == 409:
        return {"already": True, **resp.json()}
    resp.raise_for_status()
    return resp.json()


def post_reveal(rpc_url, task_run_id, payload, config=None):
    resp = requests.post(
        f"{rpc_url}/v1/task-runs/{task_run_id}/reveal",
        json=payload,
        timeout=resolve_request_timeout(config),
    )
    if resp.status_code == 409:
        return {"already": True, **resp.json()}
    resp.raise_for_status()
    return resp.json()


def compute_heuristic_prediction(task):
    baseline = int(task["baseline_q_bps"])
    pack = task["pack_json"]
    binance = pack.get("binance_snapshot", {})
    polymarket = pack.get("polymarket_snapshot", {})

    depth_imbalance = int(binance.get("depth_imbalance_bps", binance.get("imbalance_bps", 0)))
    trade_imbalance = int(binance.get("trade_imbalance_bps", 0))
    micro_move = float(binance.get("micro_move_bps", 0))

    yes_volume = int(polymarket.get("yes_volume", 0))
    no_volume = int(polymarket.get("no_volume", 0))
    volume_skew = 0.0
    if yes_volume + no_volume > 0:
        volume_skew = (yes_volume - no_volume) / (yes_volume + no_volume)

    pm_q_yes = int(polymarket.get("q_yes_bps", baseline))
    pm_edge = pm_q_yes - baseline

    raw = (
        baseline
        + int(depth_imbalance * 0.10)
        + int(trade_imbalance * 0.08)
        + int(micro_move * 20)
        + int(volume_skew * 500)
        + int(pm_edge * 0.20)
    )
    settings = ForecastSettings()
    return {
        "p_yes_bps": clamp_bps(raw, settings),
        "provider": "heuristic_v1",
        "model": None,
        "reason": "weighted blend of baseline, microstructure, and Polymarket edge",
    }


def _codex_output_schema() -> str:
    return json.dumps(
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["p_yes_bps", "reason", "confidence"],
            "properties": {
                "p_yes_bps": {"type": "integer", "minimum": 0, "maximum": 10000},
                "reason": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
        }
    )


def _write_temp_codex_schema() -> str:
    with tempfile.NamedTemporaryFile("w", prefix="forecast-codex-schema-", suffix=".json", delete=False) as handle:
        handle.write(_codex_output_schema())
        return handle.name


def _codex_prompt(system_prompt, user_prompt):
    return "\n".join(
        [
            "SYSTEM:",
            system_prompt.strip(),
            "",
            "USER:",
            user_prompt.strip(),
            "",
            "Return only JSON that satisfies the provided schema.",
        ]
    )


def _codex_system_prompt() -> str:
    return (
        "You are an AI crypto prediction miner. "
        "Estimate the probability, in basis points, that the positive Polymarket outcome will resolve true "
        "by the end of the current short-horizon market window. "
        "Use the frozen Binance and Polymarket snapshots as your only evidence. "
        "thin or wide Polymarket books are weak evidence, but do not ignore them completely. "
        "Do not swing far from 5000 based on Binance flow alone when price action is flat or signals disagree. "
        "When Polymarket is not thin and at least two independent signals align, larger moves away from 5000 are acceptable. "
        "Only move decisively away from 5000 when multiple signals align. "
        "Prefer calibrated probabilities over bold directional calls. "
        "Do not copy the market midpoint mechanically; produce an independent estimate. "
        "Output exactly one JSON object with p_yes_bps and reason."
    )


def directional_vote(value, threshold):
    if value >= threshold:
        return 1
    if value <= -threshold:
        return -1
    return 0


def build_signal_calibration(task):
    pack = task.get("pack_json", {})
    polymarket = pack.get("polymarket_snapshot", {})
    binance = pack.get("binance_snapshot", {})
    spread_bps = float(polymarket.get("spread_bps") or 0.0)
    volume24hr_clob = float(polymarket.get("volume24hr_clob") or 0.0)
    liquidity_clob = float(polymarket.get("liquidity_clob") or 0.0)
    micro_move_bps = float(binance.get("micro_move_bps") or 0.0)
    depth_imbalance_bps = int(binance.get("depth_imbalance_bps", binance.get("imbalance_bps", 0)) or 0)
    trade_imbalance_bps = int(binance.get("trade_imbalance_bps") or 0)
    pm_book_is_thin = spread_bps >= 5000 or volume24hr_clob < 100 or liquidity_clob < 25000
    flat_price_action = abs(micro_move_bps) <= 1.0
    one_sided_binance_flow = abs(depth_imbalance_bps) >= 5000 or abs(trade_imbalance_bps) >= 5000
    pm_q_yes_bps = int(polymarket.get("q_yes_bps") or task.get("baseline_q_bps") or 5000)
    return {
        "spread_bps": spread_bps,
        "volume24hr_clob": volume24hr_clob,
        "liquidity_clob": liquidity_clob,
        "micro_move_bps": micro_move_bps,
        "depth_imbalance_bps": depth_imbalance_bps,
        "trade_imbalance_bps": trade_imbalance_bps,
        "pm_q_yes_bps": pm_q_yes_bps,
        "pm_book_is_thin": pm_book_is_thin,
        "pm_signal_reliability": "low" if pm_book_is_thin else "normal",
        "flat_price_action": flat_price_action,
        "one_sided_binance_flow": one_sided_binance_flow,
        "pm_direction_vote": 0 if pm_book_is_thin else directional_vote(pm_q_yes_bps - 5000, 150),
        "price_direction_vote": directional_vote(micro_move_bps, 1.5),
        "depth_direction_vote": directional_vote(depth_imbalance_bps, 2500),
        "trade_direction_vote": directional_vote(trade_imbalance_bps, 2500),
    }


def _codex_user_prompt(task) -> str:
    calibration = build_signal_calibration(task)
    pack = task.get("pack_json", {})
    polymarket = pack.get("polymarket_snapshot", {})
    binance = pack.get("binance_snapshot", {})
    payload = {
        "task_run_id": task.get("task_run_id"),
        "asset": task.get("asset"),
        "publish_at": task.get("publish_at"),
        "commit_deadline": task.get("commit_deadline"),
        "reveal_deadline": task.get("reveal_deadline"),
        "resolve_at": task.get("resolve_at"),
        "baseline_q_bps": task.get("baseline_q_bps"),
        "snapshot_source": pack.get("snapshot_source"),
        "snapshot_frozen_at": pack.get("snapshot_frozen_at"),
        "polymarket_snapshot": {
            "question": polymarket.get("question"),
            "slug": polymarket.get("slug"),
            "positive_outcome": polymarket.get("positive_outcome"),
            "q_yes_bps": polymarket.get("q_yes_bps"),
            "best_bid": polymarket.get("best_bid"),
            "best_ask": polymarket.get("best_ask"),
            "spread_bps": polymarket.get("spread_bps"),
            "volume24hr_clob": polymarket.get("volume24hr_clob"),
            "liquidity_clob": polymarket.get("liquidity_clob"),
        },
        "binance_snapshot": {
            "best_bid": binance.get("best_bid"),
            "best_ask": binance.get("best_ask"),
            "mid_price": binance.get("mid_price"),
            "micro_price": binance.get("micro_price"),
            "micro_move_bps": calibration["micro_move_bps"],
            "depth_imbalance_bps": calibration["depth_imbalance_bps"],
            "trade_imbalance_bps": calibration["trade_imbalance_bps"],
            "top_bid_notional": binance.get("top_bid_notional"),
            "top_ask_notional": binance.get("top_ask_notional"),
        },
        "market_context": pack.get("market_context"),
        "noisy_fragments": pack.get("noisy_fragments"),
        "signal_calibration": {
            "short_horizon_seconds": int(
                max(
                    0.0,
                    (parse_time(task.get("resolve_at")) - parse_time(task.get("publish_at"))).total_seconds(),
                )
            )
            if task.get("resolve_at") and task.get("publish_at")
            else None,
            "pm_book_is_thin": calibration["pm_book_is_thin"],
            "pm_signal_reliability": calibration["pm_signal_reliability"],
            "flat_price_action": calibration["flat_price_action"],
            "one_sided_binance_flow": calibration["one_sided_binance_flow"],
            "pm_direction_vote": calibration["pm_direction_vote"],
            "price_direction_vote": calibration["price_direction_vote"],
            "depth_direction_vote": calibration["depth_direction_vote"],
            "trade_direction_vote": calibration["trade_direction_vote"],
            "guidance": (
                "If Polymarket is thin and price action is flat, stay closer to 5000 unless multiple signals align. "
                "If Polymarket is not thin and at least two signals agree, larger moves away from 5000 are allowed."
            ),
        },
        "output_requirements": {
            "p_yes_bps_range": [1500, 8500],
            "return_fields": ["p_yes_bps", "reason", "confidence"],
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def compute_codex_prediction(task, config):
    binary = str(config.get("codex_binary") or os.getenv("CODEX_BINARY") or "codex").strip() or "codex"
    model = str(config.get("codex_model") or os.getenv("CODEX_MODEL") or DEFAULT_CODEX_MODEL).strip() or DEFAULT_CODEX_MODEL
    working_dir = str(config.get("codex_working_dir") or ROOT)
    timeout_seconds = int(
        config.get("codex_timeout_seconds")
        or os.getenv("CODEX_TIMEOUT_SECONDS")
        or DEFAULT_CODEX_TIMEOUT_SECONDS
    )

    schema_path = _write_temp_codex_schema()
    try:
        with tempfile.NamedTemporaryFile("w", prefix="forecast-codex-output-", suffix=".json", delete=False) as output_handle:
            output_path = output_handle.name
        try:
            cmd = [
                binary,
                "exec",
                "--skip-git-repo-check",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "-m",
                model,
                "-C",
                working_dir,
                "--output-schema",
                schema_path,
                "-o",
                output_path,
                "-",
            ]
            completed = subprocess.run(
                cmd,
                input=_codex_prompt(_codex_system_prompt(), _codex_user_prompt(task)),
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip() or "unknown codex error"
                raise RuntimeError(f"codex exec failed: {detail}")

            with open(output_path) as handle:
                payload = json.load(handle)
        finally:
            try:
                os.remove(output_path)
            except OSError:
                pass
    finally:
        try:
            os.remove(schema_path)
        except OSError:
            pass

    if not isinstance(payload, dict):
        raise RuntimeError("codex output was not a JSON object")

    try:
        p_yes_bps = int(payload["p_yes_bps"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("codex output missing integer p_yes_bps") from exc

    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise RuntimeError("codex output missing reason")

    result = {
        "p_yes_bps": p_yes_bps,
        "provider": "codex_cli",
        "model": model,
        "reason": reason,
    }
    if payload.get("confidence") is not None:
        try:
            result["confidence"] = float(payload["confidence"])
        except (TypeError, ValueError):
            pass
    return result


def apply_codex_aggression_profile(task, prediction):
    p_yes_bps = int(prediction["p_yes_bps"])
    if prediction.get("confidence") is None:
        prediction["aggression_tier"] = "uncalibrated"
        prediction["aggression_cap_bps"] = None
        prediction["aligned_signal_count"] = None
        prediction["conflicting_signal_count"] = None
        return prediction

    direction = directional_vote(p_yes_bps - 5000, 1)
    if direction == 0:
        prediction["aggression_tier"] = "neutral"
        prediction["aggression_cap_bps"] = 0
        prediction["aligned_signal_count"] = 0
        prediction["conflicting_signal_count"] = 0
        return prediction

    calibration = build_signal_calibration(task)
    confidence = float(prediction.get("confidence") or 0.5)
    signal_votes = [
        calibration["pm_direction_vote"],
        calibration["price_direction_vote"],
        calibration["depth_direction_vote"],
        calibration["trade_direction_vote"],
    ]
    aligned_signal_count = sum(1 for vote in signal_votes if vote == direction)
    conflicting_signal_count = sum(1 for vote in signal_votes if vote == -direction)

    if (
        confidence >= 0.80
        and aligned_signal_count >= 3
        and conflicting_signal_count == 0
        and not calibration["pm_book_is_thin"]
    ):
        aggression_tier = "high"
        aggression_cap_bps = 1400
    elif (
        confidence >= 0.65
        and aligned_signal_count >= 2
        and conflicting_signal_count <= 1
        and not (calibration["pm_book_is_thin"] and calibration["flat_price_action"])
    ):
        aggression_tier = "medium"
        aggression_cap_bps = 800
    else:
        aggression_tier = "low"
        aggression_cap_bps = 300

    if calibration["flat_price_action"] and aligned_signal_count < 2:
        aggression_tier = "low"
        aggression_cap_bps = min(aggression_cap_bps, 300)
    if calibration["pm_book_is_thin"] and aligned_signal_count < 3:
        aggression_tier = "low"
        aggression_cap_bps = min(aggression_cap_bps, 300)
    if conflicting_signal_count >= 2:
        aggression_tier = "low"
        aggression_cap_bps = min(aggression_cap_bps, 250)

    centered_move_bps = min(abs(p_yes_bps - 5000), aggression_cap_bps)
    prediction["p_yes_bps"] = 5000 + direction * centered_move_bps
    prediction["aggression_tier"] = aggression_tier
    prediction["aggression_cap_bps"] = aggression_cap_bps
    prediction["aligned_signal_count"] = aligned_signal_count
    prediction["conflicting_signal_count"] = conflicting_signal_count
    return prediction


def compute_prediction(task, config=None):
    config = config or {}
    forecast_mode = str(config.get("forecast_mode") or "heuristic_v1").strip() or "heuristic_v1"
    if forecast_mode == "codex_v1":
        prediction = compute_codex_prediction(task, config)
        prediction = apply_codex_aggression_profile(task, prediction)
    else:
        prediction = compute_heuristic_prediction(task)

    settings = ForecastSettings()
    prediction["p_yes_bps"] = clamp_bps(int(prediction["p_yes_bps"]), settings)
    return prediction


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def append_log(record):
    with LOG_LOCK:
        logs = []
        if LOG_PATH.exists():
            try:
                with open(LOG_PATH) as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        logs.append(record)
        logs = logs[-200:]
        with open(LOG_PATH, "w") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)


def select_tasks_for_iteration(tasks, max_fast_tasks, include_daily=True):
    daily_tasks = [task for task in tasks if task["lane"] == "daily_anchor"]
    fast_tasks = [task for task in tasks if task["lane"] == "forecast_15m"]
    if include_daily:
        return daily_tasks + fast_tasks[:max_fast_tasks]
    return fast_tasks[:max_fast_tasks]


def resolve_parallel_tasks(config, max_fast_tasks, explicit_parallel_tasks=None):
    if explicit_parallel_tasks is not None:
        return max(1, int(explicit_parallel_tasks))
    if config.get("parallel_tasks") is not None:
        return max(1, int(config["parallel_tasks"]))
    if str(config.get("forecast_mode") or "heuristic_v1").strip() == "codex_v1":
        return max(1, min(int(max_fast_tasks or 1), DEFAULT_CODEX_PARALLEL_TASKS))
    return 1


def mine_selected_tasks(
    rpc_url,
    wallet,
    tasks,
    config=None,
    parallel_tasks=1,
    mine_task_fn=None,
):
    config = config or {}
    worker = mine_task_fn or mine_task
    if not tasks:
        return 0

    max_workers = max(1, min(int(parallel_tasks or 1), len(tasks)))
    if max_workers == 1:
        mined = 0
        for task in tasks:
            if worker(rpc_url, wallet, task, config=config):
                mined += 1
        return mined

    mined = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker, rpc_url, wallet, task, config=config) for task in tasks]
        for future in futures:
            try:
                if future.result():
                    mined += 1
            except Exception as exc:
                print(f"⚠️ Task worker crashed: {exc}")
    return mined


def mine_task(rpc_url, wallet, task_card, config=None):
    config = config or {}
    task = get_task_detail(rpc_url, task_card["task_run_id"], config=config)
    if not task:
        return False

    min_commit_remaining = resolve_min_commit_time_remaining(config)
    remaining = commit_time_remaining_seconds(task)
    if remaining < min_commit_remaining:
        print(
            f"⚠️ Skipping {task['task_run_id']}: "
            f"{remaining:.1f}s before commit deadline, need {min_commit_remaining}s"
        )
        return False

    try:
        prediction = compute_prediction(task, config=config)
    except Exception as exc:
        print(f"⚠️ Prediction failed for {task['task_run_id']}: {exc}")
        return False

    remaining = commit_time_remaining_seconds(task)
    if remaining <= 0:
        print(f"⚠️ Skipping commit for {task['task_run_id']}: commit deadline passed after prediction")
        return False

    p_yes_bps = prediction["p_yes_bps"]
    reveal_nonce = secrets.token_hex(8)
    commit_hash = compute_commit_hash(task["task_run_id"], wallet["address"], p_yes_bps, reveal_nonce)

    commit_request_id = f"req:{task['task_run_id']}:commit:{secrets.token_hex(4)}"
    commit_payload = {
        "request_id": commit_request_id,
        "task_run_id": task["task_run_id"],
        "miner_id": wallet["address"],
        "commit_hash": commit_hash,
        "nonce": reveal_nonce,
        "client_version": f"skill-v{MINER_VERSION}",
        "signature": sign_parts(
            wallet["private_key"],
            [task["task_run_id"], commit_hash, reveal_nonce, wallet["address"], commit_request_id],
        ),
    }

    try:
        post_commit(rpc_url, task["task_run_id"], commit_payload, config=config)
    except Exception as exc:
        print(f"⚠️ Commit failed for {task['task_run_id']}: {exc}")
        return False

    now = datetime.now(timezone.utc)
    remaining = (parse_time(task["reveal_deadline"]) - now).total_seconds()
    if remaining > 1:
        time.sleep(min(1.0, remaining / 2))

    reveal_request_id = f"req:{task['task_run_id']}:reveal:{secrets.token_hex(4)}"
    reveal_payload = {
        "request_id": reveal_request_id,
        "task_run_id": task["task_run_id"],
        "miner_id": wallet["address"],
        "p_yes_bps": p_yes_bps,
        "nonce": reveal_nonce,
        "schema_version": "v1",
        "signature": sign_parts(
            wallet["private_key"],
            [task["task_run_id"], str(p_yes_bps), reveal_nonce, wallet["address"], reveal_request_id],
        ),
    }

    try:
        result = post_reveal(rpc_url, task["task_run_id"], reveal_payload, config=config)
    except Exception as exc:
        print(f"⚠️ Reveal failed for {task['task_run_id']}: {exc}")
        return False

    append_log(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_run_id": task["task_run_id"],
            "asset": task["asset"],
            "lane": task["lane"],
            "p_yes_bps": p_yes_bps,
            "prediction_provider": prediction.get("provider"),
            "prediction_model": prediction.get("model"),
            "prediction_reason": prediction.get("reason"),
            "status": "revealed",
            "reward_eligibility": result["data"]["reward_eligibility"],
        }
    )
    provider = prediction.get("provider") or "unknown"
    print(f"✅ {task['task_run_id']} -> {p_yes_bps} bps via {provider} ({result['data']['reward_eligibility']})")
    return True


def main():
    parser = argparse.ArgumentParser(description="ClawChain Forecast Miner")
    parser.add_argument("--once", action="store_true", help="Run one mining iteration and exit")
    parser.add_argument("--max-tasks", type=int, default=None, help="Max forecast tasks per iteration")
    parser.add_argument("--rpc", default=None, help="RPC URL override")
    parser.add_argument("--wallet-path", default=None, help="Wallet path override")
    parser.add_argument(
        "--forecast-only",
        action="store_true",
        help="Only mine forecast_15m tasks and skip daily_anchor tasks",
    )
    parser.add_argument("--parallel-tasks", type=int, default=None, help="Parallel task workers override")
    args = parser.parse_args()

    config = load_config()
    rpc_url = args.rpc or config["rpc_url"]
    warn_insecure_rpc(rpc_url)

    wallet_path = Path(args.wallet_path or config.get("wallet_path", "~/.clawchain/wallet.json")).expanduser()
    wallet = load_wallet(wallet_path)

    if not check_miner_registered(rpc_url, wallet["address"], config=config):
        if not auto_register(rpc_url, wallet, config.get("miner_name", "openclaw-miner"), config=config):
            sys.exit(1)

    max_fast_tasks = args.max_tasks or config.get("max_tasks_per_run") or config.get("max_challenges_per_run", 2)

    while True:
        tasks = get_active_tasks(rpc_url, config=config)
        selected_tasks = select_tasks_for_iteration(tasks, max_fast_tasks, include_daily=not args.forecast_only)
        parallel_tasks = resolve_parallel_tasks(config, max_fast_tasks, explicit_parallel_tasks=args.parallel_tasks)
        mined = mine_selected_tasks(
            rpc_url,
            wallet,
            selected_tasks,
            config=config,
            parallel_tasks=parallel_tasks,
        )

        if args.once:
            break

        if mined == 0:
            time.sleep(3)
        else:
            time.sleep(1)


if __name__ == "__main__":
    main()
