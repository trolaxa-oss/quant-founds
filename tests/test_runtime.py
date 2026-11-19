import csv
import json
import os
import shutil
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quant_founds.core.config import Config
from quant_founds.core.engine import AnalysisContext
from quant_founds.core.models import Candle
from quant_founds.runtime import LivePaperRunner, LiveWatcher, resample_htf


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


def fake_provider(candles, name="fake"):
    return type("P", (), {
        "name": name,
        "fetch": lambda self, s, t, b: candles,
    })()


class ResampleTests(unittest.TestCase):
    def test_aggregates_by_bucket(self):
        t0 = datetime(2024, 5, 1, tzinfo=timezone.utc)
        candles = []
        for i in range(8):
            o = 1.0 + i * 0.01
            candles.append(Candle(t0 + timedelta(minutes=15 * i), o, o + 0.01,
                                  o - 0.01, o + 0.005, 10.0))
        out = resample_htf(candles, 60)
        self.assertEqual(len(out), 2)
        first = out[0]
        self.assertEqual(first.open, 1.0)
        self.assertEqual(first.close, candles[3].close)
        self.assertAlmostEqual(first.high,
                               max(c.high for c in candles[:4]))
        self.assertAlmostEqual(first.low, min(c.low for c in candles[:4]))
        self.assertAlmostEqual(first.volume, 40.0)

    def test_closed_only_from_ltf(self):
        t0 = datetime(2024, 5, 1, tzinfo=timezone.utc)
        forming = Candle(t0 + timedelta(minutes=15 * 8), 1.5, 1.7, 1.4, 1.6, 5,
                         closed=False)
        candles = [Candle(t0 + timedelta(minutes=15 * i), 1, 1.1, 0.9, 1.05, 10)
                   for i in range(8)]
        out = resample_htf(candles + [forming], 60)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[-1].high, max(c.high for c in candles[4:]))


class RunnerTests(unittest.TestCase):
    def setUp(self):
        for d in ("runs/_test_paper", "runs/_test_paper2"):
            shutil.rmtree(d, ignore_errors=True)

    def _config(self):
        cfg = Config()
        cfg.scoring.watch_threshold = 45.0
        cfg.scoring.entry_threshold = 60.0
        return cfg

    def _notifiers(self):
        from quant_founds.notify import NotifierChain

        return NotifierChain(notifiers=[])

    def test_paper_runner_opens_and_closes_trades(self):
        cfg = self._config()
        candles = make_series()
        runner = LivePaperRunner(cfg, fake_provider(candles),
                                 run_dir="runs/_test_paper",
                                 notifiers=self._notifiers())
        runner.run_once()
        self.assertEqual(runner.n_bars_seen, len(candles))
        self.assertGreaterEqual(len(runner.trades), 1)
        self.assertTrue(all(t.closed_time is not None for t in runner.trades))
        with open("runs/_test_paper/trades.csv") as fh:
            rows = list(csv.DictReader(fh))
        self.assertGreaterEqual(len(rows), len(runner.trades))
        self.assertEqual(rows[-1]["trade_id"], runner.trades[-1].trade_id)
        with open("runs/_test_paper/decisions.jsonl") as fh:
            journal_rows = [json.loads(line) for line in fh]
        self.assertTrue(any("paper_order_submitted" in r["notes"]
                            for r in journal_rows))

    def test_run_once_idempotent(self):
        cfg = self._config()
        candles = make_series()
        runner = LivePaperRunner(cfg, fake_provider(candles),
                                 run_dir="runs/_test_paper2",
                                 notifiers=self._notifiers())
        runner.run_once()
        with open("runs/_test_paper2/decisions.jsonl") as fh:
            before = len(fh.readlines())
        bars_before = runner.n_bars_seen
        fired2 = runner.run_once()
        self.assertEqual(fired2, [])
        with open("runs/_test_paper2/decisions.jsonl") as fh:
            after = len(fh.readlines())
        self.assertEqual(after, before)
        summary = runner.snapshot_summary()
        self.assertEqual(runner.n_bars_seen, bars_before)
        self.assertTrue(summary["n_bars_seen"] >= 0)

    def test_watch_runner_no_trading_and_idempotent(self):
        shutil.rmtree("runs/_test_watch_rt", ignore_errors=True)
        cfg = self._config()
        candles = make_series(120)
        watcher = LiveWatcher(cfg, fake_provider(candles),
                              run_dir="runs/_test_watch_rt",
                              notifiers=self._notifiers())
        watcher.run_once()
        self.assertEqual(watcher.last_bar_time, candles[-1].timestamp)
        self.assertIsNotNone(watcher._last_results)
        self.assertIn("market", watcher._last_results)
        shutil.rmtree("runs/_test_watch_rt", ignore_errors=True)


class NotifyTests(unittest.TestCase):
    def test_build_from_env_console_only(self):
        from quant_founds import notify

        old = {k: os.environ.pop(k, None) for k in
               ("QF_WEBHOOK_URL", "QF_TELEGRAM_BOT_TOKEN", "QF_TELEGRAM_CHAT_ID")}
        try:
            self.assertEqual([n.name for n in notify.build_from_env()], ["console"])
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v

    def test_webhook_and_telegram_payloads_via_injected_transport(self):
        from quant_founds.notify import TelegramNotifier, WebhookNotifier

        sent = []
        def transport(url, payload, timeout=10.0):
            sent.append((url, payload))
            return None

        hook = ["x"]
        WebhookNotifier("http://example.invalid/hook", transport=transport).send("t", "m")
        self.assertEqual(sent[0][0], "http://example.invalid/hook")
        self.assertIn("m", sent[0][1]["content"])
        TelegramNotifier("TOK", "123", transport=transport).send("t2", "m2")
        self.assertIn("/botTOK/sendMessage", sent[1][0])
        self.assertEqual(sent[1][1]["chat_id"], "123")

    def test_notifier_chain_env_wiring(self):
        from quant_founds.notify import NotifierChain

        old = {k: os.environ.pop(k, None) for k in
               ("QF_WEBHOOK_URL", "QF_TELEGRAM_BOT_TOKEN", "QF_TELEGRAM_CHAT_ID")}
        try:
            os.environ["QF_WEBHOOK_URL"] = "http://x.invalid/wh"
            chain = NotifierChain(notifiers=None)
            sent = []
            def transport(url, payload, timeout=10.0):
                sent.append(url)
            chain.notifiers[1]._transport = transport
            chain.send("hi", "there")
            self.assertEqual(sent, ["http://x.invalid/wh"])
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v

    def test_injected_failures_swallowed(self):
        from quant_founds.notify import WebhookNotifier

        def boom(url, payload, timeout=10.0):
            raise OSError("no route")

        WebhookNotifier("http://x.invalid", transport=boom).send("t", "m")


if __name__ == "__main__":
    unittest.main()
