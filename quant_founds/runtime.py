"""Live runtime (blueprint 3, 12-17): closed-bar processing on real data.

LiveWatcher     - analysis & alerting only (no orders, no accounting).
LivePaperRunner - full pipeline on live data: decision -> plan -> risk ->
                  paper broker -> trade management -> journal + alerts.
Both process closed candles only; a forming bar never reaches an engine.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime

from quant_founds.alerts import AlertEngine
from quant_founds.core.config import Config
from quant_founds.core.engine import AnalysisContext
from quant_founds.core.enums import SignalState
from quant_founds.core.models import Account, Candle, Trade
from quant_founds.decision.scorer import score_opportunity
from quant_founds.decision.signal_engine import SignalDecisionEngine
from quant_founds.engines import (AiIntelligence, DataEngine,
                                  LiquidityIntelligence, MarketIntelligence,
                                  MultiTimeframeEngine, NewsIntelligence,
                                  OrderFlowIntelligence, SmcIntelligence)
from quant_founds.execution import BrokerConfig, PaperBroker
from quant_founds.journal import Journal, utc_now
from quant_founds.notify import NotifierChain
from quant_founds.online_ai import OnlineLogit
from quant_founds.planning import build_plan
from quant_founds.risk_engine import RiskEngine
from quant_founds.sessions import SessionEngine

TIMEFRAME_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30,
                     "H1": 60, "H4": 240, "D1": 1440}


def resample_htf(candles: list[Candle], minutes: int) -> list[Candle]:
    """Closed-only higher-timeframe aggregation from lower-TF candles."""
    out: list[Candle] = []
    bucket: tuple[int, Candle] | None = None
    for c in candles:
        if not c.closed:
            continue
        slot = int(c.timestamp.timestamp() // (minutes * 60))
        if bucket is None or slot != bucket[0]:
            if bucket is not None:
                out.append(bucket[1])
            bucket = (slot, c)
        else:
            m = bucket[1]
            bucket = (slot, Candle(m.timestamp, m.open, max(m.high, c.high),
                                   min(m.low, c.low), c.close,
                                   m.volume + c.volume))
    if bucket is not None:
        out.append(bucket[1])
    return out


class LiveWatcher:
    """Analysis & alerting only - no orders, no accounting."""

    def __init__(self, cfg: Config, provider, poll_seconds: float = 30.0,
                 history_bars: int = 400, run_dir: str = "runs/live",
                 notifiers=None):
        self.cfg = cfg
        self.provider = provider
        self.poll_seconds = poll_seconds
        self.history_bars = history_bars
        self.last_bar_time = None
        self.n_bars_seen = 0
        self._last_ctx = None
        self._last_results: dict | None = None
        self.data_engine = DataEngine(cfg.data.max_gap_bars)
        self.market = MarketIntelligence()
        self.liquidity = LiquidityIntelligence()
        self.orderflow = OrderFlowIntelligence()
        self.smc = SmcIntelligence()
        self.mtf = MultiTimeframeEngine(cfg.data.higher_timeframes)
        events = None
        if cfg.news.events_csv:
            try:
                events = NewsIntelligence.from_csv(cfg.news.events_csv)
            except (OSError, KeyError, ValueError) as exc:
                print(f"news events_csv not loadable ({exc}) - running without events")
        self.news = NewsIntelligence(
            events=events,
            block_minutes_before=cfg.news.block_minutes_before,
            block_minutes_after=cfg.news.block_minutes_after,
            block_impacts=cfg.news.block_impacts,
        )
        self.ai = AiIntelligence()
        self.sessions = SessionEngine(cfg.sessions)
        self.signals = SignalDecisionEngine(cfg)
        self.notifiers = notifiers if notifiers is not None else NotifierChain()
        self.run_dir = run_dir
        self._last_ai_features: dict | None = None
        self.journal_path = os.path.join(run_dir, "decisions.jsonl")
        self.state_path = os.path.join(run_dir, "runtime_state.json")
        os.makedirs(run_dir, exist_ok=True)
        self._restore_watermark()

    def engines(self):
        return [self.data_engine, self.market, self.liquidity, self.orderflow,
                self.smc, self.mtf, self.news, self.ai, self.sessions]

    def htf_series(self, candles: list[Candle]) -> dict:
        out = {}
        for tf in self.cfg.data.higher_timeframes:
            minutes = TIMEFRAME_MINUTES.get(tf.upper())
            if minutes:
                out[tf] = resample_htf(candles, minutes)
        return out

    def _restore_watermark(self) -> None:
        try:
            with open(self.state_path) as fh:
                raw = json.load(fh)
            ts = raw.get("last_bar_time")
            if ts:
                self.last_bar_time = datetime.fromisoformat(ts)
        except (OSError, ValueError):
            pass

    def _save_watermark(self) -> None:
        if self.last_bar_time is None:
            return
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"last_bar_time": self.last_bar_time.isoformat(),
                       "n_bars_seen": self.n_bars_seen}, fh)
        os.replace(tmp, self.state_path)

    def run_once(self) -> list:
        candles = self.provider.fetch(self.cfg.data.symbol,
                                      self.cfg.data.timeframe, self.history_bars)
        if not candles:
            return []
        newest_closed = [c for c in candles if c.closed]
        if not newest_closed:
            return []
        htf = self.htf_series(newest_closed)
        fired: list = []
        for candle in newest_closed:
            if self.last_bar_time is not None and candle.timestamp <= self.last_bar_time:
                continue
            self.last_bar_time = candle.timestamp
            decision = self.process_bar(candle, newest_closed, htf)
            if decision is not None and decision.state in (
                    SignalState.WATCH, SignalState.SETUP,
                    SignalState.CONFIRMED, SignalState.ACTIVE):
                fired.append(decision)
        self._save_watermark()
        return fired

    def _analyze(self, candle, closed_candles, htf: dict):
        ctx = AnalysisContext(
            symbol=self.cfg.data.symbol,
            timeframe=self.cfg.data.timeframe,
            candles=[c for c in closed_candles
                     if c.timestamp <= candle.timestamp][-self.history_bars:],
            higher_tf={tf: [c for c in series if c.timestamp <= candle.timestamp]
                       for tf, series in htf.items()},
            timestamp=candle.timestamp,
        )
        results = {}
        for eng in self.engines():
            results[eng.engine_id] = eng.analyze(ctx)
        self._last_ai_features = {eid: getattr(r, "score", None)
                                  for eid, r in results.items()
                                  if eid != "sessions"}
        results.pop("ai", None)
        self.n_bars_seen += 1
        self._last_ctx = ctx
        self._last_results = results
        return ctx, results

    def process_bar(self, candle, closed_candles, htf: dict):
        ctx, results = self._analyze(candle, closed_candles, htf)
        return self._decide_and_report(ctx, results)

    def _decide_and_report(self, ctx, results):
        decision = self.signals.decide(ctx, results)
        if decision is None:
            return None
        self._journal(decision)
        if decision.state in (SignalState.WATCH, SignalState.SETUP,
                              SignalState.CONFIRMED):
            self.notifiers.send(f"{self.cfg.data.symbol} {self.cfg.data.timeframe}",
                                f"{decision.state.value} "
                                f"side={decision.side.value if decision.side else '-'} "
                                f"score={decision.score:.1f}")
        return decision

    def _journal(self, decision) -> None:
        row = {
            "logged_at": utc_now(),
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
        print(f"live watch on {self.cfg.data.symbol} "
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


class LivePaperRunner(LiveWatcher):
    """Full pipeline on live data: decision -> plan -> risk -> paper fill ->
    per-bar management, with journal, alerts, and account accounting."""

    def __init__(self, cfg: Config, provider, poll_seconds: float = 30.0,
                 history_bars: int = 400, run_dir: str = "runs/live_paper",
                 initial_balance: float = 10_000.0, notifiers=None,
                 news_engine=None, ai_model=None, ai_gate: bool = False,
                 ai_min_probability: float = 0.5, ai_min_samples: int = 30):
        super().__init__(cfg, provider, poll_seconds=poll_seconds,
                         history_bars=history_bars, run_dir=run_dir,
                         notifiers=notifiers)
        self.journal = Journal(run_dir)
        self.news_engine = news_engine or self.news
        self.ai_gate = ai_gate
        self.ai_min_probability = ai_min_probability
        self.ai_min_samples = ai_min_samples
        self.ai_model_path = os.path.join(run_dir, "ai_model.json")
        if ai_gate and ai_model is None:
            ai_model = OnlineLogit.load(self.ai_model_path) or OnlineLogit()
        self.ai_model = ai_model
        if ai_gate:
            self.ai.model = ai_model
        self.open_ai_features: dict | None = None
        self.account = Account(balance=initial_balance, equity=initial_balance,
                               peak_equity=initial_balance)
        self.broker = PaperBroker(BrokerConfig(
            spread=cfg.execution.spread,
            slippage=cfg.execution.slippage,
            partial_tp1_fraction=cfg.execution.partial_tp1_fraction,
            move_be_after_tp1=cfg.execution.move_be_after_tp1,
            enable_trailing=cfg.execution.enable_trailing,
            trailing_atr_multiple=cfg.execution.trailing_atr_multiple,
            point_value=cfg.risk.point_value,
            contract_size=cfg.risk.contract_size,
        ))
        self.risk = RiskEngine(cfg.risk, self.account)
        self.alerts = AlertEngine()
        self.trades: list[Trade] = []
        self.bar_index = 0
        self.last_day = None

    def process_bar(self, candle, closed_candles, htf: dict):
        ctx, results = self._analyze(candle, closed_candles, htf)
        self.bar_index += 1

        if candle.timestamp.date() != self.last_day:
            self.last_day = candle.timestamp.date()
            self.risk.reset_daily()

        # 1) manage the open paper trade with this closed bar
        if self.broker.open is not None:
            market = results.get("market")
            atr = market.extras.get("atr") if market else None
            trade = self.broker.open
            self.broker.on_bar(candle, atr)
            if self.broker.open is None:
                self._close_paper_trade(trade)

        decision = self._decide_and_report(ctx, results)

        # 2) confirmed signal + no open trade -> plan -> risk -> submit
        if (decision is not None and decision.state is SignalState.CONFIRMED
                and decision.side is not None and self.broker.open is None):
            self._try_submit(ctx, results, decision)

        self.account.peak_equity = max(self.account.peak_equity, self.account.equity)
        return decision

    def _close_paper_trade(self, trade: Trade) -> None:
        self.trades.append(trade)
        self.journal.log_trade(trade)
        self.account.balance += trade.realized_pnl
        self.account.equity = self.account.balance
        self.account.day_pnl += trade.realized_pnl
        self.account.week_pnl += trade.realized_pnl
        if trade.realized_pnl < 0:
            self.risk.register_loss(self.bar_index)
        else:
            self.risk.register_win()
        if self.ai_gate and self.ai_model is not None \
                and self.open_ai_features is not None:
            self.ai_model.update(self.open_ai_features,
                                 1.0 if trade.realized_pnl >= 0 else 0.0)
            self.ai_model.save(self.ai_model_path)
        self.open_ai_features = None
        self.signals.machine.reset()
        self.notifiers.send(
            f"{self.cfg.data.symbol} trade closed",
            f"pnl={trade.realized_pnl:+.2f} "
            f"exits={';'.join(trade.exit_reasons)}")

    def _try_submit(self, ctx, results, decision) -> None:
        cfg = self.cfg
        market = results.get("market")
        if market is None or not market.extras.get("atr"):
            decision.notes.append("no_plan")
            return
        plan = build_plan(ctx, results, decision)
        if plan is None:
            if decision.hard_failures:
                decision.notes.append("gates:" + ",".join(decision.hard_failures))
            else:
                decision.notes.append("no_plan")
            return
        results["_rr_fraction"] = min(1.0, plan.risk_reward /
                                      max(cfg.risk.min_risk_reward, 1e-9))
        score2, _ = score_opportunity(results, decision.side.value, cfg.scoring)
        decision.score = score2
        rd = self.risk.evaluate(plan, self.account.equity, self.account.day_pnl,
                                self.account.week_pnl, self.bar_index, 0)
        if not rd.approved:
            decision.notes.append("risk_rejected:" + ",".join(rd.reasons))
            decision.signal_id += "-rejected"
            self._journal(decision)
            return
        if self.ai_gate and self.ai_model is not None \
                and self.ai_model.n_updates >= self.ai_min_samples:
            prob = self.ai_model.probability(self._last_ai_features or {})
            decision.notes.append(f"ai_prob={prob:.2f}")
            if prob < self.ai_min_probability:
                decision.notes.append("ai_gate_rejected")
                decision.signal_id += "-ai-gate"
                self._journal(decision)
                return
        self.open_ai_features = self._last_ai_features
        decision.state = SignalState.ENTRY_READY
        decision.notes.append("risk_approved")
        self.broker.submit(plan, rd.position_size)
        decision.state = SignalState.ACTIVE
        self.signals.machine.state = SignalState.ACTIVE
        decision.notes.append("paper_order_submitted")
        self.alerts.emit(ctx, decision, "ENTRY", "paper_fill")
        self.notifiers.send(f"{self.cfg.data.symbol} paper entry",
                            f"{plan.side.value} size={rd.position_size:.2f} "
                            f"sl={plan.stop_loss}")
        self._journal(decision)
    def snapshot_summary(self) -> dict:
        from quant_founds.reporting import performance_report

        rep = performance_report(self.trades, self.account.balance)
        rep["n_bars_seen"] = self.n_bars_seen
        rep["open_trade"] = self.broker.open is not None
        return rep

    def run_forever(self) -> None:
        print(f"LIVE PAPER trading sim on {self.cfg.data.symbol} "
              f"{self.cfg.data.timeframe} via {self.provider.name} "
              f"- no real orders, Ctrl+C to stop")
        while True:
            try:
                for d in self.run_once():
                    side = d.side.value if d.side else "-"
                    print(f"[{d.bar_time:%H:%M}] {d.state.value:<9} {side:<4} "
                          f"score={d.score:.1f} equity={self.account.equity:.2f}")
            except KeyboardInterrupt:
                print("\nfinal paper summary:")
                print(json.dumps(self.snapshot_summary()))
                return
            except Exception as exc:
                print(f"poll error: {exc}")
            time.sleep(self.poll_seconds)
