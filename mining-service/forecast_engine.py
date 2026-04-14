from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from chain_adapter import build_anchor_tx_plan as build_chain_anchor_tx_plan
from repository import MiningRepository


FAST_ASSETS = ("BTCUSDT", "ETHUSDT")
DAILY_ASSETS = ("BTC", "ETH")
POLICY_BUNDLE_VERSION = "pb_2026_04_09_a"
ANCHOR_PAYLOAD_SCHEMA_VERSION = "clawchain.anchor_payload.v1"


@dataclass(slots=True)
class ForecastSettings:
    fast_task_seconds: int = 900
    commit_window_seconds: int = 3
    reveal_window_seconds: int = 13
    daily_cutoff_hour_utc: int = 0
    poker_mtt_daily_reward_pool_amount: int = 0
    poker_mtt_weekly_reward_pool_amount: int = 0
    poker_mtt_finalization_watermark_seconds: int = 21600
    poker_mtt_daily_policy_bundle_version: str = "poker_mtt_daily_policy_v1"
    poker_mtt_weekly_policy_bundle_version: str = "poker_mtt_weekly_policy_v1"
    baseline_pm_weight: float = 0.85
    baseline_bin_weight: float = 0.15
    min_p_yes_bps: int = 1500
    max_p_yes_bps: int = 8500
    admission_release_bps: int = 2000
    admission_mature_fast_reveals: int = 500
    admission_mature_age_hours: int = 168
    free_skip_ratio: float = 0.20
    max_binance_snapshot_freshness_seconds: int = 30
    max_polymarket_snapshot_freshness_seconds: int = 30
    min_miner_version: str = "0.4.0"
    server_version: str = "1.0.0-alpha"
    protocol: str = "clawchain-forecast-v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def as_utc_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return parse_time(value)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def clamp_bps(value: int, settings: ForecastSettings) -> int:
    return max(settings.min_p_yes_bps, min(settings.max_p_yes_bps, value))


def build_signature_hash(parts: Iterable[str]) -> bytes:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).digest()


def compute_commit_hash(task_run_id: str, miner_address: str, p_yes_bps: int, reveal_nonce: str) -> str:
    payload = f"{task_run_id}|{miner_address}|{p_yes_bps}|{reveal_nonce}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def derive_economic_unit_id(*, address: str, public_key: str, ip_address: str | None) -> str:
    if ip_address:
        basis = f"ip:{ip_address.strip().lower()}"
    else:
        basis = f"pk:{public_key.removeprefix('0x').lower()}"
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]
    return f"eu:{digest}"


