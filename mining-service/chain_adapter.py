from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib import error as urllib_error
from urllib import request as urllib_request
import weakref


CHAIN_ADAPTER_VERSION = "clawchain.chain_adapter.v1"
FUTURE_MSG_TYPE_URL = "/clawchain.settlement.v1.MsgAnchorSettlementBatch"
TYPED_TX_INTENT_VERSION = "clawchain.typed_tx_intent.v1"
DEFAULT_TYPED_SIGN_MODE = "direct"
DEFAULT_TYPED_BROADCAST_MODE = "sync"
DEFAULT_TYPED_CHAIN_ID = "clawchain-testnet-1"
DEFAULT_TYPED_FEE_AMOUNT = "10uclaw"
DEFAULT_TYPED_GAS_LIMIT = 200000
DEFAULT_TYPED_SIGN_MODE_ENUM = 1
ALLOWED_ANCHOR_SCHEMA_VERSIONS = {"settlement.v1", "clawchain.anchor_payload.v1"}
_SEQUENCE_MISMATCH_RE = re.compile(r"expected\s+(?P<expected>\d+),\s+got\s+(?P<got>\d+)")
_COIN_AMOUNT_RE = re.compile(r"^(?P<amount>\d+)(?P<denom>[a-zA-Z][a-zA-Z0-9/:._-]*)$")
_HASH_VALUE_RE = re.compile(r"^sha256:[^\s]+$")
_CLAWCHAIN_ADDRESS_RE = re.compile(r"^claw1[0-9a-z]+$")
_CLI_BROADCAST_LOCKS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _stable_hash(payload: dict) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _build_typed_tx_intent(*, future_msg: dict, memo: str) -> dict:
    return {
        "version": TYPED_TX_INTENT_VERSION,
        "body": {
            "messages": [future_msg],
            "memo": memo,
            "timeout_height": 0,
        },
        "auth_info_hints": {
            "sign_mode": DEFAULT_TYPED_SIGN_MODE,
            "fee_hint": {
                "amount": DEFAULT_TYPED_FEE_AMOUNT,
                "gas_limit": DEFAULT_TYPED_GAS_LIMIT,
            },
            "signer_hint": {
                "role": "anchor_submitter",
                "account_number_source": "anchor_runtime",
                "sequence_source": "anchor_runtime",
            },
        },
        "sign_doc_hints": {
            "chain_id": DEFAULT_TYPED_CHAIN_ID,
        },
        "broadcast_hint": {
            "mode": DEFAULT_TYPED_BROADCAST_MODE,
        },
    }


def build_anchor_tx_plan(*, anchor_job: dict, settlement_batch: dict) -> dict:
    payload = settlement_batch.get("anchor_payload_json") or {}
    canonical_root = settlement_batch.get("canonical_root") or payload.get("canonical_root")
    memo = f"anchor:v1:{settlement_batch['id']}:{canonical_root}"
    future_msg_value = {
        "settlement_batch_id": settlement_batch["id"],
        "anchor_job_id": anchor_job["id"],
        "lane": settlement_batch.get("lane"),
        "schema_version": settlement_batch.get("anchor_schema_version") or payload.get("schema_version"),
        "policy_bundle_version": payload.get("policy_bundle_version"),
        "canonical_root": canonical_root,
        "anchor_payload_hash": settlement_batch.get("anchor_payload_hash"),
        "reward_window_ids_root": payload.get("reward_window_ids_root"),
        "task_run_ids_root": payload.get("task_run_ids_root"),
        "miner_reward_rows_root": payload.get("miner_reward_rows_root"),
        "window_end_at": settlement_batch.get("window_end_at"),
        "total_reward_amount": settlement_batch.get("total_reward_amount", 0),
    }
    future_msg = {
        "type_url": FUTURE_MSG_TYPE_URL,
        "value": future_msg_value,
    }
    plan_core = {
        "adapter_version": CHAIN_ADAPTER_VERSION,
        "tx_builder_kind": "cosmos_anchor_intent_v1",
        "execution_mode": "build_only",
        "chain_family": "cosmos_sdk",
        "settlement_batch_id": settlement_batch["id"],
        "anchor_job_id": anchor_job["id"],
        "canonical_root": canonical_root,
        "anchor_payload_hash": settlement_batch.get("anchor_payload_hash"),
        "future_msg": future_msg,
        "typed_tx_intent": _build_typed_tx_intent(future_msg=future_msg, memo=memo),
        "fallback_memo": memo,
    }
    return {
        **plan_core,
        "plan_hash": _stable_hash(plan_core),
    }


def normalize_keyring_dir(keyring_dir: str | None, backend: str) -> str | None:
    if not keyring_dir:
        return None
    path = Path(keyring_dir).expanduser()
    if path.name == f"keyring-{backend}":
        path = path.parent
    return str(path)


