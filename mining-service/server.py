#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import argparse
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import logging

from eth_keys import keys as eth_keys
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from config import AppSettings, load_settings
from crypto_auth import verify_address_pubkey_binding
from forecast_engine import (
    ForecastMiningService,
    ForecastSettings,
    build_signature_hash,
    utc_now,
)
from market_data import HybridMarketDataProvider, LiveMarketDataProvider, SyntheticMarketDataProvider
from pg_repository import PostgresRepository
from repository import FakeRepository
from schemas import (
    ApplyArenaResultsRequest,
    ApplyPokerMTTFinalRankingProjectionRequest,
    BuildPokerMTTRatingSnapshotRequest,
    FinalizePokerMTTHiddenEvalRequest,
    PokerMTTHandCompletedEventRequest,
    ApplyPokerMTTResultsRequest,
    BuildPokerMTTRewardWindowRequest,
    CommitRequest,
    RegisterMinerRequest,
    RevealRequest,
    RiskDecisionOverrideRequest,
)
from chain_adapter import (
    broadcast_anchor_tx_via_cli,
    broadcast_anchor_tx_via_typed_cli,
    inspect_broadcast_tx_confirmation_async,
    inspect_cli_broadcast_readiness,
)


logger = logging.getLogger(__name__)


def create_fake_repository() -> FakeRepository:
    return FakeRepository()


def _iso_now(now_fn) -> str:
    return now_fn().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.endswith("Z"):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return None


def _verify_signature(parts: list[str], signature_hex: str, public_key_hex: str) -> bool:
    try:
        signature = eth_keys.Signature(bytes.fromhex(signature_hex.removeprefix("0x")))
        expected_pub = eth_keys.PublicKey(bytes.fromhex(public_key_hex.removeprefix("0x")))
        recovered = signature.recover_public_key_from_msg_hash(build_signature_hash(parts))
        return recovered == expected_pub
    except Exception:
        return False


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


def _envelope(*, object_id: str, object_type: str, lane: str, settings: AppSettings, now_fn, data: dict) -> dict:
    return {
        "object_id": object_id,
        "object_type": object_type,
        "lane": lane,
        "schema_version": "v1",
        "policy_bundle_version": "pb_2026_04_09_a",
        "server_time": _iso_now(now_fn),
        "trace_id": f"trc:{object_id}",
        "data": data,
    }


def _forecast_settings(settings: AppSettings) -> ForecastSettings:
    return ForecastSettings(
        fast_task_seconds=settings.fast_task_seconds,
        commit_window_seconds=settings.commit_window_seconds,
        reveal_window_seconds=settings.reveal_window_seconds,
        daily_cutoff_hour_utc=settings.daily_cutoff_hour_utc,
        poker_mtt_reward_windows_enabled=getattr(settings, "poker_mtt_reward_windows_enabled", False),
        poker_mtt_settlement_anchoring_enabled=getattr(settings, "poker_mtt_settlement_anchoring_enabled", False),
        poker_mtt_daily_reward_pool_amount=getattr(settings, "poker_mtt_daily_reward_pool_amount", 0),
        poker_mtt_weekly_reward_pool_amount=getattr(settings, "poker_mtt_weekly_reward_pool_amount", 0),
        poker_mtt_finalization_watermark_seconds=getattr(settings, "poker_mtt_finalization_watermark_seconds", 21600),
        poker_mtt_daily_policy_bundle_version=getattr(settings, "poker_mtt_daily_policy_bundle_version", "poker_mtt_daily_policy_v1"),
        poker_mtt_weekly_policy_bundle_version=getattr(settings, "poker_mtt_weekly_policy_bundle_version", "poker_mtt_weekly_policy_v1"),
        poker_mtt_projection_artifact_page_size=getattr(settings, "poker_mtt_projection_artifact_page_size", 5000),
        baseline_pm_weight=settings.baseline_pm_weight,
        baseline_bin_weight=settings.baseline_bin_weight,
        max_binance_snapshot_freshness_seconds=settings.max_binance_snapshot_freshness_seconds,
        max_polymarket_snapshot_freshness_seconds=settings.max_polymarket_snapshot_freshness_seconds,
        min_p_yes_bps=settings.min_p_yes_bps,
        max_p_yes_bps=settings.max_p_yes_bps,
        min_miner_version=settings.min_miner_version,
        server_version=settings.server_version,
        protocol=settings.protocol,
    )


