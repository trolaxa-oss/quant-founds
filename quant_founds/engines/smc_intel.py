"""Smart Money Intelligence (engine 05) - BOS/CHOCH/MSS, OB, FVG (blueprint 4.4).

Labels here describe analytical patterns with fixed numeric rules; they are
not proof of real institutional orders (blueprint note in 4.4).
"""
from __future__ import annotations

from quant_founds.core.engine import AnalysisContext, BaseEngine
from quant_founds.core.enums import Side, SourceMode
from quant_founds.core.models import Zone
from quant_founds.engines.technical import atr, swing_points


class SmcIntelligence(BaseEngine):
    engine_id = "smc"

    def __init__(self, swing_left: int = 2, swing_right: int = 2):
        self.swing_left = swing_left
        self.swing_right = swing_right
        self.zones: list[Zone] = []

    def analyze(self, ctx: AnalysisContext):
        candles = ctx.candles
        last = candles[-1]
        a = atr(candles, 14)
        evidence: list[str] = []

        high_idx, low_idx = swing_points(candles, self.swing_left, self.swing_right)
        events: list[dict] = []

        if len(high_idx) >= 2 and len(low_idx) >= 2:
            prior_high = candles[high_idx[-1]].high
            prior_low = candles[low_idx[-1]].low
            if last.close > prior_high:
                events.append({"event": "BOS", "direction": "up", "level": prior_high})
            elif last.close < prior_low:
                events.append({"event": "BOS", "direction": "down", "level": prior_low})

            high_pos = candles[high_idx[-2]]
            low_pos = candles[low_idx[-2]]
            if high_pos.timestamp < low_pos.timestamp and last.close > prior_high:
                events.append({"event": "CHOCH", "direction": "up", "level": prior_high})
            elif low_pos.timestamp < high_pos.timestamp and last.close < prior_low:
                events.append({"event": "CHOCH", "direction": "down", "level": prior_low})

        structure_state = "_".join(f"{e['event']}:{e['direction']}" for e in events) \
            if events else "quiet"

        self._detect_ob(candles, evidence)
        self._detect_fvg(candles, evidence)
        self._mitigate_zones(candles)

        window = candles[-60:] if len(candles) >= 60 else candles
        range_high = max(c.high for c in window)
        range_low = min(c.low for c in window)
        span = range_high - range_low
        equilibrium = None
        premium_discount = "unavailable"
        if span > 0:
            pos = (last.close - range_low) / span
            equilibrium = range_low + span / 2.0
            premium_discount = "premium" if pos > 0.55 else (
                "discount" if pos < 0.45 else "equilibrium")

        score = min(100.0, 35.0 * len(events) + 12.0 * len([e for e in evidence if "OB" in e or "FVG" in e]))

        res = self.make_result(
            ctx,
            state=structure_state,
            score=round(score, 1),
            confidence_label="events" if events else "quiet",
            evidence=evidence[:12],
            data_quality=1.0 if a is not None else 0.6,
            source_mode=SourceMode.HISTORICAL,
            extras={
                "events": events,
                "zones": [
                    {"kind": z.kind, "top": z.top, "bottom": z.bottom,
                     "direction": z.direction.value if z.direction else None,
                     "active": z.active, "mitigations": z.mitigations}
                    for z in self.zones if z.active
                ][-10:],
                "premium_discount": premium_discount,
                "equilibrium": equilibrium,
                "range_high": range_high,
                "range_low": range_low,
            },
        )
        ctx.results[self.engine_id] = res
        return res

    def _detect_ob(self, candles, evidence: list[str]) -> None:
        if len(candles) < 3:
            return
        c1, c2 = candles[-2], candles[-1]
        if c2.close > c2.open and c1.close < c1.open:
            self.zones.append(Zone("OB", Side.BUY, c1.high, c1.low, c1.timestamp, quality=0.8))
        elif c2.close < c2.open and c1.close > c1.open:
            self.zones.append(Zone("OB", Side.SELL, c1.high, c1.low, c1.timestamp, quality=0.8))

    def _detect_fvg(self, candles, evidence: list[str]) -> None:
        if len(candles) < 3:
            return
        a, b, c = candles[-3], candles[-2], candles[-1]
        if b.low > max(a.high, c.high):
            self.zones.append(Zone("FVG", Side.SELL, b.low, max(a.high, c.high), b.timestamp))
        elif b.high < min(a.low, c.low):
            self.zones.append(Zone("FVG", Side.BUY, min(a.low, c.low), b.high, b.timestamp))

    def _mitigate_zones(self, candles) -> None:
        last = candles[-1]
        for z in self.zones:
            if not z.active:
                continue
            overlap = last.low <= z.top and last.high >= z.bottom
            if not overlap:
                continue
            z.mitigations += 1
            if z.direction is Side.BUY and last.close < z.bottom:
                z.active = False
            elif z.direction is Side.SELL and last.close > z.top:
                z.active = False
            elif z.mitigations >= 3:
                z.active = False
