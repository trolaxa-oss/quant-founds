"""Shared trade plan construction (blueprint 5.4, 6) - used by backtester & runtime."""
from __future__ import annotations

from quant_founds.core.enums import Side
from quant_founds.core.models import TradePlan


def build_plan(ctx, results: dict, decision) -> TradePlan | None:
    """SL from the last swing +/- 0.5 ATR, TPs at 1R/2R/3R,
    TP3 overridden by the liquidity target level when aligned."""
    market = results["market"]
    liq = results["liquidity"]
    atr_value = market.extras.get("atr")
    if not atr_value:
        return None
    entry = ctx.last.close
    is_buy = decision.side is Side.BUY
    swing_low = market.extras.get("swing_lows") or []
    swing_high = market.extras.get("swing_highs") or []
    extras = liq.extras or {}

    if is_buy:
        base = min(swing_low[-1:]) if swing_low else entry - atr_value
        stop = base - 0.5 * atr_value
        if stop >= entry:
            stop = entry - 1.0 * atr_value
        stop_dist = entry - stop
        if stop_dist <= 0:
            return None
        tps = [entry + stop_dist * r for r in (1.0, 2.0, 3.0)]
        if extras.get("target_side") == "BSL" and extras.get("target_level"):
            target = extras["target_level"]
            if target > entry:
                tps[2] = target
    else:
        base = max(swing_high[-1:]) if swing_high else entry + atr_value
        stop = base + 0.5 * atr_value
        if stop <= entry:
            stop = entry + 1.0 * atr_value
        stop_dist = stop - entry
        if stop_dist <= 0:
            return None
        tps = [entry - stop_dist * r for r in (1.0, 2.0, 3.0)]
        if extras.get("target_side") == "SSL" and extras.get("target_level"):
            target = extras["target_level"]
            if target < entry:
                tps[2] = target

    risk = abs(entry - stop)
    reward = abs(tps[1] - entry)
    rr = reward / risk if risk > 0 else 0.0
    return TradePlan(
        signal_id=decision.signal_id,
        symbol=ctx.symbol,
        timeframe=ctx.timeframe,
        side=Side.BUY if is_buy else Side.SELL,
        entry=entry,
        stop_loss=round(stop, 8),
        take_profits=[round(tp, 8) for tp in tps],
        risk_reward=round(rr, 3),
        bar_time=ctx.last.timestamp,
    )
