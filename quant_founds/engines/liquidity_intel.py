"""Liquidity Intelligence (engine 04) - BSL/SSL zones, sweeps (blueprint 4.2)."""
from __future__ import annotations

from datetime import timedelta

from quant_founds.core.engine import AnalysisContext, BaseEngine
from quant_founds.core.enums import LiquidityState, SourceMode, SweepSide
from quant_founds.core.models import LiquidityLevel, SweepEvent
from quant_founds.engines.technical import atr, swing_points


class LiquidityIntelligence(BaseEngine):
    engine_id = "liquidity"

    def __init__(self, equal_tol_atr: float = 0.10, lookback: int = 120,
                 min_sweep_atr: float = 0.05):
        self.equal_tol_atr = equal_tol_atr
        self.lookback = lookback
        self.min_sweep_atr = min_sweep_atr

    def analyze(self, ctx: AnalysisContext):
        candles = ctx.candles[-self.lookback:]
        a = atr(candles, 14)
        tol = (a or 0.0) * self.equal_tol_atr
        levels: list[LiquidityLevel] = []
        events: list[SweepEvent] = []
        evidence: list[str] = []
        invalidations: list[str] = []

        high_idx, low_idx = swing_points(candles, 2, 2)
        highs = [candles[i] for i in high_idx]
        lows = [candles[i] for i in low_idx]

        levels.extend(_cluster(highs, SweepSide.BSL, tol, ctx.symbol))
        levels.extend(_cluster(lows, SweepSide.SSL, tol, ctx.symbol))

        last = candles[-1]
        prev_high = max(c.high for c in candles[-20:-1]) if len(candles) > 20 else None
        prev_low = min(c.low for c in candles[-20:-1]) if len(candles) > 20 else None

        swept_bsl: SweepEvent | None = None
        swept_ssl: SweepEvent | None = None

        if a is not None and prev_high is not None and prev_low is not None:
            broke_high = last.high > prev_high
            broke_low = last.low < prev_low
            if broke_high:
                confirmed = last.close < prev_high
                ev = SweepEvent(prev_high, SweepSide.BSL, last.timestamp, confirmed,
                                "broke_prior_high " + ("closed_back_below" if confirmed else "held_above"))
                events.append(ev)
                swept_bsl = ev
            if broke_low:
                confirmed = last.close > prev_low
                ev = SweepEvent(prev_low, SweepSide.SSL, last.timestamp, confirmed,
                                "broke_prior_low " + ("closed_back_above" if confirmed else "held_below"))
                events.append(ev)
                swept_ssl = ev
        else:
            invalidations.append("insufficient_history_for_sweep")

        for ev in events:
            for lvl in levels:
                if lvl.side is ev.side and abs(lvl.price - ev.level_price) <= max(tol, a * 0.2) \
                        and ev.confirmed:
                    lvl.state = LiquidityState.SWEPT

        nearest = None
        if levels:
            nearest = min(levels, key=lambda l: abs(l.price - last.close))
        distance_atr = None
        if nearest and a:
            distance_atr = abs(nearest.price - last.close) / a

        quality = 0.0
        main_event = swept_bsl or swept_ssl
        if main_event and main_event.confirmed:
            quality = 1.0
        elif main_event:
            quality = 0.4

        state = "sweep" if main_event else ("levels_only" if levels else "unavailable")

        res = self.make_result(
            ctx,
            state=state,
            score=round(quality * 100, 1),
            confidence_label="confirmed_sweep" if quality == 1.0 else ("unconfirmed" if main_event else "no_event"),
            evidence=evidence or [f"levels={len(levels)}"],
            invalidations=invalidations,
            data_quality=1.0 if a is not None else 0.5,
            source_mode=SourceMode.HISTORICAL,
            extras={
                "levels": [
                    {"price": l.price, "side": l.side.value, "state": l.state.value,
                     "internal": l.internal, "quality": l.quality}
                    for l in levels
                ],
                "sweeps": [
                    {"price": e.level_price, "side": e.side.value, "confirmed": e.confirmed}
                    for e in events
                ],
                "target_level": nearest.price if nearest else None,
                "target_side": nearest.side.value if nearest else None,
                "distance_atr": distance_atr,
                "atr": a,
                "bsl": prev_high,
                "ssl": prev_low,
            },
        )
        ctx.results[self.engine_id] = res
        return res


def _cluster(rows, side: SweepSide, tol: float, symbol: str) -> list[LiquidityLevel]:
    merged: list[LiquidityLevel] = []
    rows = sorted(rows, key=lambda c: c.high if side is SweepSide.BSL else c.low)
    for c in rows:
        price = c.high if side is SweepSide.BSL else c.low
        if merged and abs(price - merged[-1].price) <= max(tol, 1e-9):
            merged[-1] = LiquidityLevel(
                price=(merged[-1].price + price) / 2.0,
                side=side,
                created_at=max(merged[-1].created_at, c.timestamp),
                state=merged[-1].state,
                internal=False,
                quality=min(1.0, merged[-1].quality + 0.15),
            )
        else:
            merged.append(LiquidityLevel(price=price, side=side, created_at=c.timestamp))
    return merged
