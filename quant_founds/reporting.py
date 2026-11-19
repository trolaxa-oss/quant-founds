"""Quant Statistical Engine (09) - performance metrics, walk-forward, Monte Carlo."""
from __future__ import annotations

import random
from statistics import fmean


def performance_report(trades: list, initial_balance: float = 10_000.0) -> dict:
    if not trades:
        return {"n_trades": 0}
    pnls = [t.realized_pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    equity = initial_balance
    curve = [equity]
    for p in pnls:
        equity += p
        curve.append(equity)
    peak = curve[0]
    mdd = 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak if peak > 0 else 0.0)
    return {
        "n_trades": len(trades),
        "win_rate": round(len(wins) / len(pnls), 3),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
        "expectancy": round(fmean(pnls), 2),
        "total_pnl": round(sum(pnls), 2),
        "final_equity": round(equity, 2),
        "max_drawdown_pct": round(mdd * 100, 2),
        "equity_curve": [round(v, 2) for v in curve],
    }


def walk_forward_split(n_bars: int, folds: int = 3, train_frac: float = 0.7):
    """Yield (train_slice, test_slice) index pairs, chronological, no leakage."""
    if folds < 1 or n_bars < 10:
        return
    fold_len = n_bars // folds
    for f in range(folds):
        start = f * fold_len
        end = start + fold_len if f < folds - 1 else n_bars
        train_end = start + int((end - start) * train_frac)
        if train_end - start < 5 or end - train_end < 3:
            continue
        yield list(range(start, train_end)), list(range(train_end, end))


def monte_carlo_drawdown(pnls: list[float], runs: int = 500, seed: int = 7) -> dict:
    if not pnls:
        return {}
    rng = random.Random(seed)
    mdds: list[float] = []
    for _ in range(runs):
        order = list(pnls)
        rng.shuffle(order)
        equity = 0.0
        peak = 0.0
        mdd = 0.0
        for p in order:
            equity += p
            peak = max(peak, equity)
            mdd = max(mdd, peak - equity)
        mdds.append(mdd)
    mdds.sort()

    def pct(p):
        return round(mdds[min(len(mdds) - 1, int(p * len(mdds)))], 2)

    return {"mdd_p50": pct(0.5), "mdd_p90": pct(0.9), "mdd_p95": pct(0.95)}
