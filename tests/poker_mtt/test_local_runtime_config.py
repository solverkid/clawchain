from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "deploy" / "docker-compose.poker-mtt-local.yml"
ROCKETMQ_BROKER_CONF = ROOT / "deploy" / "poker-mtt" / "rocketmq" / "broker.conf"
ROCKETMQ_PROXY_CONF = ROOT / "deploy" / "poker-mtt" / "rocketmq" / "rmq-proxy.json"
PATCH_SCRIPT = ROOT / "scripts" / "poker_mtt" / "patch_donor_local_safety.py"
DYNAMODB_INIT_SCRIPT = ROOT / "scripts" / "poker_mtt" / "init_local_dynamodb.sh"
LOG_CHECK_SCRIPT = ROOT / "scripts" / "poker_mtt" / "check_local_run_logs.py"


def test_local_compose_includes_dynamodb_local() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    service = compose["services"]["poker_mtt_dynamodb"]

    assert service["image"] == "amazon/dynamodb-local:2.5.4"
    assert "38000:8000" in service["ports"]
    assert "-jar DynamoDBLocal.jar -sharedDb -inMemory" in service["command"]


def test_local_compose_includes_rocketmq_proxy_and_host_reachable_broker() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose["services"]

    assert "poker_mtt_rmqnamesrv" in services
    assert "poker_mtt_rmqbroker" in services
    assert "poker_mtt_rmqproxy" in services
    assert "38081:8081" in services["poker_mtt_rmqproxy"]["ports"]
    for service_name in ("poker_mtt_rmqnamesrv", "poker_mtt_rmqbroker", "poker_mtt_rmqproxy"):
        assert services[service_name]["image"] == "apache/rocketmq:5.3.2"
        assert services[service_name].get("platform") is None

    broker_conf = ROCKETMQ_BROKER_CONF.read_text(encoding="utf-8")
    assert "brokerIP1=host.docker.internal" in broker_conf
    assert "brokerIP1=127.0.0.1" not in broker_conf
    assert "brokerIP1=poker_mtt_rmqbroker" not in broker_conf
    assert "10911:10911" in services["poker_mtt_rmqbroker"]["ports"]
    assert "host.docker.internal:host-gateway" in services["poker_mtt_rmqbroker"]["extra_hosts"]
    assert "host.docker.internal:host-gateway" in services["poker_mtt_rmqproxy"]["extra_hosts"]


def test_local_rocketmq_proxy_advertises_host_mapped_grpc_port() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    proxy = compose["services"]["poker_mtt_rmqproxy"]
    proxy_conf = yaml.safe_load(ROCKETMQ_PROXY_CONF.read_text(encoding="utf-8"))

    assert "38081:8081" in proxy["ports"]
    assert (
        "./poker-mtt/rocketmq/rmq-proxy.json:/home/rocketmq/rocketmq-5.3.2/conf/rmq-proxy.json"
        in proxy["volumes"]
    )
    assert "mqadmin updatetopic -n poker_mtt_rmqnamesrv:9876 -c DefaultCluster -t DefaultHeartBeatSyncerTopic" in proxy["command"][2]
    assert "exec sh mqproxy -pc /home/rocketmq/rocketmq-5.3.2/conf/rmq-proxy.json" in proxy["command"][2]
    assert proxy_conf["useEndpointPortFromRequest"] is True
    assert proxy_conf["grpcServerPort"] == 8081


def test_local_sidecar_starts_dynamodb_local() -> None:
    start_script = (ROOT / "scripts" / "poker_mtt" / "start_local_sidecar.sh").read_text(
        encoding="utf-8"
    )

    assert "poker_mtt_dynamodb" in start_script
    assert "38000" in start_script
    assert "init_local_dynamodb_with_retry" in start_script
    assert "poker_mtt_rmqproxy" in start_script
    assert "38081" in start_script
    assert "wait_for_http_200" in start_script
    assert 'kill -0 "$(cat "$PID_FILE")"' in start_script
    assert "http://127.0.0.1:18082/v1/hello" in start_script
    assert "http://127.0.0.1:18083/v1/mtt/hello" in start_script
    assert "start_new_session=True" in start_script


