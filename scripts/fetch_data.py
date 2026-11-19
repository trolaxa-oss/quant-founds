"""Fetch real OHLCV data into a CSV the backtester can consume.

Examples:
    python scripts/fetch_data.py --provider binance --symbol BTCUSDT --timeframe M15 --bars 3000
    python scripts/fetch_data.py --provider mt5_bridge --symbol EURUSD --timeframe M15 --bars 3000
    python scripts/fetch_data.py --provider csv --out data/existing.csv   # validate + rewrite
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quant_founds.core.config import Config
from quant_founds.providers import CsvProvider, provider_from_config


def to_csv(candles, path: str) -> int:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        fh.write("timestamp,open,high,low,close,volume\n")
        for c in candles:
            fh.write(f"{c.timestamp.strftime('%Y-%m-%d %H:%M:%S')},"
                     f"{c.open:.6f},{c.high:.6f},{c.low:.6f},{c.close:.6f},"
                     f"{c.volume:.2f}\n")
    return len(candles)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch OHLCV into CSV")
    ap.add_argument("--provider", default="", help="csv | binance | mt5_bridge")
    ap.add_argument("--symbol", default="")
    ap.add_argument("--timeframe", default="")
    ap.add_argument("--bars", type=int, default=3000)
    ap.add_argument("--csv", dest="csv_path", default="", help="csv provider path")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    cfg = Config.from_toml("config/default.toml")
    if args.provider:
        cfg.data.source_mode = args.provider
    if args.symbol:
        cfg.data.symbol = args.symbol
    if args.timeframe:
        cfg.data.timeframe = args.timeframe
    out = args.out or f"data/{cfg.data.symbol}_{cfg.data.timeframe}.csv"

    if cfg.data.source_mode == "csv":
        provider = CsvProvider(path=args.csv_path or cfg.data.csv_path)
    else:
        provider = provider_from_config(cfg)

    candles = provider.fetch(cfg.data.symbol, cfg.data.timeframe, args.bars)
    n = to_csv(candles, out)
    print(f"wrote {n} closed candles for {cfg.data.symbol} {cfg.data.timeframe} -> {out}")
    print(f"run backtest: python3 scripts/run_backtest.py --csv {out}")


if __name__ == "__main__":
    main()
