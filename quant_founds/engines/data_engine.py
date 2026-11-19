"""Data Engine (01) - validation, timing, data quality (blueprint 4.0, 13)."""
from __future__ import annotations

from quant_founds.core.engine import AnalysisContext, BaseEngine
from quant_founds.core.enums import SourceMode


class DataEngine(BaseEngine):
    engine_id = "data"

    def __init__(self, max_gap_bars: int = 3):
        self.max_gap_bars = max_gap_bars

    def analyze(self, ctx: AnalysisContext):
        candles = ctx.candles
        problems: list[str] = []
        quality = 1.0

        if len(candles) < 5:
            quality = 0.0
            problems.append("insufficient_bars")
        else:
            for i in range(1, len(candles)):
                if candles[i].timestamp <= candles[i - 1].timestamp:
                    problems.append(f"non_monotonic_time@{i}")
                    quality -= 0.3
                if candles[i].close <= 0 or candles[i].low <= 0:
                    problems.append(f"non_positive_price@{i}")
                    quality -= 0.3
                if candles[i].low > candles[i].high:
                    problems.append(f"invalid_range@{i}")
                    quality -= 0.5

            if candles[-1].volume <= 0:
                problems.append("zero_volume_last_bar")
                quality -= 0.1

        quality = max(0.0, min(1.0, quality))
        state = "ok" if quality >= 0.6 else "degraded"

        res = self.make_result(
            ctx,
            state=state,
            score=round(quality * 100, 1),
            data_quality=quality,
            source_mode=SourceMode.HISTORICAL,
            evidence=[f"n_bars={len(candles)}"],
            extras={"problems": problems[:10], "n_bars": len(candles)},
        )
        if problems and ctx.debug:
            res.evidence.append("problems:" + ",".join(problems[:5]))
        return res


def load_csv_ohlcv(path: str, has_volume: bool = True):
    """Load OHLCV from CSV with columns timestamp,open,high,low,close[,volume]."""
    import csv
    from datetime import datetime, timezone
    parsed: list = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts_raw = (row.get("timestamp") or row.get("datetime") or "").strip()
            ts = _parse_ts(ts_raw)
            c = {
                "timestamp": ts,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume") or 0.0),
            }
            parsed.append(c)
    from quant_founds.core.models import Candle
    return [Candle(**row) for row in parsed]


def _parse_ts(raw: str):
    from datetime import datetime, timezone
    raw = raw.strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    candidates = [
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M", "%Y-%m-%d",
    ]
    for fmt in candidates:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"unparsed timestamp: {raw}")
