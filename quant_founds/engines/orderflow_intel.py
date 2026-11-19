"""Order Flow Intelligence (engine 03) - delta pressure from available data.

Two explicitly separated modes (blueprint 4.3):
- reverse: real delta when bid/ask or trade data was provided by caller.
- estimated: candle-volume proxy, always tagged as estimated and never
  presented as a footprint reading.
"""
from __future__ import annotations

import math
from statistics import fmean

from quant_founds.core.engine import AnalysisContext, BaseEngine
from quant_founds.core.enums import SourceMode


class OrderFlowIntelligence(BaseEngine):
    engine_id = "orderflow"

    def __init__(self, climax_ratio: float = 2.0, lookback: int = 20):
        self.climax_ratio = climax_ratio
        self.lookback = lookback

    def analyze(self, ctx: AnalysisContext, delta_series: list[float] | None = None):
        candles = ctx.candles[-self.lookback:]
        last = candles[-1]
        evidence: list[str] = []
        invalidations: list[str] = []

        if delta_series:
            mode = SourceMode.DIRECT
            delta_now = delta_series[-1]
            cum_delta = sum(delta_series)
        else:
            mode = SourceMode.ESTIMATED
            rng = last.high - last.low
            body = last.close - last.open
            if rng <= 0 or last.volume <= 0:
                delta_now = 0.0
            else:
                delta_now = (body / rng) * last.volume
            cum_delta = 0.0
            for c in candles:
                r = c.high - c.low
                if r > 0 and c.volume > 0:
                    cum_delta += (c.close - c.open) / r * c.volume

        look = candles
        avg_vol = fmean([c.volume for c in look]) if look and all(c.volume > 0 for c in look) else 0.0
        vol_ratio = (last.volume / avg_vol) if avg_vol > 0 else None

        delta_frac = None
        if avg_vol and last.volume > 0:
            delta_frac = delta_now / last.volume if last.volume else 0.0

        flags: list[str] = []
        if vol_ratio and vol_ratio >= self.climax_ratio:
            flags.append("volume_climax")
        if delta_frac is not None and abs(delta_frac) < 0.25 and (vol_ratio or 1) > 1.2:
            flags.append("absorption_candidate")
        if vol_ratio and vol_ratio < 0.5:
            flags.append("exhaustion_candidate")

        direction = None
        score = 0.0
        if delta_frac is not None:
            price_dir = 1.0 if last.close > last.open else (-1.0 if last.close < last.open else 0.0)
            divergence = abs(price_dir - (1.0 if delta_now > 0 else -1.0 if delta_now < 0 else 0.0)) > 1.0
            if divergence:
                flags.append("price_delta_divergence")
            direction = "buy" if delta_now > 0 and price_dir >= 0 else \
                        "sell" if delta_now < 0 and price_dir <= 0 else None
            if direction:
                score = min(100.0, abs(delta_frac) * 200.0)
            if mode is SourceMode.ESTIMATED:
                score *= 0.7

        evidence.append("mode=" + mode.value)
        if flags:
            evidence.extend(flags)

        res = self.make_result(
            ctx,
            state="ok" if delta_frac is not None else "unavailable",
            score=round(score, 1),
            direction=direction,
            confidence_label=("real" if mode is SourceMode.DIRECT else "estimated_proxy"),
            evidence=evidence,
            invalidations=invalidations,
            data_quality=1.0 if mode is SourceMode.DIRECT else 0.6,
            source_mode=mode,
            extras={
                "delta": delta_now,
                "cum_delta": cum_delta,
                "delta_frac": delta_frac,
                "volume_ratio": vol_ratio,
                "flags": flags,
            },
        )
        ctx.results[self.engine_id] = res
        return res
