"""Alert Engine (17) - deduplicated alert log."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Alert:
    timestamp: datetime
    symbol: str
    timeframe: str
    event: str
    signal_id: str
    reason: str


class AlertEngine:
    def __init__(self):
        self.alerts: list[Alert] = []
        self._seen: set = set()

    def emit(self, ctx, decision, event: str, reason: str, key_extra: str = "") -> Alert | None:
        key = (decision.symbol, decision.timeframe, decision.signal_id, event,
               decision.bar_time.isoformat(), key_extra)
        if key in self._seen:
            return None
        self._seen.add(key)
        a = Alert(ctx.last.timestamp, decision.symbol, decision.timeframe, event,
                  decision.signal_id, reason)
        self.alerts.append(a)
        return a

    def recent(self, n: int = 20) -> list[Alert]:
        return self.alerts[-n:]
