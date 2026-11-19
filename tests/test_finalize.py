import os
import shutil
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quant_founds.core.config import Config
from quant_founds.core.engine import AnalysisContext
from quant_founds.core.enums import Side
from quant_founds.core.models import Candle, EconomicEvent, Trade
from quant_founds.engines.news_intel import NewsIntelligence
from quant_founds.reporting import (monte_carlo_drawdown, performance_report,
                                    walk_forward_report)


def _trade(pnl, costs=0.5, hour=12):
    i = _trade.i
    _trade.i += 1
    return Trade(
        trade_id=f"t{i}", signal_id=f"s{i}", symbol="EURUSD", timeframe="M15",
        side=Side.BUY, entry_time=datetime(2024, 1, 2, hour, tzinfo=timezone.utc),
        entry_price=1.1, quantity=1000, stop_loss=1.09, take_profits=[1.12],
        realized_pnl=pnl, costs=costs,
        closed_time=datetime(2024, 1, 2, hour, tzinfo=timezone.utc)
        + timedelta(hours=1),
    )

_trade.i = 0


class ReportMetricsTests(unittest.TestCase):
    def test_new_metric_keys_present(self):
        rep = performance_report([_trade(100), _trade(-40), _trade(60)],
                                 initial_balance=10_000)
        for key in ("avg_win", "avg_loss", "total_costs", "sharpe", "sortino"):
            self.assertIn(key, rep)
        self.assertAlmostEqual(rep["avg_win"], 80.0)
        self.assertAlmostEqual(rep["avg_loss"], -40.0)
        self.assertAlmostEqual(rep["total_costs"], 1.5)
        self.assertTrue(rep["sharpe"] is None or abs(rep["sharpe"]) < 100)
        rep1 = performance_report([_trade(50), _trade(50)])
        self.assertIsNone(rep1["sharpe"])
        self.assertIsNone(rep1["sortino"])

    def test_empty_report_keys(self):
        rep = performance_report([])
        self.assertEqual(rep, {"n_trades": 0})

    def test_sharpe_sortino_separability(self):
        from quant_founds.reporting import sharpe_sortino

        returns = [0.01] * 10 + [-0.005] * 10
        sharpe, sortino = sharpe_sortino(returns)
        self.assertGreater(sharpe, 0)
        self.assertGreater(sortino, sharpe)
        self.assertEqual(sharpe_sortino([]), (None, None))


class WalkForwardReportTests(unittest.TestCase):
    def test_windows_metrics_and_stability(self):
        timestamps = [datetime(2024, 1, 1, tzinfo=timezone.utc)
                      + timedelta(minutes=15 * i) for i in range(900)]
        trades = [_trade(30), _trade(-10), _trade(25), _trade(15)]
        wf = walk_forward_report(trades, timestamps, folds=3)
        self.assertEqual(wf["n_windows"], 3)
        self.assertEqual(len(wf["windows"]), 3)
        for w in wf["windows"]:
            self.assertIn("train_bars", w)
            self.assertIn("test_bars", w)
            self.assertIn("n_trades", w["metrics"])
            self.assertNotIn("equity_curve", w["metrics"])
        self.assertEqual(wf["profitable_windows"] <= wf["n_windows"], True)
        self.assertTrue(0 <= wf["stability"] <= 1)

    def test_monte_carlo_deterministic_with_seed(self):
        pnls = [10, -5, 20, -8, 12, -3, 25, -11]
        a = monte_carlo_drawdown(pnls, runs=100, seed=3)
        b = monte_carlo_drawdown(pnls, runs=100, seed=3)
        self.assertEqual(a, b)
        self.assertIn("mdd_p95", a)


