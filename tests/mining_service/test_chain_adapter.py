from __future__ import annotations

import asyncio
import base64
import binascii
import json
from itertools import count
import subprocess
import sys
import threading
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import chain_adapter


class DummySettings:
    chain_binary = "./clawchaind"
    chain_id = "clawchain-testnet-1"
    chain_node_rpc = "tcp://127.0.0.1:26657"
    anchor_key_name = "val1"
    anchor_keyring_dir = "deploy/testnet-artifacts/val1/keyring-test"
    anchor_keyring_backend = "test"
    anchor_to_address = None
    anchor_amount = "1uclaw"
    anchor_fees = "10uclaw"
    anchor_gas = "200000"
    anchor_account_number = None
    anchor_sequence_override = None
    anchor_offline_signing = True


def sha256_ref(char: str) -> str:
    return "sha256:" + char * 64


def test_normalize_keyring_dir_accepts_backend_subdirectory():
    normalized = chain_adapter.normalize_keyring_dir(
        "deploy/testnet-artifacts/val1/keyring-test",
        "test",
    )

    assert normalized == "deploy/testnet-artifacts/val1"


def test_build_fallback_broadcast_command_defaults_to_self_transfer(monkeypatch):
    monkeypatch.setattr(
        chain_adapter,
        "resolve_key_address",
        lambda *, settings: "claw1q4akpa27mg6zv5zj4njmtvv0fhxyrtgega3564",
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_anchor_account_number",
        lambda *, settings, sender_address: 7,
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_next_sender_sequence",
        lambda *, settings, sender_address: 11,
    )

    command = chain_adapter.build_fallback_broadcast_command(
        plan={"fallback_memo": "anchor:v1:sb:sha256:test"},
        settings=DummySettings(),
    )

    assert command[:5] == ["./clawchaind", "tx", "bank", "send", "val1"]
    assert "deploy/testnet-artifacts/val1" in command
    assert "deploy/testnet-artifacts/val1/keyring-test" not in command
    assert "claw1q4akpa27mg6zv5zj4njmtvv0fhxyrtgega3564" in command
    assert "--note" in command
    assert "--memo" not in command
    assert "--offline" in command
    assert "--account-number" in command
    assert "7" in command
    assert "--sequence" in command
    assert "11" in command


def test_compile_typed_tx_intent_renders_unsigned_tx_and_sign_doc():
    plan = chain_adapter.build_anchor_tx_plan(
        anchor_job={"id": "anchor_job_01"},
        settlement_batch={
            "id": "sb_2026_04_10_0001",
            "lane": "fast",
            "anchor_schema_version": "settlement.v1",
            "canonical_root": sha256_ref("a"),
            "anchor_payload_hash": sha256_ref("b"),
            "window_end_at": "2026-04-10T03:15:00Z",
            "total_reward_amount": 12345,
            "anchor_payload_json": {
                "schema_version": "settlement.v1",
                "policy_bundle_version": "policy.v1",
                "reward_window_ids_root": sha256_ref("c"),
                "task_run_ids_root": sha256_ref("d"),
                "miner_reward_rows_root": sha256_ref("e"),
            },
        },
    )

    signing_material = chain_adapter.compile_typed_tx_intent(
        typed_tx_intent=plan["typed_tx_intent"],
        sender_address="claw1q4akpa27mg6zv5zj4njmtvv0fhxyrtgega3564",
        account_number=7,
        sequence=11,
        public_key={
            "@type": "/cosmos.crypto.secp256k1.PubKey",
            "key": "A7DJKmZ3r7VDILbBs6EuzShUJcNwWW6IvwTl1qMlIrzj",
        },
    )

    resolved_message = signing_material["resolved_typed_tx_intent"]["body"]["messages"][0]
    assert resolved_message["type_url"] == chain_adapter.FUTURE_MSG_TYPE_URL
    assert resolved_message["value"]["submitter"] == "claw1q4akpa27mg6zv5zj4njmtvv0fhxyrtgega3564"
    assert signing_material["sign_doc"]["account_number"] == 7
    assert signing_material["sign_doc"]["sequence"] == 11
    assert signing_material["sign_doc"]["chain_id"] == chain_adapter.DEFAULT_TYPED_CHAIN_ID
    assert signing_material["sign_doc_hash"].startswith("sha256:")
    assert signing_material["tx_body_bytes_hex"]
    assert signing_material["auth_info_bytes_hex"]
    assert signing_material["sign_doc_bytes_hex"]
    assert signing_material["unsigned_tx_bytes_hex"]