def _build_default_market_data_provider(settings) -> SyntheticMarketDataProvider | HybridMarketDataProvider:
    live_market_data_enabled = bool(getattr(settings, "live_market_data_enabled", False))
    if live_market_data_enabled:
        return HybridMarketDataProvider(
            live=LiveMarketDataProvider(
                timeout_seconds=float(getattr(settings, "market_data_timeout_seconds", 8.0)),
                binance_base_url=getattr(settings, "binance_base_url", "https://api.binance.com"),
                polymarket_gamma_url=getattr(settings, "polymarket_gamma_url", "https://gamma-api.polymarket.com"),
                polymarket_clob_url=getattr(settings, "polymarket_clob_url", "https://clob.polymarket.com"),
            )
        )
    return SyntheticMarketDataProvider()


def _new_anchor_reconcile_metrics(*, enabled: bool, interval_seconds: float) -> dict:
    return {
        "enabled": enabled,
        "interval_seconds": interval_seconds,
        "active": False,
        "run_count": 0,
        "success_count": 0,
        "error_count": 0,
        "consecutive_error_count": 0,
        "last_started_at": None,
        "last_completed_at": None,
        "last_result_count": 0,
        "last_error": None,
    }


async def _run_anchor_reconcile_loop(*, service: ForecastMiningService, now_fn, interval_seconds: float, metrics: dict | None = None) -> None:
    while True:
        started_at = now_fn()
        if metrics is not None:
            metrics["last_started_at"] = _iso_datetime(started_at)
        try:
            items = await service.reconcile_pending_anchor_jobs_on_chain(now=started_at)
        except Exception as exc:
            if metrics is not None:
                metrics["run_count"] += 1
                metrics["error_count"] += 1
                metrics["consecutive_error_count"] += 1
                metrics["last_completed_at"] = _iso_datetime(now_fn())
                metrics["last_error"] = str(exc)
            logger.exception("anchor reconcile loop iteration failed")
        else:
            if metrics is not None:
                metrics["run_count"] += 1
                metrics["success_count"] += 1
                metrics["consecutive_error_count"] = 0
                metrics["last_completed_at"] = _iso_datetime(now_fn())
                metrics["last_result_count"] = len(items)
                metrics["last_error"] = None
        await asyncio.sleep(interval_seconds)


def _anchor_job_reference_time(item: dict) -> datetime | None:
    return (
        _parse_datetime(item.get("last_broadcast_at"))
        or _parse_datetime(item.get("updated_at"))
        or _parse_datetime(item.get("submitted_at"))
        or _parse_datetime(item.get("created_at"))
    )


def _build_chain_health_snapshot(*, anchor_jobs: list[dict], metrics: dict, settings: AppSettings, current_time: datetime) -> dict:
    latest_broadcast_at = None
    latest_anchored_at = None
    latest_failed_at = None
    latest_failure_reason = None
    pending_confirmation_count = 0
    stale_pending_confirmation_count = 0
    awaiting_broadcast_count = 0
    anchored_count = 0
    failed_count = 0
    alerts = []
    pending_warning_seconds = float(getattr(settings, "anchor_pending_confirmation_warning_seconds", 120.0))
    loop_error_threshold = int(getattr(settings, "anchor_reconcile_loop_error_alert_threshold", 3))

    for item in anchor_jobs:
        state = item.get("state")
        broadcast_tx_hash = item.get("broadcast_tx_hash")
        reference_time = _anchor_job_reference_time(item)

        if state == "anchor_submitted" and broadcast_tx_hash:
            pending_confirmation_count += 1
            if reference_time is not None:
                age_seconds = max(0, int((current_time - reference_time).total_seconds()))
                if age_seconds >= pending_warning_seconds:
                    stale_pending_confirmation_count += 1
        elif state == "anchor_submitted":
            awaiting_broadcast_count += 1
        elif state == "anchored":
            anchored_count += 1
        elif state == "anchor_failed":
            failed_count += 1
            failed_at = item.get("updated_at") or item.get("last_broadcast_at")
            if failed_at and (latest_failed_at is None or failed_at > latest_failed_at):
                latest_failed_at = failed_at
                latest_failure_reason = item.get("failure_reason")

        broadcast_at = item.get("last_broadcast_at")
        if broadcast_at and (latest_broadcast_at is None or broadcast_at > latest_broadcast_at):
            latest_broadcast_at = broadcast_at

        anchored_at = item.get("anchored_at")
        if anchored_at and (latest_anchored_at is None or anchored_at > latest_anchored_at):
            latest_anchored_at = anchored_at

    if int(metrics.get("consecutive_error_count", 0) or 0) >= loop_error_threshold:
        alerts.append(
            {
                "code": "anchor_reconcile_loop_errors",
                "severity": "critical",
                "message": "anchor reconcile loop consecutive errors exceeded threshold",
            }
        )
    if stale_pending_confirmation_count > 0:
        alerts.append(
            {
                "code": "stale_pending_confirmation",
                "severity": "warning",
                "message": "one or more anchor jobs have pending confirmations beyond threshold",
            }
        )
    if failed_count > 0:
        alerts.append(
            {
                "code": "failed_anchor_jobs_present",
                "severity": "warning",
                "message": "one or more anchor jobs are in anchor_failed state",
            }
        )

    status = "ok"
    if any(item["severity"] == "critical" for item in alerts):
        status = "critical"
    elif alerts:
        status = "degraded"

    return {
        "status": status,
        "loop": dict(metrics),
        "anchor_jobs": {
            "total_count": len(anchor_jobs),
            "pending_confirmation_count": pending_confirmation_count,
            "stale_pending_confirmation_count": stale_pending_confirmation_count,
            "awaiting_broadcast_count": awaiting_broadcast_count,
            "anchored_count": anchored_count,
            "failed_count": failed_count,
            "latest_broadcast_at": latest_broadcast_at,
            "latest_anchored_at": latest_anchored_at,
            "latest_failed_at": latest_failed_at,
            "latest_failure_reason": latest_failure_reason,
        },
        "alerts": alerts,
    }


