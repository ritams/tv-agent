"""
Technicals Agent — the main autonomous agent.

Two modes:
  Mode 1 (signal):    Check Jamie Coutts indicators, score, alert
  Mode 2 (backtest):  Run backtests, find best strategies, rank them
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..config import config
from ..data.market_data import MarketData, to_exchange_symbol
from ..data.local_indicators import analyze_local, LocalAnalysis
from ..auth.tradingview_auth import TradingViewAuth
from ..indicators.indicator_reader import IndicatorReader
from ..indicators.scoring import score_snapshot, format_signal
from .webhook_receiver import WebhookReceiver, WebhookSignal


AgentMode = Literal["signal", "backtest", "both"]


@dataclass
class AgentConfig:
    mode: AgentMode = "both"
    assets: list[str] = field(default_factory=lambda: ["BTCUSD", "HYPEUSD"])
    signal_schedule_hours: int = 4
    backtest_schedule_hours: int = 24
    use_tradingview: bool = True
    use_local: bool = True


class TechnicalsAgent:
    def __init__(self, cfg: AgentConfig | None = None) -> None:
        self._cfg = cfg or AgentConfig()
        self._market_data = MarketData("binance")
        self._tv_auth: TradingViewAuth | None = None
        self._webhook: WebhookReceiver | None = None
        self._scheduler: AsyncIOScheduler | None = None
        self._running = False

    async def start(self) -> None:
        print("\nTechnicals Agent starting...")
        print(f"   Mode: {self._cfg.mode}")
        print(f"   Assets: {', '.join(self._cfg.assets)}")
        print(f"   Local indicators: {self._cfg.use_local}")
        print(f"   TradingView: {self._cfg.use_tradingview}")
        self._running = True

        # Start webhook receiver
        self._webhook = WebhookReceiver(3000)
        await self._webhook.start()
        self._webhook.on("signal", lambda s: print(
            f"\nTV Alert: {s.ticker} — {s.indicator}: {s.signal}"
        ))

        # Run immediately
        if self._cfg.mode in ("signal", "both"):
            await self._run_signal_check()

        # Set up scheduler
        self._scheduler = AsyncIOScheduler()
        if self._cfg.mode in ("signal", "both"):
            self._scheduler.add_job(
                self._run_signal_check, "interval",
                hours=self._cfg.signal_schedule_hours, id="signal_check",
            )
            print(f"   Signal schedule: every {self._cfg.signal_schedule_hours}h")

        if self._cfg.mode in ("backtest", "both"):
            self._scheduler.add_job(
                self._run_backtest, "interval",
                hours=self._cfg.backtest_schedule_hours, id="backtest_run",
            )
            print(f"   Backtest schedule: every {self._cfg.backtest_schedule_hours}h")

        self._scheduler.start()
        print("\nAgent running. Press Ctrl+C to stop.\n")

    async def run_once(self) -> None:
        print("\nRunning single signal check...\n")
        await self._run_signal_check()
        if self._cfg.mode in ("backtest", "both"):
            await self._run_backtest()

    # ------------------------------------------------------------------
    async def _run_signal_check(self) -> None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        print(f"\n=== Signal Check @ {ts} ===\n")

        for asset in self._cfg.assets:
            try:
                local_result: LocalAnalysis | None = None
                if self._cfg.use_local:
                    local_result = await self._run_local_analysis(asset)

                tv_result = None
                if self._cfg.use_tradingview:
                    tv_result = await self._run_tv_analysis(asset)

                self._print_combined_result(asset, local_result, tv_result)
            except Exception as e:
                print(f"  Warning: Error analyzing {asset}: {e}")

    async def _run_local_analysis(self, asset: str) -> LocalAnalysis:
        symbol = to_exchange_symbol(asset)
        print(f"  {asset} — Local analysis ({symbol})...")

        candles = await self._market_data.get_ohlcv(symbol, "1d", 300)
        analysis = analyze_local(asset, candles)

        print(f"     Price: ${analysis.price:,.0f}")
        for sig in analysis.signals:
            icon = {"buy": "\U0001f7e2", "sell": "\U0001f534"}.get(sig.signal, "\u26aa")
            print(f"     {icon} {sig.name}: {sig.details}")
        print(f"     Score: {analysis.score}/{analysis.total}")

        return analysis

    async def _run_tv_analysis(self, asset: str):
        print(f"  {asset} — TradingView analysis...")
        try:
            if not self._tv_auth:
                self._tv_auth = TradingViewAuth()
            _, _, page = await self._tv_auth.launch()
            reader = IndicatorReader(page)

            await reader.open_chart(asset)
            snapshot = await reader.snapshot(asset)
            signal = score_snapshot(snapshot)

            print(f"     {format_signal(signal)}")
            return signal
        except Exception as e:
            print(f"     Warning: TV analysis failed: {e}")
            return None

    def _print_combined_result(self, asset: str, local: LocalAnalysis | None, tv) -> None:
        if local:
            if local.score >= 3:
                level = "\U0001f7e2 BIG BUY"
            elif local.score >= 2:
                level = "\U0001f7e1 PARTIAL BUY"
            else:
                level = "\u26aa NO SIGNAL"
        else:
            level = "NO DATA"

        local_score = local.score if local else 0
        local_total = local.total if local else 0
        print(f"\n  ==== {asset}: {level} ({local_score}/{local_total} local) ====\n")

    # ------------------------------------------------------------------
    async def _run_backtest(self) -> None:
        print("\n=== Backtest Run ===\n")

        for asset in self._cfg.assets:
            try:
                await self._run_local_backtest(asset)
            except Exception as e:
                print(f"  Warning: Backtest error for {asset}: {e}")

    async def _run_local_backtest(self, asset: str) -> None:
        symbol = to_exchange_symbol(asset)
        print(f"  Backtesting {asset} ({symbol})...")

        candles = await self._market_data.get_ohlcv(symbol, "1d", 500)
        if len(candles) < 200:
            print(f"     Warning: Not enough data ({len(candles)} candles)")
            return

        trades: list[dict] = []
        hold_bars = 10
        in_trade = False
        entry_price = 0.0
        entry_bar = 0

        for i in range(200, len(candles)):
            slc = candles[: i + 1]
            analysis = analyze_local(asset, slc)

            if not in_trade and analysis.score >= 2:
                in_trade = True
                entry_price = candles[i].close
                entry_bar = i
            elif in_trade and i - entry_bar >= hold_bars:
                exit_price = candles[i].close
                pnl = ((exit_price - entry_price) / entry_price) * 100
                trades.append({"entry": entry_price, "exit": exit_price, "pnl": pnl})
                in_trade = False

        wins = [t for t in trades if t["pnl"] > 0]
        total_return = sum(t["pnl"] for t in trades)
        avg_return = total_return / len(trades) if trades else 0
        win_rate = (len(wins) / len(trades) * 100) if trades else 0

        print(f"     Trades: {len(trades)}")
        print(f"     Win Rate: {win_rate:.1f}%")
        print(f"     Avg Return: {avg_return:.2f}%")
        print(f"     Total Return: {total_return:.2f}%")

    # ------------------------------------------------------------------
    async def stop(self) -> None:
        self._running = False
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
        if self._tv_auth:
            await self._tv_auth.close()
        if self._webhook:
            await self._webhook.stop()
        await self._market_data.close()
        print("\nAgent stopped.")
