from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
MINING_SERVICE_DIR = ROOT / "mining-service"
if str(MINING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(MINING_SERVICE_DIR))

import forecast_engine
import market_data


class FailingLiveProvider:
    async def build_fast_task(self, now, settings, asset):  # noqa: ANN001
        raise RuntimeError("live feed unavailable")

    async def resolve_fast_task(self, task):  # noqa: ANN001
        raise RuntimeError("live resolution unavailable")

    async def aclose(self) -> None:
        return None


def test_hybrid_market_data_provider_falls_back_to_synthetic():
    settings = forecast_engine.ForecastSettings()
    provider = market_data.HybridMarketDataProvider(
        live=FailingLiveProvider(),
        fallback=market_data.SyntheticMarketDataProvider(),
    )

    task = asyncio.run(
        provider.build_fast_task(
            datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc),
            settings,
            "BTCUSDT",
        )
    )

    assert task["snapshot_health"] == "synthetic_fallback"
    assert task["pack_json"]["snapshot_source"] == "synthetic_fallback"
    assert "fallback_reason" in task["pack_json"]
    assert task["task_state"] == "degraded"
    assert task["degraded_reason"] == "live_market_data_unavailable"


def test_hybrid_market_data_provider_times_out_to_synthetic_fallback():
    class SlowLiveProvider:
        async def build_fast_task(self, now, settings, asset, *, publish_at=None, generated_at=None):  # noqa: ANN001
            await asyncio.sleep(0.05)
            raise AssertionError("timeout should have fired before live task completed")

        async def resolve_fast_task(self, task):  # noqa: ANN001
            raise RuntimeError("live resolution unavailable")

        async def aclose(self) -> None:
            return None

    settings = forecast_engine.ForecastSettings(fast_task_live_build_timeout_seconds=0.001)
    provider = market_data.HybridMarketDataProvider(
        live=SlowLiveProvider(),
        fallback=market_data.SyntheticMarketDataProvider(),
    )

    task = asyncio.run(
        provider.build_fast_task(
            datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc),
            settings,
            "BTCUSDT",
        )
    )

    assert task["snapshot_health"] == "synthetic_fallback"
    assert task["pack_json"]["snapshot_source"] == "synthetic_fallback"
    assert task["pack_json"]["fallback_reason"].startswith("fast_task_live_build_timeout:")


