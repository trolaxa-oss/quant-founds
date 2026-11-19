"""Providers (blueprint 4.0 & 12): pluggable OHLCV data sources.

Every provider returns closed candles only - a forming (still open) bar is
dropped at the source so no engine can ever see it (no-repaint rule).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from quant_founds.core.models import Candle


class DataProvider(ABC):
    name = "base"

    @abstractmethod
    def fetch(self, symbol: str, timeframe: str, bars: int) -> list[Candle]:
        """Return up to `bars` most recent CLOSED candles, oldest first."""


def drop_forming(candles: list[Candle]) -> list[Candle]:
    return [c for c in candles if c.closed]
