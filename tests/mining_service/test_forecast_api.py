from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
SCRIPT_DIR = ROOT / "skill" / "scripts"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import forecast_engine
import server
from config import AppSettings
from setup import generate_wallet
from eth_keys import keys as eth_keys


class FrozenClock:
    def __init__(self, now: datetime):
        self.current = now

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def _sign(parts: list[str], private_key_hex: str) -> str:
    msg_hash = forecast_engine.build_signature_hash(parts)
    signature = eth_keys.PrivateKey(bytes.fromhex(private_key_hex)).sign_msg_hash(msg_hash)
    return signature.to_bytes().hex()


def test_register_fetch_commit_reveal_flow():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))

    async def fake_broadcaster(plan, now):  # noqa: ANN001
        return {
            "tx_hash": "ABC123TX",
            "code": 0,
            "raw_log": "",
            "memo": plan["fallback_memo"],
            "broadcast_at": forecast_engine.isoformat_z(now),
            "account_number": 0,
            "sequence": 0,
            "attempt_count": 1,
        }

    app = server.create_app(
        settings=forecast_engine.ForecastSettings(fast_task_seconds=900, commit_window_seconds=3, reveal_window_seconds=13),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
        chain_broadcaster=fake_broadcaster,
    )
    wallet = generate_wallet()
    with TestClient(app) as client:
        register_resp = client.post(
            "/clawchain/miner/register",
            json={
                "address": wallet["address"],
                "name": "miner-alpha",
                "public_key": wallet["public_key"],
                "miner_version": "0.4.0",
            },
        )
        assert register_resp.status_code == 200

        active = client.get("/v1/task-runs/active").json()["data"]["items"]
        fast_task = next(item for item in active if item["lane"] == "forecast_15m")

        p_yes_bps = 6400
        reveal_nonce = "salt-1"
        commit_hash = forecast_engine.compute_commit_hash(
            task_run_id=fast_task["task_run_id"],
            miner_address=wallet["address"],
            p_yes_bps=p_yes_bps,
            reveal_nonce=reveal_nonce,
        )

        commit_request_id = "req-commit-1"
        commit_sig = _sign(
            [fast_task["task_run_id"], commit_hash, reveal_nonce, wallet["address"], commit_request_id],
            wallet["private_key"],
        )
        commit_resp = client.post(
            f"/v1/task-runs/{fast_task['task_run_id']}/commit",
            json={
                "request_id": commit_request_id,
                "task_run_id": fast_task["task_run_id"],
                "miner_id": wallet["address"],
                "economic_unit_id": f"eu:{wallet['address']}",
                "commit_hash": commit_hash,
                "nonce": reveal_nonce,
                "client_version": "skill-v0.4.0",
                "signature": commit_sig,
            },
        )
        assert commit_resp.status_code == 200

        clock.advance(5)
        reveal_request_id = "req-reveal-1"
        reveal_sig = _sign(
            [fast_task["task_run_id"], str(p_yes_bps), reveal_nonce, wallet["address"], reveal_request_id],
            wallet["private_key"],
        )
        reveal_resp = client.post(
            f"/v1/task-runs/{fast_task['task_run_id']}/reveal",
            json={
                "request_id": reveal_request_id,
                "task_run_id": fast_task["task_run_id"],
                "miner_id": wallet["address"],
                "economic_unit_id": f"eu:{wallet['address']}",
                "p_yes_bps": p_yes_bps,
                "nonce": reveal_nonce,
                "schema_version": "v1",
                "signature": reveal_sig,
            },
        )
        assert reveal_resp.status_code == 200
        assert reveal_resp.json()["data"]["reward_eligibility"] == "eligible"

        clock.advance(900)
        miner_status = client.get(f"/v1/miners/{wallet['address']}/status")
        assert miner_status.status_code == 200
        data = miner_status.json()["data"]
        assert data["settled_tasks"] == 1
        assert data["total_rewards"] >= 0
        assert "score_explanation" in data
        assert "reward_timeline" in data
        assert data["score_explanation"]["latest_fast"]["task_run_id"] == fast_task["task_run_id"]

        submissions = client.get(f"/v1/miners/{wallet['address']}/submissions").json()["data"]["items"]
        task_history = client.get(f"/v1/miners/{wallet['address']}/tasks/history").json()["data"]["items"]
        reward_holds = client.get(f"/v1/miners/{wallet['address']}/reward-holds").json()["data"]["items"]
        reward_windows = client.get(f"/v1/miners/{wallet['address']}/reward-windows").json()["data"]["items"]
        settlement_batches = client.get("/admin/settlement-batches").json()["items"]
        reward_window_proof = client.get(f"/v1/replays/reward_window/{reward_windows[0]['id']}/proof").json()["data"]
        reward_window_artifact = client.get(f"/v1/artifacts/{reward_window_proof['artifact_refs'][0]['artifact_id']}").json()["data"]
        rebuilt_window = client.post(f"/admin/reward-windows/{reward_windows[0]['id']}/rebuild").json()
        anchored_batch = client.post(f"/admin/settlement-batches/{settlement_batches[0]['id']}/retry-anchor").json()
        submitted_batch = client.post(f"/admin/settlement-batches/{settlement_batches[0]['id']}/submit-anchor").json()
        anchor_jobs = client.get("/admin/anchor-jobs").json()["items"]
        chain_tx_plan = client.get(f"/admin/anchor-jobs/{anchor_jobs[0]['id']}/chain-tx-plan").json()
        broadcast_receipt = client.post(f"/admin/anchor-jobs/{anchor_jobs[0]['id']}/broadcast-fallback").json()
        anchored_job = client.post(f"/admin/anchor-jobs/{anchor_jobs[0]['id']}/mark-anchored").json()
        anchored_proof = client.get(f"/v1/replays/reward_window/{reward_windows[0]['id']}/proof").json()["data"]
        settled_status = client.get(f"/v1/miners/{wallet['address']}/status").json()["data"]

        assert submissions[0]["task_run_id"] == fast_task["task_run_id"]
        assert submissions[0]["reward_window_id"] is not None
        assert task_history[0]["task_run_id"] == fast_task["task_run_id"]
        assert task_history[0]["reward_window_id"] == submissions[0]["reward_window_id"]
        assert reward_holds[0]["task_run_id"] == fast_task["task_run_id"]
        assert reward_windows[0]["id"] == submissions[0]["reward_window_id"]
        assert settlement_batches[0]["reward_window_ids"][0] == reward_windows[0]["id"]
        assert reward_window_proof["entity_id"] == reward_windows[0]["id"]
        assert reward_window_artifact["kind"] == "reward_window_membership"
        assert rebuilt_window["id"] == reward_windows[0]["id"]
        assert anchored_batch["id"] == settlement_batches[0]["id"]
        assert anchored_batch["state"] == "anchor_ready"
        assert anchored_batch["anchor_payload_json"]["schema_version"] == "clawchain.anchor_payload.v1"
        assert anchored_batch["anchor_payload_json"]["canonical_root"].startswith("sha256:")
        assert submitted_batch["state"] == "anchor_submitted"
        assert anchor_jobs[0]["state"] == "anchor_submitted"
        assert chain_tx_plan["tx_builder_kind"] == "cosmos_anchor_intent_v1"
        assert chain_tx_plan["future_msg"]["value"]["settlement_batch_id"] == settlement_batches[0]["id"]
        assert chain_tx_plan["typed_tx_intent"]["body"]["messages"][0] == chain_tx_plan["future_msg"]
        assert chain_tx_plan["typed_tx_intent"]["body"]["memo"] == chain_tx_plan["fallback_memo"]
        assert broadcast_receipt["tx_hash"] == "ABC123TX"
        assert broadcast_receipt["broadcast_status"] == "broadcast_submitted"
        assert broadcast_receipt["account_number"] == 0
        assert broadcast_receipt["sequence"] == 0
        assert broadcast_receipt["attempt_count"] == 1
        assert anchored_job["state"] == "anchored"
        assert any(ref["kind"] == "settlement_anchor_payload" for ref in anchored_proof["artifact_refs"])
        assert settled_status["latest_reward_window"]["id"] == reward_windows[0]["id"]
        assert settled_status["latest_reward_window"]["canonical_root"].startswith("sha256:")
        assert settled_status["latest_settlement_batch"]["id"] == settlement_batches[0]["id"]
        assert settled_status["latest_settlement_batch"]["state"] == "anchored"
        assert settled_status["latest_anchor_job"]["id"] == anchor_jobs[0]["id"]
        assert settled_status["latest_anchor_job"]["state"] == "anchored"