def _binary_info(binary: str) -> dict:
    if os.sep in binary or binary.startswith("."):
        path = Path(binary).expanduser()
        return {
            "configured": binary,
            "resolved_path": str(path.resolve()) if path.exists() else str(path),
            "available": path.exists(),
        }
    resolved = shutil.which(binary)
    return {
        "configured": binary,
        "resolved_path": resolved or binary,
        "available": resolved is not None,
    }


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def resolve_key_address(*, settings) -> str:
    key_name = getattr(settings, "anchor_key_name", None)
    keyring_dir = normalize_keyring_dir(
        getattr(settings, "anchor_keyring_dir", None),
        getattr(settings, "anchor_keyring_backend", "test"),
    )
    if not key_name or not keyring_dir:
        raise ValueError("anchor key name and keyring dir are required")

    command = [
        getattr(settings, "chain_binary", "clawchaind"),
        "keys",
        "show",
        key_name,
        "-a",
        "--keyring-backend",
        getattr(settings, "anchor_keyring_backend", "test"),
        "--keyring-dir",
        keyring_dir,
    ]
    proc = _run_command(command)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        raise ValueError(stderr or stdout or f"failed to resolve key address for {key_name}")
    address = (proc.stdout or "").strip().splitlines()[-1].strip()
    if not address:
        raise ValueError(f"empty key address for {key_name}")
    return address


def resolve_key_pubkey(*, settings) -> dict:
    key_name = getattr(settings, "anchor_key_name", None)
    keyring_dir = normalize_keyring_dir(
        getattr(settings, "anchor_keyring_dir", None),
        getattr(settings, "anchor_keyring_backend", "test"),
    )
    if not key_name or not keyring_dir:
        raise ValueError("anchor key name and keyring dir are required")

    command = [
        getattr(settings, "chain_binary", "clawchaind"),
        "keys",
        "show",
        key_name,
        "--pubkey",
        "--keyring-backend",
        getattr(settings, "anchor_keyring_backend", "test"),
        "--keyring-dir",
        keyring_dir,
    ]
    proc = _run_command(command)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        raise ValueError(stderr or stdout or f"failed to resolve key pubkey for {key_name}")

    stdout = (proc.stdout or "").strip()
    if not stdout:
        raise ValueError(f"empty key pubkey for {key_name}")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid key pubkey payload for {key_name}") from exc

    type_url = payload.get("@type") or payload.get("type_url")
    key_value = payload.get("key")
    if not type_url or not key_value:
        raise ValueError(f"incomplete key pubkey payload for {key_name}")
    return {
        "@type": type_url,
        "key": key_value,
    }


def _encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varint only supports non-negative values")
    encoded = bytearray()
    while True:
        current = value & 0x7F
        value >>= 7
        if value:
            encoded.append(current | 0x80)
            continue
        encoded.append(current)
        return bytes(encoded)


def _encode_field_key(field_number: int, wire_type: int) -> bytes:
    return _encode_varint((field_number << 3) | wire_type)


def _encode_bytes_field(field_number: int, value: bytes | None) -> bytes:
    if not value:
        return b""
    return _encode_field_key(field_number, 2) + _encode_varint(len(value)) + value


def _encode_string_field(field_number: int, value: str | None) -> bytes:
    if not value:
        return b""
    return _encode_bytes_field(field_number, value.encode("utf-8"))


def _encode_uint64_field(field_number: int, value: int | None) -> bytes:
    if value is None:
        return b""
    int_value = int(value)
    if int_value == 0:
        return b""
    return _encode_field_key(field_number, 0) + _encode_varint(int_value)


def _encode_any(*, type_url: str, value_bytes: bytes) -> bytes:
    return b"".join(
        [
            _encode_string_field(1, type_url),
            _encode_bytes_field(2, value_bytes),
        ]
    )


def _encode_anchor_settlement_msg(message_value: dict) -> bytes:
    return b"".join(
        [
            _encode_string_field(1, message_value.get("submitter")),
            _encode_string_field(2, message_value.get("settlement_batch_id")),
            _encode_string_field(3, message_value.get("anchor_job_id")),
            _encode_string_field(4, message_value.get("lane")),
            _encode_string_field(5, message_value.get("schema_version")),
            _encode_string_field(6, message_value.get("policy_bundle_version")),
            _encode_string_field(7, message_value.get("canonical_root")),
            _encode_string_field(8, message_value.get("anchor_payload_hash")),
            _encode_string_field(9, message_value.get("reward_window_ids_root")),
            _encode_string_field(10, message_value.get("task_run_ids_root")),
            _encode_string_field(11, message_value.get("miner_reward_rows_root")),
            _encode_string_field(12, message_value.get("window_end_at")),
            _encode_uint64_field(13, message_value.get("total_reward_amount")),
        ]
    )


def _validate_anchor_settlement_message_value(message_value: dict) -> None:
    submitter = str(message_value.get("submitter") or "").strip()
    if not _CLAWCHAIN_ADDRESS_RE.fullmatch(submitter):
        raise ValueError("invalid submitter address")
    if not str(message_value.get("settlement_batch_id") or "").strip():
        raise ValueError("settlement_batch_id is required")
    if not str(message_value.get("anchor_job_id") or "").strip():
        raise ValueError("anchor_job_id is required")

    schema_version = str(message_value.get("schema_version") or "").strip()
    if schema_version not in ALLOWED_ANCHOR_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported schema version {schema_version!r}")

    canonical_root = str(message_value.get("canonical_root") or "").strip()
    if not _HASH_VALUE_RE.fullmatch(canonical_root):
        raise ValueError("canonical_root must be a sha256:... value")

    anchor_payload_hash = str(message_value.get("anchor_payload_hash") or "").strip()
    if not _HASH_VALUE_RE.fullmatch(anchor_payload_hash):
        raise ValueError("anchor_payload_hash must be a sha256:... value")


