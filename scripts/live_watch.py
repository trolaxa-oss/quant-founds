"""Live paper watch mode (blueprint 12 + 17): run the pipeline on real data.

Polls a provider on an interval, processes only newly CLOSED bars, and emits
WATCH/SETUP/CONFIRMED alerts. No orders are ever sent - this is analysis and
alerting only. All decisions are journaled under runs/live/.

Examples:
    python3 scripts/live_watch.py --provider binance --symbol BTCUSDT --timeframe M15
    python3 scripts/live_watch.py --provider mt5_bridge --symbol EURUSD --timeframe M15
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quant_founds.core.config import Config
from quant_founds.core.engine import AnalysisContext
from quant_founds.core.enums import SignalState
from quant_founds.decision.signal_engine import SignalDecisionEngine
from quant_founds.engines import (AiIntelligence, DataEngine, LiquidityIntelligence,
                                  MarketIntelligence, MultiTimeframeEngine,
                                  NewsIntelligence, OrderFlowIntelligence, SmcIntelligence)
from quant_founds.providers import provider_from_config
from quant_founds.sessions import SessionEngine


class LiveWatcher:
    def __init__(self, cfg: Config, provider, poll_seconds: float = 30.0,
                 history_bars: int = 400, run_dir: str = "runs/live"):
        self.cfg = cfg
        self.provider = provider
        self.poll_seconds = poll_seconds
        self.history_bars = history_bars
        self.last_bar_time = None
        self.data_engine = DataEngine(cfg.data.max_gap_bars)
        self.market = MarketIntelligence()
        self.liquidity = LiquidityIntelligence()
        self.orderflow = OrderFlowIntelligence()
        self.smc = SmcIntelligence()
        self.mtf = MultiTimeframeEngine(cfg.data.higher_timeframes)
        self.news = NewsIntelligence()
        self.ai = AiIntelligence()
        self.sessions = SessionEngine(cfg.sessions)
        self.signals = SignalDecisionEngine(cfg)
        self.journal_path = os.path.join(run_dir, "decisions.jsonl")
        os.makedirs(run_dir, exist_ok=True)

    def engines(self):
        return [self.data_engine, self.market, self.liquidity, self.orderflow,
                self.smc, self.mtf, self.news, self.ai, self.sessions]

    def run_once(self) -> list:
        candles = self.provider.fetch(self.cfg.data.symbol, self.cfg.data.timeframe,
                                      self.history_bars)
        if not candles:
            return []
        newest_closed = [c for c in candles if c.closed]
        if not newest_closed:
            return []
        fired = []
        for candle in newest_closed:
            if self.last_bar_time is not None and candle.timestamp <= self.last_bar_time:
                continue
            self.last_bar_time = candle.timestamp
            ctx = AnalysisContext(
                symbol=self.cfg.data.symbol,
                timeframe=self.cfg.data.timeframe,
                candles=[c for c in newest_closed
                         if c.timestamp <= candle.timestamp][-self.history_bars:],
                timestamp=candle.timestamp,
            )
            results = {}
            for eng in self.engines():
                results[eng.engine_id] = eng.analyze(ctx)
            results.pop("ai", None)
            decision = self.signals.decide(ctx, results)
            if decision is None:
                continue
            self._journal(decision)
            if decision.state in (SignalState.WATCH, SignalState.SETUP,
                                  SignalState.CONFIRMED, SignalState.ACTIVE):
                fired.append(decision)
        return fired

    def _journal(self, decision) -> None:
        row = {
            "logged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "bar_time": decision.bar_time.isoformat(),
            "state": decision.state.value,
            "type": decision.signal_type.value,
            "side": decision.side.value if decision.side else None,
            "score": decision.score,
            "hard_failures": decision.hard_failures,
            "notes": list(decision.notes),
        }
        with open(self.journal_path, "a") as fh:
            fh.write(json.dumps(row) + "\n")

    def run_forever(self) -> None:
        print(f"live paper watch on {self.cfg.data.symbol} "
              f"{self.cfg.data.timeframe} via {self.provider.name} "
              f"(poll {self.poll_seconds:.0f}s, Ctrl+C to stop)")
        while True:
            try:
                for d in self.run_once():
                    side = d.side.value if d.side else "-"
                    print(f"[{d.bar_time:%H:%M}] {d.state.value:<9} {side:<4} "
                          f"score={d.score:.1f}")
            except KeyboardInterrupt:
                print("stopped")
                return
            except Exception as exc:
                print(f"poll error: {exc}")
            time.sleep(self.poll_seconds)


def main() -> None:
    ap = argparse.ArgumentParser(description="QUANT FOUNDS live paper watch")
    ap.add_argument("--provider", default="")
    ap.add_argument("--symbol", default="")
    ap.add_argument("--timeframe", default="")
    ap.add_argument("--poll", type=float, default=30.0)
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

    provider = provider_from_config(cfg)
    watcher = LiveWatcher(cfg, provider, poll_seconds=args.poll)
    if args.once:
        for d in watcher.run_once():
            print(f"[{d.bar_time:%H:%M}] {d.state.value} "
                  f"score={d.score:.1f} side={d.side.value if d.side else '-'}")
    else:
        watcher.run_forever()


if __name__ == "__main__":
    main()
