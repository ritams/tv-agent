"""
Score a chart snapshot using Jamie Coutts methodology:
- 3/3 firing -> Big Buy
- 2/3 firing -> Partial Buy
- <2 firing  -> No signal
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


SignalLevel = Literal["big_buy", "partial_buy", "none"]


@dataclass
class IndicatorValue:
    name: str
    values: dict[str, str | float]
    signal: str  # "buy" | "sell" | "neutral"
    raw: str


@dataclass
class ChartSnapshot:
    asset: str
    timestamp: datetime
    price: float
    indicators: list[IndicatorValue]
    score: int


@dataclass
class ScoredSignal:
    asset: str
    level: SignalLevel
    score: int
    total: int
    price: float
    timestamp: datetime
    details: list[dict[str, str]]


def _filter_relevant_indicators(
    asset: str, indicators: list[IndicatorValue]
) -> list[IndicatorValue]:
    is_btc = "BTC" in asset.upper()
    is_hype = "HYPE" in asset.upper()

    result: list[IndicatorValue] = []
    for ind in indicators:
        name = ind.name.lower()
        if is_btc and ("chameleon" in name or "lv v2" in name):
            result.append(ind)
        elif is_hype and "hv v2" in name:
            result.append(ind)
        elif "mri" in name:
            result.append(ind)
        elif "rsi" in name and "divergen" in name:
            result.append(ind)
    return result


def score_snapshot(snapshot: ChartSnapshot) -> ScoredSignal:
    target = _filter_relevant_indicators(snapshot.asset, snapshot.indicators)
    buy_count = sum(1 for i in target if i.signal == "buy")
    total = len(target)

    level: SignalLevel = "none"
    if buy_count >= 3 or (total > 0 and buy_count == total):
        level = "big_buy"
    elif buy_count >= 2:
        level = "partial_buy"

    return ScoredSignal(
        asset=snapshot.asset,
        level=level,
        score=buy_count,
        total=total,
        price=snapshot.price,
        timestamp=snapshot.timestamp,
        details=[{"name": i.name, "signal": i.signal} for i in target],
    )


def format_signal(signal: ScoredSignal) -> str:
    if signal.level == "big_buy":
        emoji, label = "\U0001f7e2", "BIG BUY"
    elif signal.level == "partial_buy":
        emoji, label = "\U0001f7e1", "PARTIAL BUY"
    else:
        emoji, label = "\u26aa", "NO SIGNAL"

    lines = [
        f"{emoji} {signal.asset} — {label}",
        f"Price: ${signal.price:,.0f}",
        f"Score: {signal.score}/{signal.total} signals confirmed",
    ]
    for d in signal.details:
        lines.append(f"  - {d['name']}: {d['signal']}")
    return "\n".join(lines)
