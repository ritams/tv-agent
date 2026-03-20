"""FastAPI server exposing the backtesting agent as an HTTP API for OpenClaw."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from .data.market_data import MarketData, to_exchange_symbol
from .data.local_indicators import analyze_local

app = FastAPI(title="TV Backtesting Agent", version="0.1.0")

# Shared MarketData instance (lazy init)
_md: MarketData | None = None


def _get_md() -> MarketData:
    global _md
    if _md is None:
        _md = MarketData("binance")
    return _md


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SignalRequest(BaseModel):
    assets: list[str] = Field(default=["BTCUSD", "HYPEUSD"])
    source: Literal["local", "tradingview", "both"] = "local"


class SignalDetail(BaseModel):
    name: str
    signal: str
    value: float | str
    details: str


class AssetSignalResult(BaseModel):
    asset: str
    price: float
    score: int
    total: int
    level: str
    signals: list[SignalDetail]


class SignalResponse(BaseModel):
    timestamp: str
    results: list[AssetSignalResult]


class TechnicalsRequest(BaseModel):
    asset: str
    timeframe: str = "1d"
    candles: int = 300


class TechnicalsResponse(BaseModel):
    asset: str
    price: float
    timestamp: str
    indicators: dict[str, SignalDetail]
    jamie_coutts: dict[str, int | str]


class BacktestRequest(BaseModel):
    asset: str
    timeframe: str = "1d"
    candles: int = 500
    hold_bars: int = 10
    min_score: int = 2


class TradeResult(BaseModel):
    entry_price: float
    exit_price: float
    pnl_percent: float
    entry_bar: int
    exit_bar: int


class BacktestResponse(BaseModel):
    asset: str
    total_trades: int
    win_rate: float
    avg_return: float
    total_return: float
    trades: list[TradeResult]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/signal", response_model=SignalResponse)
async def signal_check(req: SignalRequest):
    md = _get_md()
    results: list[AssetSignalResult] = []

    for asset in req.assets:
        symbol = to_exchange_symbol(asset)
        candles = await md.get_ohlcv(symbol, "1d", 300)
        analysis = analyze_local(asset, candles)

        level = "none"
        if analysis.score >= 3:
            level = "big_buy"
        elif analysis.score >= 2:
            level = "partial_buy"

        results.append(AssetSignalResult(
            asset=analysis.asset,
            price=analysis.price,
            score=analysis.score,
            total=analysis.total,
            level=level,
            signals=[
                SignalDetail(
                    name=s.name, signal=s.signal, value=s.value, details=s.details
                )
                for s in analysis.signals
            ],
        ))

    return SignalResponse(
        timestamp=datetime.now(timezone.utc).isoformat(),
        results=results,
    )


@app.post("/technicals", response_model=TechnicalsResponse)
async def technicals(req: TechnicalsRequest):
    md = _get_md()
    symbol = to_exchange_symbol(req.asset)
    candles = await md.get_ohlcv(symbol, req.timeframe, req.candles)
    analysis = analyze_local(req.asset, candles)

    indicators = {}
    for s in analysis.signals:
        key = s.name.lower().replace(" ", "_")
        indicators[key] = SignalDetail(
            name=s.name, signal=s.signal, value=s.value, details=s.details
        )

    level = "none"
    if analysis.score >= 3:
        level = "big_buy"
    elif analysis.score >= 2:
        level = "partial_buy"

    return TechnicalsResponse(
        asset=analysis.asset,
        price=analysis.price,
        timestamp=datetime.now(timezone.utc).isoformat(),
        indicators=indicators,
        jamie_coutts={"score": analysis.score, "total": analysis.total, "level": level},
    )


@app.post("/backtest", response_model=BacktestResponse)
async def backtest(req: BacktestRequest):
    md = _get_md()
    symbol = to_exchange_symbol(req.asset)
    candles = await md.get_ohlcv(symbol, req.timeframe, req.candles)

    if len(candles) < 200:
        return BacktestResponse(
            asset=req.asset, total_trades=0, win_rate=0, avg_return=0,
            total_return=0, trades=[],
        )

    trades: list[TradeResult] = []
    in_trade = False
    entry_price = 0.0
    entry_bar = 0

    for i in range(200, len(candles)):
        slc = candles[: i + 1]
        analysis = analyze_local(req.asset, slc)

        if not in_trade and analysis.score >= req.min_score:
            in_trade = True
            entry_price = candles[i].close
            entry_bar = i
        elif in_trade and i - entry_bar >= req.hold_bars:
            exit_price = candles[i].close
            pnl = ((exit_price - entry_price) / entry_price) * 100
            trades.append(TradeResult(
                entry_price=entry_price, exit_price=exit_price,
                pnl_percent=round(pnl, 2), entry_bar=entry_bar, exit_bar=i,
            ))
            in_trade = False

    wins = [t for t in trades if t.pnl_percent > 0]
    total_return = sum(t.pnl_percent for t in trades)
    avg_return = total_return / len(trades) if trades else 0
    win_rate = (len(wins) / len(trades) * 100) if trades else 0

    return BacktestResponse(
        asset=req.asset,
        total_trades=len(trades),
        win_rate=round(win_rate, 1),
        avg_return=round(avg_return, 2),
        total_return=round(total_return, 2),
        trades=trades,
    )


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------

def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    uvicorn.run(app, host=host, port=port)