def hash_user_agent(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    normalized = user_agent.strip().lower()
    if not normalized:
        return None
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
    return f"ua:{digest}"


def compute_economic_unit_components(miners: list[dict]) -> dict[str, str]:
    if not miners:
        return {}

    index_by_address = {miner["address"]: idx for idx, miner in enumerate(miners)}
    parent = list(range(len(miners)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    evidence_map: dict[str, list[int]] = {}
    for idx, miner in enumerate(miners):
        evidences = []
        if miner.get("ip_address"):
            evidences.append(f"ip:{str(miner['ip_address']).strip().lower()}")
        if miner.get("user_agent_hash"):
            evidences.append(str(miner["user_agent_hash"]))
        for evidence in evidences:
            evidence_map.setdefault(evidence, []).append(idx)

    for members in evidence_map.values():
        first = members[0]
        for other in members[1:]:
            union(first, other)

    components: dict[int, list[str]] = {}
    for miner in miners:
        root = find(index_by_address[miner["address"]])
        components.setdefault(root, []).append(miner["address"])

    result = {}
    for root, addresses in components.items():
        seed = "|".join(sorted(addresses))
        economic_unit_id = "eu:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
        for address in addresses:
            result[address] = economic_unit_id
    return result


def _seed_int(key: str, start: int, end: int) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    span = end - start + 1
    return start + (int.from_bytes(digest[:8], "big") % span)


def _bucket_start(now: datetime, seconds: int) -> datetime:
    ts = int(now.timestamp())
    bucket = ts - (ts % seconds)
    return datetime.fromtimestamp(bucket, tz=timezone.utc)


def _hour_bucket_start(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _day_bucket_start(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _week_bucket_start(value: datetime) -> datetime:
    day_start = _day_bucket_start(value)
    return day_start - timedelta(days=day_start.weekday())


def _baseline_probs(task_id: str, settings: ForecastSettings) -> tuple[int, int, int]:
    q_pm_bps = _seed_int(f"{task_id}:pm", 4200, 5800)
    q_bin_bps = _seed_int(f"{task_id}:bin", 4300, 5700)
    baseline = round(q_pm_bps * settings.baseline_pm_weight + q_bin_bps * settings.baseline_bin_weight)
    return q_pm_bps, q_bin_bps, clamp_bps(int(baseline), settings)


def canonical_json_hash(payload: dict) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def snapshot_metadata(
    *,
    snapshot_source: str,
    frozen_at: datetime,
    binance_freshness_seconds: int | None,
    polymarket_freshness_seconds: int | None,
) -> dict:
    return {
        "snapshot_source": snapshot_source,
        "snapshot_frozen_at": isoformat_z(frozen_at),
        "snapshot_freshness_seconds": {
            "binance": binance_freshness_seconds,
            "polymarket": polymarket_freshness_seconds,
        },
    }


def build_fast_task(now: datetime, settings: ForecastSettings, asset: str = "BTCUSDT") -> dict:
    publish_at = _bucket_start(now, settings.fast_task_seconds)
    resolve_at = publish_at + timedelta(seconds=settings.fast_task_seconds)
    commit_deadline = publish_at + timedelta(seconds=settings.commit_window_seconds)
    reveal_deadline = publish_at + timedelta(seconds=settings.reveal_window_seconds)
    task_id = f"tr_fast_{publish_at.strftime('%Y%m%d%H%M')}_{asset.lower()}"
    q_pm_bps, q_bin_bps, baseline_q_bps = _baseline_probs(task_id, settings)

    pack = {
        "asset": asset,
        "lane": "forecast_15m",
        **snapshot_metadata(
            snapshot_source="synthetic",
            frozen_at=now,
            binance_freshness_seconds=None,
            polymarket_freshness_seconds=None,
        ),
        "polymarket_snapshot": {
            "q_yes_bps": q_pm_bps,
            "yes_volume": _seed_int(f"{task_id}:pm:yes_volume", 50000, 300000),
            "no_volume": _seed_int(f"{task_id}:pm:no_volume", 50000, 300000),
        },
        "binance_snapshot": {
            "q_yes_bps": q_bin_bps,
            "imbalance_bps": _seed_int(f"{task_id}:bin:imbalance", -1200, 1200),
            "micro_move_bps": _seed_int(f"{task_id}:bin:micro", -250, 250),
        },
        "market_context": f"{asset} 15m synthetic market pack with public baseline and noisy context.",
        "noisy_fragments": [
            '{"symbl":"%s","imbalance_bsp":%s}' % (asset, _seed_int(f"{task_id}:n1", -999, 999)),
            '{"trader_vlume":%s,"sentmnt":"mixed"}' % _seed_int(f"{task_id}:n2", 1000, 100000),
        ],
    }
    pack_hash = canonical_json_hash(pack)

    return {
        "task_run_id": task_id,
        "lane": "forecast_15m",
        "asset": asset,
        "publish_at": isoformat_z(publish_at),
        "commit_deadline": isoformat_z(commit_deadline),
        "reveal_deadline": isoformat_z(reveal_deadline),
        "resolve_at": isoformat_z(resolve_at),
        "baseline_q_bps": baseline_q_bps,
        "baseline_method": "q_pm_85_q_bin_15",
        "snapshot_health": "healthy",
        "task_state": "reward_eligible",
        "degraded_reason": None,
        "void_reason": None,
        "resolution_source": None,
        "pack_hash": pack_hash,
        "pack_json": pack,
        "state": "published",
        "created_at": isoformat_z(now),
        "updated_at": isoformat_z(now),
    }


def build_daily_anchor_task(now: datetime, asset: str, settings: ForecastSettings | None = None) -> dict:
    config = settings or ForecastSettings()
    publish_at = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
    resolve_at = publish_at + timedelta(days=1)
    task_id = f"tr_daily_{publish_at.strftime('%Y%m%d')}_{asset.lower()}"
    q_pm_bps, q_bin_bps, _baseline_q_bps = _baseline_probs(task_id, config)
    pack = {
        "asset": asset,
        "anchor_only": True,
        **snapshot_metadata(
            snapshot_source="synthetic",
            frozen_at=now,
            binance_freshness_seconds=None,
            polymarket_freshness_seconds=None,
        ),
        "market_context": f"{asset} daily anchor lane for reliability calibration.",
        "polymarket_snapshot": {
            "q_yes_bps": q_pm_bps,
            "yes_volume": _seed_int(f"{task_id}:pm:yes_volume", 150000, 800000),
            "no_volume": _seed_int(f"{task_id}:pm:no_volume", 150000, 800000),
        },
        "binance_snapshot": {
            "q_yes_bps": q_bin_bps,
            "imbalance_bps": _seed_int(f"{task_id}:bin:imbalance", -1600, 1600),
            "micro_move_bps": _seed_int(f"{task_id}:bin:micro", -600, 600),
        },
        "noisy_fragments": [
            '{"symbl":"%s","daily_imbalance_bsp":%s}' % (asset, _seed_int(f"{task_id}:n1", -1800, 1800)),
            '{"tradr_vlume":%s,"time_horizon":"1d"}' % _seed_int(f"{task_id}:n2", 10000, 500000),
        ],
    }
    return {
        "task_run_id": task_id,
        "lane": "daily_anchor",
        "asset": asset,
        "publish_at": isoformat_z(publish_at),
        "commit_deadline": isoformat_z(resolve_at),
        "reveal_deadline": isoformat_z(resolve_at),
        "resolve_at": isoformat_z(resolve_at),
        "baseline_q_bps": 5000,
        "baseline_method": "anchor_only",
        "snapshot_health": "healthy",
        "task_state": "calibration_only",
        "degraded_reason": None,
        "void_reason": None,
        "resolution_source": None,
        "pack_hash": canonical_json_hash(pack),
        "pack_json": pack,
        "state": "published",
        "created_at": isoformat_z(now),
        "updated_at": isoformat_z(now),
    }


def ensure_active_task_runs_snapshot(now: datetime, settings: ForecastSettings) -> list[dict]:
    items = [build_fast_task(now, settings, asset=asset) for asset in FAST_ASSETS]
    items.extend(build_daily_anchor_task(now, asset=asset, settings=settings) for asset in DAILY_ASSETS)
    return items


def ensure_active_task_runs(repo, now: datetime, settings: ForecastSettings) -> list[dict]:
    return ensure_active_task_runs_snapshot(now, settings)


def resolve_fast_task(task: dict) -> dict:
    task_id = task["task_run_id"]
    commit_close_ref_price = float(task.get("commit_close_ref_price") or 0.0)
    if commit_close_ref_price <= 0:
        commit_close_ref_price = float(_seed_int(f"{task_id}:price:start", 20000_00, 80000_00)) / 100
    drift_bps = _seed_int(f"{task_id}:price:drift", -180, 180)
    end_ref_price = round(commit_close_ref_price * (1 + drift_bps / 10_000), 2)
    outcome = 1 if end_ref_price > commit_close_ref_price else 0
    return {
        "commit_close_ref_price": commit_close_ref_price,
        "end_ref_price": end_ref_price,
        "outcome": outcome,
    }


def resolve_daily_task(task: dict) -> dict:
    task_id = task["task_run_id"]
    start_ref_price = float(_seed_int(f"{task_id}:price:start", 20000_00, 80000_00)) / 100
    drift_bps = _seed_int(f"{task_id}:price:drift:daily", -600, 600)
    end_ref_price = round(start_ref_price * (1 + drift_bps / 10_000), 2)
    outcome = 1 if end_ref_price > start_ref_price else 0
    return {
        "start_ref_price": start_ref_price,
        "end_ref_price": end_ref_price,
        "outcome": outcome,
        "resolution_status": "resolved",
    }


def score_probability(p_yes_bps: int, baseline_q_bps: int, outcome: int) -> float:
    p = p_yes_bps / 10_000
    q = baseline_q_bps / 10_000
    y = float(outcome)
    improvement = (q - y) ** 2 - (p - y) ** 2
    direction_bonus = 0.015 if ((p_yes_bps >= 5000) == bool(outcome)) else 0.0
    anti_copy_cap = 0.25 if abs(p_yes_bps - baseline_q_bps) < 300 else 1.0
    return max(0.0, (improvement + direction_bonus) * anti_copy_cap)


def _reward_from_score(score: float) -> int:
    return max(0, int(round(score * 1_000_000)))


def _allocate_integer_pool_by_weights(weighted_items: list[tuple[str, float]], total_amount: int) -> dict[str, int]:
    allocations = {item_id: 0 for item_id, _ in weighted_items}
    if total_amount <= 0 or not weighted_items:
        return allocations

    positive_items = [(item_id, max(0.0, float(weight))) for item_id, weight in weighted_items]
    total_weight = sum(weight for _, weight in positive_items)
    if total_weight <= 0:
        positive_items = [(item_id, 1.0) for item_id, _ in weighted_items]
        total_weight = float(len(positive_items))

    assigned = 0
    remainders: list[tuple[float, str]] = []
    for item_id, weight in positive_items:
        exact_share = (weight / total_weight) * total_amount
        base_share = math.floor(exact_share)
        allocations[item_id] = base_share
        assigned += base_share
        remainders.append((exact_share - base_share, item_id))

    for _, item_id in sorted(remainders, key=lambda item: (-item[0], item[1]))[: total_amount - assigned]:
        allocations[item_id] += 1
    return allocations


def _hash_payload(payload: dict) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _build_anchor_job_id(settlement_batch_id: str, now: datetime) -> str:
    return f"aj_{settlement_batch_id}_{now.strftime('%Y%m%d%H%M%S')}"


def _hash_sequence(items: list[dict] | list[str]) -> str:
    return _hash_payload({"items": items})


def _reward_window_payload(reward_window: dict) -> dict:
    return {
        "reward_window_id": reward_window["id"],
        "lane": reward_window["lane"],
        "policy_bundle_version": reward_window.get("policy_bundle_version") or POLICY_BUNDLE_VERSION,
        "task_run_ids": sorted(list(reward_window.get("task_run_ids", []))),
        "miner_addresses": sorted(list(reward_window.get("miner_addresses", []))),
        "task_count": int(reward_window.get("task_count", 0) or 0),
        "submission_count": int(reward_window.get("submission_count", 0) or 0),
        "miner_count": int(reward_window.get("miner_count", 0) or 0),
        "total_reward_amount": int(reward_window.get("total_reward_amount", 0) or 0),
        "settlement_batch_id": reward_window.get("settlement_batch_id"),
    }


def _materialize_reward_window(reward_window: dict) -> tuple[dict, dict]:
    payload = _reward_window_payload(reward_window)
    materialized = {
        **reward_window,
        "policy_bundle_version": payload["policy_bundle_version"],
        "task_run_ids": payload["task_run_ids"],
        "miner_addresses": payload["miner_addresses"],
        "task_count": payload["task_count"],
        "submission_count": payload["submission_count"],
        "miner_count": payload["miner_count"],
        "total_reward_amount": payload["total_reward_amount"],
        "canonical_root": _hash_payload(payload),
    }
    return materialized, payload


def _poker_mtt_reward_window_id(lane: str, window_start: datetime, window_end: datetime) -> str:
    return f"rw_{lane}_{window_start.strftime('%Y%m%d%H%M%S')}_{window_end.strftime('%Y%m%d%H%M%S')}"


def _default_poker_mtt_policy_bundle_version(settings: ForecastSettings, lane: str) -> str:
    if lane == "poker_mtt_daily":
        return getattr(settings, "poker_mtt_daily_policy_bundle_version", "poker_mtt_daily_policy_v1")
    if lane == "poker_mtt_weekly":
        return getattr(settings, "poker_mtt_weekly_policy_bundle_version", "poker_mtt_weekly_policy_v1")
    return POLICY_BUNDLE_VERSION


def _parse_version(version: str) -> tuple[int, ...]:
    digits = []
    for part in version.replace("-", ".").split("."):
        if part.isdigit():
            digits.append(int(part))
        elif part and part[0].isdigit():
            numeric = "".join(ch for ch in part if ch.isdigit())
            if numeric:
                digits.append(int(numeric))
    return tuple(digits or [0])


class ForecastMiningService:
    def __init__(
        self,
        repo: MiningRepository,
        settings: ForecastSettings,
        task_provider=None,
        chain_broadcaster=None,
        chain_typed_broadcaster=None,
        chain_tx_confirmer=None,
    ):
        self.repo = repo
        self.settings = settings
        self.task_provider = task_provider
        self.chain_broadcaster = chain_broadcaster
        self.chain_typed_broadcaster = chain_typed_broadcaster
        self.chain_tx_confirmer = chain_tx_confirmer

    async def reconcile(self, now: datetime | None = None) -> None:
        current = now or utc_now()
        for asset in FAST_ASSETS:
            task_id = build_fast_task(current, self.settings, asset=asset)["task_run_id"]
            existing = await self.repo.get_task(task_id)
            if not existing:
                if self.task_provider:
                    task = await self.task_provider.build_fast_task(current, self.settings, asset)
                else:
                    task = build_fast_task(current, self.settings, asset=asset)
                await self.repo.upsert_task(task)
        for asset in DAILY_ASSETS:
            task = build_daily_anchor_task(current, asset=asset, settings=self.settings)
            existing = await self.repo.get_task(task["task_run_id"])
            if not existing:
                await self.repo.upsert_task(task)
        await self._settle_due_tasks(current)
        await self._settle_due_daily_tasks(current)
        await self._release_matured_holds(current)
        await self._build_reward_windows(current)
        await self._build_poker_mtt_reward_windows(current)
        await self._build_settlement_batches(current)
        await self._refresh_public_ranks()

    async def register_miner(
        self,
        *,
        address: str,
        name: str,
        public_key: str,
        miner_version: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        economic_unit_id: str | None = None,
    ) -> dict:
        if not address.startswith("claw1"):
            raise ValueError("invalid address format")
        if _parse_version(miner_version) < _parse_version(self.settings.min_miner_version):
            raise ValueError("miner version below minimum")
        now = utc_now()
        existing_miners = await self.repo.list_miners()
        user_agent_hash = hash_user_agent(user_agent)
        miner = {
            "address": address,
            "name": name or "miner",
            "registration_index": len(existing_miners) + 1,
            "status": "active",
            "public_key": public_key,
            "economic_unit_id": economic_unit_id or f"eu:{address}",
            "ip_address": ip_address,
            "user_agent_hash": user_agent_hash,
            "total_rewards": 0,
            "held_rewards": 0,
            "forecast_commits": 0,
            "forecast_reveals": 0,
            "fast_task_opportunities": 0,
            "fast_task_misses": 0,
            "fast_window_start_at": now,
            "settled_tasks": 0,
            "correct_direction_count": 0,
            "edge_score_total": 0.0,
            "admission_state": "probation",
            "model_reliability": 1.0,
            "ops_reliability": 1.0,
            "arena_multiplier": 1.0,
            "poker_mtt_multiplier": 1.0,
            "public_rank": None,
            "public_elo": 1200,
            "created_at": now,
            "updated_at": now,
        }
        component_map = compute_economic_unit_components(existing_miners + [miner])
        miner["economic_unit_id"] = component_map.get(miner["address"], miner["economic_unit_id"])
        saved = await self.repo.register_miner(miner)
        all_miners = existing_miners + [{**saved}]
        for existing in existing_miners:
            new_component_id = component_map.get(existing["address"])
            if new_component_id and new_component_id != existing.get("economic_unit_id"):
                await self.repo.update_miner(
                    existing["address"],
                    {
                        "economic_unit_id": new_component_id,
                        "updated_at": now,
                    },
                )
                all_miners = [
                    {**miner_item, "economic_unit_id": new_component_id}
                    if miner_item["address"] == existing["address"]
                    else miner_item
                    for miner_item in all_miners
                ]
        await self._sync_cluster_risk_cases(all_miners, now)
        return saved

    async def get_active_tasks(self, now: datetime | None = None) -> list[dict]:
        await self.reconcile(now)
        current = now or utc_now()
        active = []
        for task in await self.repo.list_tasks():
            if task["lane"] == "forecast_15m":
                publish_at = parse_time(task["publish_at"])
                resolve_at = parse_time(task["resolve_at"])
                if publish_at <= current < resolve_at:
                    active.append(self._task_card(task))
            elif task["lane"] == "daily_anchor":
                publish_at = parse_time(task["publish_at"])
                resolve_at = parse_time(task["resolve_at"])
                if task.get("state") == "resolved":
                    continue
                if publish_at <= current < resolve_at:
                    active.append(self._task_card(task))
        active.sort(key=lambda item: (item["lane"], item["asset"]))
        return active

    async def get_task_detail(self, task_run_id: str, now: datetime | None = None) -> dict:
        await self.reconcile(now)
        task = await self.repo.get_task(task_run_id)
        if not task:
            raise ValueError("task not found")
        return task

    async def commit_submission(
        self,
        *,
        task_run_id: str,
        miner_address: str,
        economic_unit_id: str,
        request_id: str,
        commit_hash: str,
        commit_nonce: str,
        accepted_at: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        task = await self.repo.get_task(task_run_id)
        if not task:
            raise ValueError("task not found")
        if parse_time(task["commit_deadline"]) < accepted_at:
            raise ValueError("commit window closed")
        miner = await self.repo.get_miner(miner_address)
        if not miner:
            raise ValueError("miner not registered")
        miner = await self._refresh_miner_cluster(
            miner_address=miner_address,
            ip_address=ip_address,
            user_agent=user_agent,
            now=accepted_at,
        )
        existing = await self.repo.get_submission(task_run_id, miner_address)
        if existing and existing.get("commit_hash"):
            raise ValueError("already committed")

        saved = await self.repo.save_submission(
            {
                "id": f"sub:{task_run_id}:{miner_address}",
                "task_run_id": task_run_id,
                "miner_address": miner_address,
                "economic_unit_id": miner["economic_unit_id"],
                "commit_request_id": request_id,
                "reveal_request_id": existing.get("reveal_request_id") if existing else None,
                "commit_hash": commit_hash,
                "commit_nonce": commit_nonce,
                "p_yes_bps": existing.get("p_yes_bps") if existing else None,
                "eligibility_status": existing.get("eligibility_status", "eligible") if existing else "eligible",
                "state": existing.get("state", "committed") if existing else "committed",
                "score": existing.get("score", 0.0) if existing else 0.0,
                "reward_amount": existing.get("reward_amount", 0) if existing else 0,
                "reward_window_id": existing.get("reward_window_id") if existing else None,
                "accepted_commit_at": isoformat_z(accepted_at),
                "accepted_reveal_at": existing.get("accepted_reveal_at") if existing else None,
                "created_at": existing.get("created_at", isoformat_z(accepted_at)) if existing else isoformat_z(accepted_at),
                "updated_at": isoformat_z(accepted_at),
            }
        )
        await self.repo.update_miner(
            miner_address,
            {
                "forecast_commits": miner["forecast_commits"] + 1,
                "updated_at": accepted_at,
            },
        )
        return saved

    async def reveal_submission(
        self,
        *,
        task_run_id: str,
        miner_address: str,
        economic_unit_id: str,
        request_id: str,
        p_yes_bps: int,
        reveal_nonce: str,
        accepted_at: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        task = await self.repo.get_task(task_run_id)
        if not task:
            raise ValueError("task not found")
        if parse_time(task["reveal_deadline"]) < accepted_at:
            raise ValueError("reveal window closed")
        p_yes_bps = clamp_bps(p_yes_bps, self.settings)

        miner = await self.repo.get_miner(miner_address)
        if not miner:
            raise ValueError("miner not registered")
        miner = await self._refresh_miner_cluster(
            miner_address=miner_address,
            ip_address=ip_address,
            user_agent=user_agent,
            now=accepted_at,
        )
        submission = await self.repo.get_submission(task_run_id, miner_address)
        if not submission or not submission.get("commit_hash"):
            raise ValueError("commit required before reveal")
        if submission.get("p_yes_bps") is not None:
            raise ValueError("already revealed")

        expected_commit = compute_commit_hash(task_run_id, miner_address, p_yes_bps, reveal_nonce)
        if expected_commit != submission["commit_hash"]:
            raise ValueError("reveal does not match commit hash")

        eligibility = "eligible"
        duplicate_miners = [miner_address]
        for other in await self.repo.list_submissions_for_task(task_run_id):
            if other["miner_address"] == miner_address:
                continue
            if other["economic_unit_id"] == economic_unit_id and other.get("p_yes_bps") is not None:
                eligibility = "audit_only"
                duplicate_miners.append(other["miner_address"])
                break

        saved = await self.repo.save_submission(
            {
                **submission,
                "economic_unit_id": miner["economic_unit_id"],
                "reveal_request_id": request_id,
                "p_yes_bps": p_yes_bps,
                "eligibility_status": eligibility,
                "state": "revealed",
                "accepted_reveal_at": isoformat_z(accepted_at),
                "updated_at": isoformat_z(accepted_at),
            }
        )
        if eligibility == "audit_only":
            await self._open_duplicate_reveal_case(
                task_run_id=task_run_id,
                submission_id=saved["id"],
                economic_unit_id=economic_unit_id,
                miner_addresses=sorted(set(duplicate_miners)),
                now=accepted_at,
                miner_address=miner_address,
            )

        reveal_count = miner["forecast_reveals"] + 1
        ops_reliability = self._compute_ops_reliability({**miner, "forecast_reveals": reveal_count})
        await self.repo.update_miner(
            miner_address,
            {
                "forecast_reveals": reveal_count,
                "ops_reliability": ops_reliability,
                "updated_at": accepted_at,
            },
        )
        return saved

    async def get_miner_status(self, miner_address: str, now: datetime | None = None) -> dict:
        await self.reconcile(now)
        miner = await self.repo.get_miner(miner_address)
        if not miner:
            raise ValueError("miner not found")
        current = now or utc_now()
        maturity_state = "open"
        reward_eligibility_status = "eligible"
        open_risk_case_count = await self._open_risk_case_count(miner)
        tasks = await self.repo.list_tasks()
        for task in tasks:
            if task["lane"] != "forecast_15m":
                continue
            submission = await self.repo.get_submission(task["task_run_id"], miner_address)
            if not submission:
                continue
            if submission.get("eligibility_status") and submission.get("eligibility_status") != "eligible":
                reward_eligibility_status = submission["eligibility_status"]
            if submission.get("state") == "pending_resolution":
                maturity_state = "pending_resolution"
                reward_eligibility_status = submission.get("eligibility_status", "eligible")
                break
        score_explanation = await self._build_score_explanation(miner_address, tasks)
        reward_timeline = await self._build_reward_timeline(miner, tasks, current, score_explanation)
        latest_reward_window, latest_settlement_batch, latest_anchor_job = await self._latest_settlement_snapshot(
            miner_address
        )
        return {
            "miner_id": miner["address"],
            "public_rank": miner.get("public_rank"),
            "public_elo": miner["public_elo"],
            "model_reliability": round(miner["model_reliability"], 4),
            "ops_reliability": round(miner["ops_reliability"], 4),
            "arena_multiplier": round(miner["arena_multiplier"], 4),
            "poker_mtt_multiplier": round(miner.get("poker_mtt_multiplier", 1.0), 4),
            "anti_abuse_discount": round(self._admission_release_ratio(miner, current), 4),
            "admission_state": self._admission_state(miner, current),
            "maturity_state": maturity_state,
            "reward_eligibility_status": reward_eligibility_status,
            "risk_review_state": "review_required" if open_risk_case_count > 0 else "clear",
            "open_risk_case_count": open_risk_case_count,
            "score_explanation": score_explanation,
            "reward_timeline": reward_timeline,
            "latest_reward_window": latest_reward_window,
            "latest_settlement_batch": latest_settlement_batch,
            "latest_anchor_job": latest_anchor_job,
            "total_rewards": miner["total_rewards"],
            "held_rewards": miner.get("held_rewards", 0),
            "forecast_commits": miner["forecast_commits"],
            "forecast_reveals": miner["forecast_reveals"],
            "fast_task_opportunities": miner.get("fast_task_opportunities", 0),
            "fast_task_misses": miner.get("fast_task_misses", 0),
            "settled_tasks": miner["settled_tasks"],
            "economic_unit_id": miner["economic_unit_id"],
        }

    async def override_risk_case(
        self,
        risk_case_id: str,
        *,
        decision: str,
        reason: str,
        operator_id: str,
        authority_level: str,
        now: datetime | None = None,
    ) -> dict:
        decision_to_state = {
            "clear": "cleared",
            "suppress": "suppressed",
            "escalate": "escalated",
        }
        if decision not in decision_to_state:
            raise ValueError("invalid risk decision")
        current = now or utc_now()
        risk_case = await self.repo.get_risk_case(risk_case_id)
        if not risk_case:
            raise ValueError("risk case not found")
        trace_id = f"trace:risk_override:{risk_case_id}:{current.strftime('%Y%m%d%H%M%S')}"
        override_log_id = f"ovr:{risk_case_id}:{current.strftime('%Y%m%d%H%M%S')}"
        saved_case = await self.repo.save_risk_case(
            {
                **risk_case,
                "state": decision_to_state[decision],
                "decision": decision,
                "decision_reason": reason,
                "reviewed_by": operator_id,
                "authority_level": authority_level,
                "trace_id": trace_id,
                "override_log_id": override_log_id,
                "reviewed_at": isoformat_z(current),
                "updated_at": isoformat_z(current),
            }
        )
        return {
            "operator_id": operator_id,
            "authority_level": authority_level,
            "trace_id": trace_id,
            "override_log_id": override_log_id,
            "risk_case": saved_case,
        }

    async def get_stats(self, now: datetime | None = None) -> dict:
        await self.reconcile(now)
        current = now or utc_now()
        tasks = await self.repo.list_tasks()
        active_fast = 0
        settled_fast = 0
        for task in tasks:
            if task["lane"] != "forecast_15m":
                continue
            publish_at = parse_time(task["publish_at"])
            resolve_at = parse_time(task["resolve_at"])
            if task.get("state") in {"settled", "resolved"}:
                settled_fast += 1
            elif publish_at <= current < resolve_at:
                active_fast += 1

        miners = await self.repo.list_miners()
        reward_windows = await self.repo.list_reward_windows()
        settlement_batches = await self.repo.list_settlement_batches()
        latest_reward_window = reward_windows[0] if reward_windows else None
        latest_settlement_batch = settlement_batches[0] if settlement_batches else None
        latest_anchor_job = None
        if latest_settlement_batch and latest_settlement_batch.get("anchor_job_id"):
            latest_anchor_job = await self.repo.get_anchor_job(latest_settlement_batch["anchor_job_id"])
        return {
            "protocol": self.settings.protocol,
            "server_version": self.settings.server_version,
            "active_miners": sum(1 for miner in miners if miner["status"] == "active"),
            "active_fast_tasks": active_fast,
            "settled_fast_tasks": settled_fast,
            "total_rewards_paid": sum(miner["total_rewards"] for miner in miners),
            "latest_reward_window_id": latest_reward_window["id"] if latest_reward_window else None,
            "latest_settlement_batch_id": latest_settlement_batch["id"] if latest_settlement_batch else None,
            "latest_settlement_state": latest_settlement_batch.get("state") if latest_settlement_batch else None,
            "latest_anchor_job_id": latest_anchor_job["id"] if latest_anchor_job else None,
            "latest_anchor_job_state": latest_anchor_job.get("state") if latest_anchor_job else None,
        }

    async def get_public_leaderboard(self, *, limit: int = 20, now: datetime | None = None) -> dict:
        miners = await self.repo.list_miners()
        ranked = sorted(
            miners,
            key=lambda miner: (
                miner.get("public_rank") is None,
                miner.get("public_rank") or 10**9,
                -(miner.get("public_elo") or 0),
                -(miner.get("total_rewards") or 0),
                miner.get("address") or "",
            ),
        )
        items = []
        for miner in ranked[:limit]:
            items.append(
                {
                    "address": miner["address"],
                    "name": miner.get("name"),
                    "public_rank": miner.get("public_rank"),
                    "public_elo": miner.get("public_elo"),
                    "total_rewards": miner.get("total_rewards", 0),
                    "settled_tasks": miner.get("settled_tasks", 0),
                    "model_reliability": round(float(miner.get("model_reliability", 1.0)), 6),
                    "ops_reliability": round(float(miner.get("ops_reliability", 1.0)), 6),
                    "arena_multiplier": round(float(miner.get("arena_multiplier", 1.0)), 6),
                    "admission_state": self._admission_state(miner, now or utc_now()),
                    "risk_review_state": miner.get("risk_review_state", "clear"),
                    "open_risk_case_count": miner.get("open_risk_case_count", 0),
                }
            )

        return {
            "items": items,
            "limit": limit,
            "total_miners": len(miners),
        }

    async def get_miner_submission_history(
        self,
        miner_address: str,
        *,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[dict]:
        await self.reconcile(now)
        miner = await self.repo.get_miner(miner_address)
        if not miner:
            raise ValueError("miner not found")
        return await self.repo.list_submissions_for_miner(miner_address, limit=limit)

    async def get_miner_reward_hold_history(
        self,
        miner_address: str,
        *,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[dict]:
        await self.reconcile(now)
        miner = await self.repo.get_miner(miner_address)
        if not miner:
            raise ValueError("miner not found")
        entries = await self.repo.list_hold_entries_for_miner(miner_address)
        entries.sort(
            key=lambda item: (
                item.get("updated_at") or "",
                item.get("created_at") or "",
                item.get("id") or "",
            ),
            reverse=True,
        )
        return entries[:limit]

    async def get_miner_reward_window_history(
        self,
        miner_address: str,
        *,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[dict]:
        await self.reconcile(now)
        miner = await self.repo.get_miner(miner_address)
        if not miner:
            raise ValueError("miner not found")
        submissions = await self.repo.list_submissions_for_miner(miner_address)
        reward_window_ids = {
            submission.get("reward_window_id")
            for submission in submissions
            if submission.get("reward_window_id")
        }
        reward_windows = await self.repo.list_reward_windows()
        items = [window for window in reward_windows if window["id"] in reward_window_ids]
        return items[:limit]

    async def get_miner_task_history(
        self,
        miner_address: str,
        *,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[dict]:
        await self.reconcile(now)
        miner = await self.repo.get_miner(miner_address)
        if not miner:
            raise ValueError("miner not found")

        submissions = await self.repo.list_submissions_for_miner(miner_address)
        reward_windows = {
            window["id"]: window
            for window in await self.repo.list_reward_windows()
        }
        items = []
        for submission in submissions:
            task = await self.repo.get_task(submission["task_run_id"])
            if not task:
                continue
            reward_window_id = submission.get("reward_window_id") or task.get("reward_window_id")
            reward_window = reward_windows.get(reward_window_id) if reward_window_id else None
            items.append(
                {
                    "task_run_id": task["task_run_id"],
                    "lane": task["lane"],
                    "asset": task["asset"],
                    "publish_at": task["publish_at"],
                    "resolve_at": task["resolve_at"],
                    "task_state": task.get("state"),
                    "submission_state": submission.get("state"),
                    "pending_resolution": submission.get("state") == "pending_resolution",
                    "reward_window_id": reward_window_id,
                    "settlement_batch_id": reward_window.get("settlement_batch_id") if reward_window else None,
                    "eligibility_status": submission.get("eligibility_status"),
                    "p_yes_bps": submission.get("p_yes_bps"),
                    "score": round(float(submission.get("score", 0.0)), 6),
                    "reward_amount": submission.get("reward_amount", 0),
                    "outcome": task.get("outcome"),
                    "updated_at": submission.get("updated_at"),
                }
            )
        items.sort(
            key=lambda item: (
                item.get("updated_at") or "",
                item.get("resolve_at") or "",
                item.get("task_run_id") or "",
            ),
            reverse=True,
        )
        return items[:limit]

    async def get_replay_proof(
        self,
        entity_type: str,
        entity_id: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        await self.reconcile(now)
        current = now or utc_now()
        if entity_type == "reward_window":
            reward_window = await self.repo.get_reward_window(entity_id)
            if not reward_window:
                raise ValueError("reward window not found")
            artifact_refs = await self._artifact_refs_for_entity("reward_window", entity_id)
            settlement_batch_id = reward_window.get("settlement_batch_id")
            if settlement_batch_id:
                artifact_refs.extend(await self._artifact_refs_for_entity("settlement_batch", settlement_batch_id))
            membership = {
                "task_run_ids": list(reward_window.get("task_run_ids", [])),
                "miner_addresses": list(reward_window.get("miner_addresses", [])),
                "settlement_batch_id": settlement_batch_id,
            }
            payload = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "lane": reward_window.get("lane"),
                "membership": membership,
                "total_reward_amount": reward_window.get("total_reward_amount", 0),
                "window_end_at": reward_window.get("window_end_at"),
            }
            replay_hash = "sha256:" + hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            return {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "lane": reward_window.get("lane"),
                "artifact_refs": artifact_refs,
                "policy_bundle_version": reward_window.get("policy_bundle_version") or POLICY_BUNDLE_VERSION,
                "outcome_revision": 1,
                "score_revision": 1,
                "replay_proof_hash": replay_hash,
                "membership": membership,
                "generated_at": isoformat_z(current),
            }
        if entity_type == "task_run":
            task = await self.repo.get_task(entity_id)
            if not task:
                raise ValueError("task not found")
            await self._ensure_task_pack_artifact(task, current)
            payload = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "lane": task.get("lane"),
                "pack_hash": task.get("pack_hash"),
                "outcome": task.get("outcome"),
                "reward_window_id": task.get("reward_window_id"),
            }
            replay_hash = "sha256:" + hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            return {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "lane": task.get("lane"),
                "artifact_refs": await self._artifact_refs_for_entity("task_run", entity_id),
                "policy_bundle_version": POLICY_BUNDLE_VERSION,
                "outcome_revision": 1,
                "score_revision": 1,
                "replay_proof_hash": replay_hash,
                "membership": {"reward_window_id": task.get("reward_window_id")},
                "generated_at": isoformat_z(current),
            }
        raise ValueError("unsupported entity type")

    async def rebuild_reward_window(
        self,
        reward_window_id: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        await self.reconcile(now)
        reward_window = await self.repo.get_reward_window(reward_window_id)
        if not reward_window:
            raise ValueError("reward window not found")
        current = now or utc_now()
        tasks = [
            task
            for task in await self.repo.list_tasks()
            if task.get("reward_window_id") == reward_window_id
        ]
        task_run_ids = sorted(task["task_run_id"] for task in tasks)
        miner_addresses: set[str] = set()
        submission_count = 0
        total_reward_amount = 0
        for task in tasks:
            submissions = await self.repo.list_submissions_for_task(task["task_run_id"])
            for submission in submissions:
                if submission.get("p_yes_bps") is None:
                    continue
                miner_addresses.add(submission["miner_address"])
                submission_count += 1
                total_reward_amount += int(submission.get("reward_amount", 0) or 0)

        saved = await self.repo.save_reward_window(
            _materialize_reward_window(
                {
                    **reward_window,
                    "task_count": len(task_run_ids),
                    "submission_count": submission_count,
                    "miner_count": len(miner_addresses),
                    "total_reward_amount": total_reward_amount,
                    "task_run_ids": task_run_ids,
                    "miner_addresses": sorted(miner_addresses),
                    "updated_at": isoformat_z(current),
                }
            )[0]
        )
        await self._upsert_reward_window_artifact(saved, current)
        return saved

    async def retry_anchor_settlement_batch(
        self,
        settlement_batch_id: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        await self.reconcile(now)
        batch = await self.repo.get_settlement_batch(settlement_batch_id)
        if not batch:
            raise ValueError("settlement batch not found")
        current = now or utc_now()
        reward_window_ids = list(batch.get("reward_window_ids", []))
        task_run_ids: list[str] = []
        miner_totals: dict[str, dict] = {}
        for reward_window_id in reward_window_ids:
            reward_window = await self.repo.get_reward_window(reward_window_id)
            if reward_window:
                task_run_ids.extend(reward_window.get("task_run_ids", []))
                if str(batch.get("lane") or "").startswith("poker_mtt_"):
                    projection_artifacts = await self.repo.list_artifacts_for_entity("reward_window", reward_window_id)
                    projection_artifact = next(
                        (
                            artifact
                            for artifact in projection_artifacts
                            if artifact.get("kind") == "poker_mtt_reward_window_projection"
                        ),
                        None,
                    )
                    if not projection_artifact:
                        raise ValueError("poker mtt reward window projection not found")
                    for reward_row in projection_artifact.get("payload_json", {}).get("miner_reward_rows", []):
                        current_total = miner_totals.setdefault(
                            reward_row["miner_address"],
                            {
                                "miner_address": reward_row["miner_address"],
                                "gross_reward_amount": 0,
                                "submission_count": 0,
                            },
                        )
                        current_total["gross_reward_amount"] += int(reward_row.get("gross_reward_amount", 0) or 0)
                        current_total["submission_count"] += int(reward_row.get("submission_count", 0) or 0)
                else:
                    for task_run_id in reward_window.get("task_run_ids", []):
                        submissions = await self.repo.list_submissions_for_task(task_run_id)
                        for submission in submissions:
                            reward_amount = int(submission.get("reward_amount", 0) or 0)
                            if reward_amount <= 0:
                                continue
                            current_total = miner_totals.setdefault(
                                submission["miner_address"],
                                {
                                    "miner_address": submission["miner_address"],
                                    "gross_reward_amount": 0,
                                    "submission_count": 0,
                                },
                            )
                            current_total["gross_reward_amount"] += reward_amount
                            current_total["submission_count"] += 1

        sorted_task_run_ids = sorted(set(task_run_ids))
        miner_reward_rows = sorted(miner_totals.values(), key=lambda item: item["miner_address"])
        reward_window_ids_root = _hash_sequence(sorted(reward_window_ids))
        task_run_ids_root = _hash_sequence(sorted_task_run_ids)
        miner_reward_rows_root = _hash_sequence(miner_reward_rows)
        policy_bundle_version = batch.get("policy_bundle_version") or POLICY_BUNDLE_VERSION
        canonical_root_input = {
            "schema_version": ANCHOR_PAYLOAD_SCHEMA_VERSION,
            "policy_bundle_version": policy_bundle_version,
            "settlement_batch_id": settlement_batch_id,
            "lane": batch.get("lane"),
            "window_start_at": batch.get("window_start_at"),
            "window_end_at": batch.get("window_end_at"),
            "reward_window_ids_root": reward_window_ids_root,
            "task_run_ids_root": task_run_ids_root,
            "miner_reward_rows_root": miner_reward_rows_root,
            "task_count": batch.get("task_count", 0),
            "miner_count": batch.get("miner_count", 0),
            "total_reward_amount": batch.get("total_reward_amount", 0),
        }
        canonical_root = _hash_payload(canonical_root_input)
        anchor_payload_json = {
            **canonical_root_input,
            "reward_window_ids": sorted(reward_window_ids),
            "task_run_ids": sorted_task_run_ids,
            "miner_reward_rows": miner_reward_rows,
            "canonical_root": canonical_root,
        }
        anchor_payload_hash = "sha256:" + hashlib.sha256(
            json.dumps(anchor_payload_json, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        saved = await self.repo.save_settlement_batch(
            {
                **batch,
                "state": "anchor_ready",
                "anchor_job_id": None,
                "policy_bundle_version": policy_bundle_version,
                "anchor_schema_version": ANCHOR_PAYLOAD_SCHEMA_VERSION,
                "canonical_root": canonical_root,
                "anchor_payload_json": anchor_payload_json,
                "anchor_payload_hash": anchor_payload_hash,
                "updated_at": isoformat_z(current),
            }
        )
        await self._upsert_settlement_anchor_artifact(saved, current)
        return saved

    async def list_anchor_jobs(self, *, now: datetime | None = None) -> list[dict]:
        await self.reconcile(now)
        return await self.repo.list_anchor_jobs()

    async def build_chain_tx_plan(
        self,
        anchor_job_id: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        await self.reconcile(now)
        anchor_job = await self.repo.get_anchor_job(anchor_job_id)
        if not anchor_job:
            raise ValueError("anchor job not found")
        settlement_batch = await self.repo.get_settlement_batch(anchor_job["settlement_batch_id"])
        if not settlement_batch:
            raise ValueError("settlement batch not found")
        if not settlement_batch.get("anchor_payload_json") or not settlement_batch.get("canonical_root"):
            raise ValueError("settlement batch missing canonical anchor payload")
        plan = build_chain_anchor_tx_plan(anchor_job=anchor_job, settlement_batch=settlement_batch)
        current = now or utc_now()
        await self.repo.save_artifact(
            {
                "id": f"art:anchor_job:{anchor_job_id}:chain-tx-plan",
                "kind": "chain_tx_plan",
                "entity_type": "anchor_job",
                "entity_id": anchor_job_id,
                "payload_json": plan,
                "payload_hash": plan["plan_hash"],
                "created_at": isoformat_z(current),
                "updated_at": isoformat_z(current),
            }
        )
        return plan

    async def broadcast_chain_tx_fallback(
        self,
        anchor_job_id: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        current = now or utc_now()
        plan = await self.build_chain_tx_plan(anchor_job_id, now=current)
        anchor_job = await self.repo.get_anchor_job(anchor_job_id)
        if not anchor_job:
            raise ValueError("anchor job not found")

        broadcaster = self.chain_broadcaster
        if broadcaster is None:
            raise ValueError("chain broadcaster not configured")

        try:
            receipt = await broadcaster(plan, current)
        except ValueError as exc:
            await self.mark_anchor_job_failed(anchor_job_id, failure_reason=str(exc), now=current)
            raise

        saved_job = await self.repo.save_anchor_job(
            {
                **anchor_job,
                "state": "anchor_submitted",
                "broadcast_status": "broadcast_submitted",
                "broadcast_tx_hash": receipt.get("tx_hash"),
                "last_broadcast_at": receipt.get("broadcast_at") or isoformat_z(current),
                "updated_at": isoformat_z(current),
            }
        )
        await self.repo.save_artifact(
            {
                "id": f"art:anchor_job:{anchor_job_id}:broadcast-receipt",
                "kind": "chain_broadcast_receipt",
                "entity_type": "anchor_job",
                "entity_id": anchor_job_id,
                "payload_json": {
                    "receipt": receipt,
                    "plan_hash": plan["plan_hash"],
                },
                "payload_hash": _hash_payload(
                    {
                        "receipt": receipt,
                        "plan_hash": plan["plan_hash"],
                    }
                ),
                "created_at": isoformat_z(current),
                "updated_at": isoformat_z(current),
            }
        )
        return {
            "anchor_job_id": anchor_job_id,
            "settlement_batch_id": saved_job["settlement_batch_id"],
            "broadcast_status": saved_job.get("broadcast_status"),
            "tx_hash": saved_job.get("broadcast_tx_hash"),
            "plan_hash": plan["plan_hash"],
            "memo": plan["fallback_memo"],
            "account_number": receipt.get("account_number"),
            "sequence": receipt.get("sequence"),
            "attempt_count": receipt.get("attempt_count"),
        }

    async def broadcast_chain_tx_typed(
        self,
        anchor_job_id: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        current = now or utc_now()
        plan = await self.build_chain_tx_plan(anchor_job_id, now=current)
        anchor_job = await self.repo.get_anchor_job(anchor_job_id)
        if not anchor_job:
            raise ValueError("anchor job not found")

        broadcaster = self.chain_typed_broadcaster
        if broadcaster is None:
            raise ValueError("typed chain broadcaster not configured")

        try:
            receipt = await broadcaster(plan, current)
        except ValueError as exc:
            await self.mark_anchor_job_failed(anchor_job_id, failure_reason=str(exc), now=current)
            raise

        saved_job = await self.repo.save_anchor_job(
            {
                **anchor_job,
                "state": "anchor_submitted",
                "broadcast_status": "broadcast_submitted",
                "broadcast_tx_hash": receipt.get("tx_hash"),
                "last_broadcast_at": receipt.get("broadcast_at") or isoformat_z(current),
                "updated_at": isoformat_z(current),
            }
        )
        receipt_payload = {
            "receipt": receipt,
            "plan_hash": plan["plan_hash"],
        }
        await self.repo.save_artifact(
            {
                "id": f"art:anchor_job:{anchor_job_id}:broadcast-receipt",
                "kind": "chain_broadcast_receipt",
                "entity_type": "anchor_job",
                "entity_id": anchor_job_id,
                "payload_json": receipt_payload,
                "payload_hash": _hash_payload(receipt_payload),
                "created_at": isoformat_z(current),
                "updated_at": isoformat_z(current),
            }
        )
        return {
            "anchor_job_id": anchor_job_id,
            "settlement_batch_id": saved_job["settlement_batch_id"],
            "broadcast_status": saved_job.get("broadcast_status"),
            "tx_hash": saved_job.get("broadcast_tx_hash"),
            "plan_hash": plan["plan_hash"],
            "memo": plan["fallback_memo"],
            "account_number": receipt.get("account_number"),
            "sequence": receipt.get("sequence"),
            "attempt_count": receipt.get("attempt_count"),
            "broadcast_method": receipt.get("broadcast_method"),
        }

    async def retry_failed_anchor_job_broadcast_typed(
        self,
        anchor_job_id: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        return await self._retry_failed_anchor_job_broadcast(anchor_job_id, mode="typed", now=now)

    async def retry_failed_anchor_job_broadcast_fallback(
        self,
        anchor_job_id: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        return await self._retry_failed_anchor_job_broadcast(anchor_job_id, mode="fallback", now=now)

    async def _retry_failed_anchor_job_broadcast(
        self,
        anchor_job_id: str,
        *,
        mode: str,
        now: datetime | None = None,
    ) -> dict:
        current = now or utc_now()
        await self.reconcile(current)
        anchor_job = await self.repo.get_anchor_job(anchor_job_id)
        if not anchor_job:
            batch = await self.repo.get_settlement_batch(anchor_job_id)
            if batch and batch.get("anchor_job_id"):
                anchor_job = await self.repo.get_anchor_job(batch["anchor_job_id"])
        if not anchor_job:
            raise ValueError("anchor job not found")
        if anchor_job.get("state") != "anchor_failed":
            raise ValueError("anchor job not retryable")

        previous_anchor_job_id = anchor_job["id"]
        settlement_batch_id = anchor_job["settlement_batch_id"]
        await self.retry_anchor_settlement_batch(settlement_batch_id, now=current)
        submitted_batch = await self.submit_anchor_job(settlement_batch_id, now=current)
        new_anchor_job_id = submitted_batch["anchor_job_id"]

        if mode == "typed":
            receipt = await self.broadcast_chain_tx_typed(new_anchor_job_id, now=current)
        elif mode == "fallback":
            receipt = await self.broadcast_chain_tx_fallback(new_anchor_job_id, now=current)
        else:
            raise ValueError("unsupported retry broadcast mode")

        new_anchor_job = await self.repo.get_anchor_job(new_anchor_job_id)
        return {
            "previous_anchor_job_id": previous_anchor_job_id,
            "new_anchor_job_id": new_anchor_job_id,
            "settlement_batch_id": settlement_batch_id,
            "broadcast_mode": mode,
            "anchor_job_state": new_anchor_job.get("state") if new_anchor_job else None,
            "broadcast_status": new_anchor_job.get("broadcast_status") if new_anchor_job else None,
            "tx_hash": receipt.get("tx_hash"),
            "plan_hash": receipt.get("plan_hash"),
            "account_number": receipt.get("account_number"),
            "sequence": receipt.get("sequence"),
            "attempt_count": receipt.get("attempt_count"),
            "broadcast_method": receipt.get("broadcast_method"),
        }

    async def confirm_anchor_job_on_chain(
        self,
        anchor_job_id: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        await self.reconcile(now)
        anchor_job = await self.repo.get_anchor_job(anchor_job_id)
        if not anchor_job:
            batch = await self.repo.get_settlement_batch(anchor_job_id)
            if batch and batch.get("anchor_job_id"):
                anchor_job = await self.repo.get_anchor_job(batch["anchor_job_id"])
        if not anchor_job:
            raise ValueError("anchor job not found")

        resolved_anchor_job_id = anchor_job["id"]
        tx_hash = anchor_job.get("broadcast_tx_hash")
        if not tx_hash:
            raise ValueError("anchor job missing broadcast tx hash")

        if anchor_job.get("state") == "anchored":
            return {
                "anchor_job_id": resolved_anchor_job_id,
                "settlement_batch_id": anchor_job["settlement_batch_id"],
                "chain_confirmation_status": "confirmed",
                "anchor_job_state": "anchored",
                "tx_hash": tx_hash,
                "chain_height": None,
                "tx_code": 0,
                "tx_raw_log": "",
                "anchored_at": anchor_job.get("anchored_at"),
                "failure_reason": anchor_job.get("failure_reason"),
            }

        confirmer = self.chain_tx_confirmer
        if confirmer is None:
            raise ValueError("chain tx confirmer not configured")

        current = now or utc_now()
        receipt = await confirmer(tx_hash, current)
        confirmation_status = receipt.get("confirmation_status") or "pending"
        receipt_payload = {
            "receipt": receipt,
            "anchor_job_id": resolved_anchor_job_id,
            "settlement_batch_id": anchor_job["settlement_batch_id"],
        }
        await self.repo.save_artifact(
            {
                "id": f"art:anchor_job:{resolved_anchor_job_id}:confirmation-receipt",
                "kind": "chain_confirmation_receipt",
                "entity_type": "anchor_job",
                "entity_id": resolved_anchor_job_id,
                "payload_json": receipt_payload,
                "payload_hash": _hash_payload(receipt_payload),
                "created_at": isoformat_z(current),
                "updated_at": isoformat_z(current),
            }
        )

        if confirmation_status == "confirmed":
            saved_job = await self.mark_anchor_job_anchored(resolved_anchor_job_id, now=current)
        elif confirmation_status == "failed":
            failure_reason = receipt.get("raw_log") or f"chain tx failed with code {receipt.get('code')}"
            saved_job = await self.mark_anchor_job_failed(
                resolved_anchor_job_id,
                failure_reason=failure_reason,
                now=current,
            )
        else:
            saved_job = await self.repo.get_anchor_job(resolved_anchor_job_id) or anchor_job

        return {
            "anchor_job_id": resolved_anchor_job_id,
            "settlement_batch_id": anchor_job["settlement_batch_id"],
            "chain_confirmation_status": confirmation_status,
            "anchor_job_state": saved_job.get("state"),
            "tx_hash": tx_hash,
            "chain_height": receipt.get("height"),
            "tx_code": receipt.get("code"),
            "tx_raw_log": receipt.get("raw_log"),
            "anchored_at": saved_job.get("anchored_at"),
            "failure_reason": saved_job.get("failure_reason"),
        }

    async def reconcile_pending_anchor_jobs_on_chain(
        self,
        *,
        now: datetime | None = None,
    ) -> list[dict]:
        current = now or utc_now()
        await self.reconcile(current)
        items = []
        for anchor_job in await self.repo.list_anchor_jobs():
            if anchor_job.get("state") != "anchor_submitted":
                continue
            if not anchor_job.get("broadcast_tx_hash"):
                continue
            items.append(await self.confirm_anchor_job_on_chain(anchor_job["id"], now=current))
        return items

    async def submit_anchor_job(
        self,
        settlement_batch_id: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        await self.reconcile(now)
        batch = await self.repo.get_settlement_batch(settlement_batch_id)
        if not batch:
            raise ValueError("settlement batch not found")
        if batch.get("state") != "anchor_ready":
            raise ValueError("settlement batch not anchor_ready")
        if not batch.get("anchor_payload_hash") or not batch.get("anchor_payload_json"):
            raise ValueError("settlement batch missing anchor payload")
        current = now or utc_now()
        anchor_job_id_base = _build_anchor_job_id(settlement_batch_id, current)
        anchor_job_id = anchor_job_id_base
        suffix = 1
        while await self.repo.get_anchor_job(anchor_job_id):
            anchor_job_id = f"{anchor_job_id_base}_{suffix}"
            suffix += 1
        await self.repo.save_anchor_job(
            {
                "id": anchor_job_id,
                "settlement_batch_id": settlement_batch_id,
                "lane": batch.get("lane", "forecast_15m"),
                "state": "anchor_submitted",
                "anchor_payload_hash": batch["anchor_payload_hash"],
                "broadcast_status": None,
                "broadcast_tx_hash": None,
                "last_broadcast_at": None,
                "failure_reason": None,
                "submitted_at": isoformat_z(current),
                "anchored_at": None,
                "created_at": isoformat_z(current),
                "updated_at": isoformat_z(current),
            }
        )
        return await self.repo.save_settlement_batch(
            {
                **batch,
                "state": "anchor_submitted",
                "anchor_job_id": anchor_job_id,
                "updated_at": isoformat_z(current),
            }
        )

    async def mark_anchor_job_anchored(
        self,
        anchor_job_id: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        await self.reconcile(now)
        anchor_job = await self.repo.get_anchor_job(anchor_job_id)
        if not anchor_job:
            batch = await self.repo.get_settlement_batch(anchor_job_id)
            if batch and batch.get("anchor_job_id"):
                anchor_job = await self.repo.get_anchor_job(batch["anchor_job_id"])
        if not anchor_job:
            raise ValueError("anchor job not found")
        resolved_anchor_job_id = anchor_job["id"]
        current = now or utc_now()
        saved_job = await self.repo.save_anchor_job(
            {
                **anchor_job,
                "state": "anchored",
                "anchored_at": isoformat_z(current),
                "failure_reason": None,
                "updated_at": isoformat_z(current),
            }
        )
        batch = await self.repo.get_settlement_batch(anchor_job["settlement_batch_id"])
        if batch and batch.get("anchor_job_id") == resolved_anchor_job_id:
            await self.repo.save_settlement_batch(
                {
                    **batch,
                    "state": "anchored",
                    "updated_at": isoformat_z(current),
                }
            )
        return saved_job

    async def mark_anchor_job_failed(
        self,
        anchor_job_id: str,
        *,
        failure_reason: str,
        now: datetime | None = None,
    ) -> dict:
        await self.reconcile(now)
        anchor_job = await self.repo.get_anchor_job(anchor_job_id)
        if not anchor_job:
            batch = await self.repo.get_settlement_batch(anchor_job_id)
            if batch and batch.get("anchor_job_id"):
                anchor_job = await self.repo.get_anchor_job(batch["anchor_job_id"])
        if not anchor_job:
            raise ValueError("anchor job not found")
        resolved_anchor_job_id = anchor_job["id"]
        current = now or utc_now()
        saved_job = await self.repo.save_anchor_job(
            {
                **anchor_job,
                "state": "anchor_failed",
                "failure_reason": failure_reason,
                "updated_at": isoformat_z(current),
            }
        )
        batch = await self.repo.get_settlement_batch(anchor_job["settlement_batch_id"])
        if batch and batch.get("anchor_job_id") == resolved_anchor_job_id:
            await self.repo.save_settlement_batch(
                {
                    **batch,
                    "state": "anchor_failed",
                    "updated_at": isoformat_z(current),
                }
            )
        return saved_job

    async def _build_score_explanation(self, miner_address: str, tasks: list[dict]) -> dict:
        latest_fast = None
        latest_daily = None
        latest_fast_at = None
        latest_daily_at = None
        for task in tasks:
            submission = await self.repo.get_submission(task["task_run_id"], miner_address)
            if not submission or submission.get("p_yes_bps") is None:
                continue
            timestamp_raw = submission.get("accepted_reveal_at") or submission.get("updated_at") or submission.get("accepted_commit_at")
            timestamp = as_utc_datetime(timestamp_raw)
            if task["lane"] == "forecast_15m":
                candidate = {
                    "task_run_id": task["task_run_id"],
                    "asset": task["asset"],
                    "state": submission.get("state"),
                    "p_yes_bps": submission.get("p_yes_bps"),
                    "baseline_q_bps": task.get("baseline_q_bps"),
                    "outcome": task.get("outcome"),
                    "score": round(float(submission.get("score", 0.0)), 6),
                    "reward_amount": submission.get("reward_amount", 0),
                    "reward_eligibility_status": submission.get("eligibility_status", "eligible"),
                }
                if latest_fast_at is None or timestamp >= latest_fast_at:
                    latest_fast = candidate
                    latest_fast_at = timestamp
            elif task["lane"] == "daily_anchor":
                candidate = {
                    "task_run_id": task["task_run_id"],
                    "asset": task["asset"],
                    "state": submission.get("state"),
                    "p_yes_bps": submission.get("p_yes_bps"),
                    "outcome": task.get("outcome"),
                    "anchor_multiplier": round(1.0 + float(submission.get("score", 0.0)), 6),
                }
                if latest_daily_at is None or timestamp >= latest_daily_at:
                    latest_daily = candidate
                    latest_daily_at = timestamp

        arena_entries = await self.repo.list_arena_results_for_miner(miner_address, limit=1)
        latest_arena = None
        if arena_entries:
            latest = arena_entries[0]
            latest_arena = {
                "tournament_id": latest["tournament_id"],
                "rated_or_practice": latest["rated_or_practice"],
                "eligible_for_multiplier": latest.get("eligible_for_multiplier", False),
                "arena_score": latest.get("arena_score"),
                "arena_multiplier_after": latest.get("multiplier_after", 1.0),
            }

        return {
            "latest_fast": latest_fast,
            "latest_daily": latest_daily,
            "latest_arena": latest_arena,
        }

    async def _build_reward_timeline(self, miner: dict, tasks: list[dict], current: datetime, score_explanation: dict) -> dict:
        holds = await self.repo.list_hold_entries_for_miner(miner["address"])
        open_hold_entries = [hold for hold in holds if hold.get("state") == "held"]
        pending_resolution_count = 0
        for task in tasks:
            submission = await self.repo.get_submission(task["task_run_id"], miner["address"])
            if submission and submission.get("state") == "pending_resolution":
                pending_resolution_count += 1

        latest_fast = score_explanation.get("latest_fast") or {}
        latest_daily = score_explanation.get("latest_daily") or {}
        latest_arena = score_explanation.get("latest_arena") or {}
        return {
            "released_rewards": miner["total_rewards"],
            "held_rewards": miner.get("held_rewards", 0),
            "admission_state": self._admission_state(miner, current),
            "anti_abuse_discount": round(self._admission_release_ratio(miner, current), 4),
            "open_hold_entry_count": len(open_hold_entries),
            "pending_resolution_count": pending_resolution_count,
            "latest_fast_reward_amount": latest_fast.get("reward_amount", 0),
            "latest_daily_anchor_multiplier": latest_daily.get("anchor_multiplier"),
            "latest_arena_multiplier_after": latest_arena.get("arena_multiplier_after", miner.get("arena_multiplier", 1.0)),
        }

    async def apply_poker_mtt_results(
        self,
        *,
        tournament_id: str,
        rated_or_practice: str,
        human_only: bool,
        field_size: int,
        policy_bundle_version: str,
        results: list[dict],
        completed_at: datetime,
    ) -> dict:
        if rated_or_practice not in {"rated", "practice"}:
            raise ValueError("invalid rated_or_practice")
        if field_size < 2:
            raise ValueError("field_size must be at least 2")

        await self.repo.save_poker_mtt_tournament(
            {
                "id": tournament_id,
                "runtime_source": "lepoker-gameserver",
                "rated_or_practice": rated_or_practice,
                "human_only": human_only,
                "field_size": field_size,
                "status": "completed",
                "policy_bundle_version": policy_bundle_version,
                "completed_at": isoformat_z(completed_at),
                "created_at": isoformat_z(completed_at),
                "updated_at": isoformat_z(completed_at),
            }
        )

        items = []
        for result in results:
            miner_address = result["miner_id"]
            miner = await self.repo.get_miner(miner_address)
            if not miner:
                raise ValueError(f"miner not found: {miner_address}")

            final_rank = int(result["final_rank"])
            if final_rank < 1 or final_rank > field_size:
                raise ValueError("final_rank out of range")

            tournament_result_score = clamp(float(result["tournament_result_score"]), -1.0, 1.0)
            hidden_eval_score = clamp(float(result.get("hidden_eval_score", 0.0)), -1.0, 1.0)
            consistency_input_score = clamp(float(result.get("consistency_input_score", 0.0)), -1.0, 1.0)
            total_score = round(
                clamp(
                    (tournament_result_score * 0.55)
                    + (hidden_eval_score * 0.25)
                    + (consistency_input_score * 0.20),
                    -1.0,
                    1.0,
                ),
                6,
            )
            finish_percentile = round((field_size - final_rank) / max(1, field_size - 1), 6)
            eligible_for_multiplier = rated_or_practice == "rated" and human_only
            multiplier_before = float(miner.get("poker_mtt_multiplier", 1.0))
            multiplier_after = multiplier_before
            rolling_score = None

            entry = await self.repo.save_poker_mtt_result(
                {
                    "id": f"poker_mtt:{tournament_id}:{miner_address}",
                    "tournament_id": tournament_id,
                    "miner_address": miner_address,
                    "rated_or_practice": rated_or_practice,
                    "human_only": human_only,
                    "field_size": field_size,
                    "final_rank": final_rank,
                    "finish_percentile": finish_percentile,
                    "tournament_result_score": tournament_result_score,
                    "hidden_eval_score": hidden_eval_score,
                    "consistency_input_score": consistency_input_score,
                    "total_score": total_score,
                    "eligible_for_multiplier": eligible_for_multiplier,
                    "rolling_score": None,
                    "multiplier_before": multiplier_before,
                    "multiplier_after": multiplier_after,
                    "evaluation_state": str(result.get("evaluation_state") or "provisional"),
                    "evaluation_version": policy_bundle_version,
                    "evidence_root": result.get("evidence_root"),
                    "created_at": isoformat_z(completed_at),
                    "updated_at": isoformat_z(completed_at),
                }
            )

            if eligible_for_multiplier:
                eligible_results = await self.repo.list_poker_mtt_results_for_miner(
                    miner_address,
                    eligible_only=True,
                    limit=20,
                )
                eligible_count = len(
                    await self.repo.list_poker_mtt_results_for_miner(miner_address, eligible_only=True)
                )
                if eligible_count <= 15:
                    rolling_score = 0.0
                    multiplier_after = 1.0
                else:
                    rolling_score = round(
                        sum(item["total_score"] for item in eligible_results) / max(1, len(eligible_results)),
                        6,
                    )
                    multiplier_after = round(clamp(1.0 + (rolling_score * 0.015), 0.96, 1.04), 6)
                entry = await self.repo.save_poker_mtt_result(
                    {
                        **entry,
                        "rolling_score": rolling_score,
                        "multiplier_after": multiplier_after,
                        "updated_at": isoformat_z(completed_at),
                    }
                )
                await self.repo.update_miner(
                    miner_address,
                    {
                        "poker_mtt_multiplier": multiplier_after,
                        "updated_at": completed_at,
                    },
                )

            items.append(
                {
                    "miner_id": miner_address,
                    "final_rank": final_rank,
                    "finish_percentile": finish_percentile,
                    "eligible_for_multiplier": eligible_for_multiplier,
                    "tournament_result_score": tournament_result_score,
                    "hidden_eval_score": hidden_eval_score,
                    "consistency_input_score": consistency_input_score,
                    "total_score": total_score,
                    "poker_mtt_multiplier": multiplier_after,
                    "rolling_score": rolling_score,
                }
            )

        return {
            "tournament_id": tournament_id,
            "rated_or_practice": rated_or_practice,
            "human_only": human_only,
            "field_size": field_size,
            "policy_bundle_version": policy_bundle_version,
            "items": items,
        }

    async def build_poker_mtt_reward_window(
        self,
        *,
        lane: str,
        window_start_at: datetime,
        window_end_at: datetime,
        reward_pool_amount: int,
        include_provisional: bool,
        policy_bundle_version: str | None = None,
        projection_metadata: dict | None = None,
        reward_window_id: str | None = None,
        now: datetime | None = None,
    ) -> dict:
        if lane not in {"poker_mtt_daily", "poker_mtt_weekly"}:
            raise ValueError("invalid poker mtt reward window lane")

        window_start = as_utc_datetime(window_start_at).replace(microsecond=0)
        window_end = as_utc_datetime(window_end_at).replace(microsecond=0)
        if window_end <= window_start:
            raise ValueError("window_end_at must be after window_start_at")

        current = now or utc_now()
        selected_results = []
        for result in await self.repo.list_poker_mtt_results():
            completed_at = as_utc_datetime(result.get("created_at") or result.get("updated_at"))
            if not (window_start <= completed_at < window_end):
                continue
            if result.get("rated_or_practice") != "rated":
                continue
            if result.get("human_only") is not True:
                continue
            if not include_provisional and result.get("evaluation_state") != "final":
                continue
            selected_results.append(result)

        if not selected_results:
            raise ValueError("no poker mtt results found for reward window")

        resolved_reward_window_id = reward_window_id or _poker_mtt_reward_window_id(lane, window_start, window_end)
        existing_window = await self.repo.get_reward_window(resolved_reward_window_id)
        if existing_window and existing_window.get("settlement_batch_id"):
            existing_batch = await self.repo.get_settlement_batch(existing_window["settlement_batch_id"])
            if existing_batch and existing_batch.get("state") not in {None, "open"}:
                return existing_window
        resolved_policy_bundle_version = (
            policy_bundle_version
            or (existing_window.get("policy_bundle_version") if existing_window else None)
            or _default_poker_mtt_policy_bundle_version(self.settings, lane)
        )
        tournament_ids = sorted({result["tournament_id"] for result in selected_results})
        miner_addresses = sorted({result["miner_address"] for result in selected_results})

        score_weights: dict[str, float] = {}
        submission_counts: dict[str, int] = {}
        for result in selected_results:
            miner_address = result["miner_address"]
            submission_counts[miner_address] = submission_counts.get(miner_address, 0) + 1
            score_weights[miner_address] = score_weights.get(miner_address, 0.0) + max(
                0.0,
                float(result.get("total_score", 0.0) or 0.0),
            )

        reward_allocations = _allocate_integer_pool_by_weights(
            [(miner_address, score_weights.get(miner_address, 0.0)) for miner_address in miner_addresses],
            reward_pool_amount,
        )
        miner_reward_rows = [
            {
                "miner_address": miner_address,
                "gross_reward_amount": int(reward_allocations.get(miner_address, 0)),
                "submission_count": submission_counts.get(miner_address, 0),
            }
            for miner_address in miner_addresses
        ]

        saved = await self.repo.save_reward_window(
            _materialize_reward_window(
                {
                    "id": resolved_reward_window_id,
                    "lane": lane,
                    "state": "finalized",
                    "window_start_at": isoformat_z(window_start),
                    "window_end_at": isoformat_z(window_end),
                    "task_count": len(tournament_ids),
                    "submission_count": len(selected_results),
                    "miner_count": len(miner_addresses),
                    "total_reward_amount": reward_pool_amount,
                    "settlement_batch_id": existing_window.get("settlement_batch_id") if existing_window else None,
                    "task_run_ids": tournament_ids,
                    "miner_addresses": miner_addresses,
                    "policy_bundle_version": resolved_policy_bundle_version,
                    "created_at": existing_window.get("created_at", isoformat_z(current)) if existing_window else isoformat_z(current),
                    "updated_at": isoformat_z(current),
                }
            )[0]
        )
        await self._upsert_reward_window_artifact(saved, current)
        await self._upsert_poker_mtt_reward_window_projection_artifact(
            reward_window=saved,
            now=current,
            payload={
                "reward_window_id": saved["id"],
                "lane": lane,
                "window_start_at": saved["window_start_at"],
                "window_end_at": saved["window_end_at"],
                "reward_pool_amount": reward_pool_amount,
                "policy_bundle_version": resolved_policy_bundle_version,
                "include_provisional": include_provisional,
                "tournament_ids": tournament_ids,
                "poker_mtt_result_ids": sorted(result["id"] for result in selected_results),
                "miner_reward_rows": miner_reward_rows,
                **(projection_metadata or {}),
            },
        )
        await self._build_settlement_batches(current)
        return await self.repo.get_reward_window(saved["id"]) or saved

    async def apply_arena_results(
        self,
        *,
        tournament_id: str,
        rated_or_practice: str,
        human_only: bool,
        results: list[dict],
        completed_at: datetime,
    ) -> dict:
        if rated_or_practice not in {"rated", "practice"}:
            raise ValueError("invalid rated_or_practice")
        items = []
        for result in results:
            miner_address = result["miner_id"]
            miner = await self.repo.get_miner(miner_address)
            if not miner:
                raise ValueError(f"miner not found: {miner_address}")
            arena_score = clamp(float(result["arena_score"]), -1.0, 1.0)
            eligible_for_multiplier = rated_or_practice == "rated" and human_only
            multiplier_after = miner.get("arena_multiplier", 1.0)
            conservative_skill = None

            entry = await self.repo.save_arena_result(
                {
                    "id": f"arena:{tournament_id}:{miner_address}",
                    "tournament_id": tournament_id,
                    "miner_address": miner_address,
                    "rated_or_practice": rated_or_practice,
                    "human_only": human_only,
                    "eligible_for_multiplier": eligible_for_multiplier,
                    "arena_score": arena_score,
                    "conservative_skill": None,
                    "multiplier_after": multiplier_after,
                    "created_at": isoformat_z(completed_at),
                    "updated_at": isoformat_z(completed_at),
                }
            )

            if eligible_for_multiplier:
                eligible_results = await self.repo.list_arena_results_for_miner(
                    miner_address,
                    eligible_only=True,
                    limit=20,
                )
                eligible_count = len(await self.repo.list_arena_results_for_miner(miner_address, eligible_only=True))
                if eligible_count <= 15:
                    conservative_skill = 0.0
                    multiplier_after = 1.0
                else:
                    conservative_skill = sum(item["arena_score"] for item in eligible_results) / max(1, len(eligible_results))
                    multiplier_after = round(clamp(1.0 + (conservative_skill * 0.015), 0.96, 1.04), 6)
                entry = await self.repo.save_arena_result(
                    {
                        **entry,
                        "conservative_skill": conservative_skill,
                        "multiplier_after": multiplier_after,
                        "updated_at": isoformat_z(completed_at),
                    }
                )
                await self.repo.update_miner(
                    miner_address,
                    {
                        "arena_multiplier": multiplier_after,
                        "updated_at": completed_at,
                    },
                )

            items.append(
                {
                    "miner_id": miner_address,
                    "eligible_for_multiplier": eligible_for_multiplier,
                    "arena_score": arena_score,
                    "arena_multiplier": multiplier_after,
                    "conservative_skill": conservative_skill,
                }
            )

        return {
            "tournament_id": tournament_id,
            "rated_or_practice": rated_or_practice,
            "human_only": human_only,
            "items": items,
        }

    async def _settle_due_tasks(self, now: datetime) -> None:
        for task in await self.repo.list_due_unsettled_fast_tasks(isoformat_z(now)):
            if self.task_provider:
                resolution = await self.task_provider.resolve_fast_task(task)
            else:
                resolution = resolve_fast_task(task)
            resolution_status = resolution.get("resolution_status")
            if not resolution_status:
                resolution_status = "resolved" if resolution.get("outcome") is not None else "pending"
            submissions = await self.repo.list_submissions_for_task(task["task_run_id"])

            if resolution_status != "resolved" or resolution.get("outcome") is None:
                for submission in submissions:
                    if submission.get("p_yes_bps") is None:
                        continue
                    await self.repo.save_submission(
                        {
                            **submission,
                            "state": "pending_resolution",
                            "updated_at": isoformat_z(now),
                        }
                    )

                await self.repo.upsert_task(
                    {
                        **task,
                        "commit_close_ref_price": resolution.get("commit_close_ref_price", task.get("commit_close_ref_price")),
                        "end_ref_price": resolution.get("end_ref_price"),
                        "resolution_source": resolution.get("resolution_method"),
                        "outcome": None,
                        "state": "awaiting_resolution",
                        "updated_at": isoformat_z(now),
                    }
                )
                continue

            for submission in submissions:
                p_yes_bps = submission.get("p_yes_bps")
                if p_yes_bps is None:
                    continue
                score = score_probability(
                    p_yes_bps=p_yes_bps,
                    baseline_q_bps=task["baseline_q_bps"],
                    outcome=resolution["outcome"],
                )
                reward_amount = _reward_from_score(score) if submission.get("eligibility_status") == "eligible" else 0
                direction_correct = int((p_yes_bps >= 5000) == bool(resolution["outcome"]))
                await self.repo.save_submission(
                    {
                        **submission,
                        "state": "resolved",
                        "score": score,
                        "reward_amount": reward_amount,
                        "updated_at": isoformat_z(now),
                    }
                )
                miner = await self.repo.get_miner(submission["miner_address"])
                settled_tasks = miner["settled_tasks"] + 1
                edge_score_total = miner["edge_score_total"] + score
                model_reliability = clamp(1.0 + (edge_score_total / settled_tasks) * 0.25, 0.97, 1.03)
                released_reward, held_reward, admission_state = self._split_reward_by_admission(miner, reward_amount, now)
                if held_reward > 0:
                    await self.repo.save_hold_entry(
                        {
                            "id": f"hold:{submission['id']}",
                            "miner_address": submission["miner_address"],
                            "task_run_id": task["task_run_id"],
                            "submission_id": submission["id"],
                            "amount_held": held_reward,
                            "amount_released": 0,
                            "state": "held",
                            "release_after": isoformat_z(now),
                            "created_at": isoformat_z(now),
                            "updated_at": isoformat_z(now),
                        }
                    )
                await self.repo.update_miner(
                    submission["miner_address"],
                    {
                        "total_rewards": miner["total_rewards"] + released_reward,
                        "held_rewards": miner.get("held_rewards", 0) + held_reward,
                        "settled_tasks": settled_tasks,
                        "correct_direction_count": miner["correct_direction_count"] + direction_correct,
                        "edge_score_total": edge_score_total,
                        "model_reliability": model_reliability,
                        "admission_state": admission_state,
                        "updated_at": now,
                    },
                )

            await self._apply_fast_task_participation(task, submissions, now)

            await self.repo.upsert_task(
                {
                    **task,
                    "commit_close_ref_price": resolution.get("commit_close_ref_price", task.get("commit_close_ref_price")),
                    "end_ref_price": resolution.get("end_ref_price"),
                    "resolution_source": resolution.get("resolution_method"),
                    "outcome": resolution["outcome"],
                    "state": "resolved",
                    "updated_at": isoformat_z(now),
                }
            )

    async def _settle_due_daily_tasks(self, now: datetime) -> None:
        for task in await self.repo.list_tasks():
            if task["lane"] != "daily_anchor":
                continue
            if task.get("state") == "resolved":
                continue
            if parse_time(task["resolve_at"]) > now:
                continue

            if self.task_provider and hasattr(self.task_provider, "resolve_daily_task"):
                resolution = await self.task_provider.resolve_daily_task(task)
            else:
                resolution = resolve_daily_task(task)

            resolution_status = resolution.get("resolution_status", "resolved")
            if resolution_status != "resolved" or resolution.get("outcome") is None:
                await self.repo.upsert_task(
                    {
                        **task,
                        "state": "awaiting_resolution",
                        "updated_at": isoformat_z(now),
                    }
                )
                continue

            submissions = await self.repo.list_submissions_for_task(task["task_run_id"])
            for submission in submissions:
                p_yes_bps = submission.get("p_yes_bps")
                if p_yes_bps is None:
                    continue
                anchor_multiplier = self._daily_anchor_multiplier(p_yes_bps, resolution["outcome"])
                await self.repo.save_submission(
                    {
                        **submission,
                        "state": "resolved",
                        "score": round(anchor_multiplier - 1.0, 6),
                        "reward_amount": 0,
                        "updated_at": isoformat_z(now),
                    }
                )
                miner = await self.repo.get_miner(submission["miner_address"])
                await self.repo.update_miner(
                    submission["miner_address"],
                    {
                        "model_reliability": clamp(miner["model_reliability"] * anchor_multiplier, 0.97, 1.03),
                        "updated_at": now,
                    },
                )

            await self.repo.upsert_task(
                {
                    **task,
                    "commit_close_ref_price": resolution.get("start_ref_price", task.get("commit_close_ref_price")),
                    "end_ref_price": resolution.get("end_ref_price"),
                    "resolution_source": resolution.get("resolution_method", "daily_anchor"),
                    "outcome": resolution["outcome"],
                    "state": "resolved",
                    "updated_at": isoformat_z(now),
                }
            )

    async def _release_matured_holds(self, now: datetime) -> None:
        for miner in await self.repo.list_miners():
            admission_state = self._admission_state(miner, now)
            held_rewards = miner.get("held_rewards", 0)
            if admission_state == "mature":
                released_total = 0
                for hold in await self.repo.list_due_hold_entries(isoformat_z(now)):
                    if hold["miner_address"] != miner["address"]:
                        continue
                    remaining = hold["amount_held"] - hold.get("amount_released", 0)
                    if remaining <= 0:
                        continue
                    released_total += remaining
                    await self.repo.save_hold_entry(
                        {
                            **hold,
                            "amount_released": hold["amount_held"],
                            "state": "released",
                            "updated_at": isoformat_z(now),
                        }
                    )
                if released_total > 0:
                    await self.repo.update_miner(
                        miner["address"],
                        {
                            "total_rewards": miner["total_rewards"] + released_total,
                            "held_rewards": max(0, held_rewards - released_total),
                            "admission_state": "mature",
                            "updated_at": now,
                        },
                    )
                elif held_rewards > 0:
                    await self.repo.update_miner(
                        miner["address"],
                        {
                            "total_rewards": miner["total_rewards"] + held_rewards,
                            "held_rewards": 0,
                            "admission_state": "mature",
                            "updated_at": now,
                        },
                    )
                elif miner.get("admission_state") != admission_state:
                    await self.repo.update_miner(
                        miner["address"],
                        {
                            "admission_state": "mature",
                            "updated_at": now,
                        },
                    )
            elif miner.get("admission_state") != admission_state:
                await self.repo.update_miner(
                    miner["address"],
                    {
                        "admission_state": admission_state,
                        "updated_at": now,
                    },
                )

    async def _build_reward_windows(self, now: datetime) -> None:
        grouped_tasks: dict[str, list[dict]] = {}
        for task in await self.repo.list_tasks():
            if task["lane"] != "forecast_15m":
                continue
            if task.get("state") != "resolved":
                continue
            if task.get("reward_window_id"):
                continue
            bucket = _hour_bucket_start(parse_time(task["resolve_at"]))
            reward_window_id = f"rw_{bucket.strftime('%Y%m%d%H')}"
            grouped_tasks.setdefault(reward_window_id, []).append(task)

        for reward_window_id, tasks in grouped_tasks.items():
            window_start = _hour_bucket_start(parse_time(tasks[0]["resolve_at"]))
            window_end = window_start + timedelta(hours=1)
            existing_window = await self.repo.get_reward_window(reward_window_id)
            existing_task_ids = list(existing_window.get("task_run_ids", [])) if existing_window else []
            existing_miner_addresses = list(existing_window.get("miner_addresses", [])) if existing_window else []
            task_run_ids = set(existing_task_ids)
            miner_addresses = set(existing_miner_addresses)
            submission_count = int(existing_window.get("submission_count", 0)) if existing_window else 0
            total_reward_amount = int(existing_window.get("total_reward_amount", 0)) if existing_window else 0

            for task in tasks:
                submissions = await self.repo.list_submissions_for_task(task["task_run_id"])
                task_run_ids.add(task["task_run_id"])
                for submission in submissions:
                    if submission.get("p_yes_bps") is None:
                        continue
                    miner_addresses.add(submission["miner_address"])
                    submission_count += 1
                    total_reward_amount += int(submission.get("reward_amount", 0) or 0)
                    await self.repo.save_submission(
                        {
                            **submission,
                            "reward_window_id": reward_window_id,
                            "updated_at": submission.get("updated_at") or isoformat_z(now),
                        }
                    )
                await self.repo.upsert_task(
                    {
                        **task,
                        "reward_window_id": reward_window_id,
                        "updated_at": isoformat_z(now),
                    }
                )

            saved = await self.repo.save_reward_window(
                _materialize_reward_window(
                    {
                        "id": reward_window_id,
                        "lane": "forecast_15m",
                        "state": "finalized",
                        "window_start_at": isoformat_z(window_start),
                        "window_end_at": isoformat_z(window_end),
                        "task_count": len(task_run_ids),
                        "submission_count": submission_count,
                        "miner_count": len(miner_addresses),
                        "total_reward_amount": total_reward_amount,
                        "settlement_batch_id": existing_window.get("settlement_batch_id") if existing_window else None,
                        "task_run_ids": sorted(task_run_ids),
                        "miner_addresses": sorted(miner_addresses),
                        "policy_bundle_version": existing_window.get("policy_bundle_version") if existing_window else POLICY_BUNDLE_VERSION,
                        "created_at": existing_window.get("created_at", isoformat_z(now)) if existing_window else isoformat_z(now),
                        "updated_at": isoformat_z(now),
                    }
                )[0]
            )
            await self._upsert_reward_window_artifact(saved, now)

    async def _build_poker_mtt_reward_windows(self, now: datetime) -> None:
        lane_configs = [
            ("poker_mtt_daily", int(getattr(self.settings, "poker_mtt_daily_reward_pool_amount", 0) or 0), _day_bucket_start, timedelta(days=1)),
            ("poker_mtt_weekly", int(getattr(self.settings, "poker_mtt_weekly_reward_pool_amount", 0) or 0), _week_bucket_start, timedelta(days=7)),
        ]
        all_results = await self.repo.list_poker_mtt_results()
        current = now.astimezone(timezone.utc).replace(microsecond=0)

        for lane, reward_pool_amount, bucket_fn, window_size in lane_configs:
            if reward_pool_amount <= 0:
                continue

            grouped_results: dict[datetime, list[dict]] = {}
            for result in all_results:
                if result.get("rated_or_practice") != "rated":
                    continue
                if result.get("human_only") is not True:
                    continue
                created_at = as_utc_datetime(result.get("created_at") or result.get("updated_at"))
                window_start = bucket_fn(created_at)
                window_end = window_start + window_size
                if window_end > current:
                    continue
                grouped_results.setdefault(window_start, []).append(result)

            for window_start, results in sorted(grouped_results.items()):
                provisional_count = sum(1 for result in results if result.get("evaluation_state") != "final")
                window_end = window_start + window_size
                watermark_at = window_end + timedelta(
                    seconds=int(getattr(self.settings, "poker_mtt_finalization_watermark_seconds", 0) or 0)
                )
                if provisional_count > 0 and current < watermark_at:
                    continue
                reward_window_id = _poker_mtt_reward_window_id(lane, window_start, window_end)
                existing_window = await self.repo.get_reward_window(reward_window_id)
                if existing_window and existing_window.get("settlement_batch_id"):
                    existing_batch = await self.repo.get_settlement_batch(existing_window["settlement_batch_id"])
                    if existing_batch and existing_batch.get("state") not in {None, "open"}:
                        continue

                await self.build_poker_mtt_reward_window(
                    lane=lane,
                    window_start_at=window_start,
                    window_end_at=window_end,
                    reward_pool_amount=reward_pool_amount,
                    include_provisional=provisional_count > 0,
                    policy_bundle_version=_default_poker_mtt_policy_bundle_version(self.settings, lane),
                    projection_metadata={
                        "completeness_mode": "watermark_release" if provisional_count > 0 else "all_final",
                        "provisional_result_count": provisional_count,
                        "watermark_at": isoformat_z(watermark_at),
                    },
                    reward_window_id=reward_window_id,
                    now=current,
                )

    async def _build_settlement_batches(self, now: datetime) -> None:
        reward_windows = await self.repo.list_reward_windows()
        for reward_window in reward_windows:
            settlement_batch_id = reward_window.get("settlement_batch_id") or "sb_" + reward_window["id"].removeprefix("rw_")
            existing_batch = await self.repo.get_settlement_batch(settlement_batch_id)

            if existing_batch:
                batch = existing_batch
                if existing_batch.get("state") == "open":
                    batch = await self.repo.save_settlement_batch(
                        {
                            **existing_batch,
                            "lane": reward_window["lane"],
                            "window_start_at": reward_window["window_start_at"],
                            "window_end_at": reward_window["window_end_at"],
                            "reward_window_ids": [reward_window["id"]],
                            "policy_bundle_version": reward_window.get("policy_bundle_version") or POLICY_BUNDLE_VERSION,
                            "task_count": reward_window.get("task_count", 0),
                            "miner_count": reward_window.get("miner_count", 0),
                            "total_reward_amount": reward_window.get("total_reward_amount", 0),
                            "updated_at": isoformat_z(now),
                        }
                    )
            else:
                batch = await self.repo.save_settlement_batch(
                    {
                        "id": settlement_batch_id,
                        "lane": reward_window["lane"],
                        "state": "open",
                        "window_start_at": reward_window["window_start_at"],
                        "window_end_at": reward_window["window_end_at"],
                        "reward_window_ids": [reward_window["id"]],
                        "policy_bundle_version": reward_window.get("policy_bundle_version") or POLICY_BUNDLE_VERSION,
                        "task_count": reward_window.get("task_count", 0),
                        "miner_count": reward_window.get("miner_count", 0),
                        "total_reward_amount": reward_window.get("total_reward_amount", 0),
                        "anchor_job_id": None,
                        "anchor_schema_version": None,
                        "canonical_root": None,
                        "anchor_payload_json": None,
                        "anchor_payload_hash": None,
                        "created_at": isoformat_z(now),
                        "updated_at": isoformat_z(now),
                    }
                )

            if reward_window.get("settlement_batch_id") != batch["id"]:
                saved_reward_window = await self.repo.save_reward_window(
                    _materialize_reward_window(
                        {
                            **reward_window,
                            "settlement_batch_id": batch["id"],
                            "updated_at": isoformat_z(now),
                        }
                    )[0]
                )
                await self._upsert_reward_window_artifact(saved_reward_window, now)

    async def get_artifact(self, artifact_id: str, *, now: datetime | None = None) -> dict:
        await self.reconcile(now)
        artifact = await self.repo.get_artifact(artifact_id)
        if not artifact:
            raise ValueError("artifact not found")
        return artifact

    async def _artifact_refs_for_entity(self, entity_type: str, entity_id: str) -> list[dict]:
        artifacts = await self.repo.list_artifacts_for_entity(entity_type, entity_id)
        return [
            {
                "artifact_id": artifact["id"],
                "kind": artifact["kind"],
                "payload_hash": artifact["payload_hash"],
            }
            for artifact in artifacts
        ]

    async def _ensure_task_pack_artifact(self, task: dict, now: datetime) -> dict:
        artifact_id = f"art:task_run:{task['task_run_id']}:pack"
        payload = {
            "task_run_id": task["task_run_id"],
            "lane": task["lane"],
            "asset": task["asset"],
            "pack_hash": task.get("pack_hash"),
            "pack_json": task.get("pack_json"),
        }
        return await self.repo.save_artifact(
            {
                "id": artifact_id,
                "kind": "task_pack",
                "entity_type": "task_run",
                "entity_id": task["task_run_id"],
                "payload_json": payload,
                "payload_hash": _hash_payload(payload),
                "created_at": isoformat_z(now),
                "updated_at": isoformat_z(now),
            }
        )

    async def _upsert_reward_window_artifact(self, reward_window: dict, now: datetime) -> dict:
        artifact_id = f"art:reward_window:{reward_window['id']}:membership"
        materialized_reward_window, payload = _materialize_reward_window(reward_window)
        return await self.repo.save_artifact(
            {
                "id": artifact_id,
                "kind": "reward_window_membership",
                "entity_type": "reward_window",
                "entity_id": materialized_reward_window["id"],
                "payload_json": payload,
                "payload_hash": materialized_reward_window["canonical_root"],
                "created_at": isoformat_z(now),
                "updated_at": isoformat_z(now),
            }
        )

    async def _upsert_poker_mtt_reward_window_projection_artifact(
        self,
        *,
        reward_window: dict,
        now: datetime,
        payload: dict,
    ) -> dict:
        artifact_id = f"art:reward_window:{reward_window['id']}:poker_mtt_projection"
        return await self.repo.save_artifact(
            {
                "id": artifact_id,
                "kind": "poker_mtt_reward_window_projection",
                "entity_type": "reward_window",
                "entity_id": reward_window["id"],
                "payload_json": payload,
                "payload_hash": _hash_payload(payload),
                "created_at": isoformat_z(now),
                "updated_at": isoformat_z(now),
            }
        )

    async def _upsert_settlement_anchor_artifact(self, settlement_batch: dict, now: datetime) -> dict:
        payload = settlement_batch.get("anchor_payload_json")
        if not payload:
            return {}
        artifact_id = f"art:settlement_batch:{settlement_batch['id']}:anchor"
        return await self.repo.save_artifact(
            {
                "id": artifact_id,
                "kind": "settlement_anchor_payload",
                "entity_type": "settlement_batch",
                "entity_id": settlement_batch["id"],
                "payload_json": payload,
                "payload_hash": settlement_batch["anchor_payload_hash"],
                "created_at": isoformat_z(now),
                "updated_at": isoformat_z(now),
            }
        )

    async def _apply_fast_task_participation(self, task: dict, submissions: list[dict], now: datetime) -> None:
        publish_at = parse_time(task["publish_at"])
        revealed_addresses = {submission["miner_address"] for submission in submissions if submission.get("p_yes_bps") is not None}
        tasks_by_id = {
            item["task_run_id"]: item
            for item in await self.repo.list_tasks()
            if item.get("lane") == "forecast_15m"
        }
        for miner in await self.repo.list_miners():
            if miner.get("status") != "active":
                continue
            created_at = as_utc_datetime(miner["created_at"])
            participated_in_bucket = False
            if created_at > publish_at:
                miner_submissions = await self.repo.list_submissions_for_miner(miner["address"])
                for miner_submission in miner_submissions:
                    if miner_submission.get("p_yes_bps") is None:
                        continue
                    submission_task = tasks_by_id.get(miner_submission["task_run_id"])
                    if not submission_task:
                        continue
                    if parse_time(submission_task["publish_at"]) == publish_at:
                        participated_in_bucket = True
                        break
            if created_at > publish_at and not participated_in_bucket:
                continue
            window_start, opportunities, misses = self._roll_fast_window(miner, publish_at)
            opportunities += 1
            if miner["address"] not in revealed_addresses:
                misses += 1
            await self.repo.update_miner(
                miner["address"],
                {
                    "fast_task_opportunities": opportunities,
                    "fast_task_misses": misses,
                    "fast_window_start_at": window_start,
                    "ops_reliability": self._compute_ops_reliability(
                        miner={
                            **miner,
                            "fast_task_opportunities": opportunities,
                            "fast_task_misses": misses,
                            "fast_window_start_at": window_start,
                        }
                    ),
                    "updated_at": now,
                },
            )

    async def _refresh_miner_cluster(
        self,
        *,
        miner_address: str,
        ip_address: str | None,
        user_agent: str | None,
        now: datetime,
    ) -> dict:
        miners = await self.repo.list_miners()
        current = next((miner for miner in miners if miner["address"] == miner_address), None)
        if not current:
            raise ValueError("miner not registered")

        updated_signal_hash = hash_user_agent(user_agent) or current.get("user_agent_hash")
        updated_ip = ip_address or current.get("ip_address")
        candidate_miners = []
        for miner in miners:
            if miner["address"] == miner_address:
                candidate_miners.append(
                    {
                        **miner,
                        "ip_address": updated_ip,
                        "user_agent_hash": updated_signal_hash,
                    }
                )
            else:
                candidate_miners.append(miner)

        component_map = compute_economic_unit_components(candidate_miners)
        for miner in candidate_miners:
            desired_eu = component_map.get(miner["address"], miner.get("economic_unit_id"))
            updates = {}
            if miner["address"] == miner_address:
                if updated_ip != current.get("ip_address"):
                    updates["ip_address"] = updated_ip
                if updated_signal_hash != current.get("user_agent_hash"):
                    updates["user_agent_hash"] = updated_signal_hash
            if desired_eu != miner.get("economic_unit_id"):
                updates["economic_unit_id"] = desired_eu
            if updates:
                updates["updated_at"] = now
                await self.repo.update_miner(miner["address"], updates)

        await self._sync_cluster_risk_cases(
            [
                {
                    **miner,
                    "economic_unit_id": component_map.get(miner["address"], miner.get("economic_unit_id")),
                    "ip_address": updated_ip if miner["address"] == miner_address else miner.get("ip_address"),
                    "user_agent_hash": updated_signal_hash if miner["address"] == miner_address else miner.get("user_agent_hash"),
                }
                for miner in candidate_miners
            ],
            now,
        )
        refreshed = await self.repo.get_miner(miner_address)
        return refreshed or current

    async def _open_risk_case_count(self, miner: dict) -> int:
        cases = await self.repo.list_risk_cases(state="open", economic_unit_id=miner["economic_unit_id"])
        return len(cases)

    async def _latest_settlement_snapshot(self, miner_address: str) -> tuple[dict | None, dict | None, dict | None]:
        submissions = await self.repo.list_submissions_for_miner(miner_address)
        reward_window_ids = {
            submission.get("reward_window_id")
            for submission in submissions
            if submission.get("reward_window_id")
        }
        reward_windows = await self.repo.list_reward_windows()
        latest_reward_window = next(
            (window for window in reward_windows if window["id"] in reward_window_ids),
            None,
        )
        latest_settlement_batch = None
        latest_anchor_job = None
        if latest_reward_window and latest_reward_window.get("settlement_batch_id"):
            latest_settlement_batch = await self.repo.get_settlement_batch(latest_reward_window["settlement_batch_id"])
        if latest_settlement_batch and latest_settlement_batch.get("anchor_job_id"):
            latest_anchor_job = await self.repo.get_anchor_job(latest_settlement_batch["anchor_job_id"])
        return latest_reward_window, latest_settlement_batch, latest_anchor_job

    async def _sync_cluster_risk_cases(self, miners: list[dict], now: datetime) -> None:
        clusters: dict[str, list[dict]] = {}
        for miner in miners:
            economic_unit_id = miner.get("economic_unit_id")
            if not economic_unit_id:
                continue
            clusters.setdefault(economic_unit_id, []).append(miner)

        for economic_unit_id, members in clusters.items():
            if len(members) <= 1:
                continue
            case_id = f"risk:cluster:{economic_unit_id}"
            existing_case = await self.repo.get_risk_case(case_id)
            if existing_case and existing_case.get("state") != "open":
                continue
            member_addresses = sorted(member["address"] for member in members)
            evidence_types = []
            if any(member.get("ip_address") for member in members):
                evidence_types.append("ip_address")
            if any(member.get("user_agent_hash") for member in members):
                evidence_types.append("user_agent_hash")
            await self.repo.save_risk_case(
                {
                    "id": case_id,
                    "case_type": "economic_unit_cluster",
                    "severity": "medium",
                    "state": "open",
                    "economic_unit_id": economic_unit_id,
                    "miner_address": member_addresses[0],
                    "task_run_id": None,
                    "submission_id": None,
                    "evidence_json": {
                        "member_addresses": member_addresses,
                        "member_count": len(member_addresses),
                        "evidence_types": evidence_types,
                    },
                    "created_at": isoformat_z(now),
                    "updated_at": isoformat_z(now),
                }
            )

    async def _open_duplicate_reveal_case(
        self,
        *,
        task_run_id: str,
        submission_id: str,
        economic_unit_id: str,
        miner_addresses: list[str],
        now: datetime,
        miner_address: str,
    ) -> None:
        case_id = f"risk:duplicate:{task_run_id}:{economic_unit_id}"
        existing_case = await self.repo.get_risk_case(case_id)
        if existing_case and existing_case.get("state") != "open":
            return
        await self.repo.save_risk_case(
            {
                "id": case_id,
                "case_type": "economic_unit_duplicate",
                "severity": "high",
                "state": "open",
                "economic_unit_id": economic_unit_id,
                "miner_address": miner_address,
                "task_run_id": task_run_id,
                "submission_id": submission_id,
                "evidence_json": {
                    "miner_addresses": sorted(miner_addresses),
                    "duplicate_count": len(miner_addresses),
                    "reason": "same economic unit submitted multiple reveals for one task",
                },
                "created_at": isoformat_z(now),
                "updated_at": isoformat_z(now),
            }
        )

    def _split_reward_by_admission(self, miner: dict, reward_amount: int, now: datetime) -> tuple[int, int, str]:
        admission_state = self._admission_state(miner, now)
        release_ratio = 1.0 if admission_state == "mature" else self.settings.admission_release_bps / 10_000
        released_reward = int(round(reward_amount * release_ratio))
        held_reward = reward_amount - released_reward
        return released_reward, held_reward, admission_state

    def _admission_state(self, miner: dict, now: datetime) -> str:
        created_at = as_utc_datetime(miner["created_at"])
        age_hours = max(0.0, (now - created_at).total_seconds() / 3600)
        if age_hours >= self.settings.admission_mature_age_hours:
            return "mature"
        if miner.get("forecast_reveals", 0) >= self.settings.admission_mature_fast_reveals:
            return "mature"
        return "probation"

    def _admission_release_ratio(self, miner: dict, now: datetime) -> float:
        return 1.0 if self._admission_state(miner, now) == "mature" else self.settings.admission_release_bps / 10_000

    def _daily_anchor_multiplier(self, p_yes_bps: int, outcome: int) -> float:
        max_distance = max(1, self.settings.max_p_yes_bps - 5000)
        confidence = clamp(abs(p_yes_bps - 5000) / max_distance, 0.0, 1.0)
        correct = (p_yes_bps >= 5000) == bool(outcome)
        signed = confidence if correct else -confidence
        return round(clamp(1.0 + signed * 0.015, 0.985, 1.015), 6)

    def _roll_fast_window(self, miner: dict, now: datetime) -> tuple[str, int, int]:
        window_start_raw = miner.get("fast_window_start_at") or miner.get("created_at")
        window_start = as_utc_datetime(window_start_raw)
        if (now - window_start) >= timedelta(days=1):
            return isoformat_z(now), 0, 0
        return isoformat_z(window_start), miner.get("fast_task_opportunities", 0), miner.get("fast_task_misses", 0)

    def _compute_ops_reliability(self, miner: dict) -> float:
        commit_count = miner.get("forecast_commits", 0)
        reveal_count = miner.get("forecast_reveals", 0)
        if commit_count > 0:
            reveal_discipline = clamp(0.95 + (reveal_count / commit_count) * 0.05, 0.95, 1.05)
        else:
            reveal_discipline = 1.0
        opportunities = miner.get("fast_task_opportunities", 0)
        misses = miner.get("fast_task_misses", 0)
        if opportunities <= 0:
            participation_factor = 1.0
        else:
            miss_ratio = misses / opportunities
            if miss_ratio <= self.settings.free_skip_ratio:
                participation_factor = 1.05
            else:
                overage = (miss_ratio - self.settings.free_skip_ratio) / max(1e-9, 1.0 - self.settings.free_skip_ratio)
                participation_factor = clamp(1.05 - (overage * 0.20), 0.95, 1.05)
        return round(min(reveal_discipline, participation_factor), 6)

    async def _refresh_public_ranks(self) -> None:
        miners = await self.repo.list_miners()
        ordered = sorted(
            miners,
            key=lambda miner: (
                miner["total_rewards"],
                miner["edge_score_total"],
                miner["correct_direction_count"],
            ),
            reverse=True,
        )
        for index, miner in enumerate(ordered, start=1):
            settled_tasks = max(1, miner["settled_tasks"])
            avg_edge = miner["edge_score_total"] / settled_tasks
            public_elo = 1200 + int(avg_edge * 800) + min(miner["settled_tasks"], 100)
            await self.repo.update_miner(
                miner["address"],
                {
                    "public_rank": index,
                    "public_elo": max(900, min(1800, public_elo)),
                },
            )

    def _task_card(self, task: dict) -> dict:
        return {
            "task_run_id": task["task_run_id"],
            "lane": task["lane"],
            "asset": task["asset"],
            "publish_at": task["publish_at"],
            "commit_deadline": task["commit_deadline"],
            "reveal_deadline": task["reveal_deadline"],
            "resolve_at": task["resolve_at"],
            "pack_hash": task["pack_hash"],
            "snapshot_health": task["snapshot_health"],
        }
