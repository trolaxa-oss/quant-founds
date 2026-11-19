import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quant_founds.core.config import Config
from quant_founds.core.models import Candle
from quant_founds.reporting import render_html_report
from quant_founds.backtest import Backtester


class HtmlReportTests(unittest.TestCase):
    def test_render_with_trades_and_equity(self):
        os.chdir(os.path.join(os.path.dirname(__file__), ".."))
        cfg = Config()
        res = Backtester(cfg, run_dir="runs/_test_html").run([])
        self.addCleanup(lambda: __import__("shutil").rmtree("runs/_test_html", True))
        page = render_html_report(res.trades, res.report, "runs/_test_html/report.html")
        self.assertIn("<!doctype html>", page)
        self.assertIn("No trades.", page)
        with open("runs/_test_html/report.html") as fh:
            written = fh.read()
        self.assertEqual(written, page)

    def test_html_escapes_trade_fields(self):
        from quant_founds.reporting import render_html_report as rnd

        class T:
            trade_id = "<script>x</script>abc"
            side = "buy"
            entry_time = "t"
            entry_price = 1.0
            quantity = 1
            realized_pnl = 5
            exit_reasons = ["tp1"]

        page = rnd([T()], {"n_trades": 1}, "/tmp/_esc_report.html")
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)


class LiveWatcherTests(unittest.TestCase):
    def setUp(self):
        import shutil
        for d in ("runs/_test_live", "runs/_test_live2"):
            shutil.rmtree(d, ignore_errors=True)

    def _candles(self, n=120):
        from random import Random
        rng = Random(2)
        t0 = datetime(2024, 5, 1, tzinfo=timezone.utc)
        price = 100.0
        out = []
        for i in range(n):
            o = price
            c = o + rng.gauss(0, 0.3)
            out.append(Candle(t0 + timedelta(minutes=15 * i), o,
                              max(o, c) + 0.2, min(o, c) - 0.2, c, 1000.0))
            price = c
        return out

    def test_run_once_processes_each_closed_bar_once(self):
        sys.path.insert(0, "scripts")
        from live_watch import LiveWatcher

        cfg = Config()
        candles = self._candles(80)
        provider = type("P", (), {"name": "fake",
                                  "fetch": lambda self, s, t, b: candles})()
        watcher = LiveWatcher(cfg, provider, poll_seconds=1, run_dir="runs/_test_live")
        fired = watcher.run_once()
        self.assertEqual(watcher.last_bar_time, candles[-1].timestamp)
        with open("runs/_test_live/decisions.jsonl") as fh:
            rows = [json.loads(line) for line in fh]
        self.assertEqual(len(rows), len(candles))
        states = {r["state"] for r in rows}
        allowed = {"IDLE", "WATCH", "SETUP", "CONFIRMED", "INVALIDATED"}
        self.assertTrue(states <= allowed, states)

        fired2 = watcher.run_once()
        self.assertEqual(fired2, [])
        with open("runs/_test_live/decisions.jsonl") as fh:
            rows_after = [json.loads(line) for line in fh]
        self.assertEqual(len(rows_after), len(rows))

    def test_drops_forming_bar(self):
        sys.path.insert(0, "scripts")
        from live_watch import LiveWatcher

        cfg = Config()
        candles = self._candles(30)
        forming = Candle(candles[-1].timestamp + timedelta(minutes=15),
                         100, 101, 99, 100.5, 10, closed=False)
        provider = type("P", (), {"name": "fake",
                                  "fetch": lambda self, s, t, b: candles + [forming]})()
        watcher = LiveWatcher(cfg, provider, poll_seconds=1, run_dir="runs/_test_live2")
        watcher.run_once()
        self.assertEqual(watcher.last_bar_time, candles[-1].timestamp)


if __name__ == "__main__":
    unittest.main()
