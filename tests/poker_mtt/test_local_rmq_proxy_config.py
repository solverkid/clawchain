from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROXY_CONFIG = ROOT / "deploy" / "poker-mtt" / "rocketmq" / "rmq-proxy.json"
COMPOSE_FILE = ROOT / "deploy" / "docker-compose.poker-mtt-local.yml"


def test_local_proxy_config_reuses_request_port_for_returned_endpoints() -> None:
    payload = json.loads(PROXY_CONFIG.read_text(encoding="utf-8"))

    assert payload["rocketMQClusterName"] == "DefaultCluster"
    assert payload["grpcServerPort"] == 8081
    assert payload["useEndpointPortFromRequest"] is True


def test_local_compose_mounts_custom_proxy_config() -> None:
    compose_text = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "./poker-mtt/rocketmq/rmq-proxy.json:/home/rocketmq/rocketmq-5.3.2/conf/rmq-proxy.json" in compose_text
    assert "condition: service_healthy" in compose_text
    assert "grep -q 'boot success' /home/rocketmq/logs/rocketmqlogs/broker.log" in compose_text
    assert "DefaultHeartBeatSyncerTopic" in compose_text
    assert "mqadmin updatetopic -n poker_mtt_rmqnamesrv:9876 -c DefaultCluster -t DefaultHeartBeatSyncerTopic" in compose_text