def _encode_typed_message(message: dict) -> bytes:
    type_url = message.get("type_url")
    if type_url != FUTURE_MSG_TYPE_URL:
        raise ValueError(f"unsupported typed message {type_url}")
    value = message.get("value") or {}
    return _encode_any(type_url=type_url, value_bytes=_encode_anchor_settlement_msg(value))


def _encode_tx_body(*, messages: list[dict], memo: str | None, timeout_height: int) -> bytes:
    encoded_messages = [_encode_bytes_field(1, _encode_typed_message(message)) for message in messages]
    return b"".join(
        [
            *encoded_messages,
            _encode_string_field(2, memo),
            _encode_uint64_field(3, timeout_height),
        ]
    )


def _normalize_public_key(public_key: dict) -> dict:
    type_url = public_key.get("@type") or public_key.get("type_url")
    key_base64 = public_key.get("key")
    if type_url != "/cosmos.crypto.secp256k1.PubKey":
        raise ValueError(f"unsupported public key type {type_url}")
    if not key_base64:
        raise ValueError("missing public key bytes")
    key_bytes = base64.b64decode(key_base64)
    value_bytes = _encode_bytes_field(1, key_bytes)
    return {
        "@type": type_url,
        "key": key_base64,
        "value_bytes": value_bytes,
    }


def _encode_mode_info(*, sign_mode: int) -> bytes:
    single_mode = _encode_field_key(1, 0) + _encode_varint(sign_mode)
    return _encode_bytes_field(1, single_mode)


def _parse_coin_amount(coin_amount: str) -> tuple[str, str]:
    match = _COIN_AMOUNT_RE.fullmatch((coin_amount or "").strip())
    if not match:
        raise ValueError(f"invalid coin amount {coin_amount!r}")
    return match.group("amount"), match.group("denom")


def _encode_coin(*, coin_amount: str) -> bytes:
    amount, denom = _parse_coin_amount(coin_amount)
    return b"".join(
        [
            _encode_string_field(1, denom),
            _encode_string_field(2, amount),
        ]
    )


def _encode_fee(*, coin_amount: str, gas_limit: int) -> bytes:
    return b"".join(
        [
            _encode_bytes_field(1, _encode_coin(coin_amount=coin_amount)),
            _encode_uint64_field(2, gas_limit),
        ]
    )


def _encode_signer_info(*, public_key: dict, sequence: int, sign_mode: int) -> bytes:
    normalized_key = _normalize_public_key(public_key)
    return b"".join(
        [
            _encode_bytes_field(
                1,
                _encode_any(type_url=normalized_key["@type"], value_bytes=normalized_key["value_bytes"]),
            ),
            _encode_bytes_field(2, _encode_mode_info(sign_mode=sign_mode)),
            _encode_uint64_field(3, sequence),
        ]
    )


def _encode_auth_info(*, public_key: dict, sequence: int, sign_mode: int, fee_amount: str, gas_limit: int) -> bytes:
    return b"".join(
        [
            _encode_bytes_field(1, _encode_signer_info(public_key=public_key, sequence=sequence, sign_mode=sign_mode)),
            _encode_bytes_field(2, _encode_fee(coin_amount=fee_amount, gas_limit=gas_limit)),
        ]
    )


def _encode_sign_doc(*, body_bytes: bytes, auth_info_bytes: bytes, chain_id: str, account_number: int) -> bytes:
    return b"".join(
        [
            _encode_bytes_field(1, body_bytes),
            _encode_bytes_field(2, auth_info_bytes),
            _encode_string_field(3, chain_id),
            _encode_uint64_field(4, account_number),
        ]
    )


def _encode_tx_raw(*, body_bytes: bytes, auth_info_bytes: bytes) -> bytes:
    return b"".join(
        [
            _encode_bytes_field(1, body_bytes),
            _encode_bytes_field(2, auth_info_bytes),
        ]
    )


def _resolve_typed_messages(*, typed_tx_intent: dict, sender_address: str) -> list[dict]:
    body = typed_tx_intent.get("body") or {}
    messages = []
    for message in body.get("messages") or []:
        resolved_value = dict(message.get("value") or {})
        resolved_value["submitter"] = sender_address
        messages.append(
            {
                "type_url": message.get("type_url"),
                "value": resolved_value,
            }
        )
    if not messages:
        raise ValueError("typed_tx_intent requires at least one message")
    for message in messages:
        if message.get("type_url") == FUTURE_MSG_TYPE_URL:
            _validate_anchor_settlement_message_value(message.get("value") or {})
    return messages


