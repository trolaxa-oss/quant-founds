"""Binance public klines provider (blueprint 12.1): keyless real OHLCV.

Uses only stdlib urllib. Pagination walks backwards in batches of up to 1000
klines; the currently forming kline is dropped (no-repaint).
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

from quant_founds.core.models import Candle
from quant_founds.providers.base import DataProvider, drop_forming

INTERVALS = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1": "1d",
}
BATCH = 1000


def urllib_get_json(url: str, headers: dict | None = None, timeout: float = 15.0):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class BinanceProvider(DataProvider):
    name = "binance"

    def __init__(self, base_url: str = "https://api.binance.com", transport=urllib_get_json):
        self.base_url = base_url.rstrip("/")
        self._transport = transport

    def fetch(self, symbol: str, timeframe: str, bars: int) -> list[Candle]:
        interval = INTERVALS.get(timeframe.upper())
        if interval is None:
            raise ValueError(f"unsupported timeframe {timeframe!r} for {self.name}")
        batches: list[list[Candle]] = []
        end_time: int | None = None
        remaining = bars
        while remaining > 0:
            limit = min(BATCH, remaining + 5)
            url = (f"{self.base_url}/api/v3/klines?symbol={symbol}"
                   f"&interval={interval}&limit={limit}")
            if end_time is not None:
                url += f"&endTime={end_time - 1}"
            raw = self._transport(url)
            if not raw:
                break
            candles = [self._to_candle(k) for k in raw]
            end_time = int(raw[0][0])
            batches.append(candles)
            remaining -= len([c for c in candles if c.closed])
            if len(raw) < 2:
                break
        ordered: list[Candle] = []
        for batch in reversed(batches):
            ordered.extend(batch)
        return [c for c in drop_forming(ordered) if c][-bars:]

    @staticmethod
    def _to_candle(k) -> Candle:
        open_ms, close_ms = int(k[0]), int(k[6])
        return Candle(
            timestamp=datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc),
            open=float(k[1]),
            high=float(k[2]),
            low=float(k[3]),
            close=float(k[4]),
            volume=float(k[5]),
            closed=close_ms <= int(datetime.now(timezone.utc).timestamp() * 1000),
        )