class NewsEventsTests(unittest.TestCase):
    def setUp(self):
        self.path = "runs/_test_events/events.csv"
        os.makedirs("runs/_test_events", exist_ok=True)
        with open(self.path, "w") as fh:
            fh.write("timestamp,currency,impact,name\n"
                     "2024-01-02T14:30:00+00:00,USD,high,NFP\n"
                     "2024-01-05T09:00:00+00:00,EUR,low,ECB panel\n")

    def tearDown(self):
        shutil.rmtree("runs/_test_events", ignore_errors=True)

    def _ctx(self, ts):
        candles = [Candle(ts - timedelta(minutes=15 * i), 1.1, 1.11, 1.09,
                          1.105, 100) for i in range(5)][::-1]
        return AnalysisContext(symbol="EURUSD", timeframe="M15",
                               candles=candles, timestamp=ts)

    def test_from_csv_parses_events(self):
        events = NewsIntelligence.from_csv(self.path)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].currency, "USD")
        self.assertEqual(events[0].name, "NFP")

    def test_block_window_active_and_clear(self):
        events = NewsIntelligence.from_csv(self.path)
        engine = NewsIntelligence(events=events,
                                  block_minutes_before=30,
                                  block_minutes_after=30)
        blocked = engine.analyze(self._ctx(datetime(2024, 1, 2, 14, 45,
                                                     tzinfo=timezone.utc)))
        self.assertEqual(blocked.state, "blocked")
        self.assertEqual(blocked.score, 0.0)
        clear = engine.analyze(self._ctx(datetime(2024, 1, 3, 14, 45,
                                                  tzinfo=timezone.utc)))
        self.assertEqual(clear.state, "clear")
        self.assertEqual(clear.score, 100.0)

    def test_backtester_loads_events_from_config(self):
        import shutil as sh
        sh.rmtree("runs/_test_bt_events", ignore_errors=True)
        from quant_founds.backtest import Backtester

        cfg = Config()
        cfg.news.events_csv = self.path
        bt = Backtester(cfg, run_dir="runs/_test_bt_events")
        self.assertEqual(len(bt.events), 2)
        sh.rmtree("runs/_test_bt_events", ignore_errors=True)

    def test_runtime_loads_events_and_block_params(self):
        import shutil as sh
        sh.rmtree("runs/_test_rt_events", ignore_errors=True)
        from quant_founds.runtime import LiveWatcher

        cfg = Config()
        cfg.news.events_csv = self.path
        cfg.news.block_minutes_before = 45
        provider = type("P", (), {"name": "fake",
                                  "fetch": lambda self, s, t, b: []})()
        w = LiveWatcher(cfg, provider, run_dir="runs/_test_rt_events")
        self.assertEqual(len(w.news.events), 2)
        self.assertEqual(w.news.before, timedelta(minutes=45))
        sh.rmtree("runs/_test_rt_events", ignore_errors=True)


class ConfigValidationTests(unittest.TestCase):
    def test_default_config_valid(self):
        self.assertEqual(Config().validate(), [])

    def test_invalid_values_reported(self):
        cfg = Config()
        cfg.risk.risk_per_trade_pct = 0.5
        cfg.scoring.watch_threshold = 80.0
        cfg.scoring.entry_threshold = 60.0
        cfg.scoring.weights["trend"] = -15.0
        cfg.data.timeframe = "M7"
        errors = cfg.validate()
        self.assertEqual(len(errors), 5)
        self.assertTrue(any("risk_per_trade_pct" in e for e in errors))
        self.assertTrue(any("thresholds" in e for e in errors))
        self.assertTrue(any("non-negative" in e for e in errors))
        self.assertTrue(any("timeframe" in e for e in errors))

    def test_weights_must_sum_to_100(self):
        cfg = Config()
        cfg.scoring.weights["trend"] = 10.0
        errors = cfg.validate()
        self.assertTrue(any("sum to 100" in e for e in errors))

    def test_from_toml_raises_on_invalid(self):
        os.makedirs("runs/_test_cfg", exist_ok=True)
        with open("runs/_test_cfg/bad.toml", "w") as fh:
            fh.write("[risk]\nrisk_per_trade_pct = 0.9\n")
        with self.assertRaises(ValueError):
            Config.from_toml("runs/_test_cfg/bad.toml")
        shutil.rmtree("runs/_test_cfg", ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
