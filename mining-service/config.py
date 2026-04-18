from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if not raw:
        return default
    items = tuple(item.strip() for item in raw.split(",") if item.strip())
    return items or default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw not in {"0", "false", "False"}


def _optional_int_env(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return None
    return int(raw)


def _admin_auth_default() -> bool:
    return os.getenv("CLAWCHAIN_ENV", "local").lower() not in {"local", "dev", "development", "test"}


@dataclass(slots=True)
class AppSettings:
    runtime_env: str | None = os.getenv("CLAWCHAIN_ENV")
    bind_host: str = os.getenv("CLAWCHAIN_BIND_HOST", "127.0.0.1")
    database_url: str | None = os.getenv("CLAWCHAIN_DATABASE_URL")
    live_market_data_enabled: bool = os.getenv("CLAWCHAIN_LIVE_MARKET_DATA_ENABLED", "1") not in {"0", "false", "False"}
    market_data_timeout_seconds: float = float(os.getenv("CLAWCHAIN_MARKET_DATA_TIMEOUT_SECONDS", "8.0"))
    binance_base_url: str = os.getenv("CLAWCHAIN_BINANCE_BASE_URL", "https://api.binance.com")
    polymarket_gamma_url: str = os.getenv("CLAWCHAIN_POLYMARKET_GAMMA_URL", "https://gamma-api.polymarket.com")
    polymarket_clob_url: str = os.getenv("CLAWCHAIN_POLYMARKET_CLOB_URL", "https://clob.polymarket.com")
    fast_task_seconds: int = int(os.getenv("CLAWCHAIN_FAST_TASK_SECONDS", "900"))
    commit_window_seconds: int = int(os.getenv("CLAWCHAIN_COMMIT_WINDOW_SECONDS", "3"))
    reveal_window_seconds: int = int(os.getenv("CLAWCHAIN_REVEAL_WINDOW_SECONDS", "13"))
    daily_cutoff_hour_utc: int = int(os.getenv("CLAWCHAIN_DAILY_CUTOFF_HOUR_UTC", "0"))
    poker_mtt_reward_windows_enabled: bool = _bool_env("CLAWCHAIN_POKER_MTT_REWARD_WINDOWS_ENABLED", False)
    poker_mtt_settlement_anchoring_enabled: bool = _bool_env(
        "CLAWCHAIN_POKER_MTT_SETTLEMENT_ANCHORING_ENABLED",
        False,
    )
    poker_mtt_daily_reward_pool_amount: int = int(os.getenv("CLAWCHAIN_POKER_MTT_DAILY_REWARD_POOL_AMOUNT", "0"))
    poker_mtt_weekly_reward_pool_amount: int = int(os.getenv("CLAWCHAIN_POKER_MTT_WEEKLY_REWARD_POOL_AMOUNT", "0"))
    poker_mtt_finalization_watermark_seconds: int = int(
        os.getenv("CLAWCHAIN_POKER_MTT_FINALIZATION_WATERMARK_SECONDS", "21600")
    )
    poker_mtt_daily_policy_bundle_version: str = os.getenv(
        "CLAWCHAIN_POKER_MTT_DAILY_POLICY_BUNDLE_VERSION",
        "poker_mtt_daily_policy_v1",
    )
    poker_mtt_weekly_policy_bundle_version: str = os.getenv(
        "CLAWCHAIN_POKER_MTT_WEEKLY_POLICY_BUNDLE_VERSION",
        "poker_mtt_weekly_policy_v1",
    )
    poker_mtt_projection_artifact_page_size: int = int(
        os.getenv("CLAWCHAIN_POKER_MTT_PROJECTION_ARTIFACT_PAGE_SIZE", "5000")
    )
    poker_mtt_reward_window_reconcile_lookback_days: int = int(
        os.getenv("CLAWCHAIN_POKER_MTT_REWARD_WINDOW_RECONCILE_LOOKBACK_DAYS", "35")
    )
    baseline_pm_weight: float = float(os.getenv("CLAWCHAIN_BASELINE_PM_WEIGHT", "0.85"))
    baseline_bin_weight: float = float(os.getenv("CLAWCHAIN_BASELINE_BIN_WEIGHT", "0.15"))
    max_binance_snapshot_freshness_seconds: int = int(
        os.getenv("CLAWCHAIN_MAX_BINANCE_SNAPSHOT_FRESHNESS_SECONDS", "30")
    )
    max_polymarket_snapshot_freshness_seconds: int = int(
        os.getenv("CLAWCHAIN_MAX_POLYMARKET_SNAPSHOT_FRESHNESS_SECONDS", "30")
    )
    min_p_yes_bps: int = int(os.getenv("CLAWCHAIN_MIN_P_YES_BPS", "1500"))
    max_p_yes_bps: int = int(os.getenv("CLAWCHAIN_MAX_P_YES_BPS", "8500"))
    min_miner_version: str = os.getenv("CLAWCHAIN_MIN_MINER_VERSION", "0.4.0")
    server_version: str = os.getenv("CLAWCHAIN_SERVER_VERSION", "1.0.0-alpha")
    protocol: str = os.getenv("CLAWCHAIN_PROTOCOL", "clawchain-forecast-v1")
    chain_binary: str = os.getenv("CLAWCHAIN_CHAIN_BINARY", "clawchaind")
    chain_id: str = os.getenv("CLAWCHAIN_CHAIN_ID", "clawchain-testnet-1")
    chain_node_rpc: str = os.getenv("CLAWCHAIN_CHAIN_NODE_RPC", "tcp://127.0.0.1:26657")
    anchor_key_name: str | None = os.getenv("CLAWCHAIN_ANCHOR_KEY_NAME")
    anchor_keyring_dir: str | None = os.getenv("CLAWCHAIN_ANCHOR_KEYRING_DIR")
    anchor_keyring_backend: str = os.getenv("CLAWCHAIN_ANCHOR_KEYRING_BACKEND", "test")
    anchor_to_address: str | None = os.getenv("CLAWCHAIN_ANCHOR_TO_ADDRESS")
    anchor_amount: str = os.getenv("CLAWCHAIN_ANCHOR_AMOUNT", "1uclaw")
    anchor_fees: str = os.getenv("CLAWCHAIN_ANCHOR_FEES", "10uclaw")
    anchor_gas: str = os.getenv("CLAWCHAIN_ANCHOR_GAS", "200000")
    anchor_offline_signing: bool = _bool_env("CLAWCHAIN_ANCHOR_OFFLINE_SIGNING", True)
    anchor_account_number: int | None = _optional_int_env("CLAWCHAIN_ANCHOR_ACCOUNT_NUMBER")
    anchor_sequence_override: int | None = _optional_int_env("CLAWCHAIN_ANCHOR_SEQUENCE_OVERRIDE")
    anchor_reconcile_loop_enabled: bool = _bool_env("CLAWCHAIN_ANCHOR_RECONCILE_LOOP_ENABLED", True)
    anchor_reconcile_loop_interval_seconds: float = float(
        os.getenv("CLAWCHAIN_ANCHOR_RECONCILE_LOOP_INTERVAL_SECONDS", "15.0")
    )
    anchor_reconcile_loop_error_alert_threshold: int = int(
        os.getenv("CLAWCHAIN_ANCHOR_RECONCILE_LOOP_ERROR_ALERT_THRESHOLD", "3")
    )
    anchor_pending_confirmation_warning_seconds: float = float(
        os.getenv("CLAWCHAIN_ANCHOR_PENDING_CONFIRMATION_WARNING_SECONDS", "120.0")
    )
    admin_auth_enabled: bool = _bool_env("CLAWCHAIN_ADMIN_AUTH_ENABLED", _admin_auth_default())
    admin_auth_token: str | None = os.getenv("CLAWCHAIN_ADMIN_AUTH_TOKEN")
    allow_insecure_admin_without_auth: bool = _bool_env("CLAWCHAIN_ALLOW_INSECURE_ADMIN_WITHOUT_AUTH", False)
    cors_allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: _csv_env(
            "CLAWCHAIN_CORS_ALLOWED_ORIGINS",
            (
                "http://127.0.0.1:3000",
                "http://localhost:3000",
                "http://127.0.0.1:3001",
                "http://localhost:3001",
                "https://0xverybigorange.github.io",
            ),
        )
    )


def load_settings() -> AppSettings:
    return AppSettings()
