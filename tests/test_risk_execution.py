import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quant_founds.core.config import Config
from quant_founds.core.enums import ExitReason, Side
from quant_founds.core.models import Account, Candle, TradePlan
from quant_founds.execution import BrokerConfig, PaperBroker
from quant_founds.risk_engine import RiskEngine
from quant_founds.reporting import performance_report, monte_carlo_drawdown


def plan(side=Side.BUY, entry=1.1000, stop=1.0950, tps=(1.1050, 1.1100, 1.1150),
         rr=2.0):
    from datetime import datetime, timezone
    return TradePlan("sig1", "EURUSD", "M15", side, entry, stop, list(tps), rr,
                     datetime(2024, 1, 2, tzinfo=timezone.utc))


class RiskTests(unittest.TestCase):
    def _risk(self, **overrides):
        cfg = Config()
        for k, v in overrides.items():
            setattr(cfg.risk, k, v)
        account = Account(balance=10_000, equity=10_000, peak_equity=10_000)
        return cfg, RiskEngine(cfg.risk, account)

    def test_approval_sizes_position(self):
        cfg, risk = self._risk()
        rd = risk.evaluate(plan(), 10_000, 0, 0, 0, 0)
        self.assertTrue(rd.approved)
        expected = 10_000 * 0.005 / (0.005 * 1.0 * 1.0)
        self.assertAlmostEqual(rd.position_size, expected, places=4)

    def test_rejects_low_rr(self):
        cfg, risk = self._risk(min_risk_reward=3.0)
        p = plan(rr=1.2)
        rd = risk.evaluate(p, 10_000, 0, 0, 0, 0)
        self.assertFalse(rd.approved)
        self.assertTrue(any("rr_too_low" in r for r in rd.reasons))

    def test_daily_loss_limit(self):
        cfg, risk = self._risk(daily_loss_limit_pct=0.01)
        rd = risk.evaluate(plan(), 10_000, -150.0, 0, 0, 0)
        self.assertFalse(rd.approved)
        self.assertIn("daily_loss_limit", rd.reasons)

    def test_drawdown_triggers_kill_switch(self):
        cfg, risk = self._risk(max_drawdown_stop_pct=0.05)
        rd = risk.evaluate(plan(), 10_000, 0, 0, 0, 0)
        self.assertTrue(rd.approved)
        rd2 = risk.evaluate(plan(), 9_400, 0, 0, 0, 0)
        self.assertFalse(rd2.approved)
        self.assertIn("max_drawdown_stop", rd2.reasons)
        self.assertTrue(risk.kill_switch)

    def test_cooldown_after_losses(self):
        cfg, risk = self._risk(max_consecutive_losses=2, cooldown_bars_after_losses=10)
        risk.register_loss(5)
        risk.register_loss(6)
        rd = risk.evaluate(plan(), 10_000, 0, 0, 7, 0)
        self.assertFalse(rd.approved)
        self.assertIn("loss_cooldown", rd.reasons)
        rd2 = risk.evaluate(plan(), 10_000, 0, 0, 20, 0)
        self.assertTrue(rd2.approved)


class ExecutionTests(unittest.TestCase):
    def _broker(self, **kw):
        return PaperBroker(BrokerConfig(**kw))

    def _candle(self, o, h, lo, c, ts):
        return Candle(datetime(2024, 1, 3, tzinfo=timezone.utc) + timedelta(minutes=15 * ts),
                      o, h, lo, c, 1000)

    def test_entry_fills_with_costs(self):
        b = self._broker(spread=0.0001, slippage=0.00005)
        t = b.submit(plan(side=Side.BUY, entry=1.1000), size=1.0)
        self.assertAlmostEqual(t.entry_price, 1.1 + 0.00015, places=6)

    def test_stop_loss_first_when_ambiguous(self):
        b = self._broker(spread=0.0, slippage=0.0)
        t = b.submit(plan(side=Side.BUY, entry=1.1000, stop=1.0950,
                          tps=(1.1050, 1.1100, 1.1150)), size=1.0)
        c = self._candle(1.0990, 1.1100, 1.0900, 1.1080, 1)  # bar spans SL and TP
        b.on_bar(c)
        self.assertIsNone(b.open)
        self.assertIn("stop_loss", t.exit_reasons)
        self.assertLess(t.realized_pnl, 0)

    def test_partial_tp_then_be(self):
        b = self._broker(spread=0.0, slippage=0.0,
                         partial_tp1_fraction=0.5, move_be_after_tp1=True)
        t = b.submit(plan(side=Side.BUY, entry=1.1000, stop=1.0950,
                          tps=(1.1050, 1.1100, 1.1150)), size=1.0)
        c1 = self._candle(1.1010, 1.1060, 1.1005, 1.1055, 1)
        fills = b.on_bar(c1)
        self.assertIsNotNone(b.open)
        self.assertEqual(len(t.fills), 2)
        self.assertAlmostEqual(t.stop_loss, t.entry_price, places=6)
        c2 = self._candle(1.1060, 1.1110, 1.1055, 1.1105, 2)
        b.on_bar(c2)
        self.assertIsNone(b.open)
        self.assertGreater(t.realized_pnl, 0)

    def test_pnl_sign_for_sell(self):
        b = self._broker(spread=0.0, slippage=0.0, move_be_after_tp1=False,
                         enable_trailing=False)
        t = b.submit(plan(side=Side.SELL, entry=1.1000, stop=1.1050,
                          tps=(1.0950, 1.0900, 1.0850)), size=2.0)
        c = self._candle(1.0990, 1.0995, 1.0890, 1.0895, 1)  # tp2
        b.on_bar(c)
        self.assertIsNone(b.open)
        self.assertGreater(t.realized_pnl, 0)
        self.assertIn("tp", [f.kind for f in t.fills])


class ReportingTests(unittest.TestCase):
    def test_report_metrics(self):
        class FakeTrade:
            def __init__(self, pnl):
                self.realized_pnl = pnl

        trades = [FakeTrade(100), FakeTrade(-50), FakeTrade(200), FakeTrade(-80)]
        rep = performance_report(trades, 1000.0)
        self.assertEqual(rep["n_trades"], 4)
        self.assertEqual(rep["win_rate"], 0.5)
        self.assertAlmostEqual(rep["profit_factor"], 300 / 130, places=3)
        self.assertEqual(rep["final_equity"], 1170.0)
        self.assertGreaterEqual(rep["max_drawdown_pct"], 0)

    def test_empty_report(self):
        self.assertEqual(performance_report([], 1000)["n_trades"], 0)

    def test_monte_carlo(self):
        out = monte_carlo_drawdown([50, -30, 70, -40, 90, -60], runs=200)
        self.assertIn("mdd_p50", out)


if __name__ == "__main__":
    unittest.main()