def _build_anchor_action_queue(*, anchor_jobs: list[dict], settings: AppSettings, current_time: datetime) -> list[dict]:
    items = []
    pending_warning_seconds = float(getattr(settings, "anchor_pending_confirmation_warning_seconds", 120.0))

    for item in anchor_jobs:
        reference_time = _anchor_job_reference_time(item)
        age_seconds = None
        if reference_time is not None:
            age_seconds = max(0, int((current_time - reference_time).total_seconds()))

        if item.get("state") == "anchor_failed":
            items.append(
                {
                    "action_type": "review_failed_anchor",
                    "severity": "high",
                    "anchor_job_id": item.get("id"),
                    "settlement_batch_id": item.get("settlement_batch_id"),
                    "state": item.get("state"),
                    "tx_hash": item.get("broadcast_tx_hash"),
                    "last_broadcast_at": item.get("last_broadcast_at"),
                    "updated_at": item.get("updated_at"),
                    "age_seconds": age_seconds,
                    "failure_reason": item.get("failure_reason"),
                }
            )
            continue

        if item.get("state") == "anchor_submitted" and item.get("broadcast_tx_hash") and age_seconds is not None and age_seconds >= pending_warning_seconds:
            items.append(
                {
                    "action_type": "review_stale_pending_confirmation",
                    "severity": "medium",
                    "anchor_job_id": item.get("id"),
                    "settlement_batch_id": item.get("settlement_batch_id"),
                    "state": item.get("state"),
                    "tx_hash": item.get("broadcast_tx_hash"),
                    "last_broadcast_at": item.get("last_broadcast_at"),
                    "updated_at": item.get("updated_at"),
                    "age_seconds": age_seconds,
                    "failure_reason": item.get("failure_reason"),
                }
            )

    severity_rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    items.sort(
        key=lambda item: (
            -severity_rank.get(item.get("severity", "low"), 0),
            -(item.get("age_seconds") or 0),
            item.get("anchor_job_id") or "",
        )
    )
    return items


