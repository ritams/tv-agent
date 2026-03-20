"""Market data fetcher using CCXT (exchange APIs). Gets OHLCV data directly — no browser needed."""

from __future__ import annotations

from dataclasses import dataclass

import ccxt
import ccxt.async_support as ccxt_async


@dataclass
class OHLCV:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


SYMBOL_MAP: dict[str, str] = {
    "BTCUSD": "BTC/USDT",
    "BTCUSDT": "BTC/USDT",
    "HYPEUSD": "HYPE/USDT",
    "HYPEUSDT": "HYPE/USDT",
    "XAUUSD": "XAU/USDT",
    "SPX": "SPX/USDT",
}


def to_exchange_symbol(asset: str) -> str:
    return SYMBOL_MAP.get(asset.upper(), asset)


class MarketData:
    def __init__(self, default_exchange: str = "binance") -> None:
        self._default_exchange = default_exchange
        self._exchanges: dict[str, ccxt_async.Exchange] = {}

    def _get_exchange(self, exchange_id: str) -> ccxt_async.Exchange:
        if exchange_id not in self._exchanges:
            cls = getattr(ccxt_async, exchange_id)
            self._exchanges[exchange_id] = cls({"enableRateLimit": True})
        return self._exchanges[exchange_id]

    def _exchange_for_symbol(self, symbol: str) -> ccxt_async.Exchange:
        if "HYPE" in symbol.upper():
            return self._get_exchange("bybit")
        return self._get_exchange(self._default_exchange)

    async def get_ohlcv(
        self, symbol: str, timeframe: str = "1d", limit: int = 500
    ) -> list[OHLCV]:
        exchange = self._exchange_for_symbol(symbol)
        raw = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return [
            OHLCV(
                timestamp=int(c[0]),
                open=float(c[1]),
                high=float(c[2]),
                low=float(c[3]),
                close=float(c[4]),
                volume=float(c[5]),
            )
            for c in raw
        ]

    async def get_price(self, symbol: str) -> float:
        exchange = self._exchange_for_symbol(symbol)
        ticker = await exchange.fetch_ticker(symbol)
        return float(ticker.get("last", 0) or 0)

    async def close(self) -> None:
        for ex in self._exchanges.values():
            await ex.close()
        self._exchanges.clear()
