"""
Automated per-indicator backtester using TradingView's Strategy Tester.

For each indicator, this:
1. Generates a Pine Script strategy replicating that indicator's logic
2. Deploys it to the Pine Editor on TradingView
3. Waits for the Strategy Tester to compute results (server-side, full history)
4. Scrapes the performance metrics
5. Removes the strategy and repeats for the next indicator

This is MUCH faster than bar replay — TradingView computes the backtest
server-side over thousands of bars in seconds.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from playwright.async_api import Page

from .strategy_tester_reader import StrategyTesterReader, StrategyTestResult
from ..pine.templates import get_indicator_strategy, get_all_indicator_names


@dataclass
class IndicatorBacktestResult:
    indicator: str
    result: StrategyTestResult | None = None
    error: str | None = None


@dataclass
class IndicatorBacktestReport:
    symbol: str
    timeframe: str
    results: list[IndicatorBacktestResult]
    best: IndicatorBacktestResult | None = None


class IndicatorBacktester:
    def __init__(self, page: Page) -> None:
        self._page = page
        self._tester = StrategyTesterReader(page)

    async def run_all(
        self, symbol: str, indicators: list[str] | None = None
    ) -> IndicatorBacktestReport:
        """Backtest each indicator individually and rank by performance."""
        names = indicators or get_all_indicator_names()

        print(f"\n{'='*60}")
        print(f"  Strategy Tester Backtest — {symbol}")
        print(f"  Testing {len(names)} indicators")
        print(f"{'='*60}\n")

        results: list[IndicatorBacktestResult] = []

        for i, name in enumerate(names):
            pine = get_indicator_strategy(name)
            if not pine:
                print(f"  [{i+1}/{len(names)}] {name}: no strategy template, skipping")
                results.append(IndicatorBacktestResult(
                    indicator=name, error="No strategy template"
                ))
                continue

            print(f"  [{i+1}/{len(names)}] {name}...")

            try:
                # Step 1: Remove any existing strategy
                await self._tester.remove_strategy()
                await self._page.wait_for_timeout(1000)

                # Step 2: Deploy the Pine strategy
                await self._tester.deploy_strategy(pine)

                # Step 3: Read Strategy Tester results
                result = await self._tester.read_results()

                results.append(IndicatorBacktestResult(
                    indicator=name, result=result
                ))

                # Print results inline
                if result.total_trades > 0:
                    print(
                        f"           Profit: {result.net_profit_percent:+.1f}% | "
                        f"Win: {result.win_rate:.1f}% | "
                        f"PF: {result.profit_factor:.2f} | "
                        f"Trades: {result.total_trades} | "
                        f"MaxDD: {result.max_drawdown_percent:.1f}%"
                    )
                else:
                    print(f"           No trades generated")

            except Exception as e:
                print(f"           Error: {e}")
                results.append(IndicatorBacktestResult(
                    indicator=name, error=str(e)
                ))

            await self._page.wait_for_timeout(2000)

        # Clean up
        await self._tester.remove_strategy()

        # Find best performer
        successful = [
            r for r in results
            if r.result and r.result.total_trades >= 3
        ]
        if successful:
            successful.sort(
                key=lambda r: r.result.profit_factor if r.result else 0,
                reverse=True
            )
            best = successful[0]
        else:
            best = None

        report = IndicatorBacktestReport(
            symbol=symbol,
            timeframe="1D",
            results=results,
            best=best,
        )

        self._print_summary(report)
        self._save_report(report)

        return report

    def _print_summary(self, report: IndicatorBacktestReport) -> None:
        print(f"\n{'='*60}")
        print(f"  Results Summary — {report.symbol}")
        print(f"{'='*60}")
        print(
            f"  {'Indicator':<35} {'Profit':>8} {'Win%':>7} {'PF':>6} "
            f"{'Trades':>7} {'MaxDD':>7}"
        )
        print(f"  {'-'*35} {'-'*8} {'-'*7} {'-'*6} {'-'*7} {'-'*7}")

        for r in sorted(
            report.results,
            key=lambda x: x.result.profit_factor if x.result and x.result.total_trades >= 3 else -999,
            reverse=True,
        ):
            if r.result and r.result.total_trades > 0:
                print(
                    f"  {r.indicator:<35} "
                    f"{r.result.net_profit_percent:>+7.1f}% "
                    f"{r.result.win_rate:>6.1f}% "
                    f"{r.result.profit_factor:>5.2f} "
                    f"{r.result.total_trades:>7} "
                    f"{r.result.max_drawdown_percent:>6.1f}%"
                )
            elif r.error:
                print(f"  {r.indicator:<35} {'ERROR':>8} — {r.error[:30]}")
            else:
                print(f"  {r.indicator:<35} {'—':>8} no trades")

        if report.best and report.best.result:
            print(f"\n  Best: {report.best.indicator}")
            print(
                f"    Profit: {report.best.result.net_profit_percent:+.1f}% | "
                f"PF: {report.best.result.profit_factor:.2f} | "
                f"Win: {report.best.result.win_rate:.1f}%"
            )

    def _save_report(self, report: IndicatorBacktestReport) -> None:
        d = "./backtest-results"
        os.makedirs(d, exist_ok=True)
        ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        filename = f"{d}/indicators-{report.symbol}-{ts}.json"

        data = {
            "symbol": report.symbol,
            "timeframe": report.timeframe,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results": [
                {
                    "indicator": r.indicator,
                    "result": {
                        "net_profit_percent": r.result.net_profit_percent,
                        "total_trades": r.result.total_trades,
                        "win_rate": r.result.win_rate,
                        "profit_factor": r.result.profit_factor,
                        "max_drawdown_percent": r.result.max_drawdown_percent,
                        "avg_trade_percent": r.result.avg_trade_percent,
                        "sharpe_ratio": r.result.sharpe_ratio,
                    } if r.result else None,
                    "error": r.error,
                }
                for r in report.results
            ],
            "best": report.best.indicator if report.best else None,
        }

        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n  Report saved: {filename}")
