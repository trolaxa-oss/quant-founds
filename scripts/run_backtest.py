"""Demo: generate a deterministic synthetic OHLCV series, run the backtest.

Not a market simulation for accuracy - only enough structure for the engines
to exercise realistic trend, swings, and sweeps.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import random
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quant_founds.backtest import Backtester
from quant_founds.core.config import Config
from quant_founds.engines.data_engine import load_csv_ohlcv


def generate_series(symbol: str = "EURUSD", n: int = 3000,
                    start: datetime | None = None, seed: int = 11) -> str:
    rng = random.Random(seed)
    start = start or datetime(2024, 1, 2, tzinfo=timezone.utc)
    price = 1.0800
    drift = 0.0
    rows = ["timestamp,open,high,low,close,volume"]
    ts = start
    for i in range(n):
        if i % 240 == 0:
            drift = rng.choice([-1, 1]) * rng.uniform(0.00002, 0.00012)
        shock = rng.gauss(0, 1)
        o = price
        move = drift + shock * 0.00040
        c = o + move
        hi = max(o, c) + abs(rng.gauss(0, 0.00018))
        lo = min(o, c) - abs(rng.gauss(0, 0.00018))
        vol = abs(rng.gauss(900, 250))
        rows.append(f"{ts.strftime('%Y-%m-%d %H:%M:%S')},{o:.5f},{hi:.5f},{lo:.5f},{c:.5f},{vol:.1f}")
        price = c
        ts += timedelta(minutes=15)
    path = "data/sample_EURUSD_M15.csv"
    os.makedirs("data", exist_ok=True)
    with open(path, "w") as fh:
        fh.write("\n".join(rows) + "\n")
    return path


def build_htf(candles, minutes: int) -> list:
    out = []
    bucket = None
    for c in candles:
        slot = int(c.timestamp.timestamp() // (minutes * 60))
        if bucket is None or slot != bucket["slot"]:
            if bucket:
                out.append(bucket["candle"])
            bucket = {"slot": slot, "candle": c}
        else:
            merged = bucket["candle"]
            from quant_founds.core.models import Candle
            bucket["candle"] = Candle(
                timestamp=merged.timestamp,
                open=merged.open,
                high=max(merged.high, c.high),
                low=min(merged.low, c.low),
                close=c.close,
                volume=merged.volume + c.volume,
            )
    if bucket:
        out.append(bucket["candle"])
    from quant_founds.core.models import Candle
    return [Candle(timestamp=c.timestamp, open=c.open, high=c.high, low=c.low,
                   close=c.close, volume=c.volume) for c in out]


def main() -> None:
    ap = argparse.ArgumentParser(description="QUANT FOUNDS demo backtest")
    ap.add_argument("--config", default="config/default.toml")
    ap.add_argument("--csv", default="")
    ap.add_argument("--seed-data", action="store_true", help="generate synthetic series first")
    ap.add_argument("--out", default="runs/latest")
    args = ap.parse_args()

    cfg = Config.from_toml(args.config)
    if args.seed_data:
        cfg.scoring.watch_threshold = max(45.0, cfg.scoring.watch_threshold - 10.0)
        cfg.scoring.entry_threshold = max(60.0, cfg.scoring.entry_threshold - 10.0)
    csv_path = args.csv or cfg.data.csv_path
    if args.seed_data or not os.path.exists(csv_path):
        csv_path = generate_series(cfg.data.symbol)
    candles = load_csv_ohlcv(csv_path)
    htf = {tf: build_htf(candles, minutes)
           for tf, minutes in {"H1": 60, "H4": 240}.items()}

    bt = Backtester(cfg, run_dir=args.out)
    result = bt.run(candles, htf_series=htf)

    print(json.dumps(result.report, indent=2, default=str))
    print(f"\njournal: {result.journal.run_dir}")


if __name__ == "__main__":
    main()