def test_local_dynamodb_init_creates_hand_history_tables() -> None:
    script = DYNAMODB_INIT_SCRIPT.read_text(encoding="utf-8")

    assert "--endpoint-url" in script
    assert "http://127.0.0.1:38000" in script
    assert "poker_mtt_hands" in script
    assert "poker_mtt_user_hand_history" in script
    assert "tournament_id" in script
    assert "hand_id" in script
    assert "player_user_id" in script


def test_patch_donor_local_safety_blocks_delete_group_member(tmp_path: Path) -> None:
    donor_file = tmp_path / "tencent_chat_room.go"
    backup_file = tmp_path / "tencent_chat_room.go.orig"
    donor_file.write_text(
        """
package thrid_part

import "context"

func DeleteGroupMember(ctx context.Context, groupID, chatRoomUserName string) (err error) {
	fullURL := ""
	_ = fullURL
	return
}
""".lstrip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(PATCH_SCRIPT),
            "--tencent-file",
            str(donor_file),
            "--backup",
            str(backup_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert backup_file.exists()
    patched = donor_file.read_text(encoding="utf-8")
    assert "if !config.ChatGroupAvailable" in patched
    assert "return nil" in patched

    restore = subprocess.run(
        [
            sys.executable,
            str(PATCH_SCRIPT),
            "--tencent-file",
            str(donor_file),
            "--backup",
            str(backup_file),
            "--restore",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert restore.returncode == 0, restore.stderr or restore.stdout
    assert "if !config.ChatGroupAvailable" not in donor_file.read_text(encoding="utf-8")


def test_patch_donor_local_safety_does_not_skip_delete_group_when_other_functions_are_guarded(
    tmp_path: Path,
) -> None:
    donor_file = tmp_path / "tencent_chat_room.go"
    backup_file = tmp_path / "tencent_chat_room.go.orig"
    donor_file.write_text(
        """
package thrid_part

import (
	"context"
	"le_poker/config"
)

func CreateGroup(ctx context.Context, groupID string) error {
	if !config.ChatGroupAvailable {
		return nil
	}
	return nil
}

func DeleteGroupMember(ctx context.Context, groupID, chatRoomUserName string) (err error) {
	fullURL := ""
	_ = fullURL
	return
}
""".lstrip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(PATCH_SCRIPT),
            "--tencent-file",
            str(donor_file),
            "--backup",
            str(backup_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    patched = donor_file.read_text(encoding="utf-8")
    delete_group_member = patched[patched.index("func DeleteGroupMember") :]
    assert "if !config.ChatGroupAvailable" in delete_group_member


def test_local_run_log_checker_blocks_tencent_mq_and_operation_overflow(tmp_path: Path) -> None:
    log_file = tmp_path / "run_server.log"
    log_file.write_text(
        "\n".join(
            [
                "POST https://adminapisgp.im.qcloud.com/v4/group_open_http_svc/delete_group_member",
                "send POKER_RECORD_TOPIC failed: create grpc conn failed, err=context deadline exceeded",
                "channle is full to write,length:100,cap:100",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(LOG_CHECK_SCRIPT), str(log_file)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "tencent_im_external_call" in result.stdout
    assert "rocketmq_publish_failure" in result.stdout
    assert "operation_channel_overflow" in result.stdout


def test_local_run_log_checker_can_report_allowed_historical_mq_and_overflow(tmp_path: Path) -> None:
    log_file = tmp_path / "historical.log"
    log_file.write_text(
        "\n".join(
            [
                "send POKER_RECORD_TOPIC failed: create grpc conn failed, err=context deadline exceeded",
                "channle is full to write,length:100,cap:100",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(LOG_CHECK_SCRIPT),
            "--allow-rocketmq-publish-failure",
            "--allow-operation-channel-overflow",
            str(log_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert '"blocking_findings": []' in result.stdout
