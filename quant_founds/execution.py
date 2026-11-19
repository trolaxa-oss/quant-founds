"""Execution Engine (12) - paper broker: entries, SL/TP, partial TP, BE, trailing.

Simulation is conservative: when a bar spans both TP and SL the SL is filled
first (worst-case, prevents optimistic fills from ambiguity).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from quant_founds.core.enums import ExitReason, OrderState, Side
from quant_founds.core.models import Fill, Trade, TradePlan


@dataclass
class BrokerConfig:
    spread: float = 0.00010
    slippage: float = 0.00005
    partial_tp1_fraction: float = 0.5
    move_be_after_tp1: bool = True
    enable_trailing: bool = False
    trailing_atr_multiple: float = 2.0
    point_value: float = 1.0
    contract_size: float = 1.0


class PaperBroker:
    def __init__(self, cfg: BrokerConfig):
        self.cfg = cfg
        self.open: Trade | None = None

    def submit(self, plan: TradePlan, size: float) -> Trade:
        side_price = plan.entry + self.cfg.spread + self.cfg.slippage \
            if plan.side is Side.BUY else plan.entry - self.cfg.spread - self.cfg.slippage
        trade = Trade(
            trade_id=str(uuid.uuid4()),
            signal_id=plan.signal_id,
            symbol=plan.symbol,
            timeframe=plan.timeframe,
            side=plan.side,
            entry_time=plan.bar_time,
            entry_price=side_price,
            quantity=size,
            stop_loss=plan.stop_loss,
            take_profits=list(plan.take_profits),
        )
        trade.fills.append(Fill(plan.bar_time, side_price, size, "entry"))
        self.open = trade
        return trade

    # -- per-bar management ------------------------------------------------
    def on_bar(self, candle, atr_value: float | None = None) -> list[Fill]:
        t = self.open
        if t is None or t.state is OrderState.CLOSED:
            return []
        fills: list[Fill] = []
        is_buy = t.side is Side.BUY

        tp_done = len(t.exit_reasons)
        hit_sl = candle.low <= t.stop_loss if is_buy else candle.high >= t.stop_loss

        if tp_done == 0:
            # path ambiguity: assume SL first (conservative)
            if hit_sl:
                fills.extend(self._fill_sl(t, candle))
                return fills
        else:
            if self.cfg.enable_trailing and atr_value:
                new_stop = self._trail(t, candle, atr_value)
                if self._better_stop(new_stop, t.stop_loss, is_buy):
                    t.stop_loss = new_stop
            hit_sl = candle.low <= t.stop_loss if is_buy else candle.high >= t.stop_loss
            if hit_sl:
                fills.extend(self._fill_sl(t, candle))
                return fills

        # stop untouched: fill reachable TPs sequentially within this bar
        idx = tp_done
        while idx < len(t.take_profits):
            tp = t.take_profits[idx]
            if not ((is_buy and candle.high >= tp) or (not is_buy and candle.low <= tp)):
                break
            if idx == 0:
                fills.extend(self._fill_tp(t, candle, 0, 1))
                if self.cfg.move_be_after_tp1:
                    t.stop_loss = t.entry_price
                if self.cfg.enable_trailing and atr_value:
                    t.stop_loss = self._trail(t, candle, atr_value)
                if t.state is not OrderState.CLOSED and (
                        (candle.low <= t.stop_loss) if is_buy else (candle.high >= t.stop_loss)):
                    fills.extend(self._fill_sl(t, candle))
                    return fills
            else:
                fills.extend(self._fill_tp(t, candle, idx, len(t.take_profits) - idx))
            if t.state is OrderState.CLOSED:
                break
            idx += 1

        if t.state is not OrderState.CLOSED and self.cfg.enable_trailing and atr_value:
            new_stop = self._trail(t, candle, atr_value)
            if self._better_stop(new_stop, t.stop_loss, is_buy):
                t.stop_loss = new_stop
        return fills

    # -- helpers ------------------------------------------------------------
    def _filled_qty(self, t: Trade) -> float:
        return sum(f.quantity for f in t.fills if f.kind in ("tp", "sl", "trail", "close"))

    def _pnl(self, t: Trade, price: float, qty: float) -> float:
        diff = (price - t.entry_price) if t.side is Side.BUY else (t.entry_price - price)
        return diff * qty * self.cfg.point_value * self.cfg.contract_size

    def _fill_sl(self, t: Trade, candle) -> list[Fill]:
        slip = self.cfg.slippage
        price = t.stop_loss - slip if t.side is Side.BUY else t.stop_loss + slip
        qty = t.quantity - self._filled_qty(t)
        pnl = self._pnl(t, price, qty)
        t.realized_pnl += pnl
        t.costs += abs(slip) * qty
        t.fills.append(Fill(candle.timestamp, price, qty, "sl"))
        t.exit_reasons.append(ExitReason.STOP_LOSS.value)
        self._close(t, candle.timestamp, ExitReason.STOP_LOSS)
        return t.fills

    def _fill_tp(self, t: Trade, candle, idx: int, exits_left: int) -> list[Fill]:
        is_buy = t.side is Side.BUY
        price = t.take_profits[idx] - self.cfg.slippage if is_buy else t.take_profits[idx] + self.cfg.slippage
        qty = t.quantity - self._filled_qty(t)
        if idx == 0:
            qty = t.quantity * self.cfg.partial_tp1_fraction
            remaining = t.quantity - self._filled_qty(t) - qty
            if remaining < qty * 0.1:
                qty = t.quantity - self._filled_qty(t)
        pnl = self._pnl(t, price, qty)
        t.realized_pnl += pnl
        t.fills.append(Fill(candle.timestamp, price, qty, "tp"))
        reason = [ExitReason.TAKE_PROFIT_1, ExitReason.TAKE_PROFIT_2, ExitReason.TAKE_PROFIT_3][min(idx, 2)]
        t.exit_reasons.append(reason.value)
        if self._filled_qty(t) >= t.quantity - 1e-12:
            self._close(t, candle.timestamp, ExitReason.TAKE_PROFIT_2 if idx >= 1 else ExitReason.TAKE_PROFIT_1)
        return [t.fills[-1]]

    def _trail(self, t: Trade, candle, atr_value: float) -> float:
        mult = self.cfg.trailing_atr_multiple
        if t.side is Side.BUY:
            return max(0.0, candle.close - mult * atr_value) or t.stop_loss
        return candle.close + mult * atr_value

    @staticmethod
    def _better_stop(new: float, old: float, is_buy: bool) -> bool:
        return new > old if is_buy else new < old

    def _close(self, t: Trade, ts, reason: ExitReason) -> None:
        t.state = OrderState.CLOSED
        t.closed_time = ts
        if reason.value not in t.exit_reasons:
            t.exit_reasons.append(reason.value)
        self.open = None
