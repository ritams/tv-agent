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

    async def read_legend_indicators(self, verbose: bool = False) -> list[IndicatorValue]:
        indicators: list[IndicatorValue] = []
        items = await self._page.locator('[class*="item-"][class*="study-"]').all()
        if verbose:
            print(f"  Found {len(items)} indicator items in legend")

        for item in items:
            title_el = item.locator('[class*="title-"]').first
            try:
                name = (await title_el.text_content(timeout=2000) or "").strip()
            except Exception:
                continue
            if not name:
                continue

            classes = await item.get_attribute("class") or ""
            is_disabled = "disabled" in classes

            values: dict[str, str | float] = {}
            value_items = await item.locator('[class*="valueItem-"]').all()

            for i, vi in enumerate(value_items):
                try:
                    text = (await vi.text_content(timeout=1000) or "").strip()
                except Exception:
                    text = ""
                values[f"v{i}"] = text

                try:
                    style = await vi.evaluate(
                        "(el) => { const s = getComputedStyle(el); return s.color || el.style.color || ''; }"
                    )
                except Exception:
                    style = ""
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
            # Legend text: "...O69,921H71,356L69,399C69,75669,756∅..."
            # C value runs into a duplicate. Use OHLC group and trim C by L's length.
            m = re.search(r"O([\d,.]+)H([\d,.]+)L([\d,.]+)C([\d,.]+)", text)
            if m:
                close_raw = m.group(4)
                ref_len = len(m.group(3))  # L value has same digit structure
                close_trimmed = close_raw[:ref_len]
                try:
                    price = float(close_trimmed.replace(",", ""))
                    if price > 0:
                        return price
                except ValueError:
                    pass

        value_els = await self._page.locator(
            '[class*="valueItem-"] [class*="valueTitle-"]'
        ).all()
        for el in value_els:
            text = (await el.text_content() or "").strip()
            cleaned = re.sub(r"[^0-9.]", "", text)
            if cleaned:
                try:
                    num = float(cleaned)
                    if num > 0:
                        return num
                except ValueError:
                    continue
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

    # --- Chameleon LV / HV ---
    # v0-v3 are price bands, v4/v5 are signal plots.
    # Colors: rgb(76,175,80) = green (bullish), rgb(242,54,69) = red (bearish)
    # Buy when majority of v0-v5 colors are green.
    if any(k in name for k in ("chameleon", "hv v2", "lv v2")):
        return _interpret_chameleon(values)

    # --- MRI ---
    # Many value plots (v0-v49). Has green/red zones:
    #   rgb(0,100,0) / rgb(34,139,34) = green (buy zone)
    #   rgb(179,0,0) / rgb(255,96,96) = red (sell zone)
    #   rgb(255,152,0) = orange (transition)
    #   rgb(120,123,134) = gray (neutral)
    # Buy signal when green-colored values have non-zero text; sell when red do.
    if name == "mri":
        return _interpret_mri(values)

    # --- LuxAlgo Signals & Overlays ---
    # v1/v2 colored rgb(53,205,120) = green (buy signals)
    # v3/v4 colored rgb(255,0,0) = red (sell signals)
    # Signal fires when these values are non-zero.
    if "luxalgo" in name and "signal" in name:
        return _interpret_luxalgo_signals(values)

    # --- TCG BackBurner ---
    # v0: rgb(255,0,103) = pink/red (sell pressure)
    # v1: rgb(15,237,127) = green (buy pressure)
    # Signal based on which has a non-zero value.
    if "backburner" in name:
        return _interpret_tcg_backburner(values)

    # --- TCG Hist. RSI ---
    # v0 = RSI value. v5/v6 green (overbought bands), v7/v8 pink (oversold bands)
    # v13 green = bullish signal, v14 pink = bearish signal
    if "hist" in name and "rsi" in name:
        return _interpret_tcg_hist_rsi(values)

    # --- TCG SuperStack Pro ---
    # All values are ∅ when no signal. Non-∅ values indicate active signals.
    # Need to check for non-empty values and their colors.
    if "superstack" in name:
        return _interpret_by_active_values(values)

    # --- TCG MVS / MM Trend Scout ---
    # These may have no value items (legend shows just the name).
    # Check if any colored values exist at all.
    if "mm trend" in name or "tcg mvs" in name:
        return _interpret_by_active_values(values)

    # --- GLI-TR ---
    # v0 has a color: rgb(76,175,80) = green, rgb(255,255,0) = yellow, etc.
    if "gli-tr" in name:
        return _interpret_glitr(values)

    # --- Trade Keeper ---
    # v1 has a price level with color rgb(255,82,82) = red (resistance) or green (support)
    if "trade keeper" in name:
        return _interpret_by_color(values)

    # --- RSI (standard) ---
    if name == "rsi" or (name.startswith("rsi") and "divergen" not in name):
        return _interpret_rsi(values)

    # --- RSI Divergence ---
    if "rsi" in name and "divergen" in name:
        return _interpret_by_color(values)

    # --- Fallback: color-based ---
    return _interpret_by_color(values)


def _interpret_chameleon(values: dict[str, str | float]) -> str:
    """Chameleon LV/HV: check colors of value plots. Green = bullish, Red = bearish."""
    green_count = 0
    red_count = 0
    for key, val in values.items():
        if "color" not in key or key == "_disabled":
            continue
        r, g, b = _parse_rgb(str(val))
        if r < 0:
            continue
        if g > 120 and g > r * 1.3:  # green-ish
            green_count += 1
        if r > 120 and r > g * 1.3:  # red-ish
            red_count += 1
    if green_count > red_count:
        return "buy"
    if red_count > green_count:
        return "sell"
    return "neutral"


