"""Async Playwright login + session + 2FA for TradingView."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pyotp
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ..config import config

SESSION_FILE = Path("./tv-session.json").resolve()


class TradingViewAuth:
    def __init__(self) -> None:
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._pw = None
        self._used_backup_idx = 0

    async def launch(self) -> tuple[Browser, BrowserContext, Page]:
        self._pw = await async_playwright().start()
        has_session = SESSION_FILE.exists()

        self._browser = await self._pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )

        if has_session:
            storage_state = json.loads(SESSION_FILE.read_text())
            self._context = await self._browser.new_context(
                storage_state=storage_state,
                viewport={"width": 1920, "height": 1080},
            )
        else:
            self._context = await self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
            )

        page = await self._context.new_page()

        logged_in = await self._is_logged_in(page)
        if not logged_in:
            if has_session:
                SESSION_FILE.unlink()
                print("-> Stale session removed")
            await self._login(page)

        return self._browser, self._context, page

    # ------------------------------------------------------------------
    async def _is_logged_in(self, page: Page) -> bool:
        try:
            await page.goto(
                "https://www.tradingview.com/chart/",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await page.wait_for_timeout(5000)
            if await self._is_logged_in_check(page):
                print("Already logged in via saved session")
                return True
            return False
        except Exception:
            return False

    async def _is_logged_in_check(self, page: Page) -> bool:
        selectors = [
            '[data-name="header-user-menu-button"]',
            'button[aria-label="Open user menu"]',
            '[class*="userMenu"]',
            '[class*="avatar"]',
            'img[class*="avatar"]',
        ]
        for sel in selectors:
            if await _visible(page.locator(sel).first, 1000):
                return True

        sign_in_visible = await _visible(
            page.locator('button:has-text("Sign in"), a:has-text("Sign in")').first,
            1000,
        )
        if not sign_in_visible:
            has_content = await _visible(
                page.locator('[class*="market"], [class*="chart"]').first, 1000
            )
            if has_content:
                return True
        return False

    # ------------------------------------------------------------------
    async def _login(self, page: Page) -> None:
        print("-> Logging into TradingView...")

        await page.goto(
            "https://www.tradingview.com/accounts/signin/",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        await page.wait_for_timeout(3000)

        sign_in_link = page.locator(
            'a:has-text("Sign in"), a[class*="link"]:has-text("Sign in")'
        ).first
        if await _visible(sign_in_link, 3000):
            print("  -> Switching to Sign in form...")
            await sign_in_link.click()
            await page.wait_for_timeout(2000)

        await self._screenshot(page, "login-form")

        email_option = page.locator('[class*="emailButton"], button:has-text("Email")').first
        if await _visible(email_option, 5000):
            await email_option.click()
            await page.wait_for_timeout(1000)

        # Fill email
        email_input = page.locator(
            'input[name="id_email"], input[name="id_username"], '
            'input[name="username"], input#id_email, input#id_username, input[type="email"]'
        ).first
        await email_input.wait_for(state="visible", timeout=10_000)
        await email_input.fill(config.trading_view.email)

        # Fill password
        pw_input = page.locator(
            'input[name="id_password"], input#id_password, input[type="password"]'
        ).first
        await pw_input.wait_for(state="visible", timeout=5000)
        await pw_input.fill(config.trading_view.password)

        await self._screenshot(page, "login-filled")

        # Submit
        submit_btn = page.locator(
            'button[type="submit"], button:has-text("Sign in"), '
            'button[class*="submitButton"], button[data-overflow-tooltip-text="Sign in"]'
        ).first
        await submit_btn.wait_for(state="visible", timeout=10_000)
        await submit_btn.click()
        await page.wait_for_timeout(4000)

        # Check errors
        error_banner = page.locator(
            '[class*="error"]:has-text("Invalid"), '
            '[class*="toast"]:has-text("Invalid"), '
            '[class*="alert"]:has-text("password")'
        )
        if await _visible(error_banner, 3000):
            error_text = await error_banner.text_content() or "Unknown error"
            await self._screenshot(page, "login-error")
            raise RuntimeError(f"Login failed: {error_text}")

        await self._handle_2fa(page)

        await page.wait_for_timeout(3000)
        if not await self._is_logged_in_check(page):
            await page.goto(
                "https://www.tradingview.com/chart/",
                wait_until="domcontentloaded",
                timeout=15_000,
            )
            await page.wait_for_timeout(3000)
            if not await self._is_logged_in_check(page):
                await self._screenshot(page, "login-verify-failed")
                raise RuntimeError("Login failed: could not verify logged-in state")

        await self.save_session()
        print("Logged in and session saved")

    # ------------------------------------------------------------------
    async def _handle_2fa(self, page: Page) -> None:
        two_fa_input = page.locator(
            'input[name="code"], input[placeholder*="code"], '
            'input[type="text"][maxlength="6"], input[inputmode="numeric"]'
        )
        if not await _visible(two_fa_input, 5000):
            print("-> No 2FA prompt detected")
            return

        print("-> 2FA detected")

        # TOTP (preferred)
        if config.trading_view.otp_secret:
            print("-> Using TOTP code...")
            totp = pyotp.TOTP(config.trading_view.otp_secret)
            code = totp.now()

            code_input = page.locator(
                'input[name="code"], input[placeholder*="code"], input[inputmode="numeric"]'
            ).first
            await code_input.wait_for(state="visible", timeout=5000)
            await code_input.fill(code)

            confirm = page.locator('button[type="submit"]').first
            await confirm.click()
            await page.wait_for_timeout(3000)
            print("TOTP 2FA submitted")
            return

        # Backup codes
        print("-> Using backup code...")
        backup_link = page.locator(
            'a:has-text("backup"), button:has-text("backup"), '
            'a:has-text("another way"), a:has-text("different method")'
        ).first
        if await _visible(backup_link, 3000):
            await backup_link.click()
            await page.wait_for_timeout(1000)

        if self._used_backup_idx >= len(config.trading_view.backup_codes):
            raise RuntimeError("No more backup codes available! Set TV_OTP_SECRET for TOTP-based 2FA.")

        code = config.trading_view.backup_codes[self._used_backup_idx]
        code_input = page.locator('input[name="code"], input[type="text"]').first
        await code_input.wait_for(state="visible", timeout=5000)
        await code_input.fill(code)

        confirm = page.locator('button[type="submit"]').first
        await confirm.click()
        await page.wait_for_timeout(3000)
        self._used_backup_idx += 1
        print(f"Backup code #{self._used_backup_idx} used")

    # ------------------------------------------------------------------
    async def _screenshot(self, page: Page, name: str) -> None:
        d = "./screenshots"
        os.makedirs(d, exist_ok=True)
        import time
        await page.screenshot(path=f"{d}/{name}-{int(time.time() * 1000)}.png")

    async def save_session(self) -> None:
        if not self._context:
            return
        storage = await self._context.storage_state()
        SESSION_FILE.write_text(json.dumps(storage, indent=2))

    async def close(self) -> None:
        await self.save_session()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()


async def _visible(locator, timeout: int = 3000) -> bool:
    try:
        return await locator.is_visible(timeout=timeout)
    except Exception:
        return False
