# TV Backtesting Agent

A TradingView automation agent that reads invite-only indicators from your chart, backtests them using bar replay, scores them using the Jamie Coutts methodology, and exposes everything as an API for OpenClaw integration.

## What it does

1. **Signal Check** — Logs into TradingView, reads all indicators on your chart, scores them using Jamie Coutts' 2-of-3 / 3-of-3 methodology, and tells you whether to buy or not.

2. **Backtest** — Rewinds your chart using TradingView's Bar Replay, steps through bar by bar, reads the *actual* invite-only indicator signals at each bar, simulates trades, and ranks every indicator by performance.

3. **API Server** — Exposes signal checking, technicals, and backtesting as HTTP endpoints for OpenClaw's researcher agent.

## Setup

```bash
# Install dependencies
uv sync

# Install Playwright browser
uv run playwright install chromium
```

### Environment variables

Create a `.env` file:

```
TV_EMAIL=your@email.com
TV_PASSWORD=your_password
TV_OTP_SECRET=              # TOTP secret for 2FA (preferred)
TV_2FA_BACKUP_CODES=code1,code2,code3   # Backup codes (fallback)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

## Commands

### Signal check (local — fast, no browser)

Uses exchange APIs (CCXT) to fetch price data and computes indicators locally. Takes ~5 seconds.

```bash
uv run python -m tv_backtesting signal --local
```

Output:
```
=== Jamie Coutts Signal Check (local) ===

Checking BTCUSD (BTC/USDT)...
Price: $69,862
  ⚪ Chameleon: Vol expanded, Bearish trend, Below SMA50
  ⚪ MRI: TD Buy Setup: 2/9
  ⚪ RSI Divergence: RSI: 48.0
Score: 0/3
⚪ NO SIGNAL
```

### Signal check (TradingView — reads real indicators)

Opens a browser, logs into TradingView, reads the actual invite-only indicators from the chart legend. Takes ~30 seconds.

```bash
uv run python -m tv_backtesting signal
```

Output:
```
Checking BTCUSD...
  Found 22 indicator items in legend
⚪ BTCUSD — NO SIGNAL
Price: $69,862
Score: 1/4 signals confirmed
  - MRI: sell
  - Trend Chameleon - HV v2.0: neutral
  - Trend Chameleon - LV v2.0: buy
  - RSI: neutral
```

### Backtest (bar replay — real indicators)

This is the main feature. Opens the chart, enters Bar Replay mode, steps through bars one at a time, reads every indicator's signal at each bar, then simulates trades and ranks all indicators.

```bash
uv run python -m tv_backtesting backtest BTCUSD --bars 100 --hold 10
```

Options:
- `BTCUSD` — any asset/ticker TradingView supports
- `--bars 100` — number of bars to replay (default: 100)
- `--hold 10` — hold each trade for N bars before exiting (default: 10)

**Time estimates:**

| Bars | Time |
|------|------|
| 50   | ~1 min |
| 100  | ~2 min |
| 200  | ~4 min |
| 500  | ~10 min |

Output (real 100-bar run):
```
  [1/5] Opening chart...
  [2/5] Enabling bar replay...
  [3/5] Replaying 100 bars...
         0/100 (0%)
         25/100 (25%)
         50/100 (50%)
         75/100 (75%)
         100/100 (100%) — done
  [4/5] Exiting replay...
  [5/5] Analyzing...

================================================================================
  BTCUSD — 100 bars | hold=10 bars
