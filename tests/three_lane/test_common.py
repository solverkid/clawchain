from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "three_lane"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import common


def test_build_manifest_is_deterministic_for_namespace_and_count():
    first = common.build_manifest(count=3, namespace="test-three-lane")
    second = common.build_manifest(count=3, namespace="test-three-lane")

    assert first["manifest_root"] == second["manifest_root"]
    assert [item["address"] for item in first["miners"]] == [item["address"] for item in second["miners"]]
    assert first["count"] == 3


def test_load_or_create_manifest_round_trips(tmp_path: Path):
    path = tmp_path / "miners.json"

    created = common.load_or_create_manifest(path, count=2, namespace="round-trip")
    loaded = json.loads(path.read_text(encoding="utf-8"))

    assert loaded["manifest_root"] == created["manifest_root"]
    assert len(loaded["miners"]) == 2
    assert loaded["miners"][0]["address"].startswith("claw1")


def test_register_manifest_miners_syncs_server_owned_economic_unit_and_persists(tmp_path: Path, monkeypatch):
    path = tmp_path / "miners.json"
    manifest = common.load_or_create_manifest(path, count=1, namespace="sync-existing")
    original_root = manifest["manifest_root"]
    miner = manifest["miners"][0]

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, object]):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self) -> dict[str, object]:
            return dict(self._payload)

    class FakeSession:
        headers: dict[str, str] = {}

        def get(self, url: str, timeout: float):  # noqa: ARG002
            assert url.endswith(f"/clawchain/miner/{miner['address']}")
            return FakeResponse(
                200,
                {
                    "address": miner["address"],
                    "name": miner["name"],
                    "status": "active",
                    "registration_index": 1,
                    "economic_unit_id": "eu:server-owned",
                },
            )

        def post(self, url: str, json: dict[str, object], timeout: float):  # noqa: ARG002
            raise AssertionError(f"unexpected register POST to {url} with payload {json}")

    monkeypatch.setattr(common, "requests_session", lambda: FakeSession())

    records = common.register_manifest_miners(
        base_url="http://127.0.0.1:1317",
        manifest=manifest,
        manifest_path=path,
    )

    assert records[0]["sync_source"] == "existing"
    assert records[0]["economic_unit_id"] == "eu:server-owned"
    assert manifest["miners"][0]["economic_unit_id"] == "eu:server-owned"
    assert manifest["manifest_root"] != original_root

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["miners"][0]["economic_unit_id"] == "eu:server-owned"
    assert persisted["manifest_root"] == manifest["manifest_root"]