def _interpret_mri(values: dict[str, str | float]) -> str:
    """MRI: look for non-zero values in green vs red colored slots."""
    green_active = 0
    red_active = 0
    for i in range(50):
        val_key = f"v{i}"
        color_key = f"v{i}_color"
        span_key = f"v{i}_span_color"
        color_str = str(values.get(span_key, values.get(color_key, "")))
        text = str(values.get(val_key, "")).strip()

        if not text or text in ("0", "∅", ""):
            continue

        r, g, b = _parse_rgb(color_str)
        if r < 0:
            continue
        # Green family: (0,100,0), (34,139,34), (15,237,127)
        if g > 80 and g > r * 1.3:
            green_active += 1
        # Red family: (179,0,0), (255,96,96), (255,0,103)
        if r > 120 and r > g * 1.5:
            red_active += 1

    if green_active > red_active:
        return "buy"
    if red_active > green_active:
        return "sell"
    # Fallback: check v9 (orange = transition), v34-v41 for directional plots
    return "neutral"


def _interpret_luxalgo_signals(values: dict[str, str | float]) -> str:
    """LuxAlgo Signals & Overlays: v1/v2 green (buy), v3/v4 red (sell), non-zero = active."""
    buy_active = False
    sell_active = False

    for i in [1, 2]:
        text = str(values.get(f"v{i}", "")).strip()
        color = str(values.get(f"v{i}_span_color", values.get(f"v{i}_color", "")))
        r, g, b = _parse_rgb(color)
        if text and text != "0" and text != "∅" and g > 100 and g > r:
            buy_active = True

    for i in [3, 4]:
        text = str(values.get(f"v{i}", "")).strip()
        color = str(values.get(f"v{i}_span_color", values.get(f"v{i}_color", "")))
        r, g, b = _parse_rgb(color)
        if text and text != "0" and text != "∅" and r > 100 and r > g:
            sell_active = True

    # Also check v10 trend direction: -1 = bearish, 1 = bullish
    v10 = str(values.get("v10", "")).strip()
    if v10 == "1":
        buy_active = True
    elif v10 == "-1" or v10 == "−1":
        sell_active = True

    if buy_active and not sell_active:
        return "buy"
    if sell_active and not buy_active:
        return "sell"
    return "neutral"


def _interpret_tcg_backburner(values: dict[str, str | float]) -> str:
    """TCG BackBurner: v0 pink/red = sell, v1 green = buy. Non-zero = active."""
    v0 = str(values.get("v0", "")).strip()
    v1 = str(values.get("v1", "")).strip()

    buy_val = float(v1) if v1 and v1 not in ("∅", "") else 0
    sell_val = float(v0) if v0 and v0 not in ("∅", "") else 0

    if buy_val > 0 and buy_val > sell_val:
        return "buy"
    if sell_val > 0 and sell_val > buy_val:
        return "sell"
    return "neutral"


def _interpret_tcg_hist_rsi(values: dict[str, str | float]) -> str:
    """TCG Hist. RSI: v0 is RSI value. v13 green = bullish signal, v14 pink = bearish."""
    # Check signal plots first
    v13 = str(values.get("v13", "")).strip()
    v14 = str(values.get("v14", "")).strip()

    v13_val = float(v13) if v13 and v13 not in ("∅", "") else 0
    v14_val = float(v14) if v14 and v14 not in ("∅", "") else 0

    if v13_val > 0 and v14_val == 0:
        return "buy"
    if v14_val > 0 and v13_val == 0:
        return "sell"

    # Fallback to RSI value
    v0 = str(values.get("v0", "")).strip()
    if v0 and v0 not in ("∅", ""):
        try:
            rsi = float(v0)
            if rsi < 30:
                return "buy"
            if rsi > 70:
                return "sell"
        except ValueError:
            pass
    return "neutral"


def _interpret_glitr(values: dict[str, str | float]) -> str:
    """GLI-TR: color of v0 indicates trend. Green = buy, red/yellow = neutral/sell."""
    color = str(values.get("v0_span_color", values.get("v0_color", "")))
    r, g, b = _parse_rgb(color)
    if r < 0:
        return "neutral"
    if g > 120 and g > r * 1.3:
        return "buy"
    if r > 120 and r > g * 1.3:
        return "sell"
    return "neutral"


def _interpret_by_active_values(values: dict[str, str | float]) -> str:
    """Generic: check if any non-∅ values exist with green or red colors."""
    green = 0
    red = 0
    for key, val in values.items():
        if "color" not in key or key == "_disabled":
            continue
        # Only count if the corresponding value is non-empty
        val_key = key.replace("_span_color", "").replace("_color", "")
        text = str(values.get(val_key, "")).strip()
        if not text or text in ("∅", "0", ""):
            continue
        r, g, b = _parse_rgb(str(val))
        if r < 0:
            continue
        if g > 120 and g > r * 1.3:
            green += 1
        if r > 120 and r > g * 1.3:
            red += 1
    if green > red:
        return "buy"
    if red > green:
        return "sell"
    return "neutral"


def _interpret_by_color(values: dict[str, str | float]) -> str:
    """Fallback: scan all color values for green/red."""
    for key, val in values.items():
        s = str(val).lower()
        if "color" not in key:
            continue
        r, g, b = _parse_rgb(s)
        if r >= 0:
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


def _parse_rgb(color_str: str) -> tuple[int, int, int]:
    """Extract r, g, b from 'rgb(r, g, b)'. Returns (-1,-1,-1) if no match."""
    m = re.match(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", color_str.strip().lower())
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return -1, -1, -1


async def _is_visible(locator, timeout: int = 3000) -> bool:
    try:
        return await locator.is_visible(timeout=timeout)
    except Exception:
        return False
