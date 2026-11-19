"""Pluggable OHLCV data sources (blueprint 12)."""
from __future__ import annotations

from quant_founds.core.config import Config
from quant_founds.providers.base import DataProvider
from quant_founds.providers.binance_provider import BinanceProvider
from quant_founds.providers.csv_provider import CsvProvider
from quant_founds.providers.mt5_bridge import Mt5BridgeProvider


def provider_from_config(cfg: Config, csv_path: str = "") -> DataProvider:
    source = (cfg.data.source_mode or "csv").lower()
    if source == "binance":
        return BinanceProvider(base_url=cfg.data.binance_base_url)
    if source in ("mt5_bridge", "mt5", "bridge"):
        return Mt5BridgeProvider(base_url=cfg.data.bridge_url,
                                 token_env=cfg.data.bridge_token_env)
    return CsvProvider(path=csv_path or cfg.data.csv_path)


__all__ = [
    "DataProvider",
    "CsvProvider",
    "BinanceProvider",
    "Mt5BridgeProvider",
    "provider_from_config",
]
