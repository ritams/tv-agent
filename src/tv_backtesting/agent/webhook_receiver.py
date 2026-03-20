"""TradingView Webhook Receiver — FastAPI server for TradingView alert webhooks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


@dataclass
class WebhookSignal:
    action: str
    ticker: str
    price: float
    time: str
    indicator: str
    signal: str  # "buy" | "sell" | "neutral"
    score: int
    raw: dict[str, Any]


class WebhookReceiver:
    def __init__(self, port: int = 3000) -> None:
        self._port = port
        self._signals: list[WebhookSignal] = []
        self._listeners: list[Callable[[WebhookSignal], Any]] = []
        self._server: uvicorn.Server | None = None
        self._app = FastAPI()
        self._setup_routes()

    def _setup_routes(self) -> None:
        @self._app.get("/health")
        async def health():
            return {"status": "ok", "signals": len(self._signals)}

        @self._app.post("/webhook")
        async def webhook(request: Request):
            try:
                body = await request.json()
            except Exception:
                raw_body = await request.body()
                import json
                body = json.loads(raw_body)

            signal = self._parse_signal(body)
            print(
                f"\nWebhook received: {signal.indicator} -> {signal.signal} "
                f"({signal.ticker} @ ${signal.price})"
            )
            self._signals.append(signal)
            for listener in self._listeners:
                listener(signal)

            return {"received": True}

        @self._app.get("/signals")
        async def signals():
            return [
                {
                    "action": s.action, "ticker": s.ticker, "price": s.price,
                    "time": s.time, "indicator": s.indicator, "signal": s.signal,
                    "score": s.score,
                }
                for s in self._signals[-50:]
            ]

    def _parse_signal(self, body: dict[str, Any]) -> WebhookSignal:
        return WebhookSignal(
            action=body.get("action", "unknown"),
            ticker=body.get("ticker", body.get("symbol", "unknown")),
            price=float(body.get("price", 0)),
            time=body.get("time", ""),
            indicator=body.get("indicator", "unknown"),
            signal=body.get("signal", "neutral"),
            score=int(body.get("score", 0)),
            raw=body,
        )

    def on(self, event: str, callback: Callable[[WebhookSignal], Any]) -> None:
        if event == "signal":
            self._listeners.append(callback)

    async def start(self) -> None:
        config = uvicorn.Config(
            self._app, host="0.0.0.0", port=self._port, log_level="warning"
        )
        self._server = uvicorn.Server(config)
        print(f"Webhook receiver listening on port {self._port}")
        print(f"   POST /webhook — receive TradingView alerts")
        print(f"   GET  /signals — view recent signals")
        print(f"   GET  /health  — health check")
        asyncio.create_task(self._server.serve())

    async def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
            print("Webhook receiver stopped")

    def get_latest_signal(
        self, ticker: str, indicator: str | None = None
    ) -> WebhookSignal | None:
        filtered = [
            s
            for s in self._signals
            if ticker.upper() in s.ticker.upper()
            and (not indicator or indicator.lower() in s.indicator.lower())
        ]
        return filtered[-1] if filtered else None

    def get_signal_count(self, ticker: str) -> dict[str, int]:
        from datetime import datetime, timezone, timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = [
            s
            for s in self._signals
            if ticker.upper() in s.ticker.upper()
        ]
        return {
            "buy": sum(1 for s in recent if s.signal == "buy"),
            "sell": sum(1 for s in recent if s.signal == "sell"),
            "neutral": sum(1 for s in recent if s.signal == "neutral"),
        }
