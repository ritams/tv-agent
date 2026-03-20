"""Pine Editor automation — deploy strategies and read Strategy Tester results."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from playwright.async_api import Page


@dataclass
class StrategyTestResult:
    net_profit: float = 0.0
    net_profit_percent: float = 0.0
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    avg_trade: float = 0.0
    avg_trade_percent: float = 0.0
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    buy_and_hold_return: float | None = None


class StrategyTesterReader:
    def __init__(self, page: Page) -> None:
        self._page = page

    async def deploy_strategy(self, pine_script: str) -> None:
        print("  -> Deploying Pine Script strategy...")

        await self._open_pine_editor()
        await self._page.wait_for_timeout(2000)

        # Click inside editor (Monaco)
        view_lines = self._page.locator(".view-lines").first
        if await _vis(view_lines, 3000):
            await view_lines.click()
        else:
            editor_line = self._page.locator(".view-line").first
            if await _vis(editor_line, 3000):
                await editor_line.click()
        await self._page.wait_for_timeout(300)

        # Select all + delete
        await self._page.keyboard.press("Meta+a")
        await self._page.wait_for_timeout(200)
        await self._page.keyboard.press("Backspace")
        await self._page.wait_for_timeout(300)

        # Paste via clipboard
        print("  -> Pasting Pine Script into editor via clipboard...")
        await self._page.evaluate(
            "(code) => navigator.clipboard.writeText(code)", pine_script
        )
        await self._page.keyboard.press("Meta+v")
        await self._page.wait_for_timeout(2000)

        # Click "Add to chart"
        print("  -> Clicking Add to chart...")
        add_btn = self._page.get_by_text("Add to chart", exact=True).first
        if await _vis(add_btn, 5000):
            await add_btn.click()
            print("  Clicked Add to chart")
        else:
            add_alt = self._page.locator(
                'a:has-text("Add to chart"), span:has-text("Add to chart"), [class*="addToChart"]'
            ).first
            if await _vis(add_alt, 3000):
                await add_alt.click()
                print("  Clicked Add to chart (alt selector)")
            else:
                print("  Warning: Add to chart not found, saving instead...")
                save_btn = self._page.get_by_text("Save", exact=True).first
                if await _vis(save_btn, 3000):
                    await save_btn.click()

        await self._page.wait_for_timeout(8000)

        # Check compilation errors
        error_line = self._page.locator('[class*="error"]:visible')
        count = await error_line.count()
        if count > 0:
            text = await error_line.first.text_content() or ""
            if "error" in text.lower():
                print(f"  Warning: Pine error: {text[:200]}")

        print("  Strategy deployed to chart")

    async def _open_pine_editor(self) -> None:
        print("  -> Opening Pine Editor...")
        already_open = await _vis(self._page.locator(".view-lines").first, 1000)
        if already_open:
            print("  Pine Editor already open")
            return

        pine_btn = self._page.locator('[data-name="pine-dialog-button"]').first
        if await _vis(pine_btn, 3000):
            await pine_btn.click()
            await self._page.wait_for_timeout(2000)
            print("  Pine Editor opened")
            return

        print("  Warning: Could not find Pine Editor button")

    async def read_results(self) -> StrategyTestResult:
        print("  -> Reading Strategy Tester results...")

        tester_tab = self._page.locator(
            'button:has-text("Strategy Tester"), [data-name="backtesting"]'
        ).first
        if await _vis(tester_tab, 5000):
            await tester_tab.click()
            await self._page.wait_for_timeout(2000)
        else:
            print("  Warning: Strategy Tester tab not found")

        overview_tab = self._page.locator(
            'button:has-text("Overview"), button:has-text("Performance Summary")'
        ).first
        if await _vis(overview_tab, 3000):
            await overview_tab.click()
            await self._page.wait_for_timeout(1000)

        return await self._scrape_metrics()

    async def _scrape_metrics(self) -> StrategyTestResult:
        metrics: dict[str, str] = {}

        for sel in ["table tr", '[class*="report"] tr', '[class*="row"]']:
            rows = await self._page.locator(sel).all()
            if len(rows) < 2:
                continue
            for row in rows:
                cells = await row.locator("td, th, [class*='cell']").all()
                if len(cells) >= 2:
                    label = (await cells[0].text_content() or "").strip().lower()
                    value = (await cells[1].text_content() or "").strip()
                    if label and value:
                        metrics[label] = value
            if metrics:
                break

        if not metrics:
            all_text = await self._page.locator(
                '[class*="strategyReport"], [class*="report"], [class*="backtesting"]'
            ).first.text_content() or ""
            if all_text:
                print(f"  Strategy Tester text: {all_text[:500]}")
                for line in re.split(r"\n|(?=[A-Z][a-z])", all_text):
                    m = re.match(r"(.+?)\s*[:\s]\s*([\d.,%-]+)", line)
                    if m:
                        metrics[m.group(1).strip().lower()] = m.group(2).strip()

        print(f"  Scraped {len(metrics)} metrics")
        return _parse_metrics(metrics)

    async def remove_strategy(self) -> None:
        legend = self._page.locator(
            '[class*="item-"][class*="study-"]:has-text("Backtest"), '
            '[class*="item-"][class*="study-"]:has-text("Strategy")'
        ).first

        if await _vis(legend, 3000):
            await legend.hover(force=True)
            await self._page.wait_for_timeout(500)
            remove_btn = legend.locator(
                'button[class*="close"], button[aria-label*="Remove"], [class*="delete"]'
            ).first
            if await _vis(remove_btn, 2000):
                await remove_btn.evaluate("(el) => el.click()")
                await self._page.wait_for_timeout(1000)


def _parse_metrics(metrics: dict[str, str]) -> StrategyTestResult:
    def _num(key: str) -> float:
        for k, v in metrics.items():
            if key in k:
                return float(re.sub(r"[^0-9.\-]", "", v) or 0)
        return 0.0

    def _pct(key: str) -> float:
        for k, v in metrics.items():
            if key in k and ("%" in v or "%" in k):
                return float(re.sub(r"[^0-9.\-]", "", v) or 0)
        return 0.0

    sharpe = _num("sharpe") or None
    sortino = _num("sortino") or None
    bnh = _pct("buy & hold") or _pct("buy and hold") or None

    return StrategyTestResult(
        net_profit=_num("net profit"),
        net_profit_percent=_pct("net profit"),
        total_trades=int(_num("total") or _num("trades")),
        win_rate=_pct("win") or _pct("percent profitable"),
        profit_factor=_num("profit factor"),
        max_drawdown=_num("max drawdown"),
        max_drawdown_percent=_pct("max drawdown"),
        avg_trade=_num("avg trade"),
        avg_trade_percent=_pct("avg trade"),
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        buy_and_hold_return=bnh,
    )


async def _vis(locator, timeout: int = 3000) -> bool:
    try:
        return await locator.is_visible(timeout=timeout)
    except Exception:
        return False
