import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quant_founds.backtest import Backtester
from quant_founds.core.config import Config
from quant_founds.core.enums import Side
from quant_founds.core.models import Candle


def make_series(n=900, base=1.10, seed=7):
    from random import Random
    rng = Random(seed)
    t0 = datetime(2024, 1, 2, tzinfo=timezone.utc)
    price = base
    drift = 0.0
    out = []
    for i in range(n):
        if i % 180 == 0:
            drift = rng.choice([-1, 1]) * rng.uniform(0.00002, 0.0001)
        o = price
        c = o + drift + rng.gauss(0, 0.00035)
        out.append(Candle(t0 + timedelta(minutes=15 * i), o,
                          max(o, c) + 0.0003, min(o, c) - 0.0003, c,
                          800 + rng.uniform(0, 400)))
        price = c
    return out


def build_htf(candles, minutes):
    out = []
    bucket = None
    for c in candles:
        slot = int(c.timestamp.timestamp() // (minutes * 60))
        if bucket is None or slot != bucket["slot"]:
            if bucket:
                out.append(bucket["candle"])
            bucket = {"slot": slot, "candle": c}
        else:
            m = bucket["candle"]
            bucket["candle"] = Candle(m.timestamp, m.open, max(m.high, c.high),
                                      min(m.low, c.low), c.close, m.volume + c.volume)
    if bucket:
        out.append(bucket["candle"])
    return out


class BacktestSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candles = make_series()
        cls.htf = {"H1": build_htf(cls.candles, 60)}

    def _run(self, candles, tmp):
        cfg = Config()
        cfg.scoring.watch_threshold = 45.0
        cfg.scoring.entry_threshold = 60.0
        bt = Backtester(cfg, run_dir=tmp)
        return bt.run(candles, htf_series=self.htf)

    def test_produces_report_and_journal(self):
        result = self._run(self.candles, "runs/_test_smoke")
        rep = result.report
        for key in ("n_trades", "win_rate", "profit_factor", "expectancy",
                    "max_drawdown_pct", "final_equity", "walk_forward"):
            self.assertIn(key, rep)
        self.assertTrue(os.path.exists("runs/_test_smoke/decisions.jsonl"))
        self.assertTrue(os.path.exists("runs/_test_smoke/summary.json"))
        if rep["n_trades"] > 0:
            self.assertTrue(os.path.exists("runs/_test_smoke/trades.csv"))
        self.assertTrue(os.path.exists("runs/_test_smoke"))

    def test_deterministic_run(self):
        r1 = self._run(self.candles, "runs/_test_det1")
        r2 = self._run(self.candles, "runs/_test_det2")
        self.assertEqual(r1.report["n_trades"], r2.report["n_trades"])
        self.assertAlmostEqual(r1.report["final_equity"], r2.report["final_equity"])
        p1 = [t.realized_pnl for t in r1.trades]
        p2 = [t.realized_pnl for t in r2.trades]
        self.assertEqual(len(p1), len(p2))
        if p1:
            self.assertEqual(p1, p2)

    def test_unique_trade_ids(self):
        result = self._run(self.candles, "runs/_test_ids")
        ids = [t.trade_id for t in result.trades]
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_decisions_before_warmup(self):
        cfg = Config()
        cfg.scoring.watch_threshold = 0.0
        cfg.scoring.entry_threshold = 1.0
        bt = Backtester(cfg, run_dir="runs/_test_warmup")
        result = bt.run(self.candles[:60], htf_series={"H1": build_htf(self.candles[:60], 60)})
        warmup = cfg.backtest.warmup_bars
        expected = max(0, 60 - warmup)
        self.assertLessEqual(result.decisions_count, expected)

    def test_execution_never_longs_on_sell_plan(self):
        from quant_founds.execution import BrokerConfig, PaperBroker
        b = PaperBroker(BrokerConfig())
        from quant_founds.core.models import TradePlan
        p = TradePlan("s", "EURUSD", "M15", Side.SELL, 1.1, 1.105,
                      [1.095, 1.09, 1.085], 2.0, datetime(2024, 1, 2, tzinfo=timezone.utc))
        t = b.submit(p, 1.0)
        self.assertLess(t.entry_price, 1.1)


if __name__ == "__main__":
    unittest.main()
