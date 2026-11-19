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
        errors = cfg.validate()
        if errors:
            raise ValueError("invalid config: " + "; ".join(errors))
        return cfg

    def validate(self) -> list[str]:
        """Sanity checks (blueprint 17): returns a list of error strings."""
        errors: list[str] = []
        if not (0 < self.risk.risk_per_trade_pct <= 0.05):
            errors.append("risk.risk_per_trade_pct must be in (0, 0.05]")
        if self.risk.daily_loss_limit_pct <= 0 or self.risk.weekly_loss_limit_pct <= 0:
            errors.append("risk daily/weekly loss limits must be positive")
        if not (0 < self.risk.max_drawdown_stop_pct <= 1):
            errors.append("risk.max_drawdown_stop_pct must be in (0, 1]")
        if self.risk.max_consecutive_losses < 1 or self.risk.max_open_positions < 1:
            errors.append("risk limits must allow at least one loss/position")
        if self.risk.min_risk_reward < 1:
            errors.append("risk.min_risk_reward must be >= 1")
        if self.risk.point_value <= 0 or self.risk.contract_size <= 0:
            errors.append("risk point_value/contract_size must be positive")
        if not (0 <= self.scoring.watch_threshold <= self.scoring.entry_threshold <= 100):
            errors.append("scoring thresholds must satisfy 0 <= watch <= entry <= 100")
        if any(w < 0 for w in self.scoring.weights.values()):
            errors.append("scoring weights must be non-negative")
        total = sum(self.scoring.weights.values())
        if abs(total - 100.0) > 0.5:
            errors.append(f"scoring weights must sum to 100 (got {total})")
        if not (0 < self.execution.partial_tp1_fraction <= 1):
            errors.append("execution.partial_tp1_fraction must be in (0, 1]")
        if self.execution.trailing_atr_multiple <= 0:
            errors.append("execution.trailing_atr_multiple must be positive")
        if self.execution.signal_validity_bars < 1:
            errors.append("execution.signal_validity_bars must be >= 1")
        if self.data.timeframe not in {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}:
            errors.append(f"data.timeframe '{self.data.timeframe}' is not supported")
        for tf in self.data.higher_timeframes:
            if tf not in {"M5", "M15", "M30", "H1", "H4", "D1"}:
                errors.append(f"data.higher_timeframes entry '{tf}' is not supported")
        if self.data.max_gap_bars < 0 or self.backtest.warmup_bars < 0:
            errors.append("data.max_gap_bars and backtest.warmup_bars must be >= 0")
        if self.news.block_minutes_before < 0 or self.news.block_minutes_after < 0:
            errors.append("news block minutes must be >= 0")
        return errors