def test_compile_typed_tx_intent_rejects_invalid_schema_version():
    plan = chain_adapter.build_anchor_tx_plan(
        anchor_job={"id": "anchor_job_01"},
        settlement_batch={
            "id": "sb_2026_04_10_0001",
            "lane": "fast",
            "anchor_schema_version": "bad-schema",
            "canonical_root": sha256_ref("a"),
            "anchor_payload_hash": sha256_ref("b"),
            "window_end_at": "2026-04-10T03:15:00Z",
            "total_reward_amount": 12345,
            "anchor_payload_json": {
                "schema_version": "bad-schema",
                "policy_bundle_version": "policy.v1",
                "reward_window_ids_root": sha256_ref("c"),
                "task_run_ids_root": sha256_ref("d"),
                "miner_reward_rows_root": sha256_ref("e"),
            },
        },
    )

    try:
        chain_adapter.compile_typed_tx_intent(
            typed_tx_intent=plan["typed_tx_intent"],
            sender_address="claw1q4akpa27mg6zv5zj4njmtvv0fhxyrtgega3564",
            account_number=7,
            sequence=11,
            public_key={
                "@type": "/cosmos.crypto.secp256k1.PubKey",
                "key": "A7DJKmZ3r7VDILbBs6EuzShUJcNwWW6IvwTl1qMlIrzj",
            },
        )
    except ValueError as exc:
        assert "schema version" in str(exc)
    else:
        raise AssertionError("compile_typed_tx_intent should reject invalid schema_version")


def test_resolve_typed_broadcast_spec_rejects_missing_canonical_root(monkeypatch):
    plan = chain_adapter.build_anchor_tx_plan(
        anchor_job={"id": "anchor_job_01"},
        settlement_batch={
            "id": "sb_2026_04_10_0001",
            "lane": "fast",
            "anchor_schema_version": "settlement.v1",
            "canonical_root": "",
            "anchor_payload_hash": sha256_ref("b"),
            "window_end_at": "2026-04-10T03:15:00Z",
            "total_reward_amount": 12345,
            "anchor_payload_json": {
                "schema_version": "settlement.v1",
                "policy_bundle_version": "policy.v1",
                "reward_window_ids_root": sha256_ref("c"),
                "task_run_ids_root": sha256_ref("d"),
                "miner_reward_rows_root": sha256_ref("e"),
            },
        },
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_key_address",
        lambda *, settings: "claw1q4akpa27mg6zv5zj4njmtvv0fhxyrtgega3564",
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_anchor_account_number",
        lambda *, settings, sender_address: 7,
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_next_sender_sequence",
        lambda *, settings, sender_address: 11,
    )

    try:
        chain_adapter.resolve_typed_broadcast_spec(
            plan=plan,
            settings=DummySettings(),
            unsigned_tx_path="/tmp/unsigned.json",
            signed_tx_path="/tmp/signed.json",
        )
    except ValueError as exc:
        assert "canonical_root" in str(exc)
    else:
        raise AssertionError("resolve_typed_broadcast_spec should reject missing canonical_root")


def test_resolve_anchor_account_number_from_genesis(tmp_path):
    home_dir = tmp_path / "anchor-home"
    config_dir = home_dir / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "genesis.json").write_text(
        """
        {
          "app_state": {
            "auth": {
              "accounts": [
                {
                  "@type": "/cosmos.auth.v1beta1.BaseAccount",
                  "address": "claw1anchor",
                  "account_number": "9",
                  "sequence": "0"
                }
              ]
            }
          }
        }
        """.strip()
    )

    class Settings(DummySettings):
        anchor_keyring_dir = str(home_dir)

    account_number = chain_adapter.resolve_anchor_account_number(
        settings=Settings(),
        sender_address="claw1anchor",
    )

    assert account_number == 9


def test_resolve_next_sender_sequence_uses_committed_sender_tx_count(monkeypatch):
    monkeypatch.setattr(
        chain_adapter,
        "_rpc_jsonrpc",
        lambda *, node_rpc, method, params, timeout_seconds=2.0: {
            "result": {
                "total_count": "4",
            }
        },
    )

    sequence = chain_adapter.resolve_next_sender_sequence(
        settings=DummySettings(),
        sender_address="claw1anchor",
    )

    assert sequence == 4


