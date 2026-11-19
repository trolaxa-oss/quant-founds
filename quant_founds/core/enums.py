"""QUANT FOUNDS - shared enums (blueprint section 3.3 & 5.1)."""
from __future__ import annotations

from enum import Enum


class Trend(str, Enum):
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"
    TRANSITION = "transition"
    UNAVAILABLE = "unavailable"


class MarketRegime(str, Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    UNAVAILABLE = "unavailable"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class SignalState(str, Enum):
    WATCH = "WATCH"
    SETUP = "SETUP"
    CONFIRMED = "CONFIRMED"
    ENTRY_READY = "ENTRY_READY"
    ACTIVE = "ACTIVE"
    EXITED = "EXITED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    IDLE = "IDLE"


class SignalType(str, Enum):
    BUY_SETUP = "BUY_SETUP"
    SELL_SETUP = "SELL_SETUP"
    BUY_CONFIRMATION = "BUY_CONFIRMATION"
    SELL_CONFIRMATION = "SELL_CONFIRMATION"
    BUY_ENTRY = "BUY_ENTRY"
    SELL_ENTRY = "SELL_ENTRY"
    EXIT = "EXIT"
    CANCEL = "CANCEL"
    INVALIDATION = "INVALIDATION"
    ALERT_ONLY = "ALERT_ONLY"


class LiquidityState(str, Enum):
    UNSWEPT = "unswept"
    SWEPT = "swept"
    CONSUMED = "consumed"


class SweepSide(str, Enum):
    BSL = "BSL"
    SSL = "SSL"


class OrderState(str, Enum):
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class ExitReason(str, Enum):
    TAKE_PROFIT_1 = "tp1"
    TAKE_PROFIT_2 = "tp2"
    TAKE_PROFIT_3 = "tp3"
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    TIME_EXIT = "time_exit"
    MANUAL = "manual"
    KILL_SWITCH = "kill_switch"
    SIGNAL_END = "signal_end"


class SourceMode(str, Enum):
    DIRECT = "direct"
    HISTORICAL = "historical"
    ESTIMATED = "estimated"
    EXTERNAL = "external"
    UNAVAILABLE = "unavailable"