def compile_typed_tx_intent(
    *,
    typed_tx_intent: dict,
    sender_address: str,
    account_number: int,
    sequence: int,
    public_key: dict,
    chain_id: str | None = None,
) -> dict:
    auth_info_hints = typed_tx_intent.get("auth_info_hints") or {}
    sign_mode = auth_info_hints.get("sign_mode") or DEFAULT_TYPED_SIGN_MODE
    if sign_mode != DEFAULT_TYPED_SIGN_MODE:
        raise ValueError(f"unsupported sign mode {sign_mode}")

    fee_hint = auth_info_hints.get("fee_hint") or {}
    fee_amount = fee_hint.get("amount") or DEFAULT_TYPED_FEE_AMOUNT
    gas_limit = int(fee_hint.get("gas_limit") or DEFAULT_TYPED_GAS_LIMIT)
    resolved_chain_id = chain_id or (typed_tx_intent.get("sign_doc_hints") or {}).get("chain_id") or DEFAULT_TYPED_CHAIN_ID

    resolved_messages = _resolve_typed_messages(typed_tx_intent=typed_tx_intent, sender_address=sender_address)
    body = typed_tx_intent.get("body") or {}
    resolved_typed_tx_intent = {
        **typed_tx_intent,
        "body": {
            **body,
            "messages": resolved_messages,
        },
    }

    tx_body_bytes = _encode_tx_body(
        messages=resolved_messages,
        memo=body.get("memo"),
        timeout_height=int(body.get("timeout_height") or 0),
    )
    auth_info_bytes = _encode_auth_info(
        public_key=public_key,
        sequence=sequence,
        sign_mode=DEFAULT_TYPED_SIGN_MODE_ENUM,
        fee_amount=fee_amount,
        gas_limit=gas_limit,
    )
    sign_doc_bytes = _encode_sign_doc(
        body_bytes=tx_body_bytes,
        auth_info_bytes=auth_info_bytes,
        chain_id=resolved_chain_id,
        account_number=account_number,
    )
    unsigned_tx_bytes = _encode_tx_raw(body_bytes=tx_body_bytes, auth_info_bytes=auth_info_bytes)

    return {
        "resolved_typed_tx_intent": resolved_typed_tx_intent,
        "public_key": {
            "@type": public_key.get("@type") or public_key.get("type_url"),
            "key": public_key.get("key"),
        },
        "tx_body_bytes_hex": tx_body_bytes.hex(),
        "auth_info_bytes_hex": auth_info_bytes.hex(),
        "sign_doc_bytes_hex": sign_doc_bytes.hex(),
        "unsigned_tx_bytes_hex": unsigned_tx_bytes.hex(),
        "sign_doc_hash": "sha256:" + hashlib.sha256(sign_doc_bytes).hexdigest(),
        "sign_doc": {
            "chain_id": resolved_chain_id,
            "account_number": int(account_number),
            "sequence": int(sequence),
            "sign_mode": sign_mode,
            "fee_amount": fee_amount,
            "gas_limit": gas_limit,
        },
    }


def build_typed_anchor_signing_material(*, plan: dict, settings, sequence_override: int | None = None) -> dict:
    sender_address = resolve_key_address(settings=settings)
    account_number = resolve_anchor_account_number(settings=settings, sender_address=sender_address)
    sequence = sequence_override
    if sequence is None:
        sequence = resolve_next_sender_sequence(settings=settings, sender_address=sender_address)
    public_key = resolve_key_pubkey(settings=settings)
    return compile_typed_tx_intent(
        typed_tx_intent=plan["typed_tx_intent"],
        sender_address=sender_address,
        account_number=account_number,
        sequence=sequence,
        public_key=public_key,
        chain_id=getattr(settings, "chain_id", DEFAULT_TYPED_CHAIN_ID),
    )


