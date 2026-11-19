"""Live paper watch/trade CLI (blueprint 12 + 17): run the pipeline on real data.

Defaults to watch mode (analysis + alerting, no orders). With --trade it runs
the full paper pipeline: decision -> plan -> risk -> paper fills -> trade
management, journaled under runs/live_paper/. No real orders are ever sent.

Examples:
    python3 scripts/live_watch.py --provider binance --symbol BTCUSDT --timeframe M15
    python3 scripts/live_watch.py --provider mt5_bridge --symbol EURUSD --timeframe M15
    python3 scripts/live_watch.py --provider csv --csv data/sample_EURUSD_M15.csv --trade --once
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, __file__.rsplit("/", 2)[0])

from quant_founds.core.config import Config
from quant_founds.providers import provider_from_config
from quant_founds.runtime import LivePaperRunner, LiveWatcher


def main() -> None:
    ap = argparse.ArgumentParser(description="QUANT FOUNDS live watch / paper trading")
    ap.add_argument("--provider", default="")
    ap.add_argument("--symbol", default="")
    ap.add_argument("--timeframe", default="")
    ap.add_argument("--csv", default="", help="CSV path when --provider csv")
    ap.add_argument("--poll", type=float, default=30.0)
    ap.add_argument("--history", type=int, default=400)
    ap.add_argument("--trade", action="store_true",
                    help="run the full paper pipeline (plan -> risk -> paper fills)")
    ap.add_argument("--balance", type=float, default=10_000.0)
    ap.add_argument("--run-dir", default="")
    ap.add_argument("--once", action="store_true", help="process once and exit")
    ap.add_argument("--config", default="config/default.toml")
    args = ap.parse_args()

    cfg = Config.from_toml(args.config)
    if args.provider:
        cfg.data.source_mode = args.provider
    if args.symbol:
        cfg.data.symbol = args.symbol
    if args.timeframe:
        cfg.data.timeframe = args.timeframe
    if args.csv:
        cfg.data.csv_path = args.csv
        if not args.provider:
            cfg.data.source_mode = "csv"

    provider = provider_from_config(cfg)
    runner = LivePaperRunner if args.trade else LiveWatcher
    kwargs: dict = {"poll_seconds": args.poll, "history_bars": args.history}
    if args.run_dir:
        kwargs["run_dir"] = args.run_dir
    if args.trade:
        kwargs["initial_balance"] = args.balance
    engine = runner(cfg, provider, **kwargs)

    if args.once:
        for d in engine.run_once():
            extra = ""
            if args.trade:
                extra = f" equity={engine.account.equity:.2f}"
            side = d.side.value if d.side else "-"
            print(f"[{d.bar_time:%H:%M}] {d.state.value} {side} "
                  f"score={d.score:.1f}{extra}")
        if args.trade:
            import json

            print(json.dumps(engine.snapshot_summary()))
    else:
        engine.run_forever()


if __name__ == "__main__":
    main()