def test_task_detail_exposes_frozen_snapshot_metadata():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(fast_task_seconds=900, commit_window_seconds=3, reveal_window_seconds=13),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )

    with TestClient(app) as client:
        active = client.get("/v1/task-runs/active").json()["data"]["items"]
        fast_task = next(item for item in active if item["lane"] == "forecast_15m")
        detail = client.get(f"/v1/forecast/task-runs/{fast_task['task_run_id']}")

        assert detail.status_code == 200
        pack_json = detail.json()["data"]["pack_json"]
        assert pack_json["snapshot_source"] == "synthetic"
        assert pack_json["snapshot_frozen_at"] == detail.json()["data"]["created_at"]
        assert pack_json["snapshot_freshness_seconds"] == {"binance": None, "polymarket": None}


def test_typed_broadcast_endpoint_uses_typed_chain_broadcaster():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))

    async def fake_broadcaster(plan, now):  # noqa: ANN001
        return {
            "tx_hash": "ABC123TX",
            "code": 0,
            "raw_log": "",
            "memo": plan["fallback_memo"],
            "broadcast_at": forecast_engine.isoformat_z(now),
            "account_number": 0,
            "sequence": 0,
            "attempt_count": 1,
        }

    async def fake_typed_broadcaster(plan, now):  # noqa: ANN001
        return {
            "tx_hash": "TYPED123TX",
            "code": 0,
            "raw_log": "",
            "memo": plan["fallback_memo"],
            "broadcast_at": forecast_engine.isoformat_z(now),
            "account_number": 0,
            "sequence": 1,
            "attempt_count": 1,
            "broadcast_method": "typed_msg",
        }

    app = server.create_app(
        settings=forecast_engine.ForecastSettings(fast_task_seconds=900, commit_window_seconds=3, reveal_window_seconds=13),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
        chain_broadcaster=fake_broadcaster,
        chain_typed_broadcaster=fake_typed_broadcaster,
    )
    wallet = generate_wallet()
    with TestClient(app) as client:
        register_resp = client.post(
            "/clawchain/miner/register",
            json={
                "address": wallet["address"],
                "name": "miner-typed",
                "public_key": wallet["public_key"],
                "miner_version": "0.4.0",
            },
        )
        assert register_resp.status_code == 200

        active = client.get("/v1/task-runs/active").json()["data"]["items"]
        fast_task = next(item for item in active if item["lane"] == "forecast_15m")

        p_yes_bps = 6400
        reveal_nonce = "salt-typed"
        commit_hash = forecast_engine.compute_commit_hash(
            task_run_id=fast_task["task_run_id"],
            miner_address=wallet["address"],
            p_yes_bps=p_yes_bps,
            reveal_nonce=reveal_nonce,
        )

        commit_request_id = "req-commit-typed"
        commit_sig = _sign(
            [fast_task["task_run_id"], commit_hash, reveal_nonce, wallet["address"], commit_request_id],
            wallet["private_key"],
        )
        commit_resp = client.post(
            f"/v1/task-runs/{fast_task['task_run_id']}/commit",
            json={
                "request_id": commit_request_id,
                "task_run_id": fast_task["task_run_id"],
                "miner_id": wallet["address"],
                "economic_unit_id": f"eu:{wallet['address']}",
                "commit_hash": commit_hash,
                "nonce": reveal_nonce,
                "client_version": "skill-v0.4.0",
                "signature": commit_sig,
            },
        )
        assert commit_resp.status_code == 200

        clock.advance(5)
        reveal_request_id = "req-reveal-typed"
        reveal_sig = _sign(
            [fast_task["task_run_id"], str(p_yes_bps), reveal_nonce, wallet["address"], reveal_request_id],
            wallet["private_key"],
        )
        reveal_resp = client.post(
            f"/v1/task-runs/{fast_task['task_run_id']}/reveal",
            json={
                "request_id": reveal_request_id,
                "task_run_id": fast_task["task_run_id"],
                "miner_id": wallet["address"],
                "economic_unit_id": f"eu:{wallet['address']}",
                "p_yes_bps": p_yes_bps,
                "nonce": reveal_nonce,
                "schema_version": "v1",
                "signature": reveal_sig,
            },
        )
        assert reveal_resp.status_code == 200

        clock.advance(900)
        settlement_batches = client.get("/admin/settlement-batches").json()["items"]
        client.post(f"/admin/settlement-batches/{settlement_batches[0]['id']}/retry-anchor")
        client.post(f"/admin/settlement-batches/{settlement_batches[0]['id']}/submit-anchor")
        anchor_jobs = client.get("/admin/anchor-jobs").json()["items"]

        receipt = client.post(f"/admin/anchor-jobs/{anchor_jobs[0]['id']}/broadcast-typed").json()

        assert receipt["tx_hash"] == "TYPED123TX"
        assert receipt["broadcast_status"] == "broadcast_submitted"
        assert receipt["broadcast_method"] == "typed_msg"