def resolve_typed_broadcast_spec(
    *,
    plan: dict,
    settings,
    unsigned_tx_path: str,
    signed_tx_path: str,
    sequence_override: int | None = None,
) -> dict:
    key_name = getattr(settings, "anchor_key_name", None)
    keyring_dir = normalize_keyring_dir(
        getattr(settings, "anchor_keyring_dir", None),
        getattr(settings, "anchor_keyring_backend", "test"),
    )
    if not key_name or not keyring_dir:
        raise ValueError("anchor CLI broadcaster is not configured")

    source_address = resolve_key_address(settings=settings)
    account_number = resolve_anchor_account_number(settings=settings, sender_address=source_address)
    sequence = sequence_override
    if sequence is None:
        sequence = resolve_next_sender_sequence(settings=settings, sender_address=source_address)

    resolved_messages = _resolve_typed_messages(
        typed_tx_intent=plan["typed_tx_intent"],
        sender_address=source_address,
    )
    message_value = resolved_messages[0]["value"]
    chain_id = getattr(settings, "chain_id", DEFAULT_TYPED_CHAIN_ID)
    keyring_backend = getattr(settings, "anchor_keyring_backend", "test")
    node_rpc = getattr(settings, "chain_node_rpc", "tcp://127.0.0.1:26657")

    generate_command = [
        getattr(settings, "chain_binary", "clawchaind"),
        "tx",
        "settlement",
        "anchor-batch",
        key_name,
        message_value["settlement_batch_id"],
        message_value["anchor_job_id"],
        message_value["canonical_root"],
        message_value["anchor_payload_hash"],
        "--lane",
        message_value.get("lane") or "",
        "--schema-version",
        message_value.get("schema_version") or "",
        "--policy-bundle-version",
        message_value.get("policy_bundle_version") or "",
        "--reward-window-ids-root",
        message_value.get("reward_window_ids_root") or "",
        "--task-run-ids-root",
        message_value.get("task_run_ids_root") or "",
        "--miner-reward-rows-root",
        message_value.get("miner_reward_rows_root") or "",
        "--window-end-at",
        message_value.get("window_end_at") or "",
        "--total-reward-amount",
        str(message_value.get("total_reward_amount") or 0),
        "--keyring-backend",
        keyring_backend,
        "--keyring-dir",
        keyring_dir,
        "--fees",
        getattr(settings, "anchor_fees", DEFAULT_TYPED_FEE_AMOUNT),
        "--gas",
        getattr(settings, "anchor_gas", str(DEFAULT_TYPED_GAS_LIMIT)),
        "--offline",
        "--account-number",
        str(account_number),
        "--sequence",
        str(sequence),
        "--generate-only",
        "--output",
        "json",
    ]
    sign_command = [
        getattr(settings, "chain_binary", "clawchaind"),
        "tx",
        "sign",
        unsigned_tx_path,
        "--from",
        key_name,
        "--chain-id",
        chain_id,
        "--node",
        node_rpc,
        "--keyring-backend",
        keyring_backend,
        "--keyring-dir",
        keyring_dir,
        "--offline",
        "--account-number",
        str(account_number),
        "--sequence",
        str(sequence),
        "--output",
        "json",
        "--output-document",
        signed_tx_path,
    ]
    broadcast_command = [
        getattr(settings, "chain_binary", "clawchaind"),
        "tx",
        "broadcast",
        signed_tx_path,
        "--chain-id",
        chain_id,
        "--node",
        node_rpc,
        "--output",
        "json",
    ]
    return {
        "source_address": source_address,
        "account_number": account_number,
        "sequence": sequence,
        "generate_command": generate_command,
        "sign_command": sign_command,
        "broadcast_command": broadcast_command,
    }


def _rpc_base_url(node_rpc: str) -> str:
    if node_rpc.startswith("tcp://"):
        return "http://" + node_rpc.removeprefix("tcp://")
    if node_rpc.startswith("http://") or node_rpc.startswith("https://"):
        return node_rpc.rstrip("/")
    return "http://" + node_rpc.rstrip("/")


def _rpc_status_url(node_rpc: str) -> str:
    return _rpc_base_url(node_rpc) + "/status"


def _fetch_rpc_status(node_rpc: str, timeout_seconds: float = 2.0) -> dict:
    url = _rpc_status_url(node_rpc)
    request = urllib_request.Request(url, method="GET")
    with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8") or "{}")
    result = payload.get("result") or {}
    sync_info = result.get("sync_info") or {}
    node_info = result.get("node_info") or {}
    return {
        "reachable": True,
        "status_url": url,
        "latest_block_height": sync_info.get("latest_block_height"),
        "catching_up": sync_info.get("catching_up"),
        "network": node_info.get("network"),
        "moniker": node_info.get("moniker"),
    }