================================================================================
  Indicator                                  Trades    Win%      Avg    Total   MaxDD  Buy Sell
  ------------------------------------------ ------ ------- -------- -------- ------- ---- ----
  Trade Keeper                                    3   66.7%   +2.49%   +7.48%   8.65%   26   72
  BB                                              —       —        —        —       —    0  100
  EMA                                             —       —        —        —       —    0  100
  GLI-TR Overlay v6.9 (RV)                        —       —        —        —       —    0    0
  GLI-TR v6.8 (RV)                                —       —        —        —       —    0    0
  LuxAlgo® - Price Action Concepts™ [2.1]         —       —        —        —       —    0    0
  MM Trend Scout                                  —       —        —        —       —    0    0
  RSI                                             —       —        —        —       —    0    0
  SMA                                             —       —        —        —       —    0    0
  TCG BackBurner v2.3                             —       —        —        —       —    0    0
  TCG Hist. RSI v2.2                              —       —        —        —       —    0    0
  TCG MVS                                         —       —        —        —       —    0    0
  TCG SuperStack Pro 2.3                          —       —        —        —       —    0    0
  Trend Chameleon - LV v2.0                       —       —        —        —       —    0    0
  Trend Chameleon - HV v2.0                       3   33.3%   -3.87%  -11.60%  18.34%   22   71
  MRI                                             8   50.0%   -1.55%  -12.41%  28.29%   72    0
  LuxAlgo® - Signals & Overlays™ [7.1]            3   33.3%   -5.83%  -17.49%  17.49%   26   46
  LuxAlgo® - Signals & Overlays™ [7.3.1]          3   33.3%   -5.83%  -17.49%  17.49%   26   46
  Vol · BTC                                       8   37.5%   -4.40%  -35.17%  39.11%   48   52

  Best: Trade Keeper — +7.48% total, 67% win rate, 3 trades
```

Results are saved as JSON in `./backtest-results/`.

### Why do some indicators show "—" (no signals)?

Some indicators show 0 buy and 0 sell signals in the results. This happens because:

- **MM Trend Scout, TCG MVS** — These indicators don't show any value items in the chart legend. They signal purely through visual elements on the chart canvas (plotshapes, bar colors) which we can't read from the DOM.
- **TCG SuperStack Pro, LuxAlgo Price Action Concepts** — All their legend values are `∅` (empty). They use chart overlays and shapes rather than legend values to communicate signals.
- **GLI-TR Overlay** — Shows a single `∅` value with no color data.
- **RSI** — Not broken, just stayed between 30-70 (neutral range) for the entire backtest window. It only triggers on extreme oversold/overbought.
- **Chameleon LV, TCG BackBurner, TCG Hist. RSI** — May show 0 signals in certain market conditions. These are selective indicators that only fire in specific setups.

**Bottom line:** The agent reads signals from the chart legend DOM (text values + CSS colors). Indicators that signal through chart-canvas-only visuals (shapes, background colors, bar painting) won't be detected. The indicators that DO work reliably are: MRI, Chameleon LV/HV, LuxAlgo Signals, Trade Keeper, Vol, RSI, GLI-TR v6.8, and TCG BackBurner.

### API server (for OpenClaw)

Starts a FastAPI server that OpenClaw can call.

```bash
uv run python -m tv_backtesting serve --port 8000
```

Endpoints:
- `POST /signal` — check Jamie Coutts signals for one or more assets
- `POST /technicals` — run full technical analysis on any asset
- `POST /backtest` — run a local backtest on historical data
- `GET /health` — health check

See [API.md](API.md) for full request/response documentation.

### Agent (scheduled)

Runs signal checks on a schedule and listens for TradingView webhook alerts.

```bash
uv run python -m tv_backtesting agent --local --once    # single local check
uv run python -m tv_backtesting agent                    # full scheduled agent
```

## How the backtest works

```
You run:  uv run python -m tv_backtesting backtest BTCUSD --bars 100

What happens:

1. Agent opens Chromium via Playwright
2. Logs into TradingView (uses saved session, handles 2FA)
3. Opens BTCUSD chart — all 22 indicators load automatically
4. Clicks "Bar Replay" button, clicks left side of chart to rewind
5. For each of the 100 bars:
   a. Reads the price from the OHLC legend
   b. Reads every indicator's values + colors from the chart legend DOM
   c. Interprets each indicator: green = buy, red = sell
   d. Records: {bar: 42, price: 65000, signals: {MRI: "buy", Chameleon: "sell", ...}}
   e. Presses Right Arrow to advance one bar
