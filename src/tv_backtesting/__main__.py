"""
Main entry point for the Technicals Agent.

Usage:
  uv run python -m tv_backtesting signal              # Mode 1: Jamie Coutts signal check
  uv run python -m tv_backtesting signal --local      # Mode 1: Local only (no browser)
  uv run python -m tv_backtesting backtest BTCUSD     # Mode 2: Backtest a specific asset
  uv run python -m tv_backtesting optimize BTCUSD     # Mode 2: Optimize strategy for asset
  uv run python -m tv_backtesting explore BTCUSD      # Mode 2: Explore all indicator combos
  uv run python -m tv_backtesting agent [--local] [--once]  # Full agent with scheduling
  uv run python -m tv_backtesting serve [--port 8000]       # HTTP API server for OpenClaw
"""

from __future__ import annotations

import asyncio
import sys


def main() -> None:
    args = sys.argv[1:]

    if not args:
        print("""
Usage:
  python -m tv_backtesting signal [--local]        Check Jamie Coutts signals (BTC + HYPE)
  python -m tv_backtesting backtest <SYMBOL>       Backtest with bar replay
  python -m tv_backtesting optimize <SYMBOL>       Optimize Jamie Coutts params
  python -m tv_backtesting explore <SYMBOL>        Explore indicator combinations
  python -m tv_backtesting agent [--local] [--once] Full agent with scheduling
  python -m tv_backtesting serve [--port 8000]      HTTP API server for OpenClaw
        """)
        return

    mode = args[0]

    if mode == "agent":
        from .agent.run import run_agent
        run_agent(args[1:])
        return

    if mode == "serve":
        from .api import run_server
        port = 8000
        if "--port" in args:
            idx = args.index("--port")
            if idx + 1 < len(args):
                port = int(args[idx + 1])
        run_server(port=port)
        return

    if mode == "signal":
        asyncio.run(_signal_mode("--local" in args))
    elif mode == "backtest":
        asset = args[1] if len(args) > 1 else None
        if not asset:
            print("Usage: python -m tv_backtesting backtest <SYMBOL> [--bars 100] [--hold 10]")
            sys.exit(1)
        bars_count = 100
        hold = 10
        if "--bars" in args:
            idx = args.index("--bars")
            if idx + 1 < len(args):
                bars_count = int(args[idx + 1])
        if "--hold" in args:
            idx = args.index("--hold")
            if idx + 1 < len(args):
                hold = int(args[idx + 1])
        asyncio.run(_backtest_mode(asset, bars_count, hold))
    elif mode == "optimize":
        asset = args[1] if len(args) > 1 else None
        if not asset:
            print("Usage: python -m tv_backtesting optimize <SYMBOL>")
            sys.exit(1)
        asyncio.run(_optimize_mode(asset))
    elif mode == "explore":
        asset = args[1] if len(args) > 1 else None
        if not asset:
            print("Usage: python -m tv_backtesting explore <SYMBOL>")
            sys.exit(1)
        asyncio.run(_explore_mode(asset))
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)


async def _signal_mode(local_only: bool) -> None:
    if local_only:
        from .data.market_data import MarketData, to_exchange_symbol
        from .data.local_indicators import analyze_local

        md = MarketData("binance")
        try:
            print("\n=== Jamie Coutts Signal Check (local) ===\n")
            for asset in ["BTCUSD", "HYPEUSD"]:
                symbol = to_exchange_symbol(asset)
                print(f"\nChecking {asset} ({symbol})...")
                candles = await md.get_ohlcv(symbol, "1d", 300)
                analysis = analyze_local(asset, candles)

                print(f"Price: ${analysis.price:,.0f}")
                for sig in analysis.signals:
                    icon = {"buy": "\U0001f7e2", "sell": "\U0001f534"}.get(sig.signal, "\u26aa")
                    print(f"  {icon} {sig.name}: {sig.details}")
                print(f"Score: {analysis.score}/{analysis.total}")

                if analysis.score >= 3:
                    print("\U0001f7e2 BIG BUY")
                elif analysis.score >= 2:
                    print("\U0001f7e1 PARTIAL BUY")
                else:
                    print("\u26aa NO SIGNAL")
        finally:
            await md.close()
    else:
        from .auth.tradingview_auth import TradingViewAuth
        from .indicators.indicator_reader import IndicatorReader
        from .indicators.scoring import score_snapshot, format_signal

        auth = TradingViewAuth()
        try:
            _, _, page = await auth.launch()
            reader = IndicatorReader(page)

            print("\n=== Jamie Coutts Signal Check ===\n")
            for symbol in ["BTCUSD", "HYPEUSD"]:
                print(f"\nChecking {symbol}...")
                await reader.open_chart(symbol)
                await page.wait_for_timeout(3000)

                snapshot = await reader.snapshot(symbol)
                signal = score_snapshot(snapshot)
                print(format_signal(signal))
                print()

            print("\nDone. Browser staying open for 10s...")
            await page.wait_for_timeout(10_000)
        except Exception as e:
            print(f"Fatal error: {e}")
        finally:
            await auth.close()


async def _backtest_mode(asset: str, bars: int = 100, hold: int = 10) -> None:
    from .auth.tradingview_auth import TradingViewAuth
    from .backtester.backtester import Backtester

    auth = TradingViewAuth()
    try:
        _, _, page = await auth.launch()
        bt = Backtester(page)
        await bt.run(symbol=asset, bars=bars, hold_bars=hold)
        print("\nDone. Browser staying open for 5s...")
        await page.wait_for_timeout(5_000)
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        await auth.close()


async def _optimize_mode(asset: str) -> None:
    from .auth.tradingview_auth import TradingViewAuth
    from .indicators.indicator_reader import IndicatorReader
    from .backtester.optimizer import StrategyOptimizer

    auth = TradingViewAuth()
    try:
        _, _, page = await auth.launch()
        reader = IndicatorReader(page)
        await reader.open_chart(asset)
        optimizer = StrategyOptimizer(page)
        await optimizer.optimize_jamie_coutts(asset)
        print("\nDone. Browser staying open for 10s...")
        await page.wait_for_timeout(10_000)
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        await auth.close()


async def _explore_mode(asset: str) -> None:
    from .auth.tradingview_auth import TradingViewAuth
    from .indicators.indicator_reader import IndicatorReader
    from .backtester.optimizer import StrategyOptimizer

    auth = TradingViewAuth()
    try:
        _, _, page = await auth.launch()
        reader = IndicatorReader(page)
        await reader.open_chart(asset)
        optimizer = StrategyOptimizer(page)
        await optimizer.explore_combinations(asset)
        print("\nDone. Browser staying open for 10s...")
        await page.wait_for_timeout(10_000)
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        await auth.close()


if __name__ == "__main__":
    main()
