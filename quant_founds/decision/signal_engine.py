"""Signal Decision Engine (11) + signal state machine (blueprint 5.x)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from quant_founds.core.enums import Side, SignalState, SignalType
from quant_founds.decision.filters import FilterOutcome, FilterChain
from quant_founds.decision.scorer import score_opportunity


@dataclass
class SignalDecision:
    signal_id: str
    timestamp: datetime
    bar_time: datetime
    symbol: str
    timeframe: str
    previous_state: SignalState
    state: SignalState
    signal_type: SignalType
    side: Optional[Side]
    score: float
    components: list
    filters: list[FilterOutcome]
    hard_failures: list[str]
    plan: object | None = None
    notes: list[str] = field(default_factory=list)


class SignalStateMachine:
    """Transitions: IDLE->WATCH->SETUP->CONFIRMED->(ENTRY_READY/ACTIVE by
    the execution path)->EXPIRED back to IDLE, with INVALIDATED/EXPIRED exits."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.state = SignalState.IDLE
        self.side: Side | None = None
        self.signal_id = str(uuid.uuid4())
        self.created_bar: datetime | None = None
        self.peak_score = 0.0

    def reset(self) -> None:
        self.state = SignalState.IDLE
        self.side = None
        self.signal_id = str(uuid.uuid4())
        self.created_bar = None
        self.peak_score = 0.0


class SignalDecisionEngine:
    """Central decision: merges engine evidence into one scored decision."""

    def __init__(self, cfg, filter_chain: FilterChain | None = None):
        self.cfg = cfg
        self.machine = SignalStateMachine(cfg)
        self.filters = filter_chain or FilterChain(cfg.filters)

    def decide(self, ctx, results: dict) -> Optional[SignalDecision]:
        market = results.get("market")
        if market is None:
            return None
        trend = market.extras.get("trend")
        side = side_from_trend(trend)
        score, comps = score_opportunity(results, side.value if side else "", self.cfg.scoring)
        outcomes = self.filters.evaluate(ctx, results, side.value if side else "")
        hard = self.filters.hard_failures(outcomes)

        prev = self.machine.state
        m = self.machine
        sig_state, sig_type, note = prev, SignalType.ALERT_ONLY, ""
        regime = (market.extras.get("regime") or "")

        if m.state in (SignalState.IDLE,):
            if score >= self.cfg.scoring.watch_threshold and not hard:
                sig_state, sig_type = SignalState.WATCH, SignalType.ALERT_ONLY
                m.state, m.side, m.created_bar = sig_state, side, ctx.last.timestamp
                m.peak_score = score
                note = "watch_started"
        elif m.state is SignalState.WATCH:
            if score >= self.cfg.scoring.entry_threshold * 0.85 and not hard:
                sig_state, sig_type = SignalState.SETUP, SignalType.BUY_SETUP if side is Side.BUY else SignalType.SELL_SETUP
                m.state, m.peak_score = sig_state, score
                note = "setup"
            elif score < self.cfg.scoring.watch_threshold * 0.7 or hard:
                sig_state, sig_type = SignalState.IDLE, SignalType.CANCEL
                m.reset()
                note = "watch_cancelled"
        elif m.state is SignalState.SETUP:
            if score >= self.cfg.scoring.entry_threshold and not hard:
                sig_state, sig_type = SignalState.CONFIRMED, (
                    SignalType.BUY_CONFIRMATION if side is Side.BUY else SignalType.SELL_CONFIRMATION)
                m.state, m.peak_score = sig_state, max(score, m.peak_score)
                note = "confirmed"
            elif _invalidated(results, m.side):
                sig_state, sig_type = SignalState.INVALIDATED, SignalType.INVALIDATION
                m.reset()
                note = "invalidation"
            elif score < self.cfg.scoring.entry_threshold * 0.7:
                sig_state, sig_type = SignalState.IDLE, SignalType.CANCEL
                m.reset()
                note = "setup_faded"
        elif m.state is SignalState.ACTIVE:
            sig_state, sig_type = SignalState.ACTIVE, SignalType.ALERT_ONLY
            note = "position_open"

        if prev is m.state and prev in (SignalState.IDLE,):
            sig_state = prev

        return SignalDecision(
            signal_id=m.signal_id,
            timestamp=ctx.timestamp,
            bar_time=ctx.last.timestamp,
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            previous_state=prev,
            state=m.state,
            signal_type=sig_type,
            side=side,
            score=score,
            components=comps,
            filters=outcomes,
            hard_failures=hard,
            notes=[note] if note else [],
        )


def side_from_trend(trend: str | None) -> Optional[Side]:
    if trend == "up":
        return Side.BUY
    if trend == "down":
        return Side.SELL
    return None


def _invalidated(results: dict, side: Optional[Side]) -> bool:
    smc = results.get("smc")
    if smc and smc.extras.get("events"):
        last = smc.extras["events"][-1]
        if (side is Side.BUY and last["direction"] == "down" and last["event"] in ("BOS", "CHOCH")) or \
           (side is Side.SELL and last["direction"] == "up" and last["event"] in ("BOS", "CHOCH")):
            return True
    return False