def test_confirm_chain_endpoint_marks_anchor_job_anchored():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))

    async def fake_typed_broadcaster(plan, now):  # noqa: ANN001
        return {
            "tx_hash": "TYPEDCONFIRMTX",
            "code": 0,
            "raw_log": "",
            "memo": plan["fallback_memo"],
            "broadcast_at": forecast_engine.isoformat_z(now),
            "account_number": 0,
            "sequence": 1,
            "attempt_count": 1,
            "broadcast_method": "typed_msg",
        }

    async def fake_confirmer(tx_hash, now):  # noqa: ANN001
        return {
            "tx_hash": tx_hash,
            "found": True,
            "confirmation_status": "confirmed",
            "height": 321,
            "code": 0,
            "raw_log": "",
        }

    app = server.create_app(
        settings=forecast_engine.ForecastSettings(fast_task_seconds=900, commit_window_seconds=3, reveal_window_seconds=13),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
        chain_typed_broadcaster=fake_typed_broadcaster,
        chain_tx_confirmer=fake_confirmer,
    )
    wallet = generate_wallet()
    with TestClient(app) as client:
        register_resp = client.post(
            "/clawchain/miner/register",
            json={
                "address": wallet["address"],
                "name": "miner-confirm",
                "public_key": wallet["public_key"],
                "miner_version": "0.4.0",
            },
        )
        assert register_resp.status_code == 200

        active = client.get("/v1/task-runs/active").json()["data"]["items"]
        fast_task = next(item for item in active if item["lane"] == "forecast_15m")

        p_yes_bps = 6400
        reveal_nonce = "salt-confirm"
        commit_hash = forecast_engine.compute_commit_hash(
            task_run_id=fast_task["task_run_id"],
            miner_address=wallet["address"],
            p_yes_bps=p_yes_bps,
            reveal_nonce=reveal_nonce,
        )
        commit_request_id = "req-commit-confirm"
        commit_sig = _sign(
            [fast_task["task_run_id"], commit_hash, reveal_nonce, wallet["address"], commit_request_id],
            wallet["private_key"],
        )
        commit_resp = client.post(
            f"/v1/task-runs/{fast_task['task_run_id']}/commit",
            json={
                "request_id": commit_request_id,
                "task_run_id": fast_task["task_run_id"],
                "miner_id": wallet["address"],
                "economic_unit_id": f"eu:{wallet['address']}",
                "commit_hash": commit_hash,
                "nonce": reveal_nonce,
                "client_version": "skill-v0.4.0",
                "signature": commit_sig,
            },
        )
        assert commit_resp.status_code == 200

        clock.advance(5)
        reveal_request_id = "req-reveal-confirm"
        reveal_sig = _sign(
            [fast_task["task_run_id"], str(p_yes_bps), reveal_nonce, wallet["address"], reveal_request_id],
            wallet["private_key"],
        )
        reveal_resp = client.post(
            f"/v1/task-runs/{fast_task['task_run_id']}/reveal",
            json={
                "request_id": reveal_request_id,
                "task_run_id": fast_task["task_run_id"],
                "miner_id": wallet["address"],
                "economic_unit_id": f"eu:{wallet['address']}",
                "p_yes_bps": p_yes_bps,
                "nonce": reveal_nonce,
                "schema_version": "v1",
                "signature": reveal_sig,
            },
        )
        assert reveal_resp.status_code == 200

        clock.advance(900)
        settlement_batches = client.get("/admin/settlement-batches").json()["items"]
        client.post(f"/admin/settlement-batches/{settlement_batches[0]['id']}/retry-anchor")
        client.post(f"/admin/settlement-batches/{settlement_batches[0]['id']}/submit-anchor")
        anchor_jobs = client.get("/admin/anchor-jobs").json()["items"]
        client.post(f"/admin/anchor-jobs/{anchor_jobs[0]['id']}/broadcast-typed")

        receipt = client.post(f"/admin/anchor-jobs/{anchor_jobs[0]['id']}/confirm-chain").json()
        anchor_jobs_after = client.get("/admin/anchor-jobs").json()["items"]

        assert receipt["chain_confirmation_status"] == "confirmed"
        assert receipt["anchor_job_state"] == "anchored"
        assert receipt["chain_height"] == 321
        assert anchor_jobs_after[0]["state"] == "anchored"


def test_reconcile_chain_endpoint_confirms_pending_anchor_jobs():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))

    async def fake_typed_broadcaster(plan, now):  # noqa: ANN001
        return {
            "tx_hash": "TYPEDSWEEPTX",
            "code": 0,
            "raw_log": "",
            "memo": plan["fallback_memo"],
            "broadcast_at": forecast_engine.isoformat_z(now),
            "account_number": 0,
            "sequence": 1,
            "attempt_count": 1,
            "broadcast_method": "typed_msg",
        }

    async def fake_confirmer(tx_hash, now):  # noqa: ANN001
        return {
            "tx_hash": tx_hash,
            "found": True,
            "confirmation_status": "confirmed",
            "height": 654,
            "code": 0,
            "raw_log": "",
        }

    app = server.create_app(
        settings=forecast_engine.ForecastSettings(fast_task_seconds=900, commit_window_seconds=3, reveal_window_seconds=13),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
        chain_typed_broadcaster=fake_typed_broadcaster,
        chain_tx_confirmer=fake_confirmer,
    )
    wallet = generate_wallet()
    with TestClient(app) as client:
        register_resp = client.post(
            "/clawchain/miner/register",
            json={
                "address": wallet["address"],
                "name": "miner-sweep",
                "public_key": wallet["public_key"],
                "miner_version": "0.4.0",
            },
        )
        assert register_resp.status_code == 200

        active = client.get("/v1/task-runs/active").json()["data"]["items"]
        fast_task = next(item for item in active if item["lane"] == "forecast_15m")

        p_yes_bps = 6400
        reveal_nonce = "salt-sweep"
        commit_hash = forecast_engine.compute_commit_hash(
            task_run_id=fast_task["task_run_id"],
            miner_address=wallet["address"],
            p_yes_bps=p_yes_bps,
            reveal_nonce=reveal_nonce,
        )
        commit_request_id = "req-commit-sweep"
        commit_sig = _sign(
            [fast_task["task_run_id"], commit_hash, reveal_nonce, wallet["address"], commit_request_id],
            wallet["private_key"],
        )
        commit_resp = client.post(
            f"/v1/task-runs/{fast_task['task_run_id']}/commit",
            json={
                "request_id": commit_request_id,
                "task_run_id": fast_task["task_run_id"],
                "miner_id": wallet["address"],
                "economic_unit_id": f"eu:{wallet['address']}",
                "commit_hash": commit_hash,
                "nonce": reveal_nonce,
                "client_version": "skill-v0.4.0",
                "signature": commit_sig,
            },
        )
        assert commit_resp.status_code == 200

        clock.advance(5)
        reveal_request_id = "req-reveal-sweep"
        reveal_sig = _sign(
            [fast_task["task_run_id"], str(p_yes_bps), reveal_nonce, wallet["address"], reveal_request_id],
            wallet["private_key"],
        )
        reveal_resp = client.post(
            f"/v1/task-runs/{fast_task['task_run_id']}/reveal",
            json={
                "request_id": reveal_request_id,
                "task_run_id": fast_task["task_run_id"],
                "miner_id": wallet["address"],
                "economic_unit_id": f"eu:{wallet['address']}",
                "p_yes_bps": p_yes_bps,
                "nonce": reveal_nonce,
                "schema_version": "v1",
                "signature": reveal_sig,
            },
        )
        assert reveal_resp.status_code == 200

        clock.advance(900)
        settlement_batches = client.get("/admin/settlement-batches").json()["items"]
        client.post(f"/admin/settlement-batches/{settlement_batches[0]['id']}/retry-anchor")
        client.post(f"/admin/settlement-batches/{settlement_batches[0]['id']}/submit-anchor")
        anchor_jobs = client.get("/admin/anchor-jobs").json()["items"]
        client.post(f"/admin/anchor-jobs/{anchor_jobs[0]['id']}/broadcast-typed")

        result = client.post("/admin/anchor-jobs/reconcile-chain").json()
        anchor_jobs_after = client.get("/admin/anchor-jobs").json()["items"]

        assert result["count"] == 1
        assert result["items"][0]["chain_confirmation_status"] == "confirmed"
        assert result["items"][0]["anchor_job_state"] == "anchored"
        assert anchor_jobs_after[0]["state"] == "anchored"


