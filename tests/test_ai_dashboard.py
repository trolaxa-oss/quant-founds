import json
import os
import shutil
import sys
import unittest
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quant_founds.core.models import Candle
from quant_founds.core.config import Config
from quant_founds.online_ai import OnlineLogit


def make_series(n=900, base=1.10, seed=7):
    from datetime import datetime, timedelta, timezone
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


def fake_provider(candles, name="fake"):
    return type("P", (), {
        "name": name,
        "fetch": lambda self, s, t, b: candles,
    })()


class OnlineAiTests(unittest.TestCase):
    def test_probability_bounds_and_neutral_state(self):
        model = OnlineLogit()
        self.assertEqual(model.probability({}), 0.5)
        for features in ({}, {"market": 55}, {"market": None, "x": "bad"}):
            p = model.probability(features)
            self.assertTrue(0.0 < p < 1.0)

    def test_learns_separable_feature(self):
        model = OnlineLogit(lr=0.2)
        for _ in range(300):
            model.update({"liquidity": 80.0}, 1.0)
            model.update({"liquidity": 10.0}, 0.0)
        self.assertGreater(model.probability({"liquidity": 80.0}), 0.9)
        self.assertLess(model.probability({"liquidity": 10.0}), 0.1)
        label, score = model.classify({"liquidity": 80.0})
        self.assertEqual(label, "bullish")
        self.assertTrue(0 <= score <= 100)

    def test_save_load_roundtrip(self):
        model = OnlineLogit()
        model.update({"liquidity": 80.0}, 1.0)
        model.update({"orderflow": 30.0}, 0.0)
        model.save("runs/_test_ai/model.json")
        loaded = OnlineLogit.load("runs/_test_ai/model.json")
        self.assertIsNotNone(loaded)
        self.assertAlmostEqual(loaded.bias, model.bias)
        self.assertEqual(loaded.weights, model.weights)
        self.assertEqual(loaded.n_updates, 2)
        shutil.rmtree("runs/_test_ai", ignore_errors=True)

    def test_load_rejects_missing_or_bad_version(self):
        self.assertIsNone(OnlineLogit.load("runs/_no_such_dir/m.json"))
        os.makedirs("runs/_test_ai2", exist_ok=True)
        with open("runs/_test_ai2/m.json", "w") as fh:
            json.dump({"version": "other"}, fh)
        self.assertIsNone(OnlineLogit.load("runs/_test_ai2/m.json"))
        shutil.rmtree("runs/_test_ai2", ignore_errors=True)


class AiGateTests(unittest.TestCase):
    def setUp(self):
        shutil.rmtree("runs/_test_gate", ignore_errors=True)

    def _config(self):
        cfg = Config()
        cfg.scoring.watch_threshold = 45.0
        cfg.scoring.entry_threshold = 60.0
        return cfg

    def test_untrained_model_is_inert(self):
        from quant_founds.runtime import LivePaperRunner

        runner = LivePaperRunner(self._config(), fake_provider(make_series()),
                                 run_dir="runs/_test_gate",
                                 ai_gate=True, ai_min_probability=0.5,
                                 ai_min_samples=30,
                                 notifiers=type("NC", (), {"send": lambda *a: None})())
        runner.run_once()
        self.assertGreaterEqual(len(runner.trades), 1)

    def test_low_probability_model_blocks_entries(self):
        from quant_founds.runtime import LivePaperRunner

        model = OnlineLogit()
        model.bias = -50.0
        model.n_updates = 100
        runner = LivePaperRunner(self._config(), fake_provider(make_series()),
                                 run_dir="runs/_test_gate", ai_gate=True,
                                 ai_model=model, ai_min_probability=0.5,
                                 ai_min_samples=1,
                                 notifiers=type("NC", (), {"send": lambda *a: None})())
        runner.run_once()
        self.assertEqual(runner.trades, [])
        with open("runs/_test_gate/decisions.jsonl") as fh:
            rows = [json.loads(l) for l in fh]
        self.assertTrue(any("ai_gate_rejected" in r["notes"] for r in rows))
        self.assertTrue(any(any(n.startswith("ai_prob=") for n in r["notes"])
                            for r in rows))

    def test_model_updates_from_closed_trades_and_persists(self):
        from quant_founds.runtime import LivePaperRunner

        model = OnlineLogit()
        model.bias = 50.0
        model.n_updates = 100
        runner = LivePaperRunner(self._config(), fake_provider(make_series()),
                                 run_dir="runs/_test_gate", ai_gate=True,
                                 ai_model=model, ai_min_probability=0.5,
                                 ai_min_samples=1,
                                 notifiers=type("NC", (), {"send": lambda *a: None})())
        runner.run_once()
        self.assertGreaterEqual(len(runner.trades), 1)
        self.assertEqual(model.n_updates, 100 + len(runner.trades))
        self.assertTrue(os.path.exists("runs/_test_gate/ai_model.json"))


class DashboardTests(unittest.TestCase):
    def setUp(self):
        shutil.rmtree("runs/_test_dash", ignore_errors=True)

    def _runner(self):
        from quant_founds.runtime import LivePaperRunner

        cfg = Config()
        cfg.scoring.watch_threshold = 45.0
        cfg.scoring.entry_threshold = 60.0
        runner = LivePaperRunner(cfg, fake_provider(make_series()),
                                 run_dir="runs/_test_dash",
                                 notifiers=type("NC", (), {"send": lambda *a: None})())
        runner.run_once()
        return runner

    def test_state_collection_and_rendering(self):
        from quant_founds.dashboard_live import collect_state, render_dashboard

        runner = self._runner()
        state = collect_state(runner)
        self.assertEqual(state["symbol"], cfg_sym(runner))
        self.assertGreaterEqual(len(state["trades"]), 1)
        self.assertEqual(len(state["cumulative_pnl"]), len(runner.trades))
        page = render_dashboard(state)
        self.assertIn("<!doctype html>", page.lower())
        self.assertIn("<svg", page)
        self.assertIn("لوحة التداول الورقي", page)

    def test_render_escapes_text_fields(self):
        from quant_founds.dashboard_live import render_dashboard

        page = render_dashboard({
            "now": "<x>", "symbol": '<s">', "timeframe": "M15",
            "balance": 1.0, "equity": 1.0, "peak_equity": 1.0,
            "day_pnl": 0.0, "n_bars_seen": 1, "open_trade": None,
            "trades": [{"trade_id": "<b>", "side": "buy", "entry_time": "t",
                        "entry_price": 1, "realized_pnl": -1, "exit_reasons": "<i>"}],
            "decisions": [{"bar_time": "t", "state": '<i>', "side": "buy",
                           "score": 1, "notes": ["<u>"]}],
            "metrics": {}, "ai": None, "cumulative_pnl": [-1.0],
        })
        self.assertNotIn("<script>", page)
        self.assertNotIn("<i>", page)
        self.assertFalse("<u>" in page)

    def test_loopback_http_serves_dashboard(self):
        from quant_founds.dashboard_live import start_dashboard

        runner = self._runner()
        server = start_dashboard(runner, host="127.0.0.1", port=0)
        port = server.server_address[1]
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/", timeout=10) as resp:
                body = resp.read().decode()
                self.assertEqual(resp.status, 200)
        finally:
            server.shutdown()
            server.server_close()
        self.assertIn("QUANT FOUNDS", body)
        self.assertIn(str(runner.cfg.data.symbol), body)


def cfg_sym(runner):
    return runner.cfg.data.symbol


if __name__ == "__main__":
    unittest.main()
