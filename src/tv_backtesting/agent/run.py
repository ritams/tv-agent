"""
Agent runner — entry point for the Technicals Agent.

Usage:
  uv run python -m tv_backtesting agent                  # Full agent (local + TV, scheduled)
  uv run python -m tv_backtesting agent --once           # Single run, then exit
  uv run python -m tv_backtesting agent --local          # Local only (no browser)
  uv run python -m tv_backtesting agent --local --once   # Quick local check, no browser
  uv run python -m tv_backtesting agent --tv             # TradingView only
"""

from __future__ import annotations

import asyncio
import signal
import sys

from .technicals_agent import TechnicalsAgent, AgentConfig


def run_agent(argv: list[str] | None = None) -> None:
    args = argv or sys.argv[1:]

    cfg = AgentConfig(assets=["BTCUSD", "HYPEUSD"])

    if "--local" in args:
        cfg.use_local = True
        cfg.use_tradingview = False

    if "--tv" in args:
        cfg.use_local = False
        cfg.use_tradingview = True

    if "--backtest" in args:
        cfg.mode = "backtest"

    if "--signal" in args:
        cfg.mode = "signal"

    agent = TechnicalsAgent(cfg)

    async def _run() -> None:
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, lambda: asyncio.create_task(agent.stop()))

        if "--once" in args:
            await agent.run_once()
            await agent.stop()
        else:
            await agent.start()
            # Keep running until interrupted
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass
            finally:
                await agent.stop()

    asyncio.run(_run())