def test_check_cli_broadcast_readiness_reports_ready_state(monkeypatch):
    monkeypatch.setattr(
        chain_adapter,
        "_binary_info",
        lambda binary: {"configured": binary, "resolved_path": "/abs/clawchaind", "available": True},
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_key_address",
        lambda *, settings: "claw1q4akpa27mg6zv5zj4njmtvv0fhxyrtgega3564",
    )
    monkeypatch.setattr(
        chain_adapter,
        "_fetch_rpc_status",
        lambda node_rpc: {
            "reachable": True,
            "status_url": "http://127.0.0.1:26657/status",
            "latest_block_height": "123",
            "catching_up": False,
            "network": "clawchain-testnet-1",
            "moniker": "val1",
        },
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_anchor_account_number",
        lambda *, settings, sender_address: 3,
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_next_sender_sequence",
        lambda *, settings, sender_address: 12,
    )

    report = chain_adapter.check_cli_broadcast_readiness(settings=DummySettings())

    assert report["ready"] is True
    assert report["source_key"]["ok"] is True
    assert report["target_mode"] == "self_transfer"
    assert report["target_address"] == "claw1q4akpa27mg6zv5zj4njmtvv0fhxyrtgega3564"
    assert report["signing"]["mode"] == "offline"
    assert report["signing"]["account_number"] == 3
    assert report["signing"]["next_sequence"] == 12


def test_resolve_typed_broadcast_spec_builds_generate_sign_broadcast_commands(monkeypatch):
    plan = chain_adapter.build_anchor_tx_plan(
        anchor_job={"id": "anchor_job_01"},
        settlement_batch={
            "id": "sb_2026_04_10_0001",
            "lane": "fast",
            "anchor_schema_version": "settlement.v1",
            "canonical_root": sha256_ref("a"),
            "anchor_payload_hash": sha256_ref("b"),
            "window_end_at": "2026-04-10T03:15:00Z",
            "total_reward_amount": 12345,
            "anchor_payload_json": {
                "schema_version": "settlement.v1",
                "policy_bundle_version": "policy.v1",
                "reward_window_ids_root": sha256_ref("c"),
                "task_run_ids_root": sha256_ref("d"),
                "miner_reward_rows_root": sha256_ref("e"),
            },
        },
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_key_address",
        lambda *, settings: "claw1q4akpa27mg6zv5zj4njmtvv0fhxyrtgega3564",
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_anchor_account_number",
        lambda *, settings, sender_address: 7,
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_next_sender_sequence",
        lambda *, settings, sender_address: 11,
    )

    spec = chain_adapter.resolve_typed_broadcast_spec(
        plan=plan,
        settings=DummySettings(),
        unsigned_tx_path="/tmp/unsigned.json",
        signed_tx_path="/tmp/signed.json",
    )

    assert spec["sequence"] == 11
    assert spec["account_number"] == 7
    assert spec["generate_command"][:4] == ["./clawchaind", "tx", "settlement", "anchor-batch"]
    assert "deploy/testnet-artifacts/val1" in spec["generate_command"]
    assert "--generate-only" in spec["generate_command"]
    assert spec["sign_command"][:3] == ["./clawchaind", "tx", "sign"]
    assert "/tmp/unsigned.json" in spec["sign_command"]
    assert "/tmp/signed.json" in spec["sign_command"]
    assert spec["broadcast_command"][:3] == ["./clawchaind", "tx", "broadcast"]
    assert spec["broadcast_command"][3] == "/tmp/signed.json"


def test_broadcast_anchor_tx_via_cli_retries_sequence_mismatch_once(monkeypatch):
    monkeypatch.setattr(
        chain_adapter,
        "resolve_key_address",
        lambda *, settings: "claw1q4akpa27mg6zv5zj4njmtvv0fhxyrtgega3564",
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_anchor_account_number",
        lambda *, settings, sender_address: 0,
    )
    next_sequence = count(4)
    monkeypatch.setattr(
        chain_adapter,
        "resolve_next_sender_sequence",
        lambda *, settings, sender_address: next(next_sequence),
    )

    commands: list[list[str]] = []

    def fake_run(command, capture_output, text, check):  # noqa: ANN001
        commands.append(command)
        if len(commands) == 1:
            return subprocess.CompletedProcess(
                command,
                1,
                "",
                "account sequence mismatch, expected 5, got 4: incorrect account sequence",
            )
        return subprocess.CompletedProcess(
            command,
            0,
            '{"txhash":"ABC123TX","code":0,"raw_log":""}',
            "",
        )

    monkeypatch.setattr(chain_adapter.subprocess, "run", fake_run)

    receipt = asyncio.run(
        chain_adapter.broadcast_anchor_tx_via_cli(
            plan={"fallback_memo": "anchor:v1:test:retry"},
            settings=DummySettings(),
            now="2026-04-10T03:00:00Z",
        )
    )

    assert receipt["tx_hash"] == "ABC123TX"
    assert receipt["sequence"] == 5
    assert receipt["attempt_count"] == 2
    assert commands[0][-1] == "4"
    assert commands[1][-1] == "5"


