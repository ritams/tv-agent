"""
Local indicator calculations using pandas-ta.
Implements the 3 Jamie Coutts indicators locally:
1. Chameleon (volatility contraction + trend alignment)
2. MRI (TD Sequential-style exhaustion countdown)
3. RSI Divergence
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
import pandas_ta as ta

from .market_data import OHLCV


@dataclass
class LocalSignal:
    name: str
    value: float | str
    signal: str  # "buy" | "sell" | "neutral"
    details: str


@dataclass
class LocalAnalysis:
    asset: str
    price: float
    timestamp: datetime
    signals: list[LocalSignal]
    score: int
    total: int


def _candles_to_df(candles: list[OHLCV]) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
        }
    )
    return df


# ---------------------------------------------------------------------------
# RSI Divergence
# ---------------------------------------------------------------------------

def calc_rsi_divergence(
    candles: list[OHLCV], period: int = 14, lookback: int = 5
) -> LocalSignal:
    df = _candles_to_df(candles)
    rsi_series = ta.rsi(df["close"], length=period)
    if rsi_series is None or rsi_series.dropna().shape[0] < lookback * 2:
        return LocalSignal("RSI Divergence", 0, "neutral", "Insufficient data")

    rsi_vals = rsi_series.dropna().values
    lows = df["low"].values
    highs = df["high"].values

    rsi = float(rsi_vals[-1])
    recent_rsi = rsi_vals[-lookback:]
    prev_rsi = rsi_vals[-lookback * 2 : -lookback]
    recent_lows = lows[-lookback:]
    prev_lows = lows[-lookback * 2 : -lookback]

    current_low = float(min(recent_lows))
    prev_low = float(min(prev_lows))
    current_rsi_low = float(min(recent_rsi))
    prev_rsi_low = float(min(prev_rsi))

    # Bullish divergence
    bullish_div = current_low < prev_low and current_rsi_low > prev_rsi_low
    oversold = rsi < 30

    if bullish_div or oversold:
        detail = (
            f"Bullish divergence (RSI: {rsi:.1f})"
            if bullish_div
            else f"Oversold (RSI: {rsi:.1f})"
        )
        return LocalSignal("RSI Divergence", round(rsi, 2), "buy", detail)

    # Bearish divergence
    recent_highs = highs[-lookback:]
    prev_highs = highs[-lookback * 2 : -lookback]
    current_high = float(max(recent_highs))
    prev_high = float(max(prev_highs))
    current_rsi_high = float(max(recent_rsi))
    prev_rsi_high = float(max(prev_rsi))

    bearish_div = current_high > prev_high and current_rsi_high < prev_rsi_high
    if bearish_div or rsi > 70:
        detail = (
            f"Bearish divergence (RSI: {rsi:.1f})"
            if bearish_div
            else f"Overbought (RSI: {rsi:.1f})"
        )
        return LocalSignal("RSI Divergence", round(rsi, 2), "sell", detail)

    return LocalSignal("RSI Divergence", round(rsi, 2), "neutral", f"RSI: {rsi:.1f}")


# ---------------------------------------------------------------------------
# MRI — TD Sequential (hand-rolled)
# ---------------------------------------------------------------------------

def _td_sequential(candles: list[OHLCV]) -> tuple[int, bool, bool]:
    """
    Hand-rolled TD Sequential Setup phase.
    Returns (count, buy_setup_complete, sell_setup_complete).

    Buy Setup: 9 consecutive closes < close[4 bars earlier]
    Sell Setup: 9 consecutive closes > close[4 bars earlier]
    """
    if len(candles) < 5:
        return 0, False, False

    buy_count = 0
    sell_count = 0
    buy_setup = False
    sell_setup = False

    for i in range(4, len(candles)):
        if candles[i].close < candles[i - 4].close:
            buy_count += 1
            sell_count = 0
            if buy_count >= 9:
                buy_setup = True
        elif candles[i].close > candles[i - 4].close:
            sell_count += 1
            buy_count = 0
            if sell_count >= 9:
                sell_setup = True
        else:
            buy_count = 0
            sell_count = 0

    current_count = buy_count if buy_count > 0 else -sell_count
    return current_count, buy_setup, sell_setup


def calc_mri(candles: list[OHLCV]) -> LocalSignal:
    count, buy_setup, sell_setup = _td_sequential(candles)

    if buy_setup:
        return LocalSignal("MRI", 9, "buy", "TD Buy Setup complete (9-count)")
    if sell_setup:
        return LocalSignal("MRI", -9, "sell", "TD Sell Setup complete (9-count)")

    if count > 0:
        return LocalSignal("MRI", count, "neutral", f"TD Buy Setup: {count}/9")
    if count < 0:
        return LocalSignal("MRI", count, "neutral", f"TD Sell Setup: {abs(count)}/9")

    return LocalSignal("MRI", 0, "neutral", "No active TD count")


# ---------------------------------------------------------------------------
# Chameleon — volatility contraction + trend alignment
# ---------------------------------------------------------------------------

def calc_chameleon(candles: list[OHLCV]) -> LocalSignal:
    df = _candles_to_df(candles)

    atr_series = ta.atr(df["high"], df["low"], df["close"], length=14)
    if atr_series is None or atr_series.dropna().shape[0] < 20:
        return LocalSignal("Chameleon", 0, "neutral", "Insufficient data")

    atr_sma = ta.sma(atr_series, length=20)
    sma50 = ta.sma(df["close"], length=50)
    sma200 = ta.sma(df["close"], length=200)

    if any(s is None or s.dropna().empty for s in [atr_sma, sma50, sma200]):
        return LocalSignal("Chameleon", 0, "neutral", "Insufficient data")

    current_atr = float(atr_series.iloc[-1])
    current_atr_sma = float(atr_sma.iloc[-1])
    current_sma50 = float(sma50.iloc[-1])
    current_sma200 = float(sma200.iloc[-1])
    current_price = float(df["close"].iloc[-1])

    vol_contraction = current_atr < current_atr_sma * 0.8
    bullish_trend = current_sma50 > current_sma200
    above_trend = current_price > current_sma50
    bearish_trend = current_sma50 < current_sma200
    below_trend = current_price < current_sma50

    if vol_contraction and bullish_trend and above_trend:
        return LocalSignal(
            "Chameleon",
            1,
            "buy",
            f"Vol contraction + bullish trend (ATR: {current_atr:.0f} < {current_atr_sma * 0.8:.0f})",
        )

    if vol_contraction and bearish_trend and below_trend:
        return LocalSignal(
            "Chameleon", -1, "sell", "Vol contraction + bearish trend"
        )

    details = ", ".join([
        "Vol contracted" if vol_contraction else "Vol expanded",
        "Bullish trend" if bullish_trend else "Bearish trend",
        "Above SMA50" if above_trend else "Below SMA50",
    ])
    return LocalSignal("Chameleon", 0, "neutral", details)


# ---------------------------------------------------------------------------
# Combined analysis
# ---------------------------------------------------------------------------

def analyze_local(asset: str, candles: list[OHLCV]) -> LocalAnalysis:
    price = candles[-1].close if candles else 0.0
    signals = [
        calc_chameleon(candles),
        calc_mri(candles),
        calc_rsi_divergence(candles),
    ]
    buy_count = sum(1 for s in signals if s.signal == "buy")

    return LocalAnalysis(
        asset=asset,
        price=price,
        timestamp=datetime.now(timezone.utc),
        signals=signals,
        score=buy_count,
        total=len(signals),
    )
