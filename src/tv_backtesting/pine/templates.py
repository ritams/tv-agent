"""Pine Script strategy templates for backtesting indicator combinations."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Per-indicator strategy templates for Strategy Tester backtesting.
#
# These get deployed one at a time via Pine Editor. TradingView's Strategy
# Tester then computes the full backtest server-side over the entire chart
# history — no bar replay needed.
#
# Since we can't directly read invite-only indicator outputs from Pine,
# each strategy replicates the core logic of that indicator using built-in
# Pine functions. This gives us the same signal timing on the same data.
# ---------------------------------------------------------------------------

INDICATOR_STRATEGIES: dict[str, str] = {

    "MRI": """\
//@version=5
strategy("MRI Backtest", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

// TD Sequential Setup: 9 consecutive closes < close[4] = buy setup
holdBars = input.int(10, "Hold Bars")
var int buyCount = 0
var int sellCount = 0

if close < close[4]
    buyCount += 1
    sellCount := 0
else if close > close[4]
    sellCount += 1
    buyCount := 0
else
    buyCount := 0
    sellCount := 0

buySetup = buyCount >= 9
sellSetup = sellCount >= 9

if buySetup and strategy.position_size == 0
    strategy.entry("Long", strategy.long)
if strategy.position_size > 0 and (bar_index - strategy.opentrades.entry_bar_index(0)) >= holdBars
    strategy.close("Long")

plotshape(buySetup, "Buy Setup", shape.triangleup, location.belowbar, color.green, size=size.small)
plotshape(sellSetup, "Sell Setup", shape.triangledown, location.abovebar, color.red, size=size.small)""",

    "Trend Chameleon - LV v2.0": """\
//@version=5
strategy("Chameleon LV Backtest", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

// Chameleon LV: volatility contraction + bullish trend + price above trend
holdBars = input.int(10, "Hold Bars")
atrLen = input.int(14, "ATR Length")
atrSmaLen = input.int(20, "ATR SMA Length")
trendFast = input.int(50, "Fast MA")
trendSlow = input.int(200, "Slow MA")
volThresh = input.float(0.8, "Vol Contraction Threshold")

atrVal = ta.atr(atrLen)
atrMA = ta.sma(atrVal, atrSmaLen)
smaFast = ta.sma(close, trendFast)
smaSlow = ta.sma(close, trendSlow)

volContraction = atrVal < atrMA * volThresh
bullishTrend = smaFast > smaSlow
aboveTrend = close > smaFast

buySignal = volContraction and bullishTrend and aboveTrend
sellSignal = volContraction and (not bullishTrend) and close < smaFast

if buySignal and strategy.position_size == 0
    strategy.entry("Long", strategy.long)
if strategy.position_size > 0 and (bar_index - strategy.opentrades.entry_bar_index(0)) >= holdBars
    strategy.close("Long")

bgcolor(buySignal ? color.new(color.green, 90) : sellSignal ? color.new(color.red, 90) : na)""",

    "Trend Chameleon - HV v2.0": """\
//@version=5
strategy("Chameleon HV Backtest", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

// Chameleon HV: higher volatility version — wider bands, longer lookback
holdBars = input.int(10, "Hold Bars")
atrLen = input.int(20, "ATR Length")
atrSmaLen = input.int(30, "ATR SMA Length")
trendFast = input.int(50, "Fast MA")
trendSlow = input.int(200, "Slow MA")
volThresh = input.float(0.75, "Vol Contraction Threshold")

atrVal = ta.atr(atrLen)
atrMA = ta.sma(atrVal, atrSmaLen)
smaFast = ta.sma(close, trendFast)
smaSlow = ta.sma(close, trendSlow)

volContraction = atrVal < atrMA * volThresh
bullishTrend = smaFast > smaSlow
aboveTrend = close > smaFast

buySignal = volContraction and bullishTrend and aboveTrend
sellSignal = volContraction and (not bullishTrend) and close < smaFast

if buySignal and strategy.position_size == 0
    strategy.entry("Long", strategy.long)
if strategy.position_size > 0 and (bar_index - strategy.opentrades.entry_bar_index(0)) >= holdBars
    strategy.close("Long")

bgcolor(buySignal ? color.new(color.green, 90) : sellSignal ? color.new(color.red, 90) : na)""",

    "RSI": """\
//@version=5
strategy("RSI Backtest", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

holdBars = input.int(10, "Hold Bars")
rsiLen = input.int(14, "RSI Length")
oversold = input.int(30, "Oversold")
overbought = input.int(70, "Overbought")

rsiVal = ta.rsi(close, rsiLen)

if ta.crossover(rsiVal, oversold) and strategy.position_size == 0
    strategy.entry("Long", strategy.long)
if strategy.position_size > 0 and (bar_index - strategy.opentrades.entry_bar_index(0)) >= holdBars
    strategy.close("Long")

plotshape(ta.crossover(rsiVal, oversold), "Oversold", shape.triangleup, location.belowbar, color.green, size=size.small)""",

    "LuxAlgo Signals": """\
//@version=5
strategy("LuxAlgo-Style Signals Backtest", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

// LuxAlgo Signals & Overlays approximation: trend + momentum + volatility confirmation
holdBars = input.int(10, "Hold Bars")
trendLen = input.int(50, "Trend MA Length")
momentumLen = input.int(14, "RSI Length")
atrLen = input.int(14, "ATR Length")
atrMult = input.float(1.5, "ATR Multiplier")

trendMA = ta.sma(close, trendLen)
rsiVal = ta.rsi(close, momentumLen)
atrVal = ta.atr(atrLen)

// Bullish: price crosses above trend MA + RSI recovering from oversold + volatility expanding
bullishSignal = ta.crossover(close, trendMA) and rsiVal > 40 and rsiVal < 65
// Bearish: price crosses below trend MA + RSI from overbought
bearishSignal = ta.crossunder(close, trendMA) and rsiVal < 60 and rsiVal > 35

if bullishSignal and strategy.position_size == 0
    strategy.entry("Long", strategy.long)
if strategy.position_size > 0 and (bar_index - strategy.opentrades.entry_bar_index(0)) >= holdBars
    strategy.close("Long")

plotshape(bullishSignal, "Buy", shape.triangleup, location.belowbar, color.green, size=size.small)
plotshape(bearishSignal, "Sell", shape.triangledown, location.abovebar, color.red, size=size.small)""",

    "TCG BackBurner v2.3": """\
//@version=5
strategy("TCG BackBurner Backtest", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

// BackBurner approximation: momentum divergence + support/resistance
holdBars = input.int(10, "Hold Bars")
rsiLen = input.int(14, "RSI Length")
bbLen = input.int(20, "BB Length")
bbMult = input.float(2.0, "BB Mult")

rsiVal = ta.rsi(close, rsiLen)
[bbMid, bbUp, bbLow] = ta.bb(close, bbLen, bbMult)

// Buy when price touches lower BB + RSI diverging up
priceLow = ta.lowest(low, 5)
rsiLow = ta.lowest(rsiVal, 5)
prevPriceLow = ta.lowest(low[5], 5)
prevRsiLow = ta.lowest(rsiVal[5], 5)
bullishDiv = (priceLow < prevPriceLow) and (rsiLow > prevRsiLow)

buySignal = (close <= bbLow or bullishDiv) and rsiVal < 40

if buySignal and strategy.position_size == 0
    strategy.entry("Long", strategy.long)
if strategy.position_size > 0 and (bar_index - strategy.opentrades.entry_bar_index(0)) >= holdBars
    strategy.close("Long")

plotshape(buySignal, "Buy", shape.triangleup, location.belowbar, color.green, size=size.small)""",

    "GLI-TR": """\
//@version=5
strategy("GLI-TR Backtest", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

// GLI-TR approximation: trend ribbon using multiple EMAs
holdBars = input.int(10, "Hold Bars")

ema8 = ta.ema(close, 8)
ema13 = ta.ema(close, 13)
ema21 = ta.ema(close, 21)
ema55 = ta.ema(close, 55)

// Bullish ribbon: all EMAs stacked in order
bullishRibbon = ema8 > ema13 and ema13 > ema21 and ema21 > ema55
bearishRibbon = ema8 < ema13 and ema13 < ema21 and ema21 < ema55

// Entry on ribbon alignment + price confirmation
buySignal = bullishRibbon and close > ema8 and not bullishRibbon[1]

if buySignal and strategy.position_size == 0
    strategy.entry("Long", strategy.long)
if strategy.position_size > 0 and (bar_index - strategy.opentrades.entry_bar_index(0)) >= holdBars
    strategy.close("Long")

bgcolor(bullishRibbon ? color.new(color.green, 92) : bearishRibbon ? color.new(color.red, 92) : na)""",

    "MM Trend Scout": """\
//@version=5
strategy("MM Trend Scout Backtest", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

// MM Trend Scout approximation: multi-timeframe trend + MACD confirmation
holdBars = input.int(10, "Hold Bars")

sma20 = ta.sma(close, 20)
sma50 = ta.sma(close, 50)
sma200 = ta.sma(close, 200)
[macdLine, signalLine, hist] = ta.macd(close, 12, 26, 9)

// Trend aligned + MACD crossover
trendUp = sma20 > sma50 and sma50 > sma200
macdBuy = ta.crossover(macdLine, signalLine)
buySignal = trendUp and macdBuy and close > sma20

if buySignal and strategy.position_size == 0
    strategy.entry("Long", strategy.long)
if strategy.position_size > 0 and (bar_index - strategy.opentrades.entry_bar_index(0)) >= holdBars
    strategy.close("Long")

plotshape(buySignal, "Buy", shape.triangleup, location.belowbar, color.green, size=size.small)""",

}


def get_indicator_strategy(name: str) -> str | None:
    """Get a Pine strategy template for a given indicator name."""
    # Exact match first
    if name in INDICATOR_STRATEGIES:
        return INDICATOR_STRATEGIES[name]
    # Partial match
    name_lower = name.lower()
    for key, val in INDICATOR_STRATEGIES.items():
        if key.lower() in name_lower or name_lower in key.lower():
            return val
    return None


def get_all_indicator_names() -> list[str]:
    """Return all available indicator strategy names."""
    return list(INDICATOR_STRATEGIES.keys())


def jamie_coutts_strategy(
    *,
    rsi_length: int = 14,
    rsi_oversold: int = 30,
    mri_length: int = 10,
    min_signals: int = 2,
) -> str:
    return f"""\
//@version=5
strategy("Jamie Coutts Composite [Backtest]", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

// === PARAMETERS ===
rsiLen = input.int({rsi_length}, "RSI Length")
rsiOversold = input.int({rsi_oversold}, "RSI Oversold Level")
mriLen = input.int({mri_length}, "MRI Length")
minSignals = input.int({min_signals}, "Min Signals for Entry", minval=1, maxval=3)
holdBars = input.int(10, "Hold Bars After Entry")

// === INDICATOR 1: RSI Divergence (simplified) ===
rsiVal = ta.rsi(close, rsiLen)
priceLow = ta.lowest(low, 5)
rsiLow = ta.lowest(rsiVal, 5)
prevPriceLow = ta.lowest(low[5], 5)
prevRsiLow = ta.lowest(rsiVal[5], 5)
rsiBullishDiv = (priceLow < prevPriceLow) and (rsiLow > prevRsiLow) and (rsiVal < rsiOversold + 10)
rsiSignal = rsiBullishDiv or (rsiVal < rsiOversold)

// === INDICATOR 2: MRI-style (Tone Vays inspired) ===
mriMA = ta.ema(close, mriLen)
mriCount = 0
mriCount := close < mriMA ? (nz(mriCount[1]) + 1) : 0
mriBuySignal = (mriCount >= 9) or (mriCount >= 13)

// === INDICATOR 3: Chameleon-style (volatility + trend) ===
atrVal = ta.atr(14)
atrMA = ta.sma(atrVal, 20)
volContraction = atrVal < atrMA * 0.8
trendMA50 = ta.sma(close, 50)
trendMA200 = ta.sma(close, 200)
bullishTrend = trendMA50 > trendMA200
chameleonSignal = volContraction and bullishTrend and (close > trendMA50)

// === COMPOSITE SCORING ===
score = (rsiSignal ? 1 : 0) + (mriBuySignal ? 1 : 0) + (chameleonSignal ? 1 : 0)

// === ENTRY/EXIT ===
longCondition = score >= minSignals
if (longCondition and strategy.position_size == 0)
    strategy.entry("Long", strategy.long)

if (strategy.position_size > 0 and (bar_index - strategy.opentrades.entry_bar_index(0)) >= holdBars)
    strategy.close("Long")

// === PLOTTING ===
plotshape(rsiSignal, "RSI Signal", shape.circle, location.belowbar, color.blue, size=size.tiny)
plotshape(mriBuySignal, "MRI Signal", shape.circle, location.belowbar, color.purple, size=size.tiny)
plotshape(chameleonSignal, "Chameleon Signal", shape.circle, location.belowbar, color.orange, size=size.tiny)
bgcolor(score >= 3 ? color.new(color.green, 90) : score >= 2 ? color.new(color.yellow, 90) : na)"""


def rsi_strategy(
    *, length: int = 14, oversold: int = 30, overbought: int = 70
) -> str:
    return f"""\
//@version=5
strategy("RSI Strategy [Backtest]", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

length = input.int({length}, "RSI Length")
oversold = input.int({oversold}, "Oversold")
overbought = input.int({overbought}, "Overbought")

rsiVal = ta.rsi(close, length)

if (ta.crossover(rsiVal, oversold))
    strategy.entry("Long", strategy.long)
if (ta.crossunder(rsiVal, overbought))
    strategy.close("Long")"""


def multi_indicator_strategy(
    *,
    use_rsi: bool = True,
    use_mri: bool = True,
    use_chameleon: bool = True,
    use_macd: bool = False,
    use_bb: bool = False,
    rsi_length: int = 14,
    rsi_oversold: int = 30,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bb_length: int = 20,
    bb_mult: int = 2,
    min_signals: int = 2,
    hold_bars: int = 10,
) -> str:
    indicators: list[str] = []
    signals: list[str] = []
    plots: list[str] = []
    signal_count = 0

    if use_rsi:
        signal_count += 1
        indicators.append(f"""
// RSI
rsiVal = ta.rsi(close, {rsi_length})
rsiSignal = rsiVal < {rsi_oversold}""")
        signals.append("(rsiSignal ? 1 : 0)")
        plots.append('plotshape(rsiSignal, "RSI", shape.circle, location.belowbar, color.blue, size=size.tiny)')

    if use_mri:
        signal_count += 1
        indicators.append("""
// MRI (TD Sequential style)
mriMA = ta.ema(close, 10)
mriCount = 0
mriCount := close < mriMA ? (nz(mriCount[1]) + 1) : 0
mriSignal = mriCount >= 9""")
        signals.append("(mriSignal ? 1 : 0)")
        plots.append('plotshape(mriSignal, "MRI", shape.circle, location.belowbar, color.purple, size=size.tiny)')

    if use_chameleon:
        signal_count += 1
        indicators.append("""
// Chameleon (vol contraction + trend)
atrVal = ta.atr(14)
atrMA = ta.sma(atrVal, 20)
chameleonSignal = (atrVal < atrMA * 0.8) and (ta.sma(close, 50) > ta.sma(close, 200)) and (close > ta.sma(close, 50))""")
        signals.append("(chameleonSignal ? 1 : 0)")
        plots.append('plotshape(chameleonSignal, "Chameleon", shape.circle, location.belowbar, color.orange, size=size.tiny)')

    if use_macd:
        signal_count += 1
        indicators.append(f"""
// MACD
[macdLine, signalLine, hist] = ta.macd(close, {macd_fast}, {macd_slow}, {macd_signal})
macdSignalBuy = ta.crossover(macdLine, signalLine) and macdLine < 0""")
        signals.append("(macdSignalBuy ? 1 : 0)")
        plots.append('plotshape(macdSignalBuy, "MACD", shape.circle, location.belowbar, color.green, size=size.tiny)')

    if use_bb:
        signal_count += 1
        indicators.append(f"""
// Bollinger Bands
[bbMiddle, bbUpper, bbLower] = ta.bb(close, {bb_length}, {bb_mult})
bbSignal = close < bbLower""")
        signals.append("(bbSignal ? 1 : 0)")
        plots.append('plotshape(bbSignal, "BB", shape.circle, location.belowbar, color.red, size=size.tiny)')

    ind_block = "\n".join(indicators)
    score_expr = " + ".join(signals) if signals else "0"
    plot_block = "\n".join(plots)

    return f"""\
//@version=5
strategy("Multi-Indicator Backtest", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)
{ind_block}

// Composite Score
score = {score_expr}

// Entry
if (score >= {min_signals} and strategy.position_size == 0)
    strategy.entry("Long", strategy.long)

// Exit after {hold_bars} bars
if (strategy.position_size > 0 and (bar_index - strategy.opentrades.entry_bar_index(0)) >= {hold_bars})
    strategy.close("Long")

{plot_block}
bgcolor(score >= {signal_count} ? color.new(color.green, 90) : score >= {min_signals} ? color.new(color.yellow, 90) : na)"""
