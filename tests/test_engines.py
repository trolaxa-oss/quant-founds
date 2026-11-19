import math
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quant_founds.core.engine import AnalysisContext
from quant_founds.core.models import Candle
from quant_founds.engines.technical import atr, ema, rsi, swing_points, snapshot
from quant_founds.engines.data_engine import DataEngine
from quant_founds.engines.market_intel import MarketIntelligence
from quant_founds.engines.liquidity_intel import LiquidityIntelligence
from quant_founds.engines.smc_intel import SmcIntelligence
from quant_founds.engines.orderflow_intel import OrderFlowIntelligence
from quant_founds.engines.mtf_engine import MultiTimeframeEngine


def mk(start: int, n: int, base: float = 1.10, amp: float = 0.0020, vol: float = 1000.0):
    out = []
    t0 = datetime(2024, 1, 2, tzinfo=timezone.utc)
    for i in range(n):
        v = base + amp * (1 if (i // 12) % 2 == 0 else -1) + 0.0001 * ((i * 37) % 11 - 5)
        o = v
        c = v + 0.0002 * ((i % 7) - 3)
        h = max(o, c) + 0.0004
        low = min(o, c) - 0.0004
        out.append(Candle(t0 + timedelta(minutes=15 * i), o, h, low, c, vol))
    return out


class TechnicalTests(unittest.TestCase):
    def test_ema_basic(self):
        self.assertIsNone(ema([1.0] * 5, 10))
        self.assertAlmostEqual(ema([1.0] * 10, 10), 1.0)

    def test_rsi_bounds(self):
        vals = [10 + i for i in range(30)]
        r = rsi(vals, 14)
        self.assertTrue(90 <= r <= 100)
        vals_down = [30 - i for i in range(30)]
        rd = rsi(vals_down, 14)
        self.assertTrue(0 <= rd <= 10)

    def test_atr_positive(self):
        candles = mk(0, 40)
        a = atr(candles, 14)
        self.assertGreater(a, 0)

    def test_swings_found(self):
        candles = []
        t0 = datetime(2024, 1, 2, tzinfo=timezone.utc)
        for i in range(60):
            base = 1.10 + 0.010 * math.sin(i / 5)
            candles.append(Candle(t0 + timedelta(minutes=15 * i), base - 0.0005,
                                  base + 0.002, base - 0.002, base + 0.0005, 500))
        hi, lo = swing_points(candles, 2, 2)
        self.assertTrue(len(hi) >= 1 and len(lo) >= 1)



class EngineTests(unittest.TestCase):
    def _ctx(self, n=150, **kw):
        return AnalysisContext(symbol="EURUSD", timeframe="M15", candles=mk(0, n), **kw)

    def test_data_engine_quality(self):
        res = DataEngine().analyze(self._ctx())
        self.assertGreaterEqual(res.data_quality, 0.6)
        self.assertEqual(res.state, "ok")

    def test_data_engine_detects_bad_series(self):
        candles = mk(0, 50)
        bad = candles[:-1] + [Candle(candles[0].timestamp, 1.0, 0.5, 1.5, 0.75, 1)]
        res = DataEngine().analyze(AnalysisContext("EURUSD", "M15", bad))
        self.assertLess(res.data_quality, 0.6)

    def test_market_engine_output(self):
        res = MarketIntelligence().analyze(self._ctx())
        self.assertIn(res.state, ("up", "down", "sideways", "transition"))
        self.assertIn("regime", res.extras)
        self.assertIn(res.extras["regime"],
                      ("trending", "ranging", "high_volatility", "low_volatility", "unavailable"))

    def test_liquidity_engine_output(self):
        res = LiquidityIntelligence().analyze(self._ctx())
        self.assertIn("levels", res.extras)
        self.assertIn("sweeps", res.extras)
        self.assertTrue(res.data_quality > 0)

    def test_smc_engine_zones(self):
        res = SmcIntelligence().analyze(self._ctx())
        self.assertIn("zones", res.extras)
        self.assertIn("premium_discount", res.extras)

    def test_orderflow_estimated_mode(self):
        res = OrderFlowIntelligence().analyze(self._ctx())
        self.assertEqual(res.source_mode.value, "estimated")
        self.assertIn(res.confidence_label, ("estimated_proxy",))
        self.assertLessEqual(res.score, 100 * 0.7 + 1e-9)

    def test_mtf_alignment(self):
        candles = mk(0, 150)
        res = MultiTimeframeEngine(["H1"]).analyze(
            self._ctx(), htf_series={"H1": [c for c in candles]})
        self.assertIn(res.state, ("aligned_buy", "aligned_sell", "partial", "conflict", "unavailable"))


if __name__ == "__main__":
    unittest.main()
