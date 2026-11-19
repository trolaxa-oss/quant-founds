"""Session & timing engine (14) + Safety / No-repaint helpers (19)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quant_founds.core.engine import AnalysisContext, BaseEngine
from quant_founds.core.enums import SourceMode


class SessionEngine(BaseEngine):
    engine_id = "sessions"

    def __init__(self, cfg):
        self.cfg = cfg

    def analyze(self, ctx: AnalysisContext):
        local = ctx.last.timestamp + timedelta(hours=self.cfg.timezone_offset_hours)
        hour = local.hour + local.minute / 60.0
        active: list[str] = []
        if self.cfg.asia[0] <= hour < self.cfg.asia[1]:
            active.append("asia")
        if self.cfg.london[0] <= hour < self.cfg.london[1]:
            active.append("london")
        if self.cfg.new_york[0] <= hour < self.cfg.new_york[1]:
            active.append("new_york")
        overlap = (
            "london" in active and "new_york" in active
        )
        res = self.make_result(
            ctx,
            state=",".join(active) if active else "off_session",
            confidence_label="overlap" if overlap else ("normal" if active else "quiet"),
            evidence=[f"local_hour={hour:.2f}"],
            source_mode=SourceMode.HISTORICAL,
            extras={"active": active, "overlap": overlap, "local_hour": hour},
        )
        ctx.results[self.engine_id] = res
        return res


# ---------- Safety / No-Repaint (blueprint 2 & engine 19) ----------

class SafetyViolation(Exception):
    pass


def assert_closed_only(candles, label: str) -> None:
    """Guarantee no signal is derived from a forming bar."""
    if candles and getattr(candles[-1], "closed", True) is False:
        raise SafetyViolation(f"unclosed bar used in {label}")


def check_series(entries) -> list[str]:
    problems: list[str] = []
    for a, b in zip(entries, entries[1:]):
        if b.timestamp <= a.timestamp:
            problems.append("non_monotonic")
    return problems


def bar_close_time(candle) -> datetime:
    return candle.timestamp