def create_app(
    settings: AppSettings | None = None,
    repository=None,
    now_fn=None,
    market_data_provider=None,
    chain_broadcaster=None,
    chain_typed_broadcaster=None,
    chain_tx_confirmer=None,
) -> FastAPI:
    app_settings = settings or load_settings()
    clock = now_fn or utc_now
    repo = repository
    provider = market_data_provider

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal repo, provider
        anchor_reconcile_task = None
        loop_enabled = bool(getattr(app_settings, "anchor_reconcile_loop_enabled", True))
        loop_interval_seconds = float(getattr(app_settings, "anchor_reconcile_loop_interval_seconds", 15.0))
        if repo is None:
            if not app_settings.database_url:
                raise RuntimeError("CLAWCHAIN_DATABASE_URL is required for runtime Postgres repository")
            repo = PostgresRepository(app_settings.database_url)
            await repo.init_schema()
        if provider is None:
            provider = _build_default_market_data_provider(app_settings)
        app.state.repository = repo
        app.state.market_data_provider = provider

        async def default_chain_broadcaster(plan, at_time):  # noqa: ANN001
            return await broadcast_anchor_tx_via_cli(plan=plan, settings=app_settings, now=_iso_now(lambda: at_time))

        async def default_chain_typed_broadcaster(plan, at_time):  # noqa: ANN001
            return await broadcast_anchor_tx_via_typed_cli(
                plan=plan,
                settings=app_settings,
                now=_iso_now(lambda: at_time),
            )

        async def default_chain_tx_confirmer(tx_hash, at_time):  # noqa: ANN001
            return await inspect_broadcast_tx_confirmation_async(
                settings=app_settings,
                tx_hash=tx_hash,
            )

        app.state.service = ForecastMiningService(
            repo,
            _forecast_settings(app_settings),
            task_provider=provider,
            chain_broadcaster=chain_broadcaster or default_chain_broadcaster,
            chain_typed_broadcaster=chain_typed_broadcaster or default_chain_typed_broadcaster,
            chain_tx_confirmer=chain_tx_confirmer or default_chain_tx_confirmer,
        )
        app.state.settings = app_settings
        app.state.now_fn = clock
        app.state.anchor_reconcile_metrics = _new_anchor_reconcile_metrics(
            enabled=loop_enabled,
            interval_seconds=loop_interval_seconds,
        )
        if repository is None and loop_enabled:
            app.state.anchor_reconcile_metrics["active"] = True
            anchor_reconcile_task = asyncio.create_task(
                _run_anchor_reconcile_loop(
                    service=app.state.service,
                    now_fn=clock,
                    interval_seconds=loop_interval_seconds,
                    metrics=app.state.anchor_reconcile_metrics,
                )
            )
        yield
        if anchor_reconcile_task is not None:
            app.state.anchor_reconcile_metrics["active"] = False
            anchor_reconcile_task.cancel()
            with suppress(asyncio.CancelledError):
                await anchor_reconcile_task
        if hasattr(provider, "aclose"):
            await provider.aclose()

    app = FastAPI(title="ClawChain Forecast Mining Service", version=app_settings.server_version, lifespan=lifespan)
    cors_allowed_origins = list(
        getattr(
            app_settings,
            "cors_allowed_origins",
            (
                "http://127.0.0.1:3000",
                "http://localhost:3000",
                "http://127.0.0.1:3001",
                "http://localhost:3001",
            ),
        )
    )
    if cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_allowed_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def require_admin_auth(request: Request, call_next):  # noqa: ANN001
        if (
            request.method.upper() != "OPTIONS"
            and request.url.path.startswith("/admin/")
            and bool(getattr(app_settings, "admin_auth_enabled", False))
        ):
            expected_token = getattr(app_settings, "admin_auth_token", None)
            authorization = request.headers.get("Authorization", "")
            if not expected_token or authorization != f"Bearer {expected_token}":
                return JSONResponse({"detail": "admin authorization required"}, status_code=401)
        return await call_next(request)

    def service() -> ForecastMiningService:
        return app.state.service

    def settings_obj() -> AppSettings:
        return app.state.settings

    def now() -> datetime:
        return app.state.now_fn()

    @app.get("/clawchain/version")
    async def get_version():
        return {
            "server_version": settings_obj().server_version,
            "min_miner_version": settings_obj().min_miner_version,
            "protocol": settings_obj().protocol,
        }

    @app.post("/clawchain/miner/register")
    async def register_miner(payload: RegisterMinerRequest, request: Request):
        binding_ok, binding_err = verify_address_pubkey_binding(payload.address, payload.public_key)
        if not binding_ok:
            raise HTTPException(status_code=400, detail=binding_err)
        try:
            miner = await service().register_miner(
                address=payload.address,
                name=payload.name,
                public_key=payload.public_key,
                miner_version=payload.miner_version,
                ip_address=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        except ValueError as exc:
            detail = str(exc)
            status = 409 if "already registered" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return {
            "success": True,
            "message": "miner registered successfully",
            "address": miner["address"],
            "registration_index": miner["registration_index"],
        }

    @app.get("/clawchain/miner/{address}")
    async def get_miner_info(address: str):
        miner = await app.state.repository.get_miner(address)
        if not miner:
            raise HTTPException(status_code=404, detail="miner not found")
        return {
            "address": miner["address"],
            "name": miner["name"],
            "status": miner["status"],
            "registration_index": miner["registration_index"],
            "economic_unit_id": miner["economic_unit_id"],
        }

    @app.get("/clawchain/miner/{address}/stats")
    async def get_miner_stats(address: str):
        try:
            status = await service().get_miner_status(address, now())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {
            "address": address,
            "forecast_commits": status["forecast_commits"],
            "forecast_reveals": status["forecast_reveals"],
            "settled_tasks": status["settled_tasks"],
            "total_rewards": status["total_rewards"],
            "public_rank": status["public_rank"],
            "public_elo": status["public_elo"],
        }

    @app.get("/clawchain/stats")
    async def get_stats():
        return await service().get_stats(now())

    @app.get("/v1/task-runs/active")
    async def get_active_tasks():
        items = await service().get_active_tasks(now())
        return _envelope(
            object_id="active-task-runs",
            object_type="task_run_list",
            lane="forecast_15m",
            settings=settings_obj(),
            now_fn=now,
            data={"items": items},
        )

    @app.get("/v1/forecast/task-runs/{task_run_id}")
    async def get_task_detail(task_run_id: str):
        try:
            task = await service().get_task_detail(task_run_id, now())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return _envelope(
            object_id=task_run_id,
            object_type="task_run",
            lane=task["lane"],
            settings=settings_obj(),
            now_fn=now,
            data=task,
        )

    @app.get("/v1/miners/{miner_id}/status")
    async def get_miner_status(miner_id: str):
        try:
            status = await service().get_miner_status(miner_id, now())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return _envelope(
            object_id=miner_id,
            object_type="miner_status",
            lane="forecast_15m",
            settings=settings_obj(),
            now_fn=now,
            data=status,
        )

    @app.get("/v1/miners/{miner_id}/submissions")
    async def get_miner_submissions(miner_id: str, limit: int = 20):
        try:
            items = await service().get_miner_submission_history(miner_id, limit=max(1, min(limit, 100)), now=now())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return _envelope(
            object_id=f"{miner_id}:submissions",
            object_type="miner_submission_history",
            lane="forecast_15m",
            settings=settings_obj(),
            now_fn=now,
            data={"items": items, "limit": max(1, min(limit, 100))},
        )

    @app.get("/v1/miners/{miner_id}/reward-holds")
    async def get_miner_reward_holds(miner_id: str, limit: int = 20):
        try:
            items = await service().get_miner_reward_hold_history(miner_id, limit=max(1, min(limit, 100)), now=now())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return _envelope(
            object_id=f"{miner_id}:reward-holds",
            object_type="miner_reward_hold_history",
            lane="forecast_15m",
            settings=settings_obj(),
            now_fn=now,
            data={"items": items, "limit": max(1, min(limit, 100))},
        )

    @app.get("/v1/miners/{miner_id}/reward-windows")
    async def get_miner_reward_windows(miner_id: str, limit: int = 20):
        try:
            items = await service().get_miner_reward_window_history(miner_id, limit=max(1, min(limit, 100)), now=now())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return _envelope(
            object_id=f"{miner_id}:reward-windows",
            object_type="miner_reward_window_history",
            lane="forecast_15m",
            settings=settings_obj(),
            now_fn=now,
            data={"items": items, "limit": max(1, min(limit, 100))},
        )

    @app.get("/v1/miners/{miner_id}/tasks/history")
    async def get_miner_task_history(miner_id: str, limit: int = 20):
        try:
            items = await service().get_miner_task_history(miner_id, limit=max(1, min(limit, 100)), now=now())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return _envelope(
            object_id=f"{miner_id}:tasks-history",
            object_type="miner_task_history",
            lane="forecast_15m",
            settings=settings_obj(),
            now_fn=now,
            data={"items": items, "limit": max(1, min(limit, 100))},
        )

    @app.get("/v1/replays/{entity_type}/{entity_id}/proof")
    async def get_replay_proof(entity_type: str, entity_id: str):
        try:
            proof = await service().get_replay_proof(entity_type, entity_id, now=now())
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return _envelope(
            object_id=f"{entity_type}:{entity_id}:proof",
            object_type="replay_proof",
            lane=proof.get("lane") or "forecast_15m",
            settings=settings_obj(),
            now_fn=now,
            data=proof,
        )

    @app.get("/v1/artifacts/{artifact_id}")
    async def get_artifact(artifact_id: str):
        try:
            artifact = await service().get_artifact(artifact_id, now=now())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return _envelope(
            object_id=artifact_id,
            object_type="artifact",
            lane="forecast_15m",
            settings=settings_obj(),
            now_fn=now,
            data=artifact,
        )

    @app.get("/v1/leaderboard")
    async def get_public_leaderboard(limit: int = 20):
        data = await service().get_public_leaderboard(limit=max(1, min(limit, 100)), now=now())
        return _envelope(
            object_id="leaderboard",
            object_type="leaderboard",
            lane="forecast_15m",
            settings=settings_obj(),
            now_fn=now,
            data=data,
        )

    @app.get("/admin/risk-cases")
    async def get_risk_cases(state: str | None = None):
        items = await app.state.repository.list_risk_cases(state=state)
        return {"items": items}

    @app.get("/admin/risk-cases/open")
    async def get_open_risk_cases():
        items = await app.state.repository.list_risk_cases(state="open")
        return {"items": items}

    @app.post("/admin/risk-decisions/{risk_case_id}/override")
    async def override_risk_case(risk_case_id: str, payload: RiskDecisionOverrideRequest):
        try:
            result = await service().override_risk_case(
                risk_case_id,
                decision=payload.decision,
                reason=payload.reason,
                operator_id=payload.operator_id,
                authority_level=payload.authority_level,
                now=now(),
            )
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return result

    @app.get("/admin/settlement-batches")
    async def get_settlement_batches():
        await service().reconcile(now())
        items = await app.state.repository.list_settlement_batches()
        return {"items": items}

    @app.get("/admin/anchor-jobs")
    async def get_anchor_jobs():
        items = await service().list_anchor_jobs(now=now())
        return {"items": items}

    @app.post("/admin/anchor-jobs/reconcile-chain")
    async def reconcile_anchor_jobs_on_chain():
        items = await service().reconcile_pending_anchor_jobs_on_chain(now=now())
        return {
            "count": len(items),
            "items": items,
        }

    @app.get("/admin/chain/health")
    async def get_chain_health():
        items = await app.state.repository.list_anchor_jobs()
        return _build_chain_health_snapshot(
            anchor_jobs=items,
            metrics=app.state.anchor_reconcile_metrics,
            settings=settings_obj(),
            current_time=now(),
        )

    @app.get("/admin/anchor-jobs/action-queue")
    async def get_anchor_job_action_queue():
        items = _build_anchor_action_queue(
            anchor_jobs=await app.state.repository.list_anchor_jobs(),
            settings=settings_obj(),
            current_time=now(),
        )
        return {
            "count": len(items),
            "items": items,
        }

    @app.get("/admin/chain/preflight")
    async def get_chain_preflight():
        return await inspect_cli_broadcast_readiness(settings=settings_obj())

    @app.get("/admin/anchor-jobs/{anchor_job_id}/chain-tx-plan")
    async def get_chain_tx_plan(anchor_job_id: str):
        try:
            plan = await service().build_chain_tx_plan(anchor_job_id, now=now())
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return plan

    @app.post("/admin/anchor-jobs/{anchor_job_id}/broadcast-fallback")
    async def broadcast_chain_tx_fallback(anchor_job_id: str):
        try:
            receipt = await service().broadcast_chain_tx_fallback(anchor_job_id, now=now())
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return receipt

    @app.post("/admin/anchor-jobs/{anchor_job_id}/broadcast-typed")
    async def broadcast_chain_tx_typed(anchor_job_id: str):
        try:
            receipt = await service().broadcast_chain_tx_typed(anchor_job_id, now=now())
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return receipt

    @app.post("/admin/anchor-jobs/{anchor_job_id}/confirm-chain")
    async def confirm_anchor_job_on_chain(anchor_job_id: str):
        try:
            receipt = await service().confirm_anchor_job_on_chain(anchor_job_id, now=now())
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return receipt

    @app.post("/admin/anchor-jobs/{anchor_job_id}/retry-broadcast-typed")
    async def retry_failed_anchor_job_broadcast_typed(anchor_job_id: str):
        try:
            receipt = await service().retry_failed_anchor_job_broadcast_typed(anchor_job_id, now=now())
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return receipt

    @app.post("/admin/anchor-jobs/{anchor_job_id}/retry-broadcast-fallback")
    async def retry_failed_anchor_job_broadcast_fallback(anchor_job_id: str):
        try:
            receipt = await service().retry_failed_anchor_job_broadcast_fallback(anchor_job_id, now=now())
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return receipt

    @app.post("/admin/reward-windows/{reward_window_id}/rebuild")
    async def rebuild_reward_window(reward_window_id: str):
        try:
            window = await service().rebuild_reward_window(reward_window_id, now=now())
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return window

    @app.post("/admin/settlement-batches/{settlement_batch_id}/retry-anchor")
    async def retry_anchor_settlement_batch(settlement_batch_id: str):
        try:
            batch = await service().retry_anchor_settlement_batch(settlement_batch_id, now=now())
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return batch

    @app.post("/admin/settlement-batches/{settlement_batch_id}/submit-anchor")
    async def submit_anchor_job(settlement_batch_id: str):
        try:
            batch = await service().submit_anchor_job(settlement_batch_id, now=now())
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return batch

    @app.post("/admin/anchor-jobs/{anchor_job_id}/mark-anchored")
    async def mark_anchor_job_anchored(anchor_job_id: str):
        try:
            anchor_job = await service().mark_anchor_job_anchored(anchor_job_id, now=now())
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return anchor_job

    @app.post("/admin/anchor-jobs/{anchor_job_id}/mark-failed")
    async def mark_anchor_job_failed(anchor_job_id: str, request: Request):
        payload = await request.json()
        try:
            anchor_job = await service().mark_anchor_job_failed(
                anchor_job_id,
                failure_reason=str(payload.get("failure_reason") or "operator_marked_failed"),
                now=now(),
            )
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return anchor_job

    @app.post("/admin/arena/results/apply")
    async def apply_arena_results(payload: ApplyArenaResultsRequest):
        try:
            result = await service().apply_arena_results(
                tournament_id=payload.tournament_id,
                rated_or_practice=payload.rated_or_practice,
                human_only=payload.human_only,
                results=[item.model_dump() for item in payload.results],
                completed_at=now(),
            )
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "miner not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return result

    @app.post("/admin/poker-mtt/hands/ingest")
    async def ingest_poker_mtt_hand(payload: PokerMTTHandCompletedEventRequest):
        try:
            return await service().ingest_poker_mtt_hand_event(
                payload.model_dump(exclude_none=True),
                now=now(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/admin/poker-mtt/hidden-eval/finalize")
    async def finalize_poker_mtt_hidden_eval(payload: FinalizePokerMTTHiddenEvalRequest):
        try:
            return await service().finalize_poker_mtt_hidden_eval(
                tournament_id=payload.tournament_id,
                policy_bundle_version=payload.policy_bundle_version,
                seed_assignment_id=payload.seed_assignment_id,
                baseline_sample_id=payload.baseline_sample_id,
                entries=[entry.model_dump(exclude_none=True) for entry in payload.entries],
                now=now(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/admin/poker-mtt/rating-snapshots/build")
    async def build_poker_mtt_rating_snapshot(payload: BuildPokerMTTRatingSnapshotRequest):
        try:
            return await service().build_poker_mtt_rating_snapshot(
                miner_address=payload.miner_address,
                window_start_at=payload.window_start_at,
                window_end_at=payload.window_end_at,
                public_rating=payload.public_rating,
                public_rank=payload.public_rank,
                confidence=payload.confidence,
                policy_bundle_version=payload.policy_bundle_version,
                now=now(),
            )
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "miner not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)

    @app.post("/admin/poker-mtt/results/apply")
    async def apply_poker_mtt_results(payload: ApplyPokerMTTResultsRequest):
        try:
            result = await service().apply_poker_mtt_results(
                tournament_id=payload.tournament_id,
                rated_or_practice=payload.rated_or_practice,
                human_only=payload.human_only,
                field_size=payload.field_size,
                policy_bundle_version=payload.policy_bundle_version,
                results=[item.model_dump() for item in payload.results],
                completed_at=now(),
            )
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "miner not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return result

    @app.post("/admin/poker-mtt/final-rankings/project")
    async def project_poker_mtt_final_rankings(payload: ApplyPokerMTTFinalRankingProjectionRequest):
        try:
            svc = service()
            for row in payload.rows:
                await svc.repo.save_poker_mtt_final_ranking(row.model_dump())
            result = await svc.project_poker_mtt_final_rankings(
                tournament_id=payload.tournament_id,
                rated_or_practice=payload.rated_or_practice,
                human_only=payload.human_only,
                field_size=payload.field_size,
                policy_bundle_version=payload.policy_bundle_version,
                locked_at=now(),
            )
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
        return result

    @app.post("/admin/poker-mtt/reward-windows/build")
    async def build_poker_mtt_reward_window(payload: BuildPokerMTTRewardWindowRequest):
        try:
            reward_window = await service().build_poker_mtt_reward_window(
                lane=payload.lane,
                window_start_at=payload.window_start_at,
                window_end_at=payload.window_end_at,
                reward_pool_amount=payload.reward_pool_amount,
                include_provisional=payload.include_provisional,
                policy_bundle_version=payload.policy_bundle_version,
                reward_window_id=payload.reward_window_id,
                now=now(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return reward_window

    @app.post("/v1/task-runs/{task_run_id}/commit")
    async def commit_task(task_run_id: str, payload: CommitRequest, request: Request):
        if payload.task_run_id != task_run_id:
            raise HTTPException(status_code=400, detail="task_run_id mismatch")
        miner = await app.state.repository.get_miner(payload.miner_id)
        if not miner:
            raise HTTPException(status_code=404, detail="miner not found")
        if not _verify_signature(
            [task_run_id, payload.commit_hash, payload.nonce, payload.miner_id, payload.request_id],
            payload.signature,
            miner["public_key"],
        ):
            raise HTTPException(status_code=403, detail="invalid signature")
        try:
            submission = await service().commit_submission(
                task_run_id=task_run_id,
                miner_address=payload.miner_id,
                economic_unit_id=miner["economic_unit_id"],
                request_id=payload.request_id,
                commit_hash=payload.commit_hash,
                commit_nonce=payload.nonce,
                accepted_at=now(),
                ip_address=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        except ValueError as exc:
            detail = str(exc)
            status = 409 if "already committed" in detail else 400
            if "not found" in detail:
                status = 404
            raise HTTPException(status_code=status, detail=detail)

        return _envelope(
            object_id=submission["id"],
            object_type="submission_commit",
            lane="forecast_15m",
            settings=settings_obj(),
            now_fn=now,
            data={
                "ledger_id": submission["id"],
                "accepted_at": submission["accepted_commit_at"],
                "server_cutoff": (await app.state.repository.get_task(task_run_id))["commit_deadline"],
                "validation_status": "accepted",
            },
        )

    @app.post("/v1/task-runs/{task_run_id}/reveal")
    async def reveal_task(task_run_id: str, payload: RevealRequest, request: Request):
        if payload.task_run_id != task_run_id:
            raise HTTPException(status_code=400, detail="task_run_id mismatch")
        miner = await app.state.repository.get_miner(payload.miner_id)
        if not miner:
            raise HTTPException(status_code=404, detail="miner not found")
        if not _verify_signature(
            [task_run_id, str(payload.p_yes_bps), payload.nonce, payload.miner_id, payload.request_id],
            payload.signature,
            miner["public_key"],
        ):
            raise HTTPException(status_code=403, detail="invalid signature")
        try:
            submission = await service().reveal_submission(
                task_run_id=task_run_id,
                miner_address=payload.miner_id,
                economic_unit_id=miner["economic_unit_id"],
                request_id=payload.request_id,
                p_yes_bps=payload.p_yes_bps,
                reveal_nonce=payload.nonce,
                accepted_at=now(),
                ip_address=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        except ValueError as exc:
            detail = str(exc)
            status = 409 if "already revealed" in detail else 400
            if "not found" in detail:
                status = 404
            raise HTTPException(status_code=status, detail=detail)

        task = await app.state.repository.get_task(task_run_id)
        return _envelope(
            object_id=submission["id"],
            object_type="submission_reveal",
            lane="forecast_15m",
            settings=settings_obj(),
            now_fn=now,
            data={
                "ledger_id": submission["id"],
                "accepted_at": submission["accepted_reveal_at"],
                "server_cutoff": task["reveal_deadline"],
                "pack_hash": task["pack_hash"],
                "validation_status": "accepted",
                "reward_eligibility": submission["eligibility_status"],
            },
        )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="ClawChain Forecast Mining Service")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=1317)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
