# TV Backtesting Agent — API Reference

This document describes how OpenClaw (or any external system) can use the TV Backtesting Agent as a tool.

## Quick Start

```bash
# Install
uv sync

# Run the API server
uv run python -m tv_backtesting serve --port 8000
```

---

## HTTP API Endpoints

### `POST /signal`

Check Jamie Coutts signals for one or more assets. Returns structured scoring data.

**Request:**
```json
{
  "assets": ["BTCUSD", "HYPEUSD"],
  "source": "local"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `assets` | `string[]` | `["BTCUSD", "HYPEUSD"]` | Ticker symbols to check |
| `source` | `"local" \| "tradingview" \| "both"` | `"local"` | Data source. `local` = CCXT exchange API (fast, no browser). `tradingview` = Playwright browser scraping (slow, reads proprietary indicators). |

**Response:**
```json
{
  "timestamp": "2026-03-21T12:00:00Z",
  "results": [
    {
      "asset": "BTCUSD",
      "price": 69862.0,
      "score": 1,
      "total": 3,
      "level": "none",
      "signals": [
        {
          "name": "Chameleon",
          "signal": "neutral",
          "value": 0,
          "details": "Vol expanded, Bearish trend, Below SMA50"
        },
        {
          "name": "MRI",
          "signal": "neutral",
          "value": 2,
          "details": "TD Buy Setup: 2/9"
        },
        {
          "name": "RSI Divergence",
          "signal": "neutral",
          "value": 48.0,
          "details": "RSI: 48.0"
        }
      ]
    }
  ]
}
```

| Response Field | Description |
|----------------|-------------|
| `level` | `"big_buy"` (3/3), `"partial_buy"` (2/3), or `"none"` |
| `score` | Number of indicators firing buy |
| `total` | Total indicators checked |
| `signals[].signal` | `"buy"`, `"sell"`, or `"neutral"` |

---

### `POST /technicals`

Run full technical analysis on any asset. Returns all indicator data for the researcher agent to interpret.

**Request:**
```json
{
  "asset": "SOLUSD",
  "timeframe": "1d",
  "candles": 300
}
```

**Response:**
```json
{
  "asset": "SOLUSD",
  "price": 187.50,
  "timestamp": "2026-03-21T12:00:00Z",
  "indicators": {
    "chameleon": {
      "signal": "buy",
      "value": 1,
      "details": "Vol contraction + bullish trend (ATR: 3 < 5)"
    },
    "mri": {
      "signal": "neutral",
      "value": 4,
      "details": "TD Buy Setup: 4/9"
    },
    "rsi_divergence": {
      "signal": "neutral",
      "value": 55.2,
      "details": "RSI: 55.2"
    }
  },
  "jamie_coutts": {
    "score": 1,
    "total": 3,
    "level": "none"
  }
}
```

---

### `POST /backtest`

Run a local backtest on historical data. No browser needed.

**Request:**
```json
{
  "asset": "BTCUSD",
  "timeframe": "1d",
  "candles": 500,
  "hold_bars": 10,
  "min_score": 2
}
```

**Response:**
```json
{
  "asset": "BTCUSD",
  "total_trades": 5,
  "win_rate": 60.0,
  "avg_return": 1.25,
  "total_return": 6.25,
  "trades": [
    {
      "entry_price": 65000,
      "exit_price": 67500,
      "pnl_percent": 3.85,
      "entry_bar": 250,
      "exit_bar": 260
    }
  ]
}
```

---

### `GET /health`

Health check.

**Response:**
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

---

### `POST /webhook`

Receives TradingView alert webhooks (existing functionality).

**Request** (from TradingView alert):
```json
{
  "ticker": "BTCUSD",
  "price": "69800",
  "time": "2026-03-21T12:00:00Z",
  "indicator": "JC-Composite",
  "signal": "buy",
  "score": "3"
}
```

---

## Python Callable Interface

If OpenClaw imports this package directly instead of calling HTTP:

```python
import asyncio
from tv_backtesting.data.market_data import MarketData, to_exchange_symbol
from tv_backtesting.data.local_indicators import analyze_local

async def check_signals(asset: str = "BTCUSD") -> dict:
    """Call this from OpenClaw to get Jamie Coutts signals."""
    md = MarketData("binance")
    try:
        symbol = to_exchange_symbol(asset)
        candles = await md.get_ohlcv(symbol, "1d", 300)
        analysis = analyze_local(asset, candles)
        return {
            "asset": analysis.asset,
            "price": analysis.price,
            "score": analysis.score,
            "total": analysis.total,
            "level": "big_buy" if analysis.score >= 3
                     else "partial_buy" if analysis.score >= 2
                     else "none",
            "signals": [
                {
                    "name": s.name,
                    "signal": s.signal,
                    "value": s.value,
                    "details": s.details,
                }
                for s in analysis.signals
            ],
        }
    finally:
        await md.close()

# Usage
result = asyncio.run(check_signals("BTCUSD"))
```

### Key functions for OpenClaw tool registration:

| Function | Import | Description |
|----------|--------|-------------|
| `analyze_local(asset, candles)` | `tv_backtesting.data.local_indicators` | Run all 3 Jamie Coutts indicators on OHLCV data |
| `MarketData.get_ohlcv(symbol, tf, limit)` | `tv_backtesting.data.market_data` | Fetch candles from exchange API |
| `to_exchange_symbol(asset)` | `tv_backtesting.data.market_data` | Convert "BTCUSD" → "BTC/USDT" |
| `score_snapshot(snapshot)` | `tv_backtesting.indicators.scoring` | Score a TradingView chart snapshot |
| `format_signal(signal)` | `tv_backtesting.indicators.scoring` | Human-readable signal summary |

---

## Supported Assets

Any ticker supported by CCXT exchanges. Common ones:

| Input | Exchange Symbol | Exchange |
|-------|----------------|----------|
| `BTCUSD` | `BTC/USDT` | Binance |
| `HYPEUSD` | `HYPE/USDT` | Bybit |
| `SOLUSD` | `SOL/USDT` | Binance |
| `ETHUSD` | `ETH/USDT` | Binance |
| Any valid pair | Pass directly (e.g. `SOL/USDT`) | Auto |

For assets not in the symbol map, pass the exchange symbol directly (e.g. `SOL/USDT`).

---

## Architecture

```
OpenClaw Researcher Agent
        │
        ▼
  HTTP API (FastAPI)  ──or──  Direct Python import
        │
        ▼
┌─────────────────────────────────┐
│  tv_backtesting                 │
│                                 │
│  ┌─── Local Path (fast) ─────┐ │
│  │  CCXT → OHLCV → pandas-ta │ │
│  │  Chameleon, MRI, RSI Div  │ │
│  └────────────────────────────┘ │
│                                 │
│  ┌─── TV Path (slow) ────────┐ │
│  │  Playwright → TradingView │ │
│  │  Login, legend scraping   │ │
│  │  Proprietary indicators   │ │
│  └────────────────────────────┘ │
│                                 │
│  ┌─── Backtest Engine ───────┐ │
│  │  Local: walk OHLCV data   │ │
│  │  TV: bar replay + Pine    │ │
│  └────────────────────────────┘ │
└─────────────────────────────────┘
```
