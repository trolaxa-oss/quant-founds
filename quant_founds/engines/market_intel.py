"""Market Intelligence (engine 02) - trend, regime, structure quality.

Numeric classification is fixed here to limit self-interpretation:
- trend by EMA fast vs slow plus slope sign,
- strength by ADX bands (>25 strong, 20-25 developing, <20 weak),
- regime by ADX and ATR percentile.
"""
from __future__ import annotations

from quant_founds.core.engine import AnalysisContext, BaseEngine
from quant_founds.core.enums import MarketRegime, SourceMode, Trend
from quant_founds.engines.technical import snapshot, swing_points, adx


class MarketIntelligence(BaseEngine):
    engine_id = "market"

    def analyze(self, ctx: AnalysisContext):
        snap = snapshot(ctx.candles)
        evidence: list[str] = []
        invalidations: list[str] = []

        trend = Trend.UNAVAILABLE
        strength = 0.0
        if snap.ema_fast is None or snap.ema_slow is None:
            invalidations.append("no_ema_history")
        else:
            price = ctx.last.close
            if snap.ema_fast > snap.ema_slow and price > snap.ema_fast:
                trend = Trend.UP
            elif snap.ema_fast < snap.ema_slow and price < snap.ema_fast:
                trend = Trend.DOWN
            else:
                trend = Trend.SIDEWAYS
            strength = 50.0
            if snap.ema_fast_prev is not None:
                slope = snap.ema_fast - snap.ema_fast_prev
                if slope > 0 and trend is Trend.UP or slope < 0 and trend is Trend.DOWN:
                    strength += 10.0
                    evidence.append("ema_slope_confirms")

        if (snap.adx or 0) >= 25:
            strength = min(100.0, strength + 40.0)
        elif (snap.adx or 0) >= 20:
            strength = min(100.0, strength + 20.0)
        else:
            strength = max(0.0, strength - 20.0)
            if trend in (Trend.UP, Trend.DOWN):
                trend = Trend.TRANSITION
                evidence.append("weak_adx_transition")
            else:
                evidence.append("weak_adx")

        atr_pct = snap.atr_pct or 0.0
        if atr_pct >= 0.012:
            regime = MarketRegime.HIGH_VOLATILITY
        elif (snap.adx or 0) >= 20:
            regime = MarketRegime.TRENDING
        else:
            regime = MarketRegime.RANGING

        high_idx, low_idx = swing_points(ctx.candles, 2, 2)
        recent_highs = [ctx.candles[i].high for i in high_idx[-3:]]
        recent_lows = [ctx.candles[i].low for i in low_idx[-3:]]

        score = strength
        if trend in (Trend.UP, Trend.DOWN):
            confidence = "directional"
        elif trend is Trend.SIDEWAYS:
            confidence = "range"
        else:
            confidence = "unavailable"

        res = self.make_result(
            ctx,
            state=trend.value,
            score=round(score, 1),
            direction=trend.value,
            confidence_label=confidence,
            evidence=evidence or [f"ema_fast={snap.ema_fast}", f"ema_slow={snap.ema_slow}"],
            invalidations=invalidations,
            data_quality=snap.atr_pct is not None and 1.0 or 0.7,
            source_mode=SourceMode.HISTORICAL,
            extras={
                "trend": trend.value,
                "regime": regime.value,
                "strength": round(strength, 1),
                "adx": snap.adx,
                "atr": snap.atr,
                "atr_pct": atr_pct,
                "swing_highs": recent_highs,
                "swing_lows": recent_lows,
                "ema_fast": snap.ema_fast,
                "ema_slow": snap.ema_slow,
                "rsi": snap.rsi,
                "volume_ratio": snap.volume_ratio,
            },
        )
        ctx.results[self.engine_id] = res
        return res