def test_anchor_reconcile_loop_runs_pending_confirmation_once(monkeypatch):
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))

    class DummyService:
        def __init__(self):
            self.calls: list[datetime] = []

        async def reconcile_pending_anchor_jobs_on_chain(self, *, now=None):
            self.calls.append(now)
            return []

    service = DummyService()
    metrics = {
        "enabled": True,
        "interval_seconds": 15.0,
        "active": True,
        "run_count": 0,
        "success_count": 0,
        "error_count": 0,
        "last_started_at": None,
        "last_completed_at": None,
        "last_result_count": 0,
        "last_error": None,
    }

    async def fake_sleep(seconds):  # noqa: ANN001
        raise asyncio.CancelledError()

    monkeypatch.setattr(server.asyncio, "sleep", fake_sleep)

    async def scenario():
        with pytest.raises(asyncio.CancelledError):
            await server._run_anchor_reconcile_loop(
                service=service,
                now_fn=clock.now,
                interval_seconds=15.0,
                metrics=metrics,
            )

    import asyncio

    asyncio.run(scenario())

    assert service.calls == [clock.now()]
    assert metrics["run_count"] == 1
    assert metrics["success_count"] == 1
    assert metrics["last_result_count"] == 0
    assert metrics["last_error"] is None


def test_chain_health_endpoint_reports_pending_confirmation_and_latest_failure():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))

    app = server.create_app(
        settings=AppSettings(anchor_reconcile_loop_enabled=False),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    with TestClient(app) as client:
        repo = app.state.repository
        repo._anchor_jobs["aj_pending"] = {
            "id": "aj_pending",
            "settlement_batch_id": "sb_pending",
            "lane": "forecast_15m",
            "state": "anchor_submitted",
            "anchor_payload_hash": "sha256:pending",
            "broadcast_status": "broadcast_submitted",
            "broadcast_tx_hash": "PENDINGTX",
            "last_broadcast_at": "2026-04-09T09:10:00Z",
            "failure_reason": None,
            "submitted_at": "2026-04-09T09:00:00Z",
            "anchored_at": None,
            "created_at": "2026-04-09T09:00:00Z",
            "updated_at": "2026-04-09T09:10:00Z",
        }
        repo._anchor_jobs["aj_failed"] = {
            "id": "aj_failed",
            "settlement_batch_id": "sb_failed",
            "lane": "forecast_15m",
            "state": "anchor_failed",
            "anchor_payload_hash": "sha256:failed",
            "broadcast_status": "broadcast_submitted",
            "broadcast_tx_hash": "FAILEDTX",
            "last_broadcast_at": "2026-04-09T09:05:00Z",
            "failure_reason": "rpc timeout",
            "submitted_at": "2026-04-09T09:00:00Z",
            "anchored_at": None,
            "created_at": "2026-04-09T09:00:00Z",
            "updated_at": "2026-04-09T09:11:00Z",
        }

        data = client.get("/admin/chain/health").json()

        assert data["loop"]["enabled"] is False
        assert data["loop"]["active"] is False
        assert data["anchor_jobs"]["total_count"] == 2
        assert data["anchor_jobs"]["pending_confirmation_count"] == 1
        assert data["anchor_jobs"]["failed_count"] == 1
        assert data["anchor_jobs"]["latest_broadcast_at"] == "2026-04-09T09:10:00Z"
        assert data["anchor_jobs"]["latest_failure_reason"] == "rpc timeout"


def test_chain_health_endpoint_reports_alert_thresholds():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 20, 0, tzinfo=timezone.utc))

    app = server.create_app(
        settings=AppSettings(
            anchor_reconcile_loop_enabled=False,
            anchor_reconcile_loop_error_alert_threshold=2,
            anchor_pending_confirmation_warning_seconds=60,
        ),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    with TestClient(app) as client:
        repo = app.state.repository
        repo._anchor_jobs["aj_stale"] = {
            "id": "aj_stale",
            "settlement_batch_id": "sb_stale",
            "lane": "forecast_15m",
            "state": "anchor_submitted",
            "anchor_payload_hash": "sha256:stale",
            "broadcast_status": "broadcast_submitted",
            "broadcast_tx_hash": "STALETX",
            "last_broadcast_at": "2026-04-09T09:10:00Z",
            "failure_reason": None,
            "submitted_at": "2026-04-09T09:00:00Z",
            "anchored_at": None,
            "created_at": "2026-04-09T09:00:00Z",
            "updated_at": "2026-04-09T09:10:00Z",
        }
        app.state.anchor_reconcile_metrics.update(
            {
                "active": True,
                "run_count": 5,
                "success_count": 3,
                "error_count": 2,
                "consecutive_error_count": 2,
                "last_error": "rpc unavailable",
            }
        )

        data = client.get("/admin/chain/health").json()

        assert data["status"] == "critical"
        assert data["anchor_jobs"]["stale_pending_confirmation_count"] == 1
        codes = {item["code"] for item in data["alerts"]}
        assert "stale_pending_confirmation" in codes
        assert "anchor_reconcile_loop_errors" in codes


def test_anchor_action_queue_endpoint_returns_failed_and_stale_jobs():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 20, 0, tzinfo=timezone.utc))

    app = server.create_app(
        settings=AppSettings(
            anchor_reconcile_loop_enabled=False,
            anchor_pending_confirmation_warning_seconds=60,
        ),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    with TestClient(app) as client:
        repo = app.state.repository
        repo._anchor_jobs["aj_stale"] = {
            "id": "aj_stale",
            "settlement_batch_id": "sb_stale",
            "lane": "forecast_15m",
            "state": "anchor_submitted",
            "anchor_payload_hash": "sha256:stale",
            "broadcast_status": "broadcast_submitted",
            "broadcast_tx_hash": "STALETX",
            "last_broadcast_at": "2026-04-09T09:10:00Z",
            "failure_reason": None,
            "submitted_at": "2026-04-09T09:00:00Z",
            "anchored_at": None,
            "created_at": "2026-04-09T09:00:00Z",
            "updated_at": "2026-04-09T09:10:00Z",
        }
        repo._anchor_jobs["aj_failed"] = {
            "id": "aj_failed",
            "settlement_batch_id": "sb_failed",
            "lane": "forecast_15m",
            "state": "anchor_failed",
            "anchor_payload_hash": "sha256:failed",
            "broadcast_status": "broadcast_submitted",
            "broadcast_tx_hash": "FAILEDTX",
            "last_broadcast_at": "2026-04-09T09:05:00Z",
            "failure_reason": "rpc timeout",
            "submitted_at": "2026-04-09T09:00:00Z",
            "anchored_at": None,
            "created_at": "2026-04-09T09:00:00Z",
            "updated_at": "2026-04-09T09:11:00Z",
        }
        repo._anchor_jobs["aj_anchored"] = {
            "id": "aj_anchored",
            "settlement_batch_id": "sb_anchored",
            "lane": "forecast_15m",
            "state": "anchored",
            "anchor_payload_hash": "sha256:anchored",
            "broadcast_status": "broadcast_submitted",
            "broadcast_tx_hash": "OKTX",
            "last_broadcast_at": "2026-04-09T09:04:00Z",
            "failure_reason": None,
            "submitted_at": "2026-04-09T09:00:00Z",
            "anchored_at": "2026-04-09T09:06:00Z",
            "created_at": "2026-04-09T09:00:00Z",
            "updated_at": "2026-04-09T09:06:00Z",
        }

        data = client.get("/admin/anchor-jobs/action-queue").json()

        assert data["count"] == 2
        assert data["items"][0]["action_type"] == "review_failed_anchor"
        assert data["items"][0]["anchor_job_id"] == "aj_failed"
        assert data["items"][1]["action_type"] == "review_stale_pending_confirmation"
        assert data["items"][1]["anchor_job_id"] == "aj_stale"


def test_retry_broadcast_typed_endpoint_reissues_failed_anchor_job():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))

    async def fake_typed_broadcaster(plan, now):  # noqa: ANN001
        return {
            "tx_hash": "RETRYAPI123TX",
            "code": 0,
            "raw_log": "",
            "memo": plan["fallback_memo"],
            "broadcast_at": forecast_engine.isoformat_z(now),
            "account_number": 3,
            "sequence": 8,
            "attempt_count": 1,
            "broadcast_method": "typed_msg",
        }

    app = server.create_app(
        settings=forecast_engine.ForecastSettings(fast_task_seconds=900, commit_window_seconds=3, reveal_window_seconds=13),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
        chain_typed_broadcaster=fake_typed_broadcaster,
    )
    wallet = generate_wallet()
    with TestClient(app) as client:
        register_resp = client.post(
            "/clawchain/miner/register",
            json={
                "address": wallet["address"],
                "name": "miner-retry-typed",
                "public_key": wallet["public_key"],
                "miner_version": "0.4.0",
            },
        )
        assert register_resp.status_code == 200

        active = client.get("/v1/task-runs/active").json()["data"]["items"]
        fast_task = next(item for item in active if item["lane"] == "forecast_15m")

        p_yes_bps = 6400
        reveal_nonce = "salt-retry-typed"
        commit_hash = forecast_engine.compute_commit_hash(
            task_run_id=fast_task["task_run_id"],
            miner_address=wallet["address"],
            p_yes_bps=p_yes_bps,
            reveal_nonce=reveal_nonce,
        )
        commit_request_id = "req-commit-retry-typed"
        commit_sig = _sign(
            [fast_task["task_run_id"], commit_hash, reveal_nonce, wallet["address"], commit_request_id],
            wallet["private_key"],
        )
        commit_resp = client.post(
            f"/v1/task-runs/{fast_task['task_run_id']}/commit",
            json={
                "request_id": commit_request_id,
                "task_run_id": fast_task["task_run_id"],
                "miner_id": wallet["address"],
                "economic_unit_id": f"eu:{wallet['address']}",
                "commit_hash": commit_hash,
                "nonce": reveal_nonce,
                "client_version": "skill-v0.4.0",
                "signature": commit_sig,
            },
        )
        assert commit_resp.status_code == 200

        clock.advance(5)
        reveal_request_id = "req-reveal-retry-typed"
        reveal_sig = _sign(
            [fast_task["task_run_id"], str(p_yes_bps), reveal_nonce, wallet["address"], reveal_request_id],
            wallet["private_key"],
        )
        reveal_resp = client.post(
            f"/v1/task-runs/{fast_task['task_run_id']}/reveal",
            json={
                "request_id": reveal_request_id,
                "task_run_id": fast_task["task_run_id"],
                "miner_id": wallet["address"],
                "economic_unit_id": f"eu:{wallet['address']}",
                "p_yes_bps": p_yes_bps,
                "nonce": reveal_nonce,
                "schema_version": "v1",
                "signature": reveal_sig,
            },
        )
        assert reveal_resp.status_code == 200

        clock.advance(900)
        settlement_batches = client.get("/admin/settlement-batches").json()["items"]
        client.post(f"/admin/settlement-batches/{settlement_batches[0]['id']}/retry-anchor")
        client.post(f"/admin/settlement-batches/{settlement_batches[0]['id']}/submit-anchor")
        anchor_jobs = client.get("/admin/anchor-jobs").json()["items"]
        failed = client.post(
            f"/admin/anchor-jobs/{anchor_jobs[0]['id']}/mark-failed",
            json={"failure_reason": "rpc timeout"},
        ).json()

        receipt = client.post(f"/admin/anchor-jobs/{failed['id']}/retry-broadcast-typed").json()
        anchor_jobs_after = client.get("/admin/anchor-jobs").json()["items"]

        assert receipt["previous_anchor_job_id"] == failed["id"]
        assert receipt["new_anchor_job_id"] != failed["id"]
        assert receipt["tx_hash"] == "RETRYAPI123TX"
        assert receipt["broadcast_mode"] == "typed"
        assert anchor_jobs_after[0]["id"] == receipt["new_anchor_job_id"]
        assert anchor_jobs_after[0]["state"] == "anchor_submitted"
        assert anchor_jobs_after[0]["broadcast_tx_hash"] == "RETRYAPI123TX"


