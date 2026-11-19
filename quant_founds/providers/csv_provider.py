"""CSV file provider (blueprint 12): most portable source for offline runs."""
from __future__ import annotations

from quant_founds.core.models import Candle
from quant_founds.engines.data_engine import load_csv_ohlcv
from quant_founds.providers.base import DataProvider, drop_forming


class CsvProvider(DataProvider):
    name = "csv"

    def __init__(self, path: str):
        self.path = path

    def fetch(self, symbol: str, timeframe: str, bars: int) -> list[Candle]:
        candles = load_csv_ohlcv(self.path)
        return drop_forming(candles)[-bars:]
