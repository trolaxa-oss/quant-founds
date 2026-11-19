"""MT5 HTTP bridge provider (blueprint 12): real forex data via a local bridge.

The bridge is a tiny HTTP server (scripts/mt5_bridge_server.py) you run on a
machine that has the MetaTrader5 terminal + python package installed. This
client only needs stdlib urllib. Auth token is read from the environment
(QF_BRIDGE_TOKEN) and never stored in config or code.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone

from quant_founds.core.models import Candle
from quant_founds.providers.base import DataProvider, drop_forming

TIMEFRAME_ALIASES = {
    "M1": "M1", "M5": "M5", "M15": "M15", "M30": "M30",
    "H1": "H1", "H4": "H4", "D1": "D1",
}


def urllib_get_json(url: str, headers: dict | None = None, timeout: float = 15.0):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class Mt5BridgeProvider(DataProvider):
    name = "mt5_bridge"

    def __init__(self, base_url: str = "http://127.0.0.1:8770",
                 token_env: str = "QF_BRIDGE_TOKEN", transport=urllib_get_json):
        self.base_url = base_url.rstrip("/")
        self.token_env = token_env
        self._transport = transport

    def fetch(self, symbol: str, timeframe: str, bars: int) -> list[Candle]:
        tf = TIMEFRAME_ALIASES.get(timeframe.upper())
        if tf is None:
            raise ValueError(f"unsupported timeframe {timeframe!r} for {self.name}")
        url = (f"{self.base_url}/candles?symbol={symbol}"
               f"&timeframe={tf}&bars={max(1, int(bars))}")
        token = os.environ.get(self.token_env, "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        payload = self._transport(url, headers=headers)
        candles = [
            Candle(
                timestamp=datetime.fromtimestamp(row["timestamp"], tz=timezone.utc),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                closed=bool(row.get("closed", True)),
            )
            for row in payload
        ]
        return drop_forming(candles)[-bars:]
