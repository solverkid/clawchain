from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime
from typing import Any

import httpx

import forecast_engine


POLYMARKET_SERIES_CONFIG = {
    "BTCUSDT": {
        "series_slug": "btc-up-or-down-5m",
        "slug_prefix": "btc-updown-5m-",
        "slug_template": "btc-updown-5m-{bucket_ts}",
        "bucket_seconds": 300,
        "positive_outcome": "Up",
    },
    "BTC": {
        "series_slug": "btc-up-or-down-5m",
        "slug_prefix": "btc-updown-5m-",
        "slug_template": "btc-updown-5m-{bucket_ts}",
        "bucket_seconds": 300,
        "positive_outcome": "Up",
    },
    "ETHUSDT": {
        "series_slug": "eth-up-or-down-5m",
        "slug_prefix": "eth-updown-5m-",
        "slug_template": "eth-updown-5m-{bucket_ts}",
        "bucket_seconds": 300,
        "positive_outcome": "Up",
    },
    "ETH": {
        "series_slug": "eth-up-or-down-5m",
        "slug_prefix": "eth-updown-5m-",
        "slug_template": "eth-updown-5m-{bucket_ts}",
        "bucket_seconds": 300,
        "positive_outcome": "Up",
    },
}


class MarketDataUnavailable(RuntimeError):
    pass


