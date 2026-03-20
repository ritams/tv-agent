"""Bar replay backtester — drives TradingView bar replay via Playwright."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from playwright.async_api import Page

from ..indicators.indicator_reader import IndicatorReader
from ..indicators.scoring import ChartSnapshot, ScoredSignal, score_snapshot


@dataclass
class BacktestConfig:
    symbol: str
    bars: int
    timeframe: str


@dataclass
class Trade:
    entry_date: datetime
    entry_price: float
    exit_date: datetime | None = None
    exit_price: float | None = None
    signal_level: str = ""
    pnl_percent: float | None = None


@dataclass
class BacktestStats:
    total_signals: int = 0
    big_buys: int = 0
    partial_buys: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    max_drawdown: float = 0.0
    total_return: float = 0.0


@dataclass
class BacktestResult:
    config: BacktestConfig
    signals: list[ScoredSignal]
    trades: list[Trade]
    stats: BacktestStats


class Backtester:
    def __init__(self, page: Page) -> None:
        self._page = page
        self._reader = IndicatorReader(page)

    async def run(self, cfg: BacktestConfig) -> BacktestResult:
        print(f"\nStarting backtest: {cfg.symbol} | {cfg.timeframe} | {cfg.bars} bars")

        await self._reader.open_chart(cfg.symbol)
        await self._set_timeframe(cfg.timeframe)
        await self._page.wait_for_timeout(2000)

        await self._enable_bar_replay()
        await self._go_to_start(cfg.bars)

        snapshots: list[ChartSnapshot] = []
        signals: list[ScoredSignal] = []

        for i in range(cfg.bars):
            if i % 50 == 0:
                print(f"  Bar {i}/{cfg.bars}...")

            try:
                snap = await self._reader.snapshot(cfg.symbol)
                snapshots.append(snap)
                scored = score_snapshot(snap)
                if scored.level != "none":
                    signals.append(scored)
            except Exception as e:
                print(f"  Warning: Error reading bar {i}: {e}")

            await self._step_forward()
            await self._page.wait_for_timeout(300)

        await self._disable_bar_replay()

        trades = self._simulate_trades(signals, snapshots)
        stats = self._calculate_stats(signals, trades)
        result = BacktestResult(config=cfg, signals=signals, trades=trades, stats=stats)

        self._save_results(result)
        print(f"\nBacktest complete: {cfg.symbol}")
        self._print_stats(stats)
        return result

    async def _set_timeframe(self, tf: str) -> None:
        tf_map = {
            "1m": "1", "5m": "5", "15m": "15", "30m": "30",
            "1H": "60", "4H": "240",
            "1D": "D", "1W": "W", "1M": "M",
        }
        tf_value = tf_map.get(tf, tf)

        tf_button = self._page.locator('[data-name="date-ranges-dialog"]').first
        try:
            if await tf_button.is_visible():
                await tf_button.click()
                await self._page.wait_for_timeout(500)
                option = self._page.locator(f'[data-value="{tf_value}"]').first
                if await option.is_visible():
                    await option.click()
                    await self._page.wait_for_timeout(2000)
                    return
        except Exception:
            pass

        await self._page.keyboard.press(",")
        await self._page.wait_for_timeout(300)
        await self._page.keyboard.type(tf_value)
        await self._page.keyboard.press("Enter")
        await self._page.wait_for_timeout(2000)

    async def _enable_bar_replay(self) -> None:
        print("  -> Enabling bar replay...")

        replay_btn = self._page.locator(
            '[data-name="replay"], [data-tooltip="Bar Replay"], button[aria-label*="Replay"]'
        ).first

        try:
            if await replay_btn.is_visible():
                await replay_btn.click()
                await self._page.wait_for_timeout(1000)
            else:
                toolbar_btns = await self._page.locator('[class*="toolbar"] button').all()
                for btn in toolbar_btns:
                    text = await btn.get_attribute("aria-label") or ""
                    tooltip = await btn.get_attribute("data-tooltip") or ""
                    if "replay" in text.lower() or "replay" in tooltip.lower():
                        await btn.click()
                        await self._page.wait_for_timeout(1000)
                        break
        except Exception:
            pass

        chart_area = self._page.locator('[class*="chart-markup-table"], canvas').first
        box = await chart_area.bounding_box()
        if box:
            await chart_area.click(
                force=True, position={"x": box["width"] * 0.1, "y": box["height"] / 2}
            )
            await self._page.wait_for_timeout(1000)

        print("  Bar replay enabled")

    async def _go_to_start(self, bars: int) -> None:
        print(f"  -> Positioning {bars} bars back...")

    async def _step_forward(self) -> None:
        await self._page.keyboard.down("Shift")
        await self._page.keyboard.press("ArrowRight")
        await self._page.keyboard.up("Shift")

    async def _disable_bar_replay(self) -> None:
        exit_btn = self._page.locator(
            '[data-name="replay-exit"], [data-tooltip*="Exit replay"], button:has-text("Exit Replay")'
        ).first
        try:
            if await exit_btn.is_visible():
                await exit_btn.click()
        except Exception:
            pass
        await self._page.wait_for_timeout(1000)

    def _simulate_trades(
        self, signals: list[ScoredSignal], snapshots: list[ChartSnapshot]
    ) -> list[Trade]:
        trades: list[Trade] = []
        hold_bars = 10

        for signal in signals:
            entry_idx = next(
                (
                    j
                    for j, s in enumerate(snapshots)
                    if s.timestamp >= signal.timestamp
                ),
                -1,
            )
            if entry_idx == -1:
                continue

            exit_idx = min(entry_idx + hold_bars, len(snapshots) - 1)
            exit_snap = snapshots[exit_idx]

            pnl = ((exit_snap.price - signal.price) / signal.price * 100) if signal.price else None

            trades.append(
                Trade(
                    entry_date=signal.timestamp,
                    entry_price=signal.price,
                    exit_date=exit_snap.timestamp,
                    exit_price=exit_snap.price,
                    signal_level=signal.level,
                    pnl_percent=pnl,
                )
            )
        return trades

    def _calculate_stats(
        self, signals: list[ScoredSignal], trades: list[Trade]
    ) -> BacktestStats:
        completed = [t for t in trades if t.pnl_percent is not None]
        wins = [t for t in completed if (t.pnl_percent or 0) > 0]
        returns = [t.pnl_percent or 0 for t in completed]

        max_dd = 0.0
        peak = 0.0
        cum = 0.0
        for r in returns:
            cum += r
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        return BacktestStats(
            total_signals=len(signals),
            big_buys=sum(1 for s in signals if s.level == "big_buy"),
            partial_buys=sum(1 for s in signals if s.level == "partial_buy"),
            win_rate=(len(wins) / len(completed) * 100) if completed else 0,
            avg_return=(sum(returns) / len(returns)) if returns else 0,
            max_drawdown=max_dd,
            total_return=cum,
        )

    def _print_stats(self, stats: BacktestStats) -> None:
        print(f"  Total Signals: {stats.total_signals}")
        print(f"     Big Buys: {stats.big_buys}")
        print(f"     Partial Buys: {stats.partial_buys}")
        print(f"     Win Rate: {stats.win_rate:.1f}%")
        print(f"     Avg Return: {stats.avg_return:.2f}%")
        print(f"     Max Drawdown: {stats.max_drawdown:.2f}%")
        print(f"     Total Return: {stats.total_return:.2f}%")

    def _save_results(self, result: BacktestResult) -> None:
        d = "./backtest-results"
        os.makedirs(d, exist_ok=True)
        ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        filename = f"{d}/{result.config.symbol}-{result.config.timeframe}-{ts}.json"

        # Serialize dataclasses to JSON-compatible dict
        data = {
            "config": {"symbol": result.config.symbol, "bars": result.config.bars, "timeframe": result.config.timeframe},
            "signals": [
                {"asset": s.asset, "level": s.level, "score": s.score, "total": s.total,
                 "price": s.price, "timestamp": s.timestamp.isoformat(), "details": s.details}
                for s in result.signals
            ],
            "trades": [
                {"entry_date": t.entry_date.isoformat(), "entry_price": t.entry_price,
                 "exit_date": t.exit_date.isoformat() if t.exit_date else None,
                 "exit_price": t.exit_price, "signal_level": t.signal_level,
                 "pnl_percent": t.pnl_percent}
                for t in result.trades
            ],
            "stats": {
                "total_signals": result.stats.total_signals, "big_buys": result.stats.big_buys,
                "partial_buys": result.stats.partial_buys, "win_rate": result.stats.win_rate,
                "avg_return": result.stats.avg_return, "max_drawdown": result.stats.max_drawdown,
                "total_return": result.stats.total_return,
            },
        }
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  Results saved: {filename}")
