"""Backtesting & Audit (18) - sequential loop over closed bars only.

Pipeline per closed bar (blueprint 3.2):
data -> features -> (liquidity, smc, orderflow, mtf) -> decision -> gates
-> risk approval -> paper execution -> journal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from quant_founds.core.config import Config
from quant_founds.core.engine import AnalysisContext
from quant_founds.core.enums import Side, SignalState
from quant_founds.core.models import Account, Trade, TradePlan
from quant_founds.decision.scorer import score_opportunity
from quant_founds.planning import build_plan
from quant_founds.decision.signal_engine import SignalDecisionEngine
from quant_founds.engines.ai_intel import AiIntelligence
from quant_founds.engines.data_engine import DataEngine
from quant_founds.engines.liquidity_intel import LiquidityIntelligence
from quant_founds.engines.market_intel import MarketIntelligence
from quant_founds.engines.mtf_engine import MultiTimeframeEngine
from quant_founds.engines.news_intel import NewsIntelligence
from quant_founds.engines.orderflow_intel import OrderFlowIntelligence
from quant_founds.engines.smc_intel import SmcIntelligence
from quant_founds.execution import BrokerConfig, PaperBroker
from quant_founds.journal import Journal
from quant_founds.reporting import performance_report, walk_forward_split
from quant_founds.risk_engine import RiskEngine
from quant_founds.sessions import SessionEngine, assert_closed_only


@dataclass
class BacktestResult:
    trades: list[Trade]
    report: dict
    decisions_count: int
    final_account: Account
    journal: Journal


class Backtester:
    def __init__(self, cfg: Config, events=None, run_dir: str = "runs/latest",
                 initial_balance: float = 10_000.0):
        self.cfg = cfg
        self.events = events
        self.initial_balance = initial_balance
        self.account = Account(balance=initial_balance, equity=initial_balance,
                               peak_equity=initial_balance)
        self.journal = Journal(run_dir)

    def run(self, candles, htf_series: dict | None = None, verbose: bool = False) -> BacktestResult:
        cfg = self.cfg
        broker = PaperBroker(BrokerConfig(
            spread=cfg.execution.spread,
            slippage=cfg.execution.slippage,
            partial_tp1_fraction=cfg.execution.partial_tp1_fraction,
            move_be_after_tp1=cfg.execution.move_be_after_tp1,
            enable_trailing=cfg.execution.enable_trailing,
            trailing_atr_multiple=cfg.execution.trailing_atr_multiple,
            point_value=cfg.risk.point_value,
            contract_size=cfg.risk.contract_size,
        ))
        risk = RiskEngine(cfg.risk, self.account)

        data_engine = DataEngine(cfg.data.max_gap_bars)
        market = MarketIntelligence()
        liquidity = LiquidityIntelligence()
        orderflow = OrderFlowIntelligence()
        smc = SmcIntelligence()
        mtf = MultiTimeframeEngine(cfg.data.higher_timeframes)
        news = NewsIntelligence(
            events=self.events,
            block_minutes_before=cfg.news.block_minutes_before,
            block_minutes_after=cfg.news.block_minutes_after,
            block_impacts=cfg.news.block_impacts,
        )
        ai = AiIntelligence()
        sessions = SessionEngine(cfg.sessions)
        signals = SignalDecisionEngine(cfg)

        engines = [data_engine, market, liquidity, orderflow, smc, mtf, news, ai, sessions]

        trades: list[Trade] = []
        decisions_count = 0
        warmup = cfg.backtest.warmup_bars
        last_day = None

        for i in range(len(candles)):
            candle = candles[i]
            closed_set = candles[:i + 1]
            assert_closed_only(closed_set, "backtest")

            if candle.timestamp.date() != last_day:
                last_day = candle.timestamp.date()
                risk.reset_daily()

            ctx = AnalysisContext(
                symbol=cfg.data.symbol,
                timeframe=cfg.data.timeframe,
                candles=closed_set,
                higher_tf=self._align_htf(closed_set, htf_series or {}),
                timestamp=candle.timestamp,
                debug=cfg.debug,
            )

            results = {}
            for eng in engines:
                results[eng.engine_id] = eng.analyze(ctx)
            results.pop("ai", None)

            # 1) manage open trade with current bar
            if broker.open is not None:
                trade = broker.open
                broker.on_bar(candle, results["market"].extras.get("atr"))
                if trade.state is not None and broker.open is None:
                    trades.append(trade)
                    self.journal.log_trade(trade)
                    self.account.balance += trade.realized_pnl
                    self.account.equity = self.account.balance
                    self.account.day_pnl += trade.realized_pnl
                    self.account.week_pnl += trade.realized_pnl
                    if trade.realized_pnl < 0:
                        risk.register_loss(i)
                    else:
                        risk.register_win()
                    signals.machine.reset()

            if i < warmup:
                self.account.peak_equity = max(self.account.peak_equity, self.account.equity)
                continue

            # 2) decide on this closed bar
            decision = signals.decide(ctx, results)
            decisions_count += 1
            plan = None

            # 3) build + submit when confirmed and nothing open
            if decision and decision.state is SignalState.CONFIRMED and \
                    decision.side is not None and broker.open is None:
                plan = self._build_plan(ctx, results, decision)
                if plan is not None:
                    results["_rr_fraction"] = min(1.0, plan.risk_reward / max(cfg.risk.min_risk_reward, 1e-9))
                    score2, _ = score_opportunity(results, decision.side.value, cfg.scoring)
                    decision.score = score2
                    rd = risk.evaluate(plan, self.account.equity, self.account.day_pnl,
                                       self.account.week_pnl, i, 0)
                    if rd.approved:
                        decision.state = SignalState.ENTRY_READY
                        decision.notes.append("risk_approved")
                        trade = broker.submit(plan, rd.position_size)
                        decision.state = SignalState.ACTIVE
                        signals.machine.state = SignalState.ACTIVE
                        decision.notes.append("order_submitted")
                    else:
                        decision.notes.append("risk_rejected:" + ",".join(rd.reasons))
                        decision.signal_id += "-rejected"
                elif decision.hard_failures:
                    decision.notes.append("gates:" + ",".join(decision.hard_failures))
                else:
                    decision.notes.append("no_plan")

            self.journal.log_decision(decision)

            if verbose and cfg.debug and decision:
                from quant_founds.quant_stat import render_snapshot
                print(render_snapshot(ctx, results, self.account, broker.open, decision))

            self.account.peak_equity = max(self.account.peak_equity, self.account.equity)

        report = performance_report(trades, initial_balance=self.initial_balance)
        report["decisions_count"] = decisions_count
        report["n_bars"] = len(candles)
        report["walk_forward"] = [
            {"train": tr, "test": te}
            for tr, te in walk_forward_split(len(candles), folds=3)
        ]
        report["config"] = {
            "symbol": cfg.data.symbol,
            "timeframe": cfg.data.timeframe,
            "risk_per_trade_pct": cfg.risk.risk_per_trade_pct,
            "entry_threshold": cfg.scoring.entry_threshold,
        }
        self.journal.write_summary(report)
        from quant_founds.reporting import render_html_report
        from pathlib import Path as _Path

        self.report_html_path = str(_Path(self.journal.run_dir) / "report.html")
        render_html_report(trades, report, self.report_html_path)
        return BacktestResult(trades, report, decisions_count, self.account, self.journal)

    @staticmethod
    def _align_htf(execution_candles: list, htf_series: dict) -> dict:
        """Keep only HTF bars that were fully closed before the current bar.

        An HTF bar is usable when the series contains a later bar after it,
        otherwise it is still forming and must be excluded.
        """
        if not execution_candles:
            return {tf: [] for tf in htf_series}
        now = execution_candles[-1].timestamp
        aligned = {}
        for tf, series in htf_series.items():
            usable = [c for c in series if c.timestamp <= now]
            if len(usable) >= 2:
                step = usable[-1].timestamp - usable[-2].timestamp
            else:
                usable = [c for c in series if c.timestamp < now]
                step = None
            if not step or step < timedelta(0):
                usable = usable[:-1]
            elif len(series) > len(usable):
                pass
            elif series and usable and series[-1].timestamp == now:
                usable = usable[:-1]
            aligned[tf] = usable
        return aligned

    def _build_plan(self, ctx, results, decision) -> TradePlan | None:
        return build_plan(ctx, results, decision)