def _hash_pack(pack: dict[str, Any]) -> str:
    payload = json.dumps(pack, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _asset_keywords(asset: str) -> tuple[list[re.Pattern[str]], list[re.Pattern[str]]]:
    if asset.startswith("BTC"):
        return (
            [re.compile(r"\bbitcoin\b", re.IGNORECASE), re.compile(r"\bbtc\b", re.IGNORECASE)],
            [],
        )
    if asset.startswith("ETH"):
        return (
            [
                re.compile(r"\bethereum\b", re.IGNORECASE),
                re.compile(r"\bether\b", re.IGNORECASE),
                re.compile(r"\beth\b", re.IGNORECASE),
            ],
            [re.compile(r"\bmegaeth\b", re.IGNORECASE)],
        )
    return ([re.compile(re.escape(asset), re.IGNORECASE)], [])


def _safe_json_loads(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _price_mid(bid: float, ask: float) -> float:
    return round((bid + ask) / 2, 2)


def _book_notional(levels: list[list[str]] | list[dict[str, Any]]) -> float:
    total = 0.0
    for level in levels:
        if isinstance(level, dict):
            price = _float(level.get("price"))
            size = _float(level.get("size"))
        else:
            price = _float(level[0] if len(level) > 0 else 0.0)
            size = _float(level[1] if len(level) > 1 else 0.0)
        total += price * size
    return total


def _imbalance_bps(left: float, right: float) -> int:
    total = left + right
    if total <= 0:
        return 0
    return int(round(((left - right) / total) * 10_000))


def _binance_probability(depth_imbalance_bps: int, trade_imbalance_bps: int, micro_move_bps: float) -> int:
    normalized = forecast_engine.clamp(
        (depth_imbalance_bps * 0.00004) + (trade_imbalance_bps * 0.00003) + (micro_move_bps * 0.01),
        -0.06,
        0.06,
    )
    return int(round(5000 + normalized * 10_000))


def _select_polymarket_market(markets: list[dict[str, Any]], asset: str) -> dict[str, Any]:
    required, rejected = _asset_keywords(asset)
    candidates = []
    for market in markets:
        if not market.get("enableOrderBook") or not market.get("acceptingOrders"):
            continue
        haystack = " ".join(
            str(market.get(field, "")) for field in ("question", "slug", "description", "groupItemTitle")
        )
        if not any(pattern.search(haystack) for pattern in required):
            continue
        if any(pattern.search(haystack) for pattern in rejected):
            continue
        token_ids = _safe_json_loads(market.get("clobTokenIds"))
        outcomes = _safe_json_loads(market.get("outcomes"))
        if not isinstance(token_ids, list) or len(token_ids) < 2:
            continue
        if not isinstance(outcomes, list) or "Yes" not in outcomes:
            continue
        candidates.append(market)

    if not candidates:
        raise MarketDataUnavailable(f"no suitable Polymarket market for {asset}")

    candidates.sort(
        key=lambda market: (
            _float(market.get("volume24hrClob")),
            _float(market.get("liquidityClob")),
            _float(market.get("volumeClob")),
        ),
        reverse=True,
    )
    return candidates[0]


def _market_series_slug(market: dict[str, Any]) -> str | None:
    if market.get("seriesSlug"):
        return str(market["seriesSlug"])
    for event in market.get("events", []) or []:
        if event.get("seriesSlug"):
            return str(event["seriesSlug"])
        for series in event.get("series", []) or []:
            if series.get("slug"):
                return str(series["slug"])
    return None


def _parse_market_end_date(market: dict[str, Any]) -> datetime | None:
    end_date = market.get("endDate")
    if not end_date:
        return None
    try:
        return datetime.fromisoformat(str(end_date).replace("Z", "+00:00"))
    except ValueError:
        return None


def _bucket_timestamp(now: datetime, seconds: int) -> int:
    ts = int(now.timestamp())
    return ts - (ts % seconds)


def _extract_resolved_outcome(market: dict[str, Any], positive_outcome: str) -> int | None:
    if not market.get("closed"):
        return None
    resolution_status = market.get("umaResolutionStatus")
    if resolution_status and str(resolution_status).lower() != "resolved":
        return None

    outcomes = _safe_json_loads(market.get("outcomes"))
    outcome_prices = _safe_json_loads(market.get("outcomePrices"))
    if not isinstance(outcomes, list) or not isinstance(outcome_prices, list) or len(outcomes) != len(outcome_prices):
        return None

    try:
        positive_index = outcomes.index(positive_outcome)
    except ValueError:
        return None

    parsed_prices = [_float(price, default=-1.0) for price in outcome_prices]
    if positive_index >= len(parsed_prices):
        return None
    positive_price = parsed_prices[positive_index]
    if positive_price == 1.0:
        return 1
    if positive_price == 0.0:
        return 0
    return None


def _classify_snapshot_state(settings, freshness: dict[str, int | None] | None) -> tuple[str, str, str | None]:
    freshness = freshness or {}
    binance_age = freshness.get("binance")
    polymarket_age = freshness.get("polymarket")
    if (
        binance_age is not None
        and binance_age > getattr(settings, "max_binance_snapshot_freshness_seconds", 30)
    ):
        return "degraded", "degraded", "binance_snapshot_stale"
    if (
        polymarket_age is not None
        and polymarket_age > getattr(settings, "max_polymarket_snapshot_freshness_seconds", 30)
    ):
        return "degraded", "degraded", "polymarket_snapshot_stale"
    return "live", "reward_eligible", None


def _select_series_market(markets: list[dict[str, Any]], asset: str, now: datetime) -> dict[str, Any] | None:
    config = POLYMARKET_SERIES_CONFIG.get(asset)
    if not config:
        return None

    future_candidates = []
    recent_candidates = []
    for market in markets:
        if not market.get("enableOrderBook") or not market.get("acceptingOrders"):
            continue
        series_slug = _market_series_slug(market)
        slug = str(market.get("slug", ""))
        if series_slug != config["series_slug"] and not slug.startswith(config["slug_prefix"]):
            continue
        end_date = _parse_market_end_date(market)
        if end_date is None:
            continue
        if end_date > now:
            future_candidates.append((end_date, market))
        elif (now - end_date).total_seconds() <= 900:
            recent_candidates.append((abs((end_date - now).total_seconds()), market))

    if future_candidates:
        future_candidates.sort(
            key=lambda item: (
                item[0],
                -_float(item[1].get("volume24hrClob")),
                -_float(item[1].get("liquidityClob")),
            )
        )
        return future_candidates[0][1]

    if not recent_candidates:
        return None

    recent_candidates.sort(
        key=lambda item: (
            item[0],
            -_float(item[1].get("volume24hrClob")),
            -_float(item[1].get("liquidityClob")),
        )
    )
    return recent_candidates[0][1]


class SyntheticMarketDataProvider:
    async def build_fast_task(self, now: datetime, settings, asset: str) -> dict:
        task = forecast_engine.build_fast_task(now, settings=settings, asset=asset)
        task["pack_json"]["fallback_reason"] = None
        task["pack_hash"] = _hash_pack(task["pack_json"])
        return task

    async def resolve_fast_task(self, task: dict) -> dict:
        return forecast_engine.resolve_fast_task(task)

    async def aclose(self) -> None:
        return None


class LiveMarketDataProvider:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 8.0,
        binance_base_url: str = "https://api.binance.com",
        polymarket_gamma_url: str = "https://gamma-api.polymarket.com",
        polymarket_clob_url: str = "https://clob.polymarket.com",
    ):
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._binance_base_url = binance_base_url.rstrip("/")
        self._polymarket_gamma_url = polymarket_gamma_url.rstrip("/")
        self._polymarket_clob_url = polymarket_clob_url.rstrip("/")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def build_fast_task(self, now: datetime, settings, asset: str) -> dict:
        base_task = forecast_engine.build_fast_task(now, settings=settings, asset=asset)
        market_bundle = await self._fetch_market_bundle(asset, settings, now)
        snapshot_freshness_seconds = market_bundle.get("snapshot_freshness_seconds", {"binance": 0, "polymarket": 0})
        snapshot_health, task_state, degraded_reason = _classify_snapshot_state(settings, snapshot_freshness_seconds)

        pack = {
            "asset": asset,
            "lane": "forecast_15m",
            **forecast_engine.snapshot_metadata(
                snapshot_source="live",
                frozen_at=now,
                binance_freshness_seconds=snapshot_freshness_seconds.get("binance"),
                polymarket_freshness_seconds=snapshot_freshness_seconds.get("polymarket"),
            ),
            "polymarket_snapshot": market_bundle["polymarket_snapshot"],
            "binance_snapshot": market_bundle["binance_snapshot"],
            "market_context": market_bundle["market_context"],
            "noisy_fragments": market_bundle["noisy_fragments"],
        }

        base_task.update(
            {
                "baseline_q_bps": market_bundle["baseline_q_bps"],
                "baseline_method": (
                    f"q_pm_{int(settings.baseline_pm_weight * 100)}_q_bin_{int(settings.baseline_bin_weight * 100)}"
                ),
                "snapshot_health": snapshot_health,
                "task_state": task_state,
                "degraded_reason": degraded_reason,
                "void_reason": None,
                "pack_hash": _hash_pack(pack),
                "pack_json": pack,
                "commit_close_ref_price": market_bundle["commit_close_ref_price"],
            }
        )
        return base_task

    async def resolve_fast_task(self, task: dict) -> dict:
        polymarket_snapshot = task.get("pack_json", {}).get("polymarket_snapshot", {})
        resolution = await self._get_polymarket_resolution(
            slug=polymarket_snapshot.get("slug"),
            positive_outcome=polymarket_snapshot.get("positive_outcome", "Up"),
        )
        if resolution["resolution_status"] == "resolved":
            return {
                "commit_close_ref_price": _float(task.get("commit_close_ref_price")),
                "end_ref_price": None,
                "outcome": resolution["outcome"],
                "resolution_status": "resolved",
                "resolution_method": "polymarket_gamma",
            }
        return {
            "commit_close_ref_price": _float(task.get("commit_close_ref_price")),
            "end_ref_price": None,
            "outcome": None,
            "resolution_status": "pending",
            "resolution_method": resolution.get("resolution_method", "polymarket_gamma_pending"),
        }

    async def _fetch_market_bundle(self, asset: str, settings, now: datetime) -> dict[str, Any]:
        binance_task = asyncio.create_task(self._fetch_binance_snapshot(asset, settings))
        polymarket_task = asyncio.create_task(self._fetch_polymarket_snapshot(asset, now))
        binance_snapshot, polymarket_snapshot = await asyncio.gather(binance_task, polymarket_task)
        baseline_q_bps = forecast_engine.clamp_bps(
            int(
                round(
                    (polymarket_snapshot["q_yes_bps"] * settings.baseline_pm_weight)
                    + (binance_snapshot["q_yes_bps"] * settings.baseline_bin_weight)
                )
            ),
            settings,
        )
        market_context = (
            f"{asset} 15m live pack. Binance order book shows {binance_snapshot['depth_imbalance_bps']} bps depth "
            f"imbalance and {binance_snapshot['trade_imbalance_bps']} bps recent trade pressure. "
            f"Polymarket anchor is '{polymarket_snapshot['question']}' with midpoint {polymarket_snapshot['q_yes_bps']} bps."
        )
        noisy_fragments = [
            json.dumps(
                {
                    "symbl": asset,
                    "mid_prce": binance_snapshot["mid_price"],
                    "depth_imbalnce_bps": binance_snapshot["depth_imbalance_bps"],
                },
                separators=(",", ":"),
            ),
            json.dumps(
                {
                    "pm_mrket": polymarket_snapshot["slug"],
                    "yes_mdpnt_bps": polymarket_snapshot["q_yes_bps"],
                    "vol24rh": polymarket_snapshot["volume24hr_clob"],
                },
                separators=(",", ":"),
            ),
        ]
        return {
            "baseline_q_bps": baseline_q_bps,
            "commit_close_ref_price": binance_snapshot["mid_price"],
            "market_context": market_context,
            "noisy_fragments": noisy_fragments,
            "binance_snapshot": binance_snapshot,
            "polymarket_snapshot": polymarket_snapshot,
            "snapshot_freshness_seconds": {"binance": 0, "polymarket": 0},
        }

    async def _fetch_binance_snapshot(self, asset: str, settings) -> dict[str, Any]:
        depth_task = asyncio.create_task(
            self._get_json(f"{self._binance_base_url}/api/v3/depth", params={"symbol": asset, "limit": 5})
        )
        book_task = asyncio.create_task(
            self._get_json(f"{self._binance_base_url}/api/v3/ticker/bookTicker", params={"symbol": asset})
        )
        trades_task = asyncio.create_task(
            self._get_json(f"{self._binance_base_url}/api/v3/trades", params={"symbol": asset, "limit": 20})
        )
        depth, book_ticker, trades = await asyncio.gather(depth_task, book_task, trades_task)

        best_bid = _float(book_ticker.get("bidPrice"))
        best_ask = _float(book_ticker.get("askPrice"))
        bid_qty = _float(book_ticker.get("bidQty"))
        ask_qty = _float(book_ticker.get("askQty"))
        mid_price = _price_mid(best_bid, best_ask)
        micro_price = round(((best_ask * bid_qty) + (best_bid * ask_qty)) / max(bid_qty + ask_qty, 1e-9), 4)
        micro_move_bps = round(((micro_price - mid_price) / max(mid_price, 1e-9)) * 10_000, 4)

        bid_notional = _book_notional(depth.get("bids", []))
        ask_notional = _book_notional(depth.get("asks", []))
        depth_imbalance_bps = _imbalance_bps(bid_notional, ask_notional)

        aggressive_buy = 0.0
        aggressive_sell = 0.0
        for trade in trades:
            notional = _float(trade.get("price")) * _float(trade.get("qty"))
            if trade.get("isBuyerMaker"):
                aggressive_sell += notional
            else:
                aggressive_buy += notional
        trade_imbalance_bps = _imbalance_bps(aggressive_buy, aggressive_sell)
        q_yes_bps = forecast_engine.clamp_bps(
            _binance_probability(depth_imbalance_bps, trade_imbalance_bps, micro_move_bps),
            settings,
        )

        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "bid_qty": bid_qty,
            "ask_qty": ask_qty,
            "mid_price": mid_price,
            "micro_price": micro_price,
            "micro_move_bps": micro_move_bps,
            "depth_imbalance_bps": depth_imbalance_bps,
            "trade_imbalance_bps": trade_imbalance_bps,
            "top_bid_notional": round(bid_notional, 2),
            "top_ask_notional": round(ask_notional, 2),
            "q_yes_bps": q_yes_bps,
        }

    async def _fetch_polymarket_snapshot(self, asset: str, now: datetime) -> dict[str, Any]:
        market = await self._get_direct_series_market(asset, now)
        if market is None:
            markets = await self._get_json(
                f"{self._polymarket_gamma_url}/markets",
                params={"active": "true", "closed": "false", "limit": 200},
            )
            if not isinstance(markets, list):
                raise MarketDataUnavailable("Polymarket markets response was not a list")
            market = _select_series_market(markets, asset, now) or _select_polymarket_market(markets, asset)
        token_ids = _safe_json_loads(market.get("clobTokenIds"))
        outcomes = _safe_json_loads(market.get("outcomes"))
        positive_outcome = POLYMARKET_SERIES_CONFIG.get(asset, {}).get("positive_outcome", "Yes")
        if positive_outcome not in outcomes:
            positive_outcome = "Yes" if "Yes" in outcomes else outcomes[0]
        positive_index = outcomes.index(positive_outcome)
        positive_token_id = token_ids[positive_index]
        primary_event = (market.get("events") or [{}])[0]

        book_task = asyncio.create_task(
            self._get_json(f"{self._polymarket_clob_url}/book", params={"token_id": positive_token_id})
        )
        midpoint_task = asyncio.create_task(
            self._get_json(f"{self._polymarket_clob_url}/midpoint", params={"token_id": positive_token_id})
        )
        book, midpoint = await asyncio.gather(book_task, midpoint_task)

        q_yes = _float(midpoint.get("mid"))
        if q_yes <= 0:
            q_yes = (_float(market.get("bestBid")) + _float(market.get("bestAsk"))) / 2
        q_yes_bps = int(round(q_yes * 10_000))

        bids = book.get("bids", [])
        asks = book.get("asks", [])
        top_bid = _float((bids[0] or {}).get("price") if bids else market.get("bestBid"))
        top_ask = _float((asks[0] or {}).get("price") if asks else market.get("bestAsk"))
        top_bid_size = _float((bids[0] or {}).get("size") if bids else 0.0)
        top_ask_size = _float((asks[0] or {}).get("size") if asks else 0.0)
        spread_bps = 0.0
        if top_bid > 0 and top_ask > 0:
            spread_bps = round(((top_ask - top_bid) / ((top_ask + top_bid) / 2)) * 10_000, 2)

        return {
            "market_id": market.get("id"),
            "question": market["question"],
            "slug": market["slug"],
            "series_slug": _market_series_slug(market),
            "event_id": primary_event.get("id"),
            "event_slug": primary_event.get("slug"),
            "event_start_time": market.get("eventStartTime") or primary_event.get("startTime") or market.get("startDate"),
            "end_date": market.get("endDate"),
            "condition_id": market.get("conditionId"),
            "positive_outcome": positive_outcome,
            "outcomes": outcomes,
            "yes_token_id": positive_token_id,
            "q_yes_bps": q_yes_bps,
            "best_bid": top_bid,
            "best_ask": top_ask,
            "best_bid_size": top_bid_size,
            "best_ask_size": top_ask_size,
            "spread_bps": spread_bps,
            "volume24hr_clob": round(_float(market.get("volume24hrClob")), 2),
            "liquidity_clob": round(_float(market.get("liquidityClob")), 2),
            "last_trade_price": _float(market.get("lastTradePrice")),
        }

    async def _get_direct_series_market(self, asset: str, now: datetime) -> dict[str, Any] | None:
        config = POLYMARKET_SERIES_CONFIG.get(asset)
        if not config or not config.get("slug_template"):
            return None
        bucket_ts = _bucket_timestamp(now, int(config.get("bucket_seconds", 300)))
        slug = str(config["slug_template"]).format(bucket_ts=bucket_ts)
        try:
            market = await self._get_json(f"{self._polymarket_gamma_url}/markets/slug/{slug}", params=None)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return market if isinstance(market, dict) else None

    async def _get_polymarket_resolution(self, slug: str | None, positive_outcome: str) -> dict[str, Any]:
        if not slug:
            return {"resolution_status": "pending", "outcome": None, "resolution_method": "missing_slug"}
        try:
            market = await self._get_json(f"{self._polymarket_gamma_url}/markets/slug/{slug}", params=None)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {"resolution_status": "pending", "outcome": None, "resolution_method": "slug_not_found"}
            raise
        if not isinstance(market, dict):
            return {"resolution_status": "pending", "outcome": None, "resolution_method": "invalid_market_payload"}
        outcome = _extract_resolved_outcome(market, positive_outcome)
        if outcome is None:
            return {"resolution_status": "pending", "outcome": None, "resolution_method": "polymarket_gamma_pending"}
        return {"resolution_status": "resolved", "outcome": outcome, "resolution_method": "polymarket_gamma"}

    async def _get_json(self, url: str, params: dict[str, Any] | None) -> Any:
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()


