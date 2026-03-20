"""Grid search + combo explorer for strategy optimization."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from typing import Any

from playwright.async_api import Page

from .strategy_tester_reader import StrategyTesterReader, StrategyTestResult
from ..pine.templates import jamie_coutts_strategy, multi_indicator_strategy


@dataclass
class OptimizationRun:
    params: dict[str, Any]
    pine_script: str
    result: StrategyTestResult | None = None
    error: str | None = None


@dataclass
class OptimizationResult:
    symbol: str
    timeframe: str
    runs: list[OptimizationRun]
    best_run: OptimizationRun | None = None


class StrategyOptimizer:
    def __init__(self, page: Page) -> None:
        self._page = page
        self._tester = StrategyTesterReader(page)

    async def optimize_jamie_coutts(self, symbol: str) -> OptimizationResult:
        print(f"\nOptimizing Jamie Coutts strategy for {symbol}...")

        param_grid = _generate_jamie_coutts_grid()
        runs: list[OptimizationRun] = []

        for i, params in enumerate(param_grid):
            print(f"  Run {i + 1}/{len(param_grid)}: {params}")
            pine = jamie_coutts_strategy(**params)

            try:
                await self._tester.remove_strategy()
                await self._tester.deploy_strategy(pine)
                result = await self._tester.read_results()
                runs.append(OptimizationRun(params=params, pine_script=pine, result=result))
                print(
                    f"    -> Profit: {result.net_profit_percent}% | Win: {result.win_rate}% | "
                    f"PF: {result.profit_factor} | Trades: {result.total_trades}"
                )
            except Exception as e:
                print(f"    Warning: {e}")
                runs.append(OptimizationRun(params=params, pine_script=pine, error=str(e)))

            await self._page.wait_for_timeout(2000)

        successful = [r for r in runs if r.result and r.result.total_trades >= 5]
        successful.sort(key=lambda r: r.result.profit_factor if r.result else 0, reverse=True)
        best = successful[0] if successful else None

        opt_result = OptimizationResult(symbol=symbol, timeframe="1D", runs=runs, best_run=best)
        _save_results(opt_result)

        if best and best.result:
            print(f"\nBest params: {best.params}")
            print(
                f"   Profit: {best.result.net_profit_percent}% | Win: {best.result.win_rate}% | "
                f"PF: {best.result.profit_factor}"
            )

        return opt_result

    async def explore_combinations(self, symbol: str) -> OptimizationResult:
        print(f"\nExploring indicator combinations for {symbol}...")

        combos = _generate_combination_grid()
        runs: list[OptimizationRun] = []

        for i, params in enumerate(combos):
            enabled = [k.replace("use_", "") for k, v in params.items() if k.startswith("use_") and v]
            print(f"  Combo {i + 1}/{len(combos)}: [{', '.join(enabled)}]")

            pine = multi_indicator_strategy(**params)

            try:
                await self._tester.remove_strategy()
                await self._tester.deploy_strategy(pine)
                result = await self._tester.read_results()
                runs.append(OptimizationRun(params=params, pine_script=pine, result=result))
                print(
                    f"    -> Profit: {result.net_profit_percent}% | Win: {result.win_rate}% | "
                    f"PF: {result.profit_factor}"
                )
            except Exception as e:
                runs.append(OptimizationRun(params=params, pine_script=pine, error=str(e)))

            await self._page.wait_for_timeout(2000)

        successful = [r for r in runs if r.result and r.result.total_trades >= 5]
        successful.sort(key=lambda r: r.result.profit_factor if r.result else 0, reverse=True)
        best = successful[0] if successful else None

        opt_result = OptimizationResult(symbol=symbol, timeframe="1D", runs=runs, best_run=best)
        _save_results(opt_result)
        return opt_result


def _generate_jamie_coutts_grid() -> list[dict[str, Any]]:
    grid: list[dict[str, Any]] = []
    for rsi_length in [10, 14, 21]:
        for rsi_oversold in [25, 30, 35]:
            for mri_length in [8, 10, 13]:
                for min_signals in [2, 3]:
                    grid.append({
                        "rsi_length": rsi_length,
                        "rsi_oversold": rsi_oversold,
                        "mri_length": mri_length,
                        "min_signals": min_signals,
                    })
    return grid


def _generate_combination_grid() -> list[dict[str, Any]]:
    indicators = ["rsi", "mri", "chameleon", "macd", "bb"]
    combos: list[dict[str, Any]] = []

    for mask in range(1, 1 << len(indicators)):
        active = [ind for j, ind in enumerate(indicators) if mask & (1 << j)]
        if len(active) < 2:
            continue
        params: dict[str, Any] = {
            f"use_{ind}": (ind in active) for ind in indicators
        }
        params["min_signals"] = max(2, int(len(active) * 0.6))
        combos.append(params)
    return combos


def _save_results(result: OptimizationResult) -> None:
    d = "./backtest-results"
    os.makedirs(d, exist_ok=True)
    ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    filename = f"{d}/optimize-{result.symbol}-{ts}.json"

    data = {
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "runs": [
            {
                "params": r.params,
                "result": {
                    "net_profit_percent": r.result.net_profit_percent,
                    "total_trades": r.result.total_trades,
                    "win_rate": r.result.win_rate,
                    "profit_factor": r.result.profit_factor,
                } if r.result else None,
                "error": r.error,
            }
            for r in result.runs
        ],
        "best_params": result.best_run.params if result.best_run else None,
    }
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Optimization results saved: {filename}")