def test_settlement_batch_refreshes_open_batch_for_later_same_hour_tasks():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))
    app = server.create_app(
        settings=AppSettings(
            live_market_data_enabled=False,
            fast_task_seconds=60,
            commit_window_seconds=30,
            reveal_window_seconds=55,
        ),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    wallet = generate_wallet()

    def submit_active_fast_round(client: TestClient, *, round_idx: int) -> None:
        active = client.get("/v1/task-runs/active").json()["data"]["items"]
        fast_tasks = sorted(
            [item for item in active if item["lane"] == "forecast_15m"],
            key=lambda item: item["asset"],
        )
        assert [task["asset"] for task in fast_tasks] == ["BTCUSDT", "ETHUSDT"]

        pending_reveals: list[tuple[dict, int, str]] = []
        for task_idx, task in enumerate(fast_tasks, start=1):
            p_yes_bps = 5000 + (round_idx * 100) + task_idx
            reveal_nonce = f"round-{round_idx}-task-{task_idx}"
            commit_hash = forecast_engine.compute_commit_hash(
                task_run_id=task["task_run_id"],
                miner_address=wallet["address"],
                p_yes_bps=p_yes_bps,
                reveal_nonce=reveal_nonce,
            )
            commit_request_id = f"commit-r{round_idx}-t{task_idx}"
            commit_sig = _sign(
                [task["task_run_id"], commit_hash, reveal_nonce, wallet["address"], commit_request_id],
                wallet["private_key"],
            )
            commit_resp = client.post(
                f"/v1/task-runs/{task['task_run_id']}/commit",
                json={
                    "request_id": commit_request_id,
                    "task_run_id": task["task_run_id"],
                    "miner_id": wallet["address"],
                    "economic_unit_id": f"eu:{wallet['address']}",
                    "commit_hash": commit_hash,
                    "nonce": reveal_nonce,
                    "client_version": "skill-v0.4.0",
                    "signature": commit_sig,
                },
            )
            assert commit_resp.status_code == 200
            pending_reveals.append((task, p_yes_bps, reveal_nonce))

        clock.advance(5)

        for task_idx, (task, p_yes_bps, reveal_nonce) in enumerate(pending_reveals, start=1):
            reveal_request_id = f"reveal-r{round_idx}-t{task_idx}"
            reveal_sig = _sign(
                [task["task_run_id"], str(p_yes_bps), reveal_nonce, wallet["address"], reveal_request_id],
                wallet["private_key"],
            )
            reveal_resp = client.post(
                f"/v1/task-runs/{task['task_run_id']}/reveal",
                json={
                    "request_id": reveal_request_id,
                    "task_run_id": task["task_run_id"],
                    "miner_id": wallet["address"],
                    "economic_unit_id": f"eu:{wallet['address']}",
                    "p_yes_bps": p_yes_bps,
                    "nonce": reveal_nonce,
                    "schema_version": "v1",
                    "signature": reveal_sig,
                },
            )
            assert reveal_resp.status_code == 200

        clock.advance(65)

    with TestClient(app) as client:
        register_resp = client.post(
            "/clawchain/miner/register",
            json={
                "address": wallet["address"],
                "name": "miner-batch-refresh",
                "public_key": wallet["public_key"],
                "miner_version": "0.4.0",
            },
        )
        assert register_resp.status_code == 200

        submit_active_fast_round(client, round_idx=1)
        first_batch = client.get("/admin/settlement-batches").json()["items"][0]
        assert first_batch["task_count"] == 2

        submit_active_fast_round(client, round_idx=2)
        reward_window = client.get(f"/v1/miners/{wallet['address']}/reward-windows").json()["data"]["items"][0]
        refreshed_batch = client.get("/admin/settlement-batches").json()["items"][0]

        assert reward_window["task_run_ids"] == [
            "tr_fast_202604090900_btcusdt",
            "tr_fast_202604090900_ethusdt",
            "tr_fast_202604090901_btcusdt",
            "tr_fast_202604090901_ethusdt",
        ]
        assert refreshed_batch["id"] == first_batch["id"]
        assert refreshed_batch["state"] == "open"
        assert refreshed_batch["task_count"] == 4
        assert refreshed_batch["miner_count"] == 1
        assert refreshed_batch["total_reward_amount"] == reward_window["total_reward_amount"]


def test_stats_endpoint_reports_forecast_state():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    with TestClient(app) as client:
        data = client.get("/clawchain/stats").json()

        assert data["active_miners"] == 0
        assert data["active_fast_tasks"] >= 1
        assert data["protocol"] == "clawchain-forecast-v1"


def test_chain_preflight_endpoint_reports_readiness(monkeypatch):
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))

    async def fake_preflight(*, settings):  # noqa: ANN001
        return {
            "adapter_version": "clawchain.chain_adapter.v1",
            "binary": {"available": True, "resolved_path": "/abs/clawchaind"},
            "source_key": {"name": "val1", "address": "claw1source", "ok": True},
            "target_address": "claw1source",
            "target_mode": "self_transfer",
            "rpc": {"reachable": True, "latest_block_height": "123"},
            "ready": True,
            "warnings": [],
        }

    monkeypatch.setattr(server, "inspect_cli_broadcast_readiness", fake_preflight)

    app = server.create_app(
        settings=AppSettings(
            chain_binary="./clawchaind",
            anchor_key_name="val1",
            anchor_keyring_dir="deploy/testnet-artifacts/val1/keyring-test",
        ),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    with TestClient(app) as client:
        data = client.get("/admin/chain/preflight").json()

        assert data["ready"] is True
        assert data["target_mode"] == "self_transfer"
        assert data["source_key"]["address"] == "claw1source"


def test_create_app_uses_live_provider_when_repo_is_injected(monkeypatch):
    class DummyLiveProvider:
        def __init__(self, **kwargs):  # noqa: ANN003
            self.kwargs = kwargs

    class DummyHybridProvider:
        def __init__(self, *, live):
            self.live = live

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(server, "LiveMarketDataProvider", DummyLiveProvider)
    monkeypatch.setattr(server, "HybridMarketDataProvider", DummyHybridProvider)

    app = server.create_app(
        settings=AppSettings(live_market_data_enabled=True),
        repository=server.create_fake_repository(),
    )
    with TestClient(app) as client:
        provider = client.app.state.market_data_provider

        assert isinstance(provider, DummyHybridProvider)
        assert isinstance(provider.live, DummyLiveProvider)


def test_status_endpoint_allows_local_dashboard_origin():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    wallet = generate_wallet()
    with TestClient(app) as client:
        register_resp = client.post(
            "/clawchain/miner/register",
            json={
                "address": wallet["address"],
                "name": "miner-alpha",
                "public_key": wallet["public_key"],
                "miner_version": "0.4.0",
            },
        )
        assert register_resp.status_code == 200

        status_resp = client.get(
            f"/v1/miners/{wallet['address']}/status",
            headers={"origin": "http://127.0.0.1:3000"},
        )
        assert status_resp.status_code == 200
        assert status_resp.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"


def test_leaderboard_endpoint_returns_sorted_public_miners():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    wallet_a = generate_wallet()
    wallet_b = generate_wallet()
    wallet_c = generate_wallet()

    with TestClient(app) as client:
        for index, wallet in enumerate((wallet_a, wallet_b, wallet_c), start=1):
            register_resp = client.post(
                "/clawchain/miner/register",
                json={
                    "address": wallet["address"],
                    "name": f"miner-{index}",
                    "public_key": wallet["public_key"],
                    "miner_version": "0.4.0",
                },
            )
            assert register_resp.status_code == 200

        repo = app.state.repository
        import asyncio

        asyncio.run(
            repo.update_miner(
                wallet_a["address"],
                {
                    "public_rank": 2,
                    "public_elo": 1280,
                    "total_rewards": 900,
                    "settled_tasks": 6,
                },
            )
        )
        asyncio.run(
            repo.update_miner(
                wallet_b["address"],
                {
                    "public_rank": 1,
                    "public_elo": 1350,
                    "total_rewards": 1200,
                    "settled_tasks": 9,
                },
            )
        )
        asyncio.run(
            repo.update_miner(
                wallet_c["address"],
                {
                    "public_rank": None,
                    "public_elo": 1180,
                    "total_rewards": 300,
                    "settled_tasks": 2,
                },
            )
        )

        leaderboard_resp = client.get("/v1/leaderboard")
        assert leaderboard_resp.status_code == 200
        data = leaderboard_resp.json()["data"]
        assert data["items"][0]["address"] == wallet_b["address"]
        assert data["items"][1]["address"] == wallet_a["address"]
        assert data["items"][2]["address"] == wallet_c["address"]
        assert data["items"][0]["public_elo"] == 1350
        assert data["items"][0]["settled_tasks"] == 9


def test_register_binds_server_side_economic_unit():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    wallet = generate_wallet()
    with TestClient(app) as client:
        register_resp = client.post(
            "/clawchain/miner/register",
            json={
                "address": wallet["address"],
                "name": "miner-alpha",
                "public_key": wallet["public_key"],
                "miner_version": "0.4.0",
                "economic_unit_id": "eu:spoofed-client-value",
            },
        )
        assert register_resp.status_code == 200

        miner_resp = client.get(f"/clawchain/miner/{wallet['address']}")
        assert miner_resp.status_code == 200
        assert miner_resp.json()["economic_unit_id"] != "eu:spoofed-client-value"


def test_register_recomputes_transitive_economic_unit_clusters():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    wallet_a = generate_wallet()
    wallet_b = generate_wallet()
    wallet_c = generate_wallet()
    with TestClient(app) as client:
        for wallet, ip, user_agent in [
            (wallet_a, "10.0.0.1", "ua-a"),
            (wallet_b, "10.0.0.2", "ua-shared"),
            (wallet_c, "10.0.0.1", "ua-shared"),
        ]:
            resp = client.post(
                "/clawchain/miner/register",
                json={
                    "address": wallet["address"],
                    "name": "miner",
                    "public_key": wallet["public_key"],
                    "miner_version": "0.4.0",
                },
                headers={"x-forwarded-for": ip, "user-agent": user_agent},
            )
            assert resp.status_code == 200

        miner_a = client.get(f"/clawchain/miner/{wallet_a['address']}").json()
        miner_b = client.get(f"/clawchain/miner/{wallet_b['address']}").json()
        miner_c = client.get(f"/clawchain/miner/{wallet_c['address']}").json()

        assert miner_a["economic_unit_id"] == miner_b["economic_unit_id"] == miner_c["economic_unit_id"]


def test_admin_open_risk_cases_and_miner_status_count():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(fast_task_seconds=900, commit_window_seconds=3, reveal_window_seconds=13),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    wallet_a = generate_wallet()
    wallet_b = generate_wallet()

    with TestClient(app) as client:
        for wallet in (wallet_a, wallet_b):
            register_resp = client.post(
                "/clawchain/miner/register",
                json={
                    "address": wallet["address"],
                    "name": "miner-alpha",
                    "public_key": wallet["public_key"],
                    "miner_version": "0.4.0",
                },
                headers={"x-forwarded-for": "10.0.0.1", "user-agent": "shared-agent"},
            )
            assert register_resp.status_code == 200

        active = client.get("/v1/task-runs/active").json()["data"]["items"]
        fast_task = next(item for item in active if item["lane"] == "forecast_15m")

        for idx, wallet in enumerate((wallet_a, wallet_b), start=1):
            p_yes_bps = 6200 + idx * 100
            reveal_nonce = f"salt-{idx}"
            commit_hash = forecast_engine.compute_commit_hash(
                task_run_id=fast_task["task_run_id"],
                miner_address=wallet["address"],
                p_yes_bps=p_yes_bps,
                reveal_nonce=reveal_nonce,
            )
            commit_request_id = f"req-commit-{idx}"
            commit_sig = _sign(
                [fast_task["task_run_id"], commit_hash, reveal_nonce, wallet["address"], commit_request_id],
                wallet["private_key"],
            )
            commit_resp = client.post(
                f"/v1/task-runs/{fast_task['task_run_id']}/commit",
                json={
                    "request_id": commit_request_id,
                    "task_run_id": fast_task["task_run_id"],
                    "miner_id": wallet["address"],
                    "commit_hash": commit_hash,
                    "nonce": reveal_nonce,
                    "client_version": "skill-v0.4.0",
                    "signature": commit_sig,
                },
                headers={"x-forwarded-for": "10.0.0.1", "user-agent": "shared-agent"},
            )
            assert commit_resp.status_code == 200

            clock.advance(1)
            reveal_request_id = f"req-reveal-{idx}"
            reveal_sig = _sign(
                [fast_task["task_run_id"], str(p_yes_bps), reveal_nonce, wallet["address"], reveal_request_id],
                wallet["private_key"],
            )
            reveal_resp = client.post(
                f"/v1/task-runs/{fast_task['task_run_id']}/reveal",
                json={
                    "request_id": reveal_request_id,
                    "task_run_id": fast_task["task_run_id"],
                    "miner_id": wallet["address"],
                    "p_yes_bps": p_yes_bps,
                    "nonce": reveal_nonce,
                    "schema_version": "v1",
                    "signature": reveal_sig,
                },
                headers={"x-forwarded-for": "10.0.0.1", "user-agent": "shared-agent"},
            )
            assert reveal_resp.status_code == 200

        cases_resp = client.get("/admin/risk-cases/open")
        assert cases_resp.status_code == 200
        cases = cases_resp.json()["items"]
        assert any(case["case_type"] == "economic_unit_duplicate" for case in cases)

        miner_status = client.get(f"/v1/miners/{wallet_b['address']}/status")
        assert miner_status.status_code == 200
        assert miner_status.json()["data"]["open_risk_case_count"] >= 1


def test_admin_risk_override_closes_case_and_returns_operator_metadata():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(fast_task_seconds=900, commit_window_seconds=3, reveal_window_seconds=13),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    wallet_a = generate_wallet()
    wallet_b = generate_wallet()

    with TestClient(app) as client:
        for wallet in (wallet_a, wallet_b):
            register_resp = client.post(
                "/clawchain/miner/register",
                json={
                    "address": wallet["address"],
                    "name": "miner-alpha",
                    "public_key": wallet["public_key"],
                    "miner_version": "0.4.0",
                },
                headers={"x-forwarded-for": "10.0.0.1", "user-agent": "shared-agent"},
            )
            assert register_resp.status_code == 200

        cases_before = client.get("/admin/risk-cases/open")
        assert cases_before.status_code == 200
        case = cases_before.json()["items"][0]

        miner_status_before = client.get(f"/v1/miners/{wallet_b['address']}/status")
        assert miner_status_before.status_code == 200
        open_count_before = miner_status_before.json()["data"]["open_risk_case_count"]

        override_resp = client.post(
            f"/admin/risk-decisions/{case['id']}/override",
            json={
                "decision": "clear",
                "reason": "reviewed and accepted as same operator",
                "operator_id": "ops-1",
                "authority_level": "admin",
            },
        )
        assert override_resp.status_code == 200
        payload = override_resp.json()

        assert payload["operator_id"] == "ops-1"
        assert payload["authority_level"] == "admin"
        assert payload["trace_id"].startswith("trace:risk_override:")
        assert payload["override_log_id"].startswith("ovr:")
        assert payload["risk_case"]["id"] == case["id"]
        assert payload["risk_case"]["state"] == "cleared"
        assert payload["risk_case"]["decision"] == "clear"
        assert payload["risk_case"]["decision_reason"] == "reviewed and accepted as same operator"
        assert payload["risk_case"]["reviewed_by"] == "ops-1"
        assert payload["risk_case"]["authority_level"] == "admin"
        assert payload["risk_case"]["reviewed_at"] == clock.now().isoformat().replace("+00:00", "Z")

        cases_after = client.get("/admin/risk-cases/open")
        assert cases_after.status_code == 200
        assert all(item["id"] != case["id"] for item in cases_after.json()["items"])

        miner_status_after = client.get(f"/v1/miners/{wallet_b['address']}/status")
        assert miner_status_after.status_code == 200
        assert miner_status_after.json()["data"]["open_risk_case_count"] == open_count_before - 1


def test_admin_apply_arena_results_updates_multiplier():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    wallet = generate_wallet()
    with TestClient(app) as client:
        register_resp = client.post(
            "/clawchain/miner/register",
            json={
                "address": wallet["address"],
                "name": "arena-miner",
                "public_key": wallet["public_key"],
                "miner_version": "0.4.0",
            },
        )
        assert register_resp.status_code == 200

        for index in range(16):
            resp = client.post(
                "/admin/arena/results/apply",
                json={
                    "tournament_id": f"arena-rated-{index}",
                    "rated_or_practice": "rated",
                    "human_only": True,
                    "results": [
                        {
                            "miner_id": wallet["address"],
                            "arena_score": 0.9,
                        }
                    ],
                },
            )
            assert resp.status_code == 200

        miner_status = client.get(f"/v1/miners/{wallet['address']}/status")
        assert miner_status.status_code == 200
        assert miner_status.json()["data"]["arena_multiplier"] > 1.0


def poker_mtt_reward_ready_refs(
    tournament_id: str,
    miner_address: str,
    *,
    locked_at: str = "2026-04-10T09:00:00Z",
) -> dict:
    return {
        "final_ranking_id": f"poker_mtt_final_ranking:{tournament_id}:{miner_address}",
        "standing_snapshot_id": f"poker_mtt_standing_snapshot:{tournament_id}:abc",
        "standing_snapshot_hash": f"sha256:{tournament_id}",
        "evidence_root": f"sha256:evidence:{tournament_id}:{miner_address}",
        "evidence_state": "complete",
        "locked_at": locked_at,
    }


def test_admin_apply_poker_mtt_results_updates_poker_multiplier():
    clock = FrozenClock(datetime(2026, 4, 9, 9, 0, 1, tzinfo=timezone.utc))
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    wallet = generate_wallet()
    with TestClient(app) as client:
        register_resp = client.post(
            "/clawchain/miner/register",
            json={
                "address": wallet["address"],
                "name": "poker-mtt-miner",
                "public_key": wallet["public_key"],
                "miner_version": "0.4.0",
            },
        )
        assert register_resp.status_code == 200

        for index in range(16):
            resp = client.post(
                "/admin/poker-mtt/results/apply",
                json={
                    "tournament_id": f"poker-mtt-rated-{index}",
                    "rated_or_practice": "rated",
                    "human_only": True,
                    "field_size": 30,
                    "policy_bundle_version": "poker_mtt_v1",
                    "results": [
                        {
                            "miner_id": wallet["address"],
                            "final_rank": 2,
                            "tournament_result_score": 0.9,
                            "hidden_eval_score": 0.6,
                            "consistency_input_score": 0.3,
                            "evaluation_state": "final",
                            **poker_mtt_reward_ready_refs(
                                f"poker-mtt-rated-{index}",
                                wallet["address"],
                            ),
                        }
                    ],
                },
            )
            assert resp.status_code == 200

        miner_status = client.get(f"/v1/miners/{wallet['address']}/status")
        assert miner_status.status_code == 200
        assert miner_status.json()["data"]["poker_mtt_multiplier"] > 1.0


def test_admin_build_poker_mtt_reward_window_creates_anchor_ready_batch():
    clock = FrozenClock(datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc))
    app = server.create_app(
        settings=forecast_engine.ForecastSettings(),
        repository=server.create_fake_repository(),
        now_fn=clock.now,
    )
    wallet_one = generate_wallet()
    wallet_two = generate_wallet()
    with TestClient(app) as client:
        for wallet, name in ((wallet_one, "poker-window-one"), (wallet_two, "poker-window-two")):
            register_resp = client.post(
                "/clawchain/miner/register",
                json={
                    "address": wallet["address"],
                    "name": name,
                    "public_key": wallet["public_key"],
                    "miner_version": "0.4.0",
                },
            )
            assert register_resp.status_code == 200

        apply_resp = client.post(
            "/admin/poker-mtt/results/apply",
            json={
                "tournament_id": "poker-mtt-api-daily-1",
                "rated_or_practice": "rated",
                "human_only": True,
                "field_size": 30,
                "policy_bundle_version": "poker_mtt_v1",
                "results": [
                    {
                        "miner_id": wallet_one["address"],
                        "final_rank": 1,
                        "tournament_result_score": 1.0,
                        "hidden_eval_score": 0.0,
                        "consistency_input_score": 0.0,
                        "evaluation_state": "final",
                        **poker_mtt_reward_ready_refs("poker-mtt-api-daily-1", wallet_one["address"]),
                    },
                    {
                        "miner_id": wallet_two["address"],
                        "final_rank": 2,
                        "tournament_result_score": 0.5,
                        "hidden_eval_score": 0.0,
                        "consistency_input_score": 0.0,
                        "evaluation_state": "final",
                        **poker_mtt_reward_ready_refs("poker-mtt-api-daily-1", wallet_two["address"]),
                    },
                ],
            },
        )
        assert apply_resp.status_code == 200

        clock.advance(15 * 60 * 60)

        reward_window = client.post(
            "/admin/poker-mtt/reward-windows/build",
            json={
                "lane": "poker_mtt_daily",
                "window_start_at": "2026-04-10T00:00:00Z",
                "window_end_at": "2026-04-11T00:00:00Z",
                "reward_pool_amount": 100,
                "include_provisional": False,
                "policy_bundle_version": "poker_mtt_daily_policy_v2",
            },
        )
        assert reward_window.status_code == 200

        settlement_batches = client.get("/admin/settlement-batches").json()["items"]
        anchored_batch = client.post(f"/admin/settlement-batches/{settlement_batches[0]['id']}/retry-anchor").json()
        submitted_batch = client.post(f"/admin/settlement-batches/{settlement_batches[0]['id']}/submit-anchor").json()
        anchor_jobs = client.get("/admin/anchor-jobs").json()["items"]
        chain_tx_plan = client.get(f"/admin/anchor-jobs/{anchor_jobs[0]['id']}/chain-tx-plan").json()

        assert reward_window.json()["lane"] == "poker_mtt_daily"
        assert reward_window.json()["task_run_ids"] == ["poker-mtt-api-daily-1"]
        assert reward_window.json()["policy_bundle_version"] == "poker_mtt_daily_policy_v2"
        assert settlement_batches[0]["lane"] == "poker_mtt_daily"
        assert anchored_batch["state"] == "anchor_ready"
        assert anchored_batch["anchor_payload_json"]["task_run_ids"] == ["poker-mtt-api-daily-1"]
        assert anchored_batch["anchor_payload_json"]["policy_bundle_version"] == "poker_mtt_daily_policy_v2"
        assert submitted_batch["state"] == "anchor_submitted"
        assert anchor_jobs[0]["settlement_batch_id"] == settlement_batches[0]["id"]
        assert chain_tx_plan["future_msg"]["value"]["settlement_batch_id"] == settlement_batches[0]["id"]
