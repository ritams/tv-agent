"""Chart legend scraper — reads indicator values from TradingView via Playwright."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from playwright.async_api import Page

from ..config import config
from .scoring import IndicatorValue, ChartSnapshot


class IndicatorReader:
    def __init__(self, page: Page) -> None:
        self._page = page

    async def open_chart(self, symbol: str) -> None:
        url = f"https://www.tradingview.com/chart/?symbol={symbol}"
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await self._page.wait_for_timeout(5000)
        try:
            await self._page.wait_for_selector("canvas", timeout=15_000)
        except Exception:
            print("Warning: Chart canvas not found")

    async def switch_symbol(self, symbol: str) -> None:
        symbol_btn = self._page.locator(
            '[data-name="header-toolbar-quick-search"], '
            '[class*="apply-common-tooltip"][class*="button"]:has([class*="value-JQZ0HKD4"])'
        ).first

        if await _is_visible(symbol_btn):
            await symbol_btn.click()
        else:
            symbol_text = self._page.locator(
                '#header-toolbar-symbol-search, [id*="symbol-search"]'
            ).first
            if await _is_visible(symbol_text):
                await symbol_text.click()
            else:
                await self.open_chart(symbol)
                return

        await self._page.wait_for_timeout(1000)
        search_input = self._page.locator(
            'input[data-role="search"], input[type="search"], '
            'input[placeholder*="Search"], input[class*="search"]'
        ).first
        await search_input.wait_for(state="visible", timeout=5000)
        await search_input.fill(symbol)
        await self._page.wait_for_timeout(1500)
        await self._page.keyboard.press("Enter")
        await self._page.wait_for_timeout(4000)

    async def enable_all_indicators(self) -> int:
        enabled = 0
        items = await self._page.locator(
            '[class*="item-"][class*="study-"][class*="disabled"]'
        ).all()
        print(f"  Found {len(items)} disabled indicators, enabling...")

        for item in items:
            title = await item.locator('[class*="title-"]').first.text_content() or ""
            try:
                await item.hover(force=True)
                await self._page.wait_for_timeout(300)
                vis_btn = item.locator(
                    'button[class*="hide"], button[class*="visibility"], '
                    'button[aria-label*="isibility"]'
                ).first
                if await _is_visible(vis_btn, timeout=1000):
                    await vis_btn.click(force=True)
                    await self._page.wait_for_timeout(500)
                    enabled += 1
                    print(f"    Enabled: {title.strip()}")
                else:
                    title_el = item.locator('[class*="title-"]').first
                    await title_el.dblclick(force=True)
                    await self._page.wait_for_timeout(500)
            except Exception:
                print(f"    Warning: Could not enable: {title.strip()}")

        if enabled > 0:
            await self._page.wait_for_timeout(3000)
        return enabled

    async def read_legend_indicators(self) -> list[IndicatorValue]:
        indicators: list[IndicatorValue] = []
        items = await self._page.locator('[class*="item-"][class*="study-"]').all()
        print(f"  Found {len(items)} indicator items in legend")

        for item in items:
            title_el = item.locator('[class*="title-"]').first
            name = (await title_el.text_content() or "").strip()
            if not name:
                continue

            classes = await item.get_attribute("class") or ""
            is_disabled = "disabled" in classes

            values: dict[str, str | float] = {}
            value_items = await item.locator('[class*="valueItem-"]').all()

            for i, vi in enumerate(value_items):
                text = (await vi.text_content() or "").strip()
                values[f"v{i}"] = text

                style = await vi.evaluate(
                    "(el) => { const s = getComputedStyle(el); return s.color || el.style.color || ''; }"
                )
                if style:
                    values[f"v{i}_color"] = style

                colored_span = vi.locator('[class*="value"]').first
                try:
                    span_style = await colored_span.evaluate(
                        "(el) => { const s = getComputedStyle(el); return s.color || el.style.color || ''; }"
                    )
                except Exception:
                    span_style = ""
                if span_style:
                    values[f"v{i}_span_color"] = span_style

            values["_disabled"] = "true" if is_disabled else "false"
            signal = _interpret_signal(name, values)
            indicators.append(
                IndicatorValue(name=name, values=values, signal=signal, raw=json.dumps(values))
            )

        return indicators

    async def get_current_price(self) -> float:
        main_legend = self._page.locator('[class*="legendMainSourceWrapper"]').first
        if await _is_visible(main_legend):
            text = await main_legend.text_content() or ""
            m = re.search(r"C([\d.]+)", text)
            if m:
                price = float(m.group(1))
                if price > 0:
                    return price

        value_els = await self._page.locator(
            '[class*="valueItem-"] [class*="valueTitle-"]'
        ).all()
        for el in value_els:
            text = (await el.text_content() or "").strip()
            cleaned = re.sub(r"[^0-9.]", "", text)
            if cleaned:
                num = float(cleaned)
                if num > 0:
                    return num
        return 0.0

    async def snapshot(self, asset: str) -> ChartSnapshot:
        price = await self.get_current_price()
        indicators = await self.read_legend_indicators()
        buy_count = sum(1 for i in indicators if i.signal == "buy")
        return ChartSnapshot(
            asset=asset,
            timestamp=datetime.now(timezone.utc),
            price=price,
            indicators=indicators,
            score=buy_count,
        )

    async def screenshot(self, name: str) -> str:
        d = config.screenshot_dir
        os.makedirs(d, exist_ok=True)
        ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        filepath = f"{d}/{name}-{ts}.png"
        await self._page.screenshot(path=filepath, full_page=False)
        print(f"  Screenshot: {filepath}")
        return filepath


# ---------------------------------------------------------------------------
# Signal interpretation helpers
# ---------------------------------------------------------------------------

def _interpret_signal(
    indicator_name: str, values: dict[str, str | float]
) -> str:
    name = indicator_name.lower()
    if any(k in name for k in ("chameleon", "hv v2", "lv v2")):
        return _interpret_by_color(values)
    if "mri" in name:
        return _interpret_by_color(values)
    if "rsi" in name and "divergen" in name:
        return _interpret_by_color(values)
    if name == "rsi" or name.startswith("rsi"):
        return _interpret_rsi(values)
    return "neutral"


def _interpret_by_color(values: dict[str, str | float]) -> str:
    for key, val in values.items():
        s = str(val).lower()
        if "color" not in key:
            continue
        m = re.match(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", s)
        if m:
            r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if g > 120 and g > r * 1.5:
                return "buy"
            if r > 120 and r > g * 1.5:
                return "sell"
        if any(c in s for c in ("green", "lime", "#00ff", "#0f0")):
            return "buy"
        if any(c in s for c in ("red", "#ff0000", "#f00")):
            return "sell"
    return "neutral"


def _interpret_rsi(values: dict[str, str | float]) -> str:
    for key, val in values.items():
        if key.startswith("v") and "_" not in key:
            try:
                num = float(val)
            except (ValueError, TypeError):
                continue
            if num < 30:
                return "buy"
            if num > 70:
                return "sell"
    return "neutral"


async def _is_visible(locator, timeout: int = 3000) -> bool:
    try:
        return await locator.is_visible(timeout=timeout)
    except Exception:
        return False
