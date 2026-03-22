"""
Optimized bar replay backtester using real TradingView indicators.

How it works:
1. Opens a chart for the given asset (e.g., BTCUSD)
2. Enables TradingView's "Bar Replay" — rewinds the chart to the past
3. Steps forward one bar at a time (each bar = 1 day on daily chart)
4. At each bar, reads every indicator's signal from the chart legend
5. After collecting all bars, simulates trades per-indicator and ranks them

This reads the ACTUAL invite-only indicator signals, not approximations.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from playwright.async_api import Page

from ..indicators.indicator_reader import IndicatorReader


@dataclass
class BarData:
    bar: int
    price: float
    signals: dict[str, str]  # indicator_name -> "buy"|"sell"|"neutral"


@dataclass
class IndicatorResult:
    name: str
    trades: int
    wins: int
    win_rate: float
    avg_return: float
    total_return: float
    max_drawdown: float
    buy_bars: int
    sell_bars: int


@dataclass
class ReplayBacktestResult:
    symbol: str
    timeframe: str
    total_bars: int
    hold_bars: int
    bar_data: list[BarData]
    indicator_results: list[IndicatorResult]


class Backtester:
    def __init__(self, page: Page) -> None:
        self._page = page
        self._reader = IndicatorReader(page)

    async def run(
        self,
        symbol: str,
        bars: int = 100,
        timeframe: str = "1D",
        hold_bars: int = 10,
        target_indicators: list[str] | None = None,
    ) -> ReplayBacktestResult:
        """
        Run a bar replay backtest on the given symbol.

        Args:
            symbol: Asset ticker (e.g., "BTCUSD")
            bars: Number of bars to replay through
            timeframe: Chart timeframe (e.g., "1D", "4H")
            hold_bars: How many bars to hold a trade before exiting
            target_indicators: Only track these indicators (None = all)
        """
        print(f"\n{'='*60}")
        print(f"  Bar Replay Backtest")
        print(f"  {symbol} | {timeframe} | {bars} bars | hold={hold_bars}")
        print(f"{'='*60}\n")

        # Step 1: Open chart
        print("  [1/5] Opening chart...")
        await self._reader.open_chart(symbol)
        await self._set_timeframe(timeframe)
        await self._page.wait_for_timeout(2000)

        # Step 2: Enable bar replay and position
        print("  [2/5] Enabling bar replay...")
        await self._enable_bar_replay()

        # Step 3: Collect data bar by bar
        print(f"  [3/5] Replaying {bars} bars...")
        bar_data = await self._collect_bars(symbol, bars, target_indicators)

        # Step 4: Exit replay
        print("  [4/5] Exiting replay...")
        await self._disable_bar_replay()

        # Step 5: Analyze results
        print("  [5/5] Analyzing...")
        indicator_results = self._analyze(bar_data, hold_bars)

        result = ReplayBacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            total_bars=len(bar_data),
            hold_bars=hold_bars,
            bar_data=bar_data,
            indicator_results=indicator_results,
        )

        self._print_results(result)
        self._save_results(result)

        return result

    async def _collect_bars(
        self,
        symbol: str,
        bars: int,
        target_indicators: list[str] | None,
    ) -> list[BarData]:
        """Step through bars and read indicator signals. Optimized for speed."""
        data: list[BarData] = []

        for bar in range(bars):
            if bar % 25 == 0:
                pct = int(bar / bars * 100)
                print(f"         {bar}/{bars} ({pct}%)")

            try:
                # Read price
                price = await self._reader.get_current_price()

                # Read indicators — fast path: only read legend once
                indicators = await self._reader.read_legend_indicators()

                signals: dict[str, str] = {}
                for ind in indicators:
                    if target_indicators:
                        # Only track indicators we care about
                        if not any(t.lower() in ind.name.lower() for t in target_indicators):
                            continue
                    signals[ind.name] = ind.signal

                data.append(BarData(bar=bar, price=price, signals=signals))

            except Exception:
                pass  # skip bad bars silently

            # Step forward — minimal delay
            await self._page.keyboard.down("Shift")
            await self._page.keyboard.press("ArrowRight")
            await self._page.keyboard.up("Shift")
            await self._page.wait_for_timeout(250)

        print(f"         {bars}/{bars} (100%) — done")
        return data

    def _analyze(
        self, bar_data: list[BarData], hold_bars: int
    ) -> list[IndicatorResult]:
        """Simulate trades per-indicator and compute stats."""
        # Get all indicator names
        all_names: set[str] = set()
        for bd in bar_data:
            all_names.update(bd.signals.keys())

        results: list[IndicatorResult] = []

        for name in sorted(all_names):
            # Simulate: enter on buy, hold for hold_bars, then exit
            trades: list[float] = []
            in_trade = False
            entry_price = 0.0
            entry_bar = 0
            buy_bars = 0
            sell_bars = 0

            for bd in bar_data:
                sig = bd.signals.get(name, "neutral")
                if sig == "buy":
                    buy_bars += 1
                elif sig == "sell":
                    sell_bars += 1

                if not in_trade and sig == "buy" and bd.price > 0:
                    in_trade = True
                    entry_price = bd.price
                    entry_bar = bd.bar
                elif in_trade and bd.bar - entry_bar >= hold_bars and bd.price > 0:
                    pnl = ((bd.price - entry_price) / entry_price) * 100
                    trades.append(pnl)
                    in_trade = False

            # Stats
            total_trades = len(trades)
            wins = sum(1 for t in trades if t > 0)
            total_return = sum(trades)
            avg_return = total_return / total_trades if total_trades else 0

            # Max drawdown
            peak = 0.0
            cum = 0.0
            max_dd = 0.0
            for r in trades:
                cum += r
                if cum > peak:
                    peak = cum
                dd = peak - cum
                if dd > max_dd:
                    max_dd = dd

            results.append(IndicatorResult(
                name=name,
                trades=total_trades,
                wins=wins,
                win_rate=(wins / total_trades * 100) if total_trades else 0,
                avg_return=round(avg_return, 2),
                total_return=round(total_return, 2),
                max_drawdown=round(max_dd, 2),
                buy_bars=buy_bars,
                sell_bars=sell_bars,
            ))

        # Sort by total return descending
        results.sort(key=lambda r: r.total_return, reverse=True)
        return results

    def _print_results(self, result: ReplayBacktestResult) -> None:
        print(f"\n{'='*80}")
        print(f"  {result.symbol} — {result.total_bars} bars | hold={result.hold_bars} bars")
        print(f"{'='*80}")
        print(
            f"  {'Indicator':<42} {'Trades':>6} {'Win%':>7} "
            f"{'Avg':>8} {'Total':>8} {'MaxDD':>7} {'Buy':>4} {'Sell':>4}"
        )
        print(f"  {'-'*42} {'-'*6} {'-'*7} {'-'*8} {'-'*8} {'-'*7} {'-'*4} {'-'*4}")

        for r in result.indicator_results:
            if r.trades > 0:
                print(
                    f"  {r.name:<42} {r.trades:>6} {r.win_rate:>6.1f}% "
                    f"{r.avg_return:>+7.2f}% {r.total_return:>+7.2f}% "
                    f"{r.max_drawdown:>6.2f}% {r.buy_bars:>4} {r.sell_bars:>4}"
                )
            else:
                print(
                    f"  {r.name:<42} {'—':>6} {'—':>7} "
                    f"{'—':>8} {'—':>8} {'—':>7} {r.buy_bars:>4} {r.sell_bars:>4}"
                )

        # Best performer
        with_trades = [r for r in result.indicator_results if r.trades >= 2]
        if with_trades:
            best = with_trades[0]  # already sorted by total_return
            print(f"\n  Best: {best.name} — {best.total_return:+.2f}% total, "
                  f"{best.win_rate:.0f}% win rate, {best.trades} trades")

    def _save_results(self, result: ReplayBacktestResult) -> None:
        d = "./backtest-results"
        os.makedirs(d, exist_ok=True)
        ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        filename = f"{d}/replay-{result.symbol}-{result.timeframe}-{ts}.json"

        data = {
            "symbol": result.symbol,
            "timeframe": result.timeframe,
            "total_bars": result.total_bars,
            "hold_bars": result.hold_bars,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "indicator_results": [
                {
                    "name": r.name,
                    "trades": r.trades,
                    "wins": r.wins,
                    "win_rate": r.win_rate,
                    "avg_return": r.avg_return,
                    "total_return": r.total_return,
                    "max_drawdown": r.max_drawdown,
                    "buy_bars": r.buy_bars,
                    "sell_bars": r.sell_bars,
                }
                for r in result.indicator_results
            ],
        }
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n  Results saved: {filename}")

    # ------------------------------------------------------------------
    # TradingView controls
    # ------------------------------------------------------------------

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
        # Find the VISIBLE replay button (there may be multiple, only one is visible)
        replay_btns = await self._page.locator('button[aria-label="Bar Replay"]').all()
        for btn in replay_btns:
            try:
                if await btn.is_visible(timeout=500):
                    await btn.click()
                    await self._page.wait_for_timeout(2000)
                    break
            except Exception:
                continue

        # Click left side of chart to start replay from further back in history
        chart_area = self._page.locator("canvas").first
        box = await chart_area.bounding_box()
        if box:
            await chart_area.click(
                force=True,
                position={"x": box["width"] * 0.15, "y": box["height"] / 2},
            )
            await self._page.wait_for_timeout(2000)

    async def _disable_bar_replay(self) -> None:
        exit_btn = self._page.locator(
            '[data-name="replay-exit"], [data-tooltip*="Exit replay"], '
            'button:has-text("Exit Replay")'
        ).first
        try:
            if await exit_btn.is_visible():
                await exit_btn.click()
        except Exception:
            pass
        await self._page.wait_for_timeout(1000)
