"""Core data models shared by all engines (blueprint 3.3 unified interface)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .enums import (
    LiquidityState,
    MarketRegime,
    OrderState,
    Side,
    SignalState,
    SourceMode,
    SweepSide,
)


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    closed: bool = True

    def __post_init__(self) -> None:
        ts = self.timestamp
        if ts.tzinfo is None:
            object.__setattr__(self, "timestamp", ts.replace(tzinfo=timezone.utc))


@dataclass
class EngineResult:
    """Unified engine output; every engine must return this shape."""
    engine_id: str
    timestamp: datetime
    data_timestamp: datetime
    symbol: str
    timeframe: str
    state: str = "unavailable"
    score: Optional[float] = None
    direction: Optional[str] = None
    confidence_label: str = "unavailable"
    evidence: list[str] = field(default_factory=list)
    invalidations: list[str] = field(default_factory=list)
    data_quality: float = 1.0
    source_mode: SourceMode = SourceMode.HISTORICAL
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class LiquidityLevel:
    price: float
    side: SweepSide
    created_at: datetime
    state: LiquidityState = LiquidityState.UNSWEPT
    internal: bool = False
    quality: float = 1.0


@dataclass
class SweepEvent:
    level_price: float
    side: SweepSide
    timestamp: datetime
    confirmed: bool
    details: str = ""


@dataclass
class Zone:
    kind: str          # "OB", "FVG", "SR"
    direction: Side | None
    top: float
    bottom: float
    created_at: datetime
    active: bool = True
    mitigations: int = 0
    quality: float = 1.0


@dataclass
class TradePlan:
    signal_id: str
    symbol: str
    timeframe: str
    side: Side
    entry: float
    stop_loss: float
    take_profits: list[float]
    risk_reward: float
    bar_time: datetime


@dataclass
class Fill:
    timestamp: datetime
    price: float
    quantity: float
    kind: str  # entry | tp | sl | trail | close


@dataclass
class Trade:
    trade_id: str
    signal_id: str
    symbol: str
    timeframe: str
    side: Side
    entry_time: datetime
    entry_price: float
    quantity: float
    stop_loss: float
    take_profits: list[float]
    fills: list[Fill] = field(default_factory=list)
    realized_pnl: float = 0.0
    exit_reasons: list[str] = field(default_factory=list)
    state: OrderState = OrderState.FILLED
    closed_time: Optional[datetime] = None
    session: str = ""
    costs: float = 0.0


@dataclass
class Account:
    currency_code: str = "USD"
    balance: float = 10_000.0
    equity: float = 10_000.0
    peak_equity: float = 10_000.0
    day_pnl: float = 0.0
    week_pnl: float = 0.0
    consecutive_losses: int = 0


@dataclass
class EconomicEvent:
    timestamp: datetime
    currency: str
    impact: str  # low | medium | high
    name: str = ""
