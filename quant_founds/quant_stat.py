"""Dashboard (16) - single unified market reading rendered as text."""
from __future__ import annotations


def render_snapshot(ctx, results: dict, account, open_trade, decision) -> str:
    lines: list[str] = []
    lines.append("=" * 62)
    lines.append(f"QUANT FOUNDS  |  {ctx.symbol} {ctx.timeframe}  |  bar {ctx.last.timestamp}")
    lines.append("=" * 62)
    for engine_id, res in results.items():
        state = getattr(res, "state", "?")
        score = getattr(res, "score", None)
        label = getattr(res, "confidence_label", "")
        src = getattr(res, "source_mode", "")
        lines.append(f"  {engine_id:<12} {state:<28} score={score} [{label}] src={src.value}")
    if decision:
        lines.append("-" * 62)
        lines.append(f"  SIGNAL  {decision.state.value}  side={decision.side.value if decision.side else '-'}"
                     f"  score={decision.score}")
        if decision.hard_failures:
            lines.append(f"  blocked by: {', '.join(decision.hard_failures)}")
        wins = [f"{c.key} {c.earned:.1f}/{c.max_points}" for c in decision.components if c.earned]
        lines.append(f"  evidence: {'; '.join(wins)}")
    if open_trade:
        lines.append("-" * 62)
        lines.append(f"  OPEN {open_trade.side.value.upper()} qty={open_trade.quantity:.4f}"
                     f" entry={open_trade.entry_price:.5f} SL={open_trade.stop_loss:.5f}"
                     f" pnl={open_trade.realized_pnl:.2f} exits={open_trade.exit_reasons}")
    lines.append("-" * 62)
    lines.append(f"  ACCOUNT  balance={account.balance:.2f} {account.currency_code}"
                 f"  equity={account.equity:.2f}  day_pnl={account.day_pnl:.2f}"
                 f"  consec_losses={account.consecutive_losses}")
    lines.append("")
    return "\n".join(lines)
