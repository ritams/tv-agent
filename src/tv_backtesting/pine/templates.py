"""Pine Script strategy templates for backtesting indicator combinations."""

from __future__ import annotations


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
