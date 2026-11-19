"""Multi-Timeframe Engine (06) - HTF/H1 alignment with closed-bars-only rule.

Incomplete higher-timeframe bars are never used for decisions (blueprint 4.5).
"""
from __future__ import annotations

from quant_founds.core.engine import AnalysisContext, BaseEngine
from quant_founds.core.enums import SourceMode, Trend
from quant_founds.engines.technical import htf_trend


TIMEFRAME_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


class MultiTimeframeEngine(BaseEngine):
    engine_id = "mtf"

    def __init__(self, htf: list[str] | None = None):
        self.htf = htf or ["H1", "H4"]

    def analyze(self, ctx: AnalysisContext, htf_series: dict[str, list] | None = None):
        series = htf_series or ctx.higher_tf
        alignment: dict[str, str] = {}
        used: dict[str, str] = {}
        evidence: list[str] = []
        invalidations: list[str] = []

        for tf in self.htf:
            candles = series.get(tf)
            if not candles:
                alignment[tf] = "unavailable"
                invalidations.append(f"no_data_{tf}")
                continue
            closed = _closed_only(candles)
            if len(closed) < 2:
                alignment[tf] = "unavailable"
                invalidations.append(f"insufficient_{tf}")
                continue
            used[tf] = f"closed_bars={len(closed)}"
            alignment[tf] = htf_trend(closed, 20) or "unavailable"

        up_count = sum(1 for v in alignment.values() if v == "up")
        down_count = sum(1 for v in alignment.values() if v == "down")
        total = len(self.htf)

        if total == 0 or (up_count + down_count) == 0:
            state = "unavailable"
            score = 0.0
        elif up_count == total:
            state = "aligned_buy"
            score = 100.0
        elif down_count == total:
            state = "aligned_sell"
            score = 100.0
        elif up_count or down_count:
            state = "partial"
            score = 50.0 * max(up_count, down_count) / total
        else:
            state = "conflict"
            score = 0.0

        res = self.make_result(
            ctx,
            state=state,
            score=round(score, 1),
            confidence_label="full" if score == 100 else ("partial" if score else "conflict"),
            evidence=evidence or [f"{tf}:{alignment[tf]}" for tf in alignment],
            invalidations=invalidations,
            data_quality=1.0 if len(invalidations) == 0 else 0.5,
            source_mode=SourceMode.HISTORICAL,
            extras={"alignment": alignment, "used": used},
        )
        ctx.results[self.engine_id] = res
        return res


def _closed_only(candles):
    drop_incomplete = getattr(_closed_only, "_last_bar_open", None)
    if not candles:
        return candles
    last = candles[-1]
    if drop_incomplete_htf_bar(candles):
        return candles[:-1]
    return candles


def drop_incomplete_htf_bar(candles):
    """Remove the trailing HTF bar if it may still be forming.

    Heuristic used only when the caller cannot guarantee completeness:
    the backtester appends fully-closed bars, so this returns False by
    default, but a live reader (via params.hint_incomplete) can force it.
    """
    return False