def test_broadcast_anchor_tx_via_cli_serializes_concurrent_calls(monkeypatch):
    monkeypatch.setattr(
        chain_adapter,
        "resolve_key_address",
        lambda *, settings: "claw1q4akpa27mg6zv5zj4njmtvv0fhxyrtgega3564",
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_anchor_account_number",
        lambda *, settings, sender_address: 0,
    )
    next_sequence = count(20)
    monkeypatch.setattr(
        chain_adapter,
        "resolve_next_sender_sequence",
        lambda *, settings, sender_address: next(next_sequence),
    )

    active_calls = 0
    max_active_calls = 0
    state_lock = threading.Lock()

    def fake_run(command, capture_output, text, check):  # noqa: ANN001
        nonlocal active_calls, max_active_calls
        with state_lock:
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
        time.sleep(0.05)
        with state_lock:
            active_calls -= 1
        txhash = f"TX-{command[-1]}"
        return subprocess.CompletedProcess(
            command,
            0,
            f'{{"txhash":"{txhash}","code":0,"raw_log":""}}',
            "",
        )

    monkeypatch.setattr(chain_adapter.subprocess, "run", fake_run)

    async def scenario():
        return await asyncio.gather(
            chain_adapter.broadcast_anchor_tx_via_cli(
                plan={"fallback_memo": "anchor:v1:test:serial-1"},
                settings=DummySettings(),
                now="2026-04-10T03:10:00Z",
            ),
            chain_adapter.broadcast_anchor_tx_via_cli(
                plan={"fallback_memo": "anchor:v1:test:serial-2"},
                settings=DummySettings(),
                now="2026-04-10T03:10:01Z",
            ),
        )

    receipts = asyncio.run(scenario())

    assert [receipt["sequence"] for receipt in receipts] == [20, 21]
    assert max_active_calls == 1


