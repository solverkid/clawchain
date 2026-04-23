#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPT_DIR = ROOT / "skill" / "scripts"
if str(SKILL_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPT_DIR))

from setup import generate_wallet  # noqa: E402


DEFAULT_BUILD_DIR = ROOT / "build" / "three-lane"
DEFAULT_MANIFEST_PATH = DEFAULT_BUILD_DIR / "miners-33.json"
DEFAULT_STATUS_PATH = DEFAULT_BUILD_DIR / "status.json"
DEFAULT_NAMESPACE = "three-lane-local-v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def deterministic_private_key(namespace: str, index: int) -> str:
    return hashlib.sha256(f"{namespace}:{index}".encode("utf-8")).hexdigest()


def build_manifest(*, count: int = 33, namespace: str = DEFAULT_NAMESPACE) -> dict[str, Any]:
    miners: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        wallet = generate_wallet(private_key_override=deterministic_private_key(namespace, index))
        address = wallet["address"]
        miners.append(
            {
                "index": index,
                "name": f"lane-miner-{index:02d}",
                "address": address,
                "public_key": wallet["public_key"],
                "private_key": wallet["private_key"],
                "economic_unit_id": f"eu:{address}",
                "poker_mtt_user_id": address,
                "arena_miner_id": address,
            }
        )
    payload = {
        "schema_version": "clawchain.three_lane_manifest.v1",
        "namespace": namespace,
        "count": count,
        "created_at": isoformat_z(utc_now()),
        "miners": miners,
    }
    payload["manifest_root"] = hash_payload(
        _manifest_identity_rows(payload)
    )
    return payload


def _manifest_identity_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "index": item["index"],
            "address": item["address"],
            "public_key": item["public_key"],
            "economic_unit_id": item["economic_unit_id"],
        }
        for item in manifest["miners"]
    ]


def refresh_manifest_root(manifest: dict[str, Any]) -> dict[str, Any]:
    manifest["manifest_root"] = hash_payload(_manifest_identity_rows(manifest))
    return manifest


def persist_manifest(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    refresh_manifest_root(manifest)
    ensure_parent(path)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_or_create_manifest(path: Path = DEFAULT_MANIFEST_PATH, *, count: int = 33, namespace: str = DEFAULT_NAMESPACE) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    payload = build_manifest(count=count, namespace=namespace)
    return persist_manifest(path, payload)


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def requests_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


def wait_for_http(url: str, *, timeout_seconds: float = 60.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=2.0)
            if 200 <= response.status_code < 300:
                return
            last_error = RuntimeError(f"http {response.status_code}")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"timeout waiting for {url}: {last_error}")


def register_manifest_miners(
    *,
    base_url: str,
    manifest: dict[str, Any],
    log_path: Path | None = None,
    manifest_path: Path | None = None,
    request_timeout_seconds: float = 10.0,
) -> list[dict[str, Any]]:
    session = requests_session()
    registered: list[dict[str, Any]] = []
    manifest_updated = False
    for miner in manifest["miners"]:
        get_response = session.get(
            f"{base_url}/clawchain/miner/{miner['address']}",
            timeout=request_timeout_seconds,
        )
        if get_response.status_code == 200:
            body = get_response.json()
            effective_economic_unit_id = body.get("economic_unit_id") or miner["economic_unit_id"]
            if effective_economic_unit_id != miner["economic_unit_id"]:
                miner["economic_unit_id"] = effective_economic_unit_id
                manifest_updated = True
            record = {
                "at": isoformat_z(utc_now()),
                "event": "miner_registered",
                "miner_address": miner["address"],
                "http_status": get_response.status_code,
                "economic_unit_id": effective_economic_unit_id,
                "response_id": body.get("id") or body.get("address") or miner["address"],
                "sync_source": "existing",
            }
            registered.append(record)
            if log_path is not None:
                append_jsonl(log_path, record)
            continue
        if get_response.status_code != 404:
            raise RuntimeError(
                f"get miner failed {miner['address']}: {get_response.status_code} {get_response.text}"
            )
        payload = {
            "address": miner["address"],
            "name": miner["name"],
            "public_key": miner["public_key"],
            "miner_version": "0.4.0",
            "economic_unit_id": miner["economic_unit_id"],
        }
        response = session.post(
            f"{base_url}/clawchain/miner/register",
            json=payload,
            timeout=request_timeout_seconds,
        )
        if response.status_code not in {200, 409}:
            raise RuntimeError(f"register miner failed {miner['address']}: {response.status_code} {response.text}")
        body = response.json()
        effective_economic_unit_id = body.get("economic_unit_id") or miner["economic_unit_id"]
        if response.status_code == 409:
            refresh_response = session.get(
                f"{base_url}/clawchain/miner/{miner['address']}",
                timeout=request_timeout_seconds,
            )
            if refresh_response.status_code != 200:
                raise RuntimeError(
                    f"refresh miner failed {miner['address']}: {refresh_response.status_code} {refresh_response.text}"
                )
            body = refresh_response.json()
            effective_economic_unit_id = body.get("economic_unit_id") or effective_economic_unit_id
        if effective_economic_unit_id != miner["economic_unit_id"]:
            miner["economic_unit_id"] = effective_economic_unit_id
            manifest_updated = True
        record = {
            "at": isoformat_z(utc_now()),
            "event": "miner_registered",
            "miner_address": miner["address"],
            "http_status": response.status_code,
            "economic_unit_id": effective_economic_unit_id,
            "response_id": body.get("id") or body.get("address") or miner["address"],
            "sync_source": "registered" if response.status_code == 200 else "already_registered",
        }
        registered.append(record)
        if log_path is not None:
            append_jsonl(log_path, record)
    if manifest_updated and manifest_path is not None:
        persist_manifest(manifest_path, manifest)
    return registered


def write_status(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