def test_live_market_data_provider_builds_task_from_market_snapshots():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        query = dict(request.url.params)

        if request.url.host == "api.binance.com" and path == "/api/v3/depth":
            return httpx.Response(
                200,
                json={
                    "lastUpdateId": 1,
                    "bids": [["70000.0", "2.0"], ["69999.0", "1.0"]],
                    "asks": [["70001.0", "1.0"], ["70002.0", "2.0"]],
                },
            )
        if request.url.host == "api.binance.com" and path == "/api/v3/ticker/bookTicker":
            return httpx.Response(
                200,
                json={
                    "symbol": query["symbol"],
                    "bidPrice": "70000.0",
                    "bidQty": "2.0",
                    "askPrice": "70001.0",
                    "askQty": "1.0",
                },
            )
        if request.url.host == "api.binance.com" and path == "/api/v3/trades":
            return httpx.Response(
                200,
                json=[
                    {"price": "70001.0", "qty": "0.5", "isBuyerMaker": False},
                    {"price": "70000.5", "qty": "0.4", "isBuyerMaker": False},
                    {"price": "70000.0", "qty": "0.6", "isBuyerMaker": True},
                ],
            )
        if request.url.host == "gamma-api.polymarket.com" and path.startswith("/markets/slug/btc-updown-5m-"):
            return httpx.Response(
                200,
                json={
                    "id": "market-btc-5m",
                    "question": "Bitcoin Up or Down - April 10, 9:00AM-9:05AM UTC",
                    "slug": request.url.path.split("/")[-1],
                    "description": "Polymarket 5m up/down market.",
                    "enableOrderBook": True,
                    "acceptingOrders": True,
                    "volume24hrClob": 35018.48,
                    "liquidityClob": 14559.25,
                    "volumeClob": 35018.48,
                    "bestBid": 0.5,
                    "bestAsk": 0.51,
                    "lastTradePrice": 0.51,
                    "conditionId": "cond-btc-5m",
                    "clobTokenIds": json.dumps(["token_up", "token_down"]),
                    "outcomes": json.dumps(["Up", "Down"]),
                    "eventStartTime": "2026-04-10T09:00:00Z",
                    "endDate": "2026-04-10T09:05:00Z",
                    "events": [
                        {
                            "id": "event-btc-5m",
                            "slug": request.url.path.split("/")[-1],
                            "seriesSlug": "btc-up-or-down-5m",
                        }
                    ],
                },
            )
        if request.url.host == "gamma-api.polymarket.com" and path == "/markets":
            raise AssertionError("BTC 5m discovery should use /markets/slug/*, not list scanning")
        if request.url.host == "clob.polymarket.com" and path == "/midpoint":
            if query["token_id"] == "token_up":
                return httpx.Response(200, json={"mid": "0.505"})
            return httpx.Response(200, json={"mid": "0.4885"})
        if request.url.host == "clob.polymarket.com" and path == "/book":
            if query["token_id"] == "token_up":
                return httpx.Response(
                    200,
                    json={
                        "bids": [{"price": "0.50", "size": "1500"}, {"price": "0.49", "size": "1200"}],
                        "asks": [{"price": "0.51", "size": "1600"}, {"price": "0.52", "size": "1100"}],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "bids": [{"price": "0.488", "size": "1000"}, {"price": "0.487", "size": "900"}],
                    "asks": [{"price": "0.489", "size": "1200"}, {"price": "0.490", "size": "800"}],
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = market_data.LiveMarketDataProvider(client=client)
    settings = forecast_engine.ForecastSettings(
        baseline_pm_weight=0.7,
        baseline_bin_weight=0.3,
    )

    task = asyncio.run(
        provider.build_fast_task(
            datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc),
            settings,
            "BTCUSDT",
        )
    )
    asyncio.run(provider.aclose())

    assert task["snapshot_health"] == "live"
    assert task["commit_close_ref_price"] == 70000.5
    assert task["baseline_q_bps"] > 0
    assert task["pack_json"]["snapshot_source"] == "live"
    assert task["pack_json"]["polymarket_snapshot"]["slug"].startswith("btc-updown-5m-")
    assert task["pack_json"]["polymarket_snapshot"]["series_slug"] == "btc-up-or-down-5m"
    assert task["pack_json"]["binance_snapshot"]["best_bid"] == 70000.0


def test_live_market_data_provider_freezes_snapshot_metadata():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        query = dict(request.url.params)

        if request.url.host == "api.binance.com" and path == "/api/v3/depth":
            return httpx.Response(200, json={"lastUpdateId": 1, "bids": [["70000.0", "2.0"]], "asks": [["70001.0", "1.0"]]})
        if request.url.host == "api.binance.com" and path == "/api/v3/ticker/bookTicker":
            return httpx.Response(
                200,
                json={"symbol": query["symbol"], "bidPrice": "70000.0", "bidQty": "2.0", "askPrice": "70001.0", "askQty": "1.0"},
            )
        if request.url.host == "api.binance.com" and path == "/api/v3/trades":
            return httpx.Response(200, json=[{"price": "70001.0", "qty": "0.5", "isBuyerMaker": False}])
        if request.url.host == "gamma-api.polymarket.com" and path.startswith("/markets/slug/btc-updown-5m-"):
            return httpx.Response(
                200,
                json={
                    "id": "market-btc-5m",
                    "question": "Bitcoin Up or Down - April 10, 9:00AM-9:05AM UTC",
                    "slug": request.url.path.split("/")[-1],
                    "description": "Polymarket 5m up/down market.",
                    "enableOrderBook": True,
                    "acceptingOrders": True,
                    "volume24hrClob": 35018.48,
                    "liquidityClob": 14559.25,
                    "volumeClob": 35018.48,
                    "bestBid": 0.5,
                    "bestAsk": 0.51,
                    "lastTradePrice": 0.51,
                    "conditionId": "cond-btc-5m",
                    "clobTokenIds": json.dumps(["token_up", "token_down"]),
                    "outcomes": json.dumps(["Up", "Down"]),
                    "eventStartTime": "2026-04-10T09:00:00Z",
                    "endDate": "2026-04-10T09:05:00Z",
                    "events": [{"id": "event-btc-5m", "slug": request.url.path.split("/")[-1], "seriesSlug": "btc-up-or-down-5m"}],
                },
            )
        if request.url.host == "clob.polymarket.com" and path == "/midpoint":
            return httpx.Response(200, json={"mid": "0.505"})
        if request.url.host == "clob.polymarket.com" and path == "/book":
            return httpx.Response(200, json={"bids": [{"price": "0.50", "size": "1500"}], "asks": [{"price": "0.51", "size": "1600"}]})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = market_data.LiveMarketDataProvider(client=client)
    task = asyncio.run(
        provider.build_fast_task(
            datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc),
            forecast_engine.ForecastSettings(),
            "BTCUSDT",
        )
    )
    asyncio.run(provider.aclose())

    assert task["pack_json"]["snapshot_source"] == "live"
    assert task["pack_json"]["snapshot_frozen_at"] == task["created_at"]
    assert task["pack_json"]["snapshot_freshness_seconds"] == {"binance": 0, "polymarket": 0}