6. After all bars collected:
   - For each indicator, simulates trades (enter on "buy", exit after N bars)
   - Calculates: total trades, win rate, avg return, total return, max drawdown
   - Ranks all indicators by total return
7. Prints the results table and saves JSON to ./backtest-results/
```

## How indicator signals are detected

The agent reads each indicator's values and colors from the TradingView chart legend DOM. Each indicator has a specific interpretation:

| Indicator | How we detect buy/sell |
|---|---|
| Chameleon LV/HV | Majority of plot value colors are green vs red |
| MRI | Non-zero values in green-colored vs red-colored slots |
| LuxAlgo Signals | v1/v2 (green) non-zero = buy, v3/v4 (red) non-zero = sell |
| Trade Keeper | Value color green vs red |
| TCG BackBurner | v1 (green value) > v0 (pink value) = buy |
| TCG Hist. RSI | Signal plot v13 (green) > 0 = buy, v14 (pink) > 0 = sell |
| GLI-TR | v0 plot color green = buy, red = sell |
| RSI | Value < 30 = buy (oversold), > 70 = sell (overbought) |
| Others | Generic green/red color detection on value plots |

The agent reads the *actual* invite-only indicator outputs — not approximations. Whatever the indicator author coded as green/red is what we detect.

## Indicators on the chart

The backtest reads whatever indicators are currently on the chart. To test a new indicator, just add it to the chart in TradingView and run the backtest again. Currently on Daniel's chart:

**Invite-only / proprietary:**
- MRI (Tone Vays style)
- Trend Chameleon - LV v2.0 / HV v2.0
- LuxAlgo - Signals & Overlays [7.1] / [7.3.1]
- LuxAlgo - Price Action Concepts [2.1]
- MM Trend Scout
- Trade Keeper
- TCG BackBurner v2.3 / SuperStack Pro 2.3 / MVS / Hist. RSI v2.2
- GLI-TR Overlay v6.9 / v6.8

**Standard:**
- RSI, SMA, EMA, Bollinger Bands, Volume

## Changing the asset

The chart can show any asset TradingView supports. Just pass a different symbol:

```bash
uv run python -m tv_backtesting backtest ETHUSD --bars 100
uv run python -m tv_backtesting backtest SOLUSD --bars 200
uv run python -m tv_backtesting backtest XAUUSD --bars 100     # Gold
uv run python -m tv_backtesting backtest AAPL --bars 100       # Apple stock
```

All indicators on the chart will recalculate for that asset automatically.

## Project structure

```
src/tv_backtesting/
  __main__.py              CLI entry point
  config.py                Settings from .env (pydantic-settings)
  api.py                   FastAPI server for OpenClaw

  auth/
    tradingview_auth.py    Playwright login + session + 2FA

  indicators/
    indicator_reader.py    Chart legend scraper + signal interpretation
    scoring.py             Jamie Coutts 2/3, 3/3 scoring

  data/
    market_data.py         CCXT exchange API wrapper (async)
    local_indicators.py    Local Chameleon, MRI, RSI Divergence (pandas-ta)

  backtester/
    backtester.py          Bar replay backtester (main feature)
    strategy_tester_reader.py   Pine Editor automation
    optimizer.py           Grid search + combo explorer

  pine/
    templates.py           Pine Script strategy generators

  agent/
    technicals_agent.py    Scheduled agent with webhook listener
    webhook_receiver.py    FastAPI webhook for TradingView alerts
    run.py                 Agent CLI runner
```

## Dependencies

- **playwright** — browser automation for TradingView
- **ccxt** — exchange API for price data (Binance, Bybit)
- **pandas-ta** — local technical indicator calculations
- **fastapi + uvicorn** — API server
- **pyotp** — 2FA TOTP codes
- **pydantic-settings** — configuration management
- **apscheduler** — scheduled agent runs
