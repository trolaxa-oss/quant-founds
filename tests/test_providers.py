import os
import sys
import time
import unittest
from datetime import timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quant_founds.core.config import Config
from quant_founds.providers import CsvProvider, Mt5BridgeProvider, provider_from_config
from quant_founds.providers import BinanceProvider


def kline(i, open_ms, high_extra=2.0):
    """Synthetic Binance kline row: [open_time, o, h, l, c, vol, close_time, ...]"""
    o = 100.0 + i * 0.01
    c = o + 0.5
    return [open_ms, repr(o), repr(o + 1.0), repr(o - 1.0), repr(c),
            "10.0", open_ms + 900_000 - 1, "0", "0", "0", "0", "0"]


class BinanceTests(unittest.TestCase):
    def test_parses_and_drops_forming(self):
        now_ms = int(time.time() * 1000)
        closed_open = now_ms - 900_000
        forming_open = now_ms
        closed = kline(0, closed_open)
        closed[6] = closed_open + 900_000 - 1
        forming = kline(1, forming_open)
        forming[6] = forming_open + 900_000 + 500_000

        def transport(url, headers=None, timeout=15.0):
            return [closed, forming] if "endTime" not in url else []

        p = BinanceProvider(transport=transport)
        candles = p.fetch("BTCUSDT", "M15", 10)
        self.assertEqual(len(candles), 1)
        self.assertTrue(candles[0].closed)
        self.assertEqual(candles[0].timestamp.tzinfo, timezone.utc)

    def test_pagination_backwards(self):
        now_ms = int(time.time() * 1000)
        base = now_ms - 10 * 900_000

        def k(i):
            row = kline(i, base + i * 900_000)
            row[6] = base + i * 900_000 + 900_000 - 1
            return row

        page1 = [k(3), k(4), k(5)]
        page2 = [k(1), k(2)]
        calls = []

        def transport(url, headers=None, timeout=15.0):
            calls.append(url)
            if "endTime" not in url:
                return page1
            return page2 if page2 else []

        candles = BinanceProvider(transport=transport).fetch("BTCUSDT", "M15", 5)
        self.assertEqual(len(candles), 5)
        self.assertTrue(all(candles[i].timestamp < candles[i + 1].timestamp
                            for i in range(len(candles) - 1)))
        self.assertIn("endTime", calls[1])

    def test_unsupported_interval(self):
        with self.assertRaises(ValueError):
            BinanceProvider(transport=lambda *a, **kw: []).fetch("BTCUSDT", "W1", 5)


class CsvProviderTests(unittest.TestCase):
    def test_reads_and_slices(self):
        path = os.path.join("data", "sample_EURUSD_M15.csv")
        if not os.path.exists(path):
            self.skipTest("sample data not generated")
        candles = CsvProvider(path).fetch("EURUSD", "M15", 100)
        self.assertLessEqual(len(candles), 100)
        self.assertTrue(all(c.closed for c in candles))


class Mt5BridgeTests(unittest.TestCase):
    def test_parses_payload_and_drops_forming(self):
        now = 1_700_000_000

        def transport(url, headers=None, timeout=15.0):
            self.assertIn("symbol=EURUSD", url)
            self.assertIn("timeframe=M15", url)
            self.assertIn("bars=50", url)
            return [
                {"timestamp": now - 1800, "open": 1.1, "high": 1.11, "low": 1.09,
                 "close": 1.105, "volume": 100.0, "closed": True},
                {"timestamp": now - 900, "open": 1.105, "high": 1.12, "low": 1.1,
                 "close": 1.11, "volume": 60.0, "closed": True},
                {"timestamp": now, "open": 1.11, "high": 1.13, "low": 1.11,
                 "close": 1.12, "volume": 10.0, "closed": False},
            ]

        p = Mt5BridgeProvider(transport=transport)
        candles = p.fetch("EURUSD", "M15", 50)
        self.assertEqual(len(candles), 2)
        self.assertTrue(all(c.closed for c in candles))

    def test_token_from_env(self):
        seen = {}

        def transport(url, headers=None, timeout=15.0):
            seen["auth"] = (headers or {}).get("Authorization")
            return []

        os.environ["QF_BRIDGE_TOKEN"] = "secret-token-123"
        try:
            Mt5BridgeProvider(transport=transport).fetch("EURUSD", "M15", 5)
        finally:
            del os.environ["QF_BRIDGE_TOKEN"]
        self.assertEqual(seen["auth"], "Bearer secret-token-123")


class ProviderFactoryTests(unittest.TestCase):
    def test_factory_modes(self):
        cfg = Config()
        cfg.data.source_mode = "binance"
        self.assertIsInstance(provider_from_config(cfg), BinanceProvider)
        cfg.data.source_mode = "mt5_bridge"
        self.assertIsInstance(provider_from_config(cfg), Mt5BridgeProvider)
        cfg.data.source_mode = "csv"
        self.assertIsInstance(provider_from_config(cfg), CsvProvider)

    def test_config_from_toml_accepts_new_keys(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as fh:
            fh.write('[data]\nsource_mode = "binance"\nbridge_url = "http://127.0.0.1:9"\n')
            tmp = fh.name
        cfg = Config.from_toml(tmp)
        os.unlink(tmp)
        self.assertEqual(cfg.data.source_mode, "binance")
        self.assertEqual(cfg.data.bridge_url, "http://127.0.0.1:9")


if __name__ == "__main__":
    unittest.main()