class HybridMarketDataProvider:
    def __init__(self, *, live: LiveMarketDataProvider, fallback: SyntheticMarketDataProvider | None = None):
        self._live = live
        self._fallback = fallback or SyntheticMarketDataProvider()

    async def build_fast_task(self, now: datetime, settings, asset: str) -> dict:
        try:
            return await self._live.build_fast_task(now, settings, asset)
        except Exception as exc:
            task = await self._fallback.build_fast_task(now, settings, asset)
            task["snapshot_health"] = "synthetic_fallback"
            task["task_state"] = "degraded"
            task["degraded_reason"] = "live_market_data_unavailable"
            task["void_reason"] = None
            task["pack_json"]["snapshot_source"] = "synthetic_fallback"
            task["pack_json"]["fallback_reason"] = str(exc)
            task["pack_hash"] = _hash_pack(task["pack_json"])
            return task

    async def resolve_fast_task(self, task: dict) -> dict:
        if task.get("pack_json", {}).get("snapshot_source") == "synthetic_fallback":
            return await self._fallback.resolve_fast_task(task)
        try:
            return await self._live.resolve_fast_task(task)
        except Exception as exc:
            return {
                "commit_close_ref_price": _float(task.get("commit_close_ref_price")),
                "end_ref_price": None,
                "outcome": None,
                "resolution_status": "pending",
                "resolution_method": "live_resolution_error",
                "resolution_error": str(exc),
            }

    async def aclose(self) -> None:
        await self._live.aclose()
