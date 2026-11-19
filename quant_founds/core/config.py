"""Configuration loading (blueprint 17 & 19: user-configurable, nothing hard-coded)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DataConfig:
    symbol: str = "EURUSD"
    timeframe: str = "M15"
    higher_timeframes: list[str] = field(default_factory=lambda: ["H1", "H4"])
    source_mode: str = "csv"
    csv_path: str = "data/sample_EURUSD_M15.csv"
    max_gap_bars: int = 3
    binance_base_url: str = "https://api.binance.com"
    bridge_url: str = "http://127.0.0.1:8770"
    bridge_token_env: str = "QF_BRIDGE_TOKEN"


@dataclass
class ScoringConfig:
    watch_threshold: float = 55.0
    entry_threshold: float = 70.0
    weights: dict[str, float] = field(default_factory=lambda: {
        "trend": 15.0,
        "structure": 15.0,
        "liquidity": 20.0,
        "orderflow": 15.0,
        "momentum_volatility": 10.0,
        "mtf": 10.0,
        "context": 5.0,
        "risk_reward": 10.0,
    })


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 0.005
    daily_loss_limit_pct: float = 0.02
    weekly_loss_limit_pct: float = 0.05
    max_drawdown_stop_pct: float = 0.10
    max_consecutive_losses: int = 4
    cooldown_bars_after_losses: int = 10
    max_open_positions: int = 1
    min_risk_reward: float = 1.5
    point_value: float = 1.0
    contract_size: float = 1.0


@dataclass
class ExecutionConfig:
    spread: float = 0.00010
    slippage: float = 0.00005
    commission_per_lot: float = 0.0
    partial_tp1_fraction: float = 0.5
    move_be_after_tp1: bool = True
    trailing_atr_multiple: float = 2.0
    enable_trailing: bool = True
    signal_validity_bars: int = 8


@dataclass
class SessionConfig:
    timezone_offset_hours: float = 0.0
    asia: tuple[float, float] = (0.0, 9.0)
    london: tuple[float, float] = (7.0, 16.0)
    new_york: tuple[float, float] = (12.0, 21.0)
    enabled: bool = True


@dataclass
class NewsConfig:
    enabled: bool = True
    block_minutes_before: int = 30
    block_minutes_after: int = 30
    block_impacts: list[str] = field(default_factory=lambda: ["high"])
    events_csv: str = ""


@dataclass
class FilterConfig:
    enabled: dict[str, bool] = field(default_factory=lambda: {})
    min_volume_ratio: float = 0.8
    max_volume_ratio: float = 6.0
    atr_min_pct: float = 0.0005
    atr_max_pct: float = 0.02
    min_distance_to_zone_atr: float = 0.2


@dataclass
class BacktestConfig:
    warmup_bars: int = 60
    start: str = ""
    end: str = ""


@dataclass
class Config:
    data: DataConfig = field(default_factory=DataConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    sessions: SessionConfig = field(default_factory=SessionConfig)
    news: NewsConfig = field(default_factory=NewsConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    debug: bool = False

    @classmethod
    def from_toml(cls, path: str | Path) -> "Config":
        raw: dict[str, Any] = {}
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
        cfg = cls()
        sections = {
            "data": DataConfig,
            "scoring": ScoringConfig,
            "risk": RiskConfig,
            "execution": ExecutionConfig,
            "sessions": SessionConfig,
            "news": NewsConfig,
            "filters": FilterConfig,
            "backtest": BacktestConfig,
        }
        for name, klass in sections.items():
            if name in raw:
                kwargs = {k: (v if not isinstance(v, list) else v) for k, v in raw[name].items()}
                obj = klass(**kwargs)
                setattr(cfg, name, obj)
        if "debug" in raw:
            cfg.debug = bool(raw["debug"])
        return cfg