def test_broadcast_anchor_tx_via_typed_cli_retries_sequence_mismatch_once(monkeypatch):
    plan = chain_adapter.build_anchor_tx_plan(
        anchor_job={"id": "anchor_job_01"},
        settlement_batch={
            "id": "sb_2026_04_10_0001",
            "lane": "fast",
            "anchor_schema_version": "settlement.v1",
            "canonical_root": sha256_ref("a"),
            "anchor_payload_hash": sha256_ref("b"),
            "window_end_at": "2026-04-10T03:15:00Z",
            "total_reward_amount": 12345,
            "anchor_payload_json": {
                "schema_version": "settlement.v1",
                "policy_bundle_version": "policy.v1",
                "reward_window_ids_root": sha256_ref("c"),
                "task_run_ids_root": sha256_ref("d"),
                "miner_reward_rows_root": sha256_ref("e"),
            },
        },
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_key_address",
        lambda *, settings: "claw1q4akpa27mg6zv5zj4njmtvv0fhxyrtgega3564",
    )
    monkeypatch.setattr(
        chain_adapter,
        "resolve_anchor_account_number",
        lambda *, settings, sender_address: 0,
    )
    next_sequence = count(4)
    monkeypatch.setattr(
        chain_adapter,
        "resolve_next_sender_sequence",
        lambda *, settings, sender_address: next(next_sequence),
    )

    commands: list[list[str]] = []

    def fake_run(command, capture_output, text, check):  # noqa: ANN001
        commands.append(command)
        if command[:3] == ["./clawchaind", "tx", "broadcast"] and len(commands) < 4:
            return subprocess.CompletedProcess(
                command,
                1,
                "",
                "account sequence mismatch, expected 5, got 4: incorrect account sequence",
            )
        if command[:3] == ["./clawchaind", "tx", "broadcast"]:
            return subprocess.CompletedProcess(
                command,
                0,
                '{"txhash":"TYPED123TX","code":0,"raw_log":""}',
                "",
            )
        if command[:3] == ["./clawchaind", "tx", "sign"]:
            output_path = command[command.index("--output-document") + 1]
            Path(output_path).write_text('{"body":{},"auth_info":{},"signatures":["abc"]}')
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:4] == ["./clawchaind", "tx", "settlement", "anchor-batch"]:
            return subprocess.CompletedProcess(
                command,
                0,
                '{"body":{"messages":[{"@type":"/clawchain.settlement.v1.MsgAnchorSettlementBatch"}]},"auth_info":{"signer_infos":[]},"signatures":[]}',
                "",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(chain_adapter.subprocess, "run", fake_run)

    receipt = asyncio.run(
        chain_adapter.broadcast_anchor_tx_via_typed_cli(
            plan=plan,
            settings=DummySettings(),
            now="2026-04-10T03:00:00Z",
        )
    )

    assert receipt["tx_hash"] == "TYPED123TX"
    assert receipt["sequence"] == 5
    assert receipt["attempt_count"] == 2
    assert receipt["broadcast_method"] == "typed_msg"


def test_inspect_broadcast_tx_confirmation_returns_confirmed_from_rpc(monkeypatch):
    monkeypatch.setattr(
        chain_adapter,
        "_rpc_jsonrpc",
        lambda *, node_rpc, method, params, timeout_seconds=2.0: {
            "result": {
                "hash": "ABC123TX",
                "height": "123",
                "tx_result": {
                    "code": 0,
                    "log": "",
                },
            }
        },
    )

    receipt = chain_adapter.inspect_broadcast_tx_confirmation(
        settings=DummySettings(),
        tx_hash="ABC123TX",
    )

    assert receipt["tx_hash"] == "ABC123TX"
    assert receipt["confirmation_status"] == "confirmed"
    assert receipt["found"] is True
    assert receipt["height"] == 123
    assert receipt["code"] == 0


def test_inspect_broadcast_tx_confirmation_encodes_hex_hash_for_rpc(monkeypatch):
    captured = {}

    def fake_rpc_jsonrpc(*, node_rpc, method, params, timeout_seconds=2.0):  # noqa: ANN001
        captured.update({"method": method, "params": params})
        return {
            "result": {
                "hash": "588F27F61C2CBD638E20A6F08BD0149A3FDABCFE3D98513CB2910816D02E3F6A",
                "height": "456",
                "tx_result": {
                    "code": 0,
                    "log": "",
                },
            }
        }

    monkeypatch.setattr(chain_adapter, "_rpc_jsonrpc", fake_rpc_jsonrpc)

    tx_hash = "588F27F61C2CBD638E20A6F08BD0149A3FDABCFE3D98513CB2910816D02E3F6A"
    receipt = chain_adapter.inspect_broadcast_tx_confirmation(
        settings=DummySettings(),
        tx_hash=tx_hash,
    )

    assert receipt["confirmation_status"] == "confirmed"
    assert captured["method"] == "tx"
    assert captured["params"]["hash"] == base64.b64encode(binascii.unhexlify(tx_hash)).decode()


def test_inspect_broadcast_tx_confirmation_returns_pending_when_not_found(monkeypatch):
    def fake_rpc_jsonrpc(*, node_rpc, method, params, timeout_seconds=2.0):  # noqa: ANN001
        raise ValueError("tx not found")

    monkeypatch.setattr(chain_adapter, "_rpc_jsonrpc", fake_rpc_jsonrpc)

    receipt = chain_adapter.inspect_broadcast_tx_confirmation(
        settings=DummySettings(),
        tx_hash="ABC123TX",
    )

    assert receipt["tx_hash"] == "ABC123TX"
    assert receipt["confirmation_status"] == "pending"
    assert receipt["found"] is False


def test_inspect_broadcast_settlement_confirmation_async_returns_combined_receipt(monkeypatch):
    def fake_inspect_broadcast_tx_confirmation(*, settings, tx_hash):  # noqa: ANN001
        assert settings is not None
        return {
            "tx_hash": tx_hash,
            "found": True,
            "confirmation_status": "confirmed",
            "height": 123,
            "code": 0,
            "raw_log": "",
        }

    def fake_inspect_settlement_anchor(*, settings, settlement_batch_id):  # noqa: ANN001
        assert settings is not None
        assert settlement_batch_id == "sb_2026_04_10_0001"
        return {
            "found": True,
            "settlement_batch_id": settlement_batch_id,
            "query_height": 124,
            "anchor": {
                "settlement_batch_id": settlement_batch_id,
                "canonical_root": sha256_ref("a"),
                "anchor_payload_hash": sha256_ref("b"),
            },
        }

    monkeypatch.setattr(
        chain_adapter,
        "inspect_broadcast_tx_confirmation",
        fake_inspect_broadcast_tx_confirmation,
    )
    monkeypatch.setattr(
        chain_adapter,
        "inspect_settlement_anchor",
        fake_inspect_settlement_anchor,
    )

    receipt = asyncio.run(
        chain_adapter.inspect_broadcast_settlement_confirmation_async(
            settings=DummySettings(),
            tx_hash="ABC123TX",
            settlement_batch_id="sb_2026_04_10_0001",
        )
    )

    assert receipt["tx_hash"] == "ABC123TX"
    assert receipt["confirmation_status"] == "confirmed"
    assert receipt["query_response"]["anchor"]["settlement_batch_id"] == "sb_2026_04_10_0001"


def test_inspect_settlement_anchor_returns_decoded_anchor(monkeypatch):
    anchor_payload = {
        "settlement_batch_id": "sb_2026_04_10_0001",
        "canonical_root": "sha256:canonical",
        "anchor_payload_hash": "sha256:payload",
    }
    captured = {}

    def fake_rpc_jsonrpc(*, node_rpc, method, params, timeout_seconds=2.0):  # noqa: ANN001
        captured.update({"method": method, "params": params})
        return {
            "result": {
                "response": {
                    "height": "99",
                    "value": base64.b64encode(json.dumps(anchor_payload).encode("utf-8")).decode("ascii"),
                }
            }
        }

    monkeypatch.setattr(chain_adapter, "_rpc_jsonrpc", fake_rpc_jsonrpc)

    result = chain_adapter.inspect_settlement_anchor(
        settings=DummySettings(),
        settlement_batch_id="sb_2026_04_10_0001",
    )

    assert captured["method"] == "abci_query"
    assert captured["params"]["path"] == "/store/settlement/key"
    assert result["found"] is True
    assert result["query_height"] == 99
    assert result["anchor"] == anchor_payload


def test_inspect_settlement_anchor_returns_not_found_when_store_value_empty(monkeypatch):
    monkeypatch.setattr(
        chain_adapter,
        "_rpc_jsonrpc",
        lambda *, node_rpc, method, params, timeout_seconds=2.0: {
            "result": {
                "response": {
                    "height": "88",
                    "value": None,
                }
            }
        },
    )

    result = chain_adapter.inspect_settlement_anchor(
        settings=DummySettings(),
        settlement_batch_id="sb_missing",
    )

    assert result["found"] is False
    assert result["settlement_batch_id"] == "sb_missing"
    assert result["query_height"] == 88


def test_chain_adapter_confirms_anchor_by_querying_stored_state():
    adapter = chain_adapter.FakeSettlementChainAdapter(
        query_response={
            "settlement_batch_id": "sb_1",
            "canonical_root": "sha256:" + "a" * 64,
            "anchor_payload_hash": "sha256:" + "b" * 64,
        }
    )

    result = adapter.confirm_settlement_anchor(
        settlement_batch_id="sb_1",
        canonical_root="sha256:" + "a" * 64,
        anchor_payload_hash="sha256:" + "b" * 64,
    )

    assert result["confirmed"] is True
    assert result["confirmation_status"] == "confirmed"


def test_chain_adapter_distinguishes_missing_fallback_and_mismatched_anchor_state():
    typed_missing = chain_adapter.confirm_settlement_anchor_response(
        query_response={},
        settlement_batch_id="sb_1",
        canonical_root=sha256_ref("a"),
        anchor_payload_hash=sha256_ref("b"),
        tx_receipt={"confirmation_status": "confirmed"},
        broadcast_method="typed_msg",
    )
    fallback_missing = chain_adapter.confirm_settlement_anchor_response(
        query_response={},
        settlement_batch_id="sb_1",
        canonical_root=sha256_ref("a"),
        anchor_payload_hash=sha256_ref("b"),
        tx_receipt={"confirmation_status": "confirmed"},
        broadcast_method="fallback_memo",
    )
    mismatch = chain_adapter.confirm_settlement_anchor_response(
        query_response={
            "settlement_batch_id": "sb_1",
            "canonical_root": sha256_ref("c"),
            "anchor_payload_hash": sha256_ref("b"),
        },
        settlement_batch_id="sb_1",
        canonical_root=sha256_ref("a"),
        anchor_payload_hash=sha256_ref("b"),
        tx_receipt={"confirmation_status": "confirmed"},
        broadcast_method="typed_msg",
    )

    assert typed_missing["confirmation_status"] == "typed_tx_accepted_state_missing"
    assert fallback_missing["confirmation_status"] == "fallback_memo_tx_accepted_no_typed_state"
    assert mismatch["confirmation_status"] == "root_hash_mismatch"


def test_chain_adapter_rejects_confirmed_anchor_with_metadata_drift():
    expected_anchor = {
        "settlement_batch_id": "sb_1",
        "anchor_job_id": "anchor_job_1",
        "lane": "poker_mtt_daily",
        "schema_version": "settlement.v1",
        "policy_bundle_version": "policy.v1",
        "canonical_root": sha256_ref("a"),
        "anchor_payload_hash": sha256_ref("b"),
        "reward_window_ids_root": sha256_ref("c"),
        "task_run_ids_root": sha256_ref("d"),
        "miner_reward_rows_root": sha256_ref("e"),
        "window_end_at": "2026-04-10T03:15:00Z",
        "total_reward_amount": 12345,
    }
    result = chain_adapter.confirm_settlement_anchor_response(
        query_response={
            "anchor": {
                **expected_anchor,
                "policy_bundle_version": "policy.v2",
                "total_reward_amount": 12344,
            }
        },
        settlement_batch_id="sb_1",
        canonical_root=sha256_ref("a"),
        anchor_payload_hash=sha256_ref("b"),
        expected_anchor=expected_anchor,
        tx_receipt={"confirmation_status": "confirmed"},
        broadcast_method="typed_msg",
    )

    assert result["confirmed"] is False
    assert result["confirmation_status"] == "anchor_metadata_mismatch"
    assert result["metadata_mismatches"] == ["policy_bundle_version", "total_reward_amount"]


def test_inspect_broadcast_settlement_confirmation_combines_tx_and_anchor(monkeypatch):
    monkeypatch.setattr(
        chain_adapter,
        "inspect_broadcast_tx_confirmation",
        lambda *, settings, tx_hash: {
            "tx_hash": tx_hash,
            "found": True,
            "confirmed": True,
            "confirmation_status": "confirmed",
            "height": 123,
            "code": 0,
            "raw_log": "",
        },
    )
    monkeypatch.setattr(
        chain_adapter,
        "inspect_settlement_anchor",
        lambda *, settings, settlement_batch_id: {
            "found": True,
            "settlement_batch_id": settlement_batch_id,
            "query_height": 456,
            "anchor": {
                "settlement_batch_id": settlement_batch_id,
                "canonical_root": sha256_ref("a"),
                "anchor_payload_hash": sha256_ref("b"),
            },
        },
    )

    receipt = chain_adapter.inspect_broadcast_settlement_confirmation(
        settings=DummySettings(),
        tx_hash="ABC123",
        settlement_batch_id="sb_123",
    )

    assert receipt["confirmation_status"] == "confirmed"
    assert receipt["confirmed"] is True
    assert receipt["query_response"]["settlement_batch_id"] == "sb_123"


def test_inspect_broadcast_settlement_confirmation_skips_anchor_query_when_tx_pending(monkeypatch):
    monkeypatch.setattr(
        chain_adapter,
        "inspect_broadcast_tx_confirmation",
        lambda *, settings, tx_hash: {
            "tx_hash": tx_hash,
            "found": False,
            "confirmation_status": "pending",
            "height": None,
            "code": None,
            "raw_log": "",
        },
    )

    def _unexpected_query(*, settings, settlement_batch_id):  # noqa: ANN001
        raise AssertionError("anchor query should not run for pending tx")

    monkeypatch.setattr(chain_adapter, "inspect_settlement_anchor", _unexpected_query)

    receipt = chain_adapter.inspect_broadcast_settlement_confirmation(
        settings=DummySettings(),
        tx_hash="PENDING123",
        settlement_batch_id="sb_123",
    )

    assert receipt["confirmation_status"] == "pending"
    assert "query_response" not in receipt
