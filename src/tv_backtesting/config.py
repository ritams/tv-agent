from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field


class TradingViewSettings(BaseSettings):
    email: str = ""
    password: str = ""
    otp_secret: str = ""
    backup_codes: list[str] = []

    model_config = {"env_prefix": "TV_"}

    def __init__(self, **kw):
        super().__init__(**kw)
        # Parse backup codes from comma-separated env var
        raw = self.model_config.get("_raw_backup", "")
        if not self.backup_codes:
            import os
            raw = os.getenv("TV_2FA_BACKUP_CODES", "")
            if raw:
                self.backup_codes = [
                    c.strip().replace("-", "") for c in raw.split(",") if c.strip()
                ]


class TelegramSettings(BaseSettings):
    bot_token: str = ""
    chat_id: str = ""

    model_config = {"env_prefix": "TELEGRAM_"}


class IndicatorNames(BaseSettings):
    chameleon_btc: str = "Chameleon LV v2.0"
    chameleon_hype: str = "HV v2.0"
    mri: str = "MRI"
    rsi_divergence: str = "RSI Divergence"


class Config(BaseSettings):
    trading_view: TradingViewSettings = Field(default_factory=TradingViewSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    indicators: IndicatorNames = Field(default_factory=IndicatorNames)
    assets: list[str] = ["BTCUSD", "HYPEUSD", "XAUUSD", "SPX"]
    screenshot_dir: str = "./screenshots"


def load_config() -> Config:
    from dotenv import load_dotenv
    load_dotenv()
    return Config()


config = load_config()