def _rpc_jsonrpc(*, node_rpc: str, method: str, params: dict, timeout_seconds: float = 2.0) -> dict:
    request = urllib_request.Request(
        _rpc_base_url(node_rpc),
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8") or "{}")
    if payload.get("error"):
        error_payload = payload["error"]
        message = error_payload.get("message") or str(error_payload)
        detail = error_payload.get("data")
        if detail:
            raise ValueError(f"{message}: {detail}")
        raise ValueError(message)
    return payload


def _normalize_tx_hash_param(tx_hash: str) -> str:
    normalized = (tx_hash or "").strip()
    if not normalized:
        raise ValueError("tx hash is required")
    if normalized.lower().startswith("0x"):
        normalized = normalized[2:]
    try:
        return base64.b64encode(bytes.fromhex(normalized)).decode("ascii")
    except ValueError:
        return normalized


def inspect_broadcast_tx_confirmation(*, settings, tx_hash: str) -> dict:
    try:
        payload = _rpc_jsonrpc(
            node_rpc=getattr(settings, "chain_node_rpc", "tcp://127.0.0.1:26657"),
            method="tx",
            params={
                "hash": _normalize_tx_hash_param(tx_hash),
                "prove": False,
            },
        )
    except ValueError as exc:
        lowered = str(exc).lower()
        if "not found" in lowered:
            return {
                "tx_hash": tx_hash,
                "found": False,
                "confirmation_status": "pending",
                "height": None,
                "code": None,
                "raw_log": "",
            }
        raise

    result = payload.get("result") or {}
    tx_result = result.get("tx_result") or {}
    code = int(tx_result.get("code", 0) or 0)
    raw_log = tx_result.get("log") or tx_result.get("raw_log") or ""
    height = result.get("height")
    return {
        "tx_hash": result.get("hash") or tx_hash,
        "found": True,
        "confirmation_status": "confirmed" if code == 0 else "failed",
        "height": int(height) if height is not None else None,
        "code": code,
        "raw_log": raw_log,
    }


async def inspect_broadcast_tx_confirmation_async(*, settings, tx_hash: str) -> dict:
    return await asyncio.to_thread(inspect_broadcast_tx_confirmation, settings=settings, tx_hash=tx_hash)


def _load_genesis_account_number(*, home_dir: str, sender_address: str) -> int | None:
    genesis_path = Path(home_dir).expanduser() / "config" / "genesis.json"
    if not genesis_path.exists():
        return None
    payload = json.loads(genesis_path.read_text(encoding="utf-8"))
    accounts = (
        payload.get("app_state", {})
        .get("auth", {})
        .get("accounts", [])
    )
    for account in accounts:
        if account.get("address") != sender_address:
            continue
        return int(account.get("account_number", 0) or 0)
    return None


def resolve_anchor_account_number(*, settings, sender_address: str) -> int:
    configured = getattr(settings, "anchor_account_number", None)
    if configured is not None:
        return int(configured)
    keyring_dir = normalize_keyring_dir(
        getattr(settings, "anchor_keyring_dir", None),
        getattr(settings, "anchor_keyring_backend", "test"),
    )
    if keyring_dir:
        account_number = _load_genesis_account_number(home_dir=keyring_dir, sender_address=sender_address)
        if account_number is not None:
            return account_number
    raise ValueError(
        "anchor account number unresolved; configure CLAWCHAIN_ANCHOR_ACCOUNT_NUMBER or provide config/genesis.json under anchor keyring dir"
    )


def _fetch_sender_tx_count(*, node_rpc: str, sender_address: str, timeout_seconds: float = 2.0) -> int:
    payload = _rpc_jsonrpc(
        node_rpc=node_rpc,
        method="tx_search",
        params={
            "query": f"message.sender='{sender_address}'",
            "prove": False,
            "page": "1",
            "per_page": "1",
            "order_by": "desc",
        },
        timeout_seconds=timeout_seconds,
    )
    result = payload.get("result") or {}
    total_count = result.get("total_count")
    if total_count is None:
        raise ValueError("missing total_count from tx_search response")
    return int(total_count)


def resolve_next_sender_sequence(*, settings, sender_address: str) -> int:
    configured = getattr(settings, "anchor_sequence_override", None)
    if configured is not None:
        return int(configured)
    return _fetch_sender_tx_count(
        node_rpc=getattr(settings, "chain_node_rpc", "tcp://127.0.0.1:26657"),
        sender_address=sender_address,
    )


def _sequence_retry_allowed(*, settings) -> bool:
    return bool(getattr(settings, "anchor_offline_signing", True)) and getattr(
        settings, "anchor_sequence_override", None
    ) is None


def _is_sequence_mismatch_error(error_message: str) -> bool:
    lowered = error_message.lower()
    return "sequence mismatch" in lowered or "incorrect account sequence" in lowered


def _extract_expected_sequence(error_message: str) -> int | None:
    match = _SEQUENCE_MISMATCH_RE.search(error_message)
    if not match:
        return None
    return int(match.group("expected"))


def _get_cli_broadcast_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _CLI_BROADCAST_LOCKS.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _CLI_BROADCAST_LOCKS[loop] = lock
    return lock


def resolve_fallback_broadcast_spec(*, plan: dict, settings, sequence_override: int | None = None) -> dict:
    key_name = getattr(settings, "anchor_key_name", None)
    keyring_dir = normalize_keyring_dir(
        getattr(settings, "anchor_keyring_dir", None),
        getattr(settings, "anchor_keyring_backend", "test"),
    )
    if not key_name or not keyring_dir:
        raise ValueError("anchor CLI broadcaster is not configured")

    source_address = resolve_key_address(settings=settings)
    to_address = getattr(settings, "anchor_to_address", None) or source_address
    if not to_address:
        raise ValueError("anchor target address unresolved")

    offline_signing = bool(getattr(settings, "anchor_offline_signing", True))
    account_number = None
    sequence = None
    if offline_signing:
        account_number = resolve_anchor_account_number(settings=settings, sender_address=source_address)
        sequence = sequence_override
        if sequence is None:
            sequence = resolve_next_sender_sequence(settings=settings, sender_address=source_address)

    command = [
        getattr(settings, "chain_binary", "clawchaind"),
        "tx",
        "bank",
        "send",
        key_name,
        to_address,
        getattr(settings, "anchor_amount", "1uclaw"),
        "--chain-id",
        getattr(settings, "chain_id", "clawchain-testnet-1"),
        "--node",
        getattr(settings, "chain_node_rpc", "tcp://127.0.0.1:26657"),
        "--keyring-backend",
        getattr(settings, "anchor_keyring_backend", "test"),
        "--keyring-dir",
        keyring_dir,
        "--fees",
        getattr(settings, "anchor_fees", "10uclaw"),
        "--gas",
        getattr(settings, "anchor_gas", "200000"),
        "--note",
        plan["fallback_memo"],
        "--yes",
        "--output",
        "json",
    ]
    if offline_signing:
        command.extend(
            [
                "--offline",
                "--account-number",
                str(account_number),
                "--sequence",
                str(sequence),
            ]
        )

    return {
        "source_address": source_address,
        "to_address": to_address,
        "offline_signing": offline_signing,
        "account_number": account_number,
        "sequence": sequence,
        "command": command,
    }


def check_cli_broadcast_readiness(*, settings) -> dict:
    backend = getattr(settings, "anchor_keyring_backend", "test")
    normalized_keyring_dir = normalize_keyring_dir(getattr(settings, "anchor_keyring_dir", None), backend)
    binary = _binary_info(getattr(settings, "chain_binary", "clawchaind"))
    report = {
        "adapter_version": CHAIN_ADAPTER_VERSION,
        "chain_id": getattr(settings, "chain_id", "clawchain-testnet-1"),
        "node_rpc": getattr(settings, "chain_node_rpc", "tcp://127.0.0.1:26657"),
        "binary": binary,
        "keyring": {
            "backend": backend,
            "configured_dir": getattr(settings, "anchor_keyring_dir", None),
            "normalized_dir": normalized_keyring_dir,
            "exists": bool(normalized_keyring_dir and Path(normalized_keyring_dir).expanduser().exists()),
        },
        "source_key": {
            "name": getattr(settings, "anchor_key_name", None),
            "address": None,
            "ok": False,
        },
        "target_address": None,
        "target_mode": None,
        "signing": {
            "mode": "offline" if getattr(settings, "anchor_offline_signing", True) else "online",
            "account_number": None,
            "next_sequence": None,
            "ok": not getattr(settings, "anchor_offline_signing", True),
        },
        "rpc": {
            "reachable": False,
            "status_url": _rpc_status_url(getattr(settings, "chain_node_rpc", "tcp://127.0.0.1:26657")),
        },
        "ready": False,
        "warnings": [],
    }

    if binary["available"] and report["source_key"]["name"] and normalized_keyring_dir:
        try:
            source_address = resolve_key_address(settings=settings)
            report["source_key"]["address"] = source_address
            report["source_key"]["ok"] = True
        except ValueError as exc:
            report["source_key"]["error"] = str(exc)
    else:
        if not binary["available"]:
            report["warnings"].append("chain binary not found")
        if not report["source_key"]["name"]:
            report["warnings"].append("anchor key name not configured")
        if not normalized_keyring_dir:
            report["warnings"].append("anchor keyring dir not configured")

    configured_target = getattr(settings, "anchor_to_address", None)
    if configured_target:
        report["target_address"] = configured_target
        report["target_mode"] = "configured"
    elif report["source_key"]["address"]:
        report["target_address"] = report["source_key"]["address"]
        report["target_mode"] = "self_transfer"
        report["warnings"].append("anchor_to_address not configured; using self-transfer fallback target")
    else:
        report["warnings"].append("anchor target address unavailable")

    try:
        report["rpc"] = _fetch_rpc_status(getattr(settings, "chain_node_rpc", "tcp://127.0.0.1:26657"))
    except (urllib_error.URLError, TimeoutError, ValueError, OSError) as exc:
        report["rpc"]["error"] = str(exc)
        report["warnings"].append("chain rpc unreachable")

    if report["source_key"]["ok"] and getattr(settings, "anchor_offline_signing", True):
        try:
            report["signing"]["account_number"] = resolve_anchor_account_number(
                settings=settings,
                sender_address=report["source_key"]["address"],
            )
        except ValueError as exc:
            report["signing"]["account_number_error"] = str(exc)
            report["warnings"].append("anchor account number unresolved")

        if report["rpc"]["reachable"]:
            try:
                report["signing"]["next_sequence"] = resolve_next_sender_sequence(
                    settings=settings,
                    sender_address=report["source_key"]["address"],
                )
            except (urllib_error.URLError, TimeoutError, ValueError, OSError) as exc:
                report["signing"]["sequence_error"] = str(exc)
                report["warnings"].append("anchor sequence unresolved")

        report["signing"]["ok"] = (
            report["signing"]["account_number"] is not None
            and report["signing"]["next_sequence"] is not None
        )

    report["ready"] = bool(
        binary["available"]
        and report["source_key"]["ok"]
        and report["target_address"]
        and report["rpc"]["reachable"]
        and report["signing"]["ok"]
    )
    return report


async def inspect_cli_broadcast_readiness(*, settings) -> dict:
    return await asyncio.to_thread(check_cli_broadcast_readiness, settings=settings)


def build_fallback_broadcast_command(*, plan: dict, settings) -> list[str]:
    return resolve_fallback_broadcast_spec(plan=plan, settings=settings)["command"]


def _execute_cli_broadcast(command: list[str]) -> dict:
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        raise ValueError(stderr or stdout or f"clawchaind exited with {proc.returncode}")
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid clawchaind output: {exc}") from exc
    if int(payload.get("code", 0) or 0) != 0:
        raise ValueError(payload.get("raw_log") or f"broadcast failed with code {payload.get('code')}")
    return {
        "tx_hash": payload.get("txhash") or payload.get("tx_hash"),
        "code": int(payload.get("code", 0) or 0),
        "raw_log": payload.get("raw_log", ""),
    }


def _execute_cli_json_command(command: list[str]) -> dict:
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        raise ValueError(stderr or stdout or f"clawchaind exited with {proc.returncode}")
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid clawchaind output: {exc}") from exc


def _execute_cli_command(command: list[str]) -> None:
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        raise ValueError(stderr or stdout or f"clawchaind exited with {proc.returncode}")


def _write_json_file(path: str, payload: dict) -> None:
    Path(path).write_text(json.dumps(payload), encoding="utf-8")


async def broadcast_anchor_tx_via_cli(*, plan: dict, settings, now) -> dict:
    async with _get_cli_broadcast_lock():
        broadcast_spec = resolve_fallback_broadcast_spec(plan=plan, settings=settings)
        attempt_count = 1
        try:
            result = await asyncio.to_thread(_execute_cli_broadcast, broadcast_spec["command"])
        except ValueError as exc:
            if not (_sequence_retry_allowed(settings=settings) and _is_sequence_mismatch_error(str(exc))):
                raise
            retry_sequence = _extract_expected_sequence(str(exc))
            if retry_sequence is None:
                retry_sequence = resolve_next_sender_sequence(
                    settings=settings,
                    sender_address=broadcast_spec["source_address"],
                )
            if retry_sequence == broadcast_spec["sequence"]:
                raise
            broadcast_spec = resolve_fallback_broadcast_spec(
                plan=plan,
                settings=settings,
                sequence_override=retry_sequence,
            )
            result = await asyncio.to_thread(_execute_cli_broadcast, broadcast_spec["command"])
            attempt_count = 2
    if not result.get("tx_hash"):
        raise ValueError("missing tx hash from clawchaind output")
    return {
        **result,
        "memo": plan["fallback_memo"],
        "broadcast_at": now,
        "account_number": broadcast_spec.get("account_number"),
        "sequence": broadcast_spec.get("sequence"),
        "attempt_count": attempt_count,
        "command": broadcast_spec["command"],
    }


def _run_typed_broadcast_pipeline(*, spec: dict) -> dict:
    unsigned_tx = _execute_cli_json_command(spec["generate_command"])
    _write_json_file(spec["unsigned_tx_path"], unsigned_tx)
    _execute_cli_command(spec["sign_command"])
    return _execute_cli_broadcast(spec["broadcast_command"])


async def broadcast_anchor_tx_via_typed_cli(*, plan: dict, settings, now) -> dict:
    async with _get_cli_broadcast_lock():
        with tempfile.TemporaryDirectory(prefix="clawchain-anchor-typed-") as temp_dir:
            unsigned_tx_path = str(Path(temp_dir) / "unsigned_tx.json")
            signed_tx_path = str(Path(temp_dir) / "signed_tx.json")

            broadcast_spec = resolve_typed_broadcast_spec(
                plan=plan,
                settings=settings,
                unsigned_tx_path=unsigned_tx_path,
                signed_tx_path=signed_tx_path,
            )
            broadcast_spec["unsigned_tx_path"] = unsigned_tx_path
            broadcast_spec["signed_tx_path"] = signed_tx_path
            attempt_count = 1
            try:
                result = await asyncio.to_thread(_run_typed_broadcast_pipeline, spec=broadcast_spec)
            except ValueError as exc:
                if not (_sequence_retry_allowed(settings=settings) and _is_sequence_mismatch_error(str(exc))):
                    raise
                retry_sequence = _extract_expected_sequence(str(exc))
                if retry_sequence is None:
                    retry_sequence = resolve_next_sender_sequence(
                        settings=settings,
                        sender_address=broadcast_spec["source_address"],
                    )
                if retry_sequence == broadcast_spec["sequence"]:
                    raise
                broadcast_spec = resolve_typed_broadcast_spec(
                    plan=plan,
                    settings=settings,
                    unsigned_tx_path=unsigned_tx_path,
                    signed_tx_path=signed_tx_path,
                    sequence_override=retry_sequence,
                )
                broadcast_spec["unsigned_tx_path"] = unsigned_tx_path
                broadcast_spec["signed_tx_path"] = signed_tx_path
                result = await asyncio.to_thread(_run_typed_broadcast_pipeline, spec=broadcast_spec)
                attempt_count = 2

    if not result.get("tx_hash"):
        raise ValueError("missing tx hash from clawchaind output")
    return {
        **result,
        "memo": plan["fallback_memo"],
        "broadcast_at": now,
        "account_number": broadcast_spec.get("account_number"),
        "sequence": broadcast_spec.get("sequence"),
        "attempt_count": attempt_count,
        "broadcast_method": "typed_msg",
        "generate_command": broadcast_spec["generate_command"],
        "sign_command": broadcast_spec["sign_command"],
        "broadcast_command": broadcast_spec["broadcast_command"],
    }
