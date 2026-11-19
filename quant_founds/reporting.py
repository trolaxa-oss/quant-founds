"""Quant Statistical Engine (09) - performance metrics, walk-forward, Monte Carlo."""
from __future__ import annotations

import math
import random
from statistics import fmean, pstdev


def sharpe_sortino(returns: list[float]) -> tuple:
    """Per-trade reward/risk ratios (blueprint 15.2); None when undefined."""
    if not returns:
        return None, None
    mu = fmean(returns)
    sd = pstdev(returns)
    sharpe = round(mu / sd, 3) if sd > 0 else None
    downside = math.sqrt(fmean([r * r for r in returns if r < 0])) \
        if any(r < 0 for r in returns) else 0.0
    sortino = round(mu / downside, 3) if downside > 0 else None
    return sharpe, sortino


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
    returns = [p / initial_balance for p in pnls]
    sharpe, sortino = sharpe_sortino(returns)
    return {
        "n_trades": len(trades),
        "win_rate": round(len(wins) / len(pnls), 3),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
        "expectancy": round(fmean(pnls), 2),
        "avg_win": round(fmean(wins), 2) if wins else None,
        "avg_loss": round(fmean(losses), 2) if losses else None,
        "total_costs": round(sum(getattr(t, "costs", 0.0) or 0.0 for t in trades), 2),
        "total_pnl": round(sum(pnls), 2),
        "final_equity": round(equity, 2),
        "max_drawdown_pct": round(mdd * 100, 2),
        "sharpe": sharpe,
        "sortino": sortino,
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


def walk_forward_report(trades: list, timestamps: list, folds: int = 3) -> dict:
    """Per-test-window performance (blueprint 15.2/16). The system is rule-based
    (no fitted parameters), so windows are evaluated as-is for stability."""
    windows = []
    for train, test in walk_forward_split(len(timestamps), folds=folds):
        start = timestamps[test[0]]
        end = timestamps[test[-1]]
        in_window = [t for t in trades
                     if getattr(t, "closed_time", None)
                     and start <= t.closed_time <= end]
        rep = performance_report(in_window)
        rep.pop("equity_curve", None)
        windows.append({
            "train_bars": [train[0], train[-1]],
            "test_bars": [test[0], test[-1]],
            "metrics": rep,
        })
    profitable = sum(1 for w in windows
                     if w["metrics"].get("n_trades", 0)
                     and (w["metrics"].get("total_pnl") or 0) > 0)
    return {"windows": windows, "n_windows": len(windows),
            "profitable_windows": profitable,
            "stability": round(profitable / len(windows), 3) if windows else None}


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


def render_html_report(trades: list, report: dict, path: str) -> str:
    """Standalone HTML performance report (blueprint 10/18) - no dependencies."""
    import html
    import os

    def esc(v):
        return html.escape(str(v))

    rows = "".join(
        "<tr>"
        f"<td>{esc(getattr(t, 'trade_id', '')[:8])}</td>"
        f"<td>{esc(getattr(t, 'side', getattr(t, 'symbol', '')))}</td>"
        f"<td>{esc(getattr(t, 'entry_time', ''))}</td>"
        f"<td>{esc(getattr(t, 'entry_price', ''))}</td>"
        f"<td>{esc(getattr(t, 'quantity', ''))}</td>"
        f"<td>{esc(getattr(t, 'realized_pnl', ''))}</td>"
        f"<td>{esc(';'.join(getattr(t, 'exit_reasons', [])))}</td>"
        "</tr>"
        for t in trades
    )
    if rows:
        trades_block = f"""
        <h2>Trades</h2>
        <table>
          <tr><th>id</th><th>side</th><th>entry_time</th><th>entry</th>
              <th>qty</th><th>pnl</th><th>exits</th></tr>
          {rows}
        </table>"""
    else:
        trades_block = "<p>No trades.</p>"

    equity = report.get("equity_curve") or []
    svg = ""
    if len(equity) >= 2:
        w, hgt, pad = 720, 220, 12
        lo, hi = min(equity), max(equity)
        span = (hi - lo) or 1.0

        def px(i, v):
            x = pad + (w - 2 * pad) * i / (len(equity) - 1)
            y = hgt - pad - (hgt - 2 * pad) * (v - lo) / span
            return f"{x:.1f},{y:.1f}"

        pts = " ".join(px(i, v) for i, v in enumerate(equity))
        svg = f"""
        <h2>Equity curve</h2>
        <svg width="{w}" height="{hgt}" role="img">
          <polyline fill="none" stroke="#1a7f37" stroke-width="2" points="{pts}"/>
        </svg>"""

    metrics_rows = "".join(
        f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>"
        for k, v in report.items()
        if not isinstance(v, (list, dict))
    )

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>QUANT FOUNDS report</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #222; }}
 table {{ border-collapse: collapse; margin: 0.5rem 0 1.5rem; }}
 td, th {{ border: 1px solid #ccc; padding: 4px 10px; font-size: 0.9rem; }}
 h1 {{ margin-bottom: 0.2rem; }}
 h2 {{ margin-top: 1.5rem; }}
</style></head><body>
<h1>QUANT FOUNDS — performance report</h1>
<table>{metrics_rows}</table>
{svg}
{trades_block}
</body></html>"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        fh.write(page)
    return page