def test_live_market_data_provider_marks_stale_snapshot_as_degraded():
    class StaleLiveProvider(market_data.LiveMarketDataProvider):
        async def _fetch_market_bundle(self, asset: str, settings, now: datetime):  # noqa: ANN001
            return {
                "baseline_q_bps": 5400,
                "commit_close_ref_price": 70000.5,
                "market_context": f"{asset} stale bundle",
                "noisy_fragments": [],
                "binance_snapshot": {"best_bid": 70000.0, "best_ask": 70001.0, "q_yes_bps": 5300},
                "polymarket_snapshot": {"slug": "btc-updown-5m-1775752500", "q_yes_bps": 5500},
                "snapshot_freshness_seconds": {"binance": 31, "polymarket": 2},
            }

    provider = StaleLiveProvider()
    task = asyncio.run(
        provider.build_fast_task(
            datetime(2026, 4, 10, 9, 0, 1, tzinfo=timezone.utc),
            forecast_engine.ForecastSettings(),
            "BTCUSDT",
        )
    )
    asyncio.run(provider.aclose())

    assert task["snapshot_health"] == "degraded"
    assert task["task_state"] == "degraded"
    assert task["degraded_reason"] == "binance_snapshot_stale"


def test_live_market_data_provider_builds_eth_task_from_direct_slug():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        query = dict(request.url.params)

        if request.url.host == "api.binance.com" and path == "/api/v3/depth":
            return httpx.Response(
                200,
                json={
                    "lastUpdateId": 1,
                    "bids": [["3500.0", "10.0"], ["3499.5", "8.0"]],
                    "asks": [["3500.5", "7.0"], ["3501.0", "9.0"]],
                },
            )
        if request.url.host == "api.binance.com" and path == "/api/v3/ticker/bookTicker":
            return httpx.Response(
                200,
                json={
                    "symbol": query["symbol"],
                    "bidPrice": "3500.0",
                    "bidQty": "10.0",
                    "askPrice": "3500.5",
                    "askQty": "7.0",
                },
            )
        if request.url.host == "api.binance.com" and path == "/api/v3/trades":
            return httpx.Response(
                200,
                json=[
                    {"price": "3500.5", "qty": "1.5", "isBuyerMaker": False},
                    {"price": "3500.3", "qty": "1.0", "isBuyerMaker": False},
                    {"price": "3500.0", "qty": "0.9", "isBuyerMaker": True},
                ],
            )
        if request.url.host == "gamma-api.polymarket.com" and path.startswith("/markets/slug/eth-updown-5m-"):
            return httpx.Response(
                200,
                json={
                    "id": "market-eth-5m",
                    "question": "Ethereum Up or Down - April 10, 9:05AM-9:10AM UTC",
                    "slug": request.url.path.split("/")[-1],
                    "description": "Polymarket 5m ETH up/down market.",
                    "enableOrderBook": True,
                    "acceptingOrders": True,
                    "volume24hrClob": 18000.0,
                    "liquidityClob": 9000.0,
                    "volumeClob": 18000.0,
                    "bestBid": 0.61,
                    "bestAsk": 0.63,
                    "lastTradePrice": 0.62,
                    "conditionId": "cond-eth-5m",
                    "clobTokenIds": json.dumps(["token_eth_up", "token_eth_down"]),
                    "outcomes": json.dumps(["Up", "Down"]),
                    "eventStartTime": "2026-04-10T09:05:00Z",
                    "endDate": "2026-04-10T09:10:00Z",
                    "events": [{"id": "event-eth-5m", "slug": request.url.path.split("/")[-1], "seriesSlug": "eth-up-or-down-5m"}],
                },
            )
        if request.url.host == "gamma-api.polymarket.com" and path == "/markets":
            raise AssertionError("ETH 5m discovery should use /markets/slug/*, not list scanning")
        if request.url.host == "clob.polymarket.com" and path == "/midpoint":
            return httpx.Response(200, json={"mid": "0.62"})
        if request.url.host == "clob.polymarket.com" and path == "/book":
            return httpx.Response(
                200,
                json={
                    "bids": [{"price": "0.61", "size": "1000"}],
                    "asks": [{"price": "0.63", "size": "1200"}],
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = market_data.LiveMarketDataProvider(client=client)

    task = asyncio.run(
        provider.build_fast_task(
            datetime(2026, 4, 10, 9, 5, 1, tzinfo=timezone.utc),
            forecast_engine.ForecastSettings(),
            "ETHUSDT",
        )
    )
    asyncio.run(provider.aclose())

    assert task["snapshot_health"] == "live"
    assert task["pack_json"]["polymarket_snapshot"]["slug"].startswith("eth-updown-5m-")
    assert task["pack_json"]["polymarket_snapshot"]["series_slug"] == "eth-up-or-down-5m"
    assert task["pack_json"]["polymarket_snapshot"]["positive_outcome"] == "Up"


def test_live_market_data_provider_uses_polymarket_resolved_outcome_when_available():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if request.url.host == "gamma-api.polymarket.com" and path == "/markets/slug/btc-updown-5m-1775752500":
            return httpx.Response(
                200,
                json={
                    "slug": "btc-updown-5m-1775752500",
                    "closed": True,
                    "umaResolutionStatus": "resolved",
                    "outcomes": json.dumps(["Up", "Down"]),
                    "outcomePrices": json.dumps(["0", "1"]),
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = market_data.LiveMarketDataProvider(client=client)
    resolution = asyncio.run(
        provider.resolve_fast_task(
            {
                "asset": "BTCUSDT",
                "commit_close_ref_price": 70000.5,
                "pack_json": {
                    "snapshot_source": "live",
                    "polymarket_snapshot": {"slug": "btc-updown-5m-1775752500", "positive_outcome": "Up"},
                },
            }
        )
    )
    asyncio.run(provider.aclose())

    assert resolution["outcome"] == 0
    assert resolution["commit_close_ref_price"] == 70000.5
    assert resolution["end_ref_price"] is None
    assert resolution["resolution_status"] == "resolved"


def test_live_market_data_provider_returns_pending_when_polymarket_not_resolved():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == "gamma-api.polymarket.com" and path == "/markets/slug/btc-updown-5m-1775752500":
            return httpx.Response(
                200,
                json={
                    "slug": "btc-updown-5m-1775752500",
                    "closed": False,
                    "umaResolutionStatus": "open",
                    "outcomes": json.dumps(["Up", "Down"]),
                    "outcomePrices": json.dumps(["0.49", "0.51"]),
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = market_data.LiveMarketDataProvider(client=client)
    resolution = asyncio.run(
        provider.resolve_fast_task(
            {
                "asset": "BTCUSDT",
                "commit_close_ref_price": 70000.5,
                "pack_json": {
                    "snapshot_source": "live",
                    "polymarket_snapshot": {"slug": "btc-updown-5m-1775752500", "positive_outcome": "Up"},
                },
            }
        )
    )
    asyncio.run(provider.aclose())

    assert resolution["outcome"] is None
    assert resolution["commit_close_ref_price"] == 70000.5
    assert resolution["end_ref_price"] is None
    assert resolution["resolution_status"] == "pending"


def test_hybrid_market_data_provider_does_not_fallback_for_live_resolution_errors():
    class FailingResolveLiveProvider:
        async def build_fast_task(self, now, settings, asset):  # noqa: ANN001
            raise AssertionError("not used")

        async def resolve_fast_task(self, task):  # noqa: ANN001
            raise RuntimeError("gamma timeout")

        async def aclose(self) -> None:
            return None

    provider = market_data.HybridMarketDataProvider(
        live=FailingResolveLiveProvider(),
        fallback=market_data.SyntheticMarketDataProvider(),
    )

    resolution = asyncio.run(
        provider.resolve_fast_task(
            {
                "asset": "BTCUSDT",
                "commit_close_ref_price": 70000.5,
                "pack_json": {
                    "snapshot_source": "live",
                    "polymarket_snapshot": {"slug": "btc-updown-5m-1775752500", "positive_outcome": "Up"},
                },
            }
        )
    )

    assert resolution["outcome"] is None
    assert resolution["commit_close_ref_price"] == 70000.5
    assert resolution["end_ref_price"] is None
    assert resolution["resolution_status"] == "pending"
