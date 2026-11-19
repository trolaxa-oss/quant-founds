import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quant_founds.core.config import Config
from quant_founds.core.engine import AnalysisContext
from quant_founds.core.models import Candle, EconomicEvent
from quant_founds.engines.news_intel import NewsIntelligence
from quant_founds.engines.market_intel import MarketIntelligence
from quant_founds.decision.filters import FilterChain
from quant_founds.decision.scorer import score_opportunity
from quant_founds.decision.signal_engine import SignalDecisionEngine


def series(n=150, base=1.10, drift=0.0004, seed_vary=0.0008):
    from random import Random
    rng = Random(5)
    out = []
    t0 = datetime(2024, 1, 2, tzinfo=timezone.utc)
    price = base
    for i in range(n):
        o = price
        c = o + drift * rng.choice([1, 1, 1, -1]) + rng.gauss(0, seed_vary)
        h = max(o, c) + 0.0004
        lo = min(o, c) - 0.0004
        out.append(Candle(t0 + timedelta(minutes=15 * i), o, h, lo, c, 1000 + rng.uniform(0, 300)))
        price = c
    return out


class ScorerTests(unittest.TestCase):
    def test_weights_sum_100(self):
        cfg = Config()
        self.assertAlmostEqual(sum(cfg.scoring.weights.values()), 100.0)

    def test_score_bounds(self):
        cfg = Config()
        ctx = AnalysisContext(symbol="EURUSD", timeframe="M15", candles=series())
        m = MarketIntelligence()
        ctx.results["market"] = m.analyze(ctx)
        score, comps = score_opportunity(ctx.results, "buy", cfg.scoring)
        self.assertTrue(0.0 <= score <= 100.1)
        self.assertTrue(all(c.max_points >= c.earned >= 0 for c in comps))


class SignalEngineTests(unittest.TestCase):
    def _engine(self):
        cfg = Config()
        cfg.scoring.watch_threshold = 20.0
        cfg.scoring.entry_threshold = 30.0
        for name in ("mtf", "data_quality"):
            cfg.filters.enabled[name] = False
        return cfg, SignalDecisionEngine(cfg)

    def test_watch_transition(self):
        cfg, eng = self._engine()
        candles = series()
        saw_watch = False
        for i in range(80, len(candles)):
            ctx = AnalysisContext(symbol="EURUSD", timeframe="M15",
                                  candles=candles[:i + 1])
            m = MarketIntelligence()
            results = {"market": m.analyze(ctx)}
            d = eng.decide(ctx, results)
            if d and d.state.value == "WATCH":
                saw_watch = True
                break
        self.assertTrue(saw_watch)


class FilterTests(unittest.TestCase):
    def test_news_block(self):
        cfg = Config()
        ctxcandles = series(30)
        ev = EconomicEvent(ctxcandles[-1].timestamp, "EUR", "high", "test")
        news = NewsIntelligence(events=[ev])
        ctx = AnalysisContext(symbol="EURUSD", timeframe="M15", candles=ctxcandles)
        res = news.analyze(ctx)
        self.assertTrue(res.extras["blocked"])

    def test_news_clear_outside_window(self):
        cfg = Config()
        ctxcandles = series(30)
        ev = EconomicEvent(ctxcandles[-1].timestamp + timedelta(hours=6), "EUR", "high", "test")
        news = NewsIntelligence(events=[ev])
        ctx = AnalysisContext(symbol="EURUSD", timeframe="M15", candles=ctxcandles)
        res = news.analyze(ctx)
        self.assertFalse(res.extras["blocked"])

    def test_filter_chain_outputs(self):
        cfg = Config()
        ctx = AnalysisContext(symbol="EURUSD", timeframe="M15", candles=series())
        m = MarketIntelligence()
        results = {"market": m.analyze(ctx)}
        fc = FilterChain(cfg.filters)
        outcomes = fc.evaluate(ctx, results, "buy")
        names = [o.name for o in outcomes]
        self.assertIn("trend", names)
        self.assertIn("data_quality", names)


if __name__ == "__main__":
    unittest.main()
