"""Base engine interface + analysis context (blueprint 2 & 3.3)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .enums import MarketRegime, Side, Trend
from .models import Candle


@dataclass
class AnalysisContext:
    """Snapshot of everything engines may read at decision time.

    Only closed candles are ever attached here (safety/no-repaint principle,
    blueprint section 2 and engine 19). Highest timeframe series must also be
    closed-only: the MTF engine drops the last HTF bar unless it is complete.
    """
    symbol: str
    timeframe: str
    candles: list[Candle]
    higher_tf: dict[str, list[Candle]] = field(default_factory=dict)
    timestamp: datetime = datetime.now()
    results: dict[str, object] = field(default_factory=dict)
    debug: bool = False

    @property
    def last(self) -> Candle:
        return self.candles[-1]

    def closes(self) -> list[float]:
        return [c.close for c in self.candles]


class BaseEngine(ABC):
    engine_id: str = "base"
    version: str = "1.0"

    @abstractmethod
    def analyze(self, ctx: AnalysisContext) -> object:
        ...

    def make_result(self, ctx: AnalysisContext, **kwargs):
        from .models import EngineResult
        return EngineResult(
            engine_id=f"{self.engine_id}@{self.version}",
            timestamp=ctx.timestamp,
            data_timestamp=ctx.last.timestamp,
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            **kwargs,
        )

    @staticmethod
    def trend_side(trend: Trend) -> Optional[Side]:
        if trend is Trend.UP:
            return Side.BUY
        if trend is Trend.DOWN:
            return Side.SELL
        return None

    @staticmethod
    def regime_allows_ranging(regime: MarketRegime) -> bool:
        return regime is not MarketRegime.TRENDING
