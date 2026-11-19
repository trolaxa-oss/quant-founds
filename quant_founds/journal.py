"""Journal & Reporting (11) - decision log, trades, CSV export, metrics."""
from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Journal:
    """Appends every decision (including rejections) as JSONL; trades as CSV."""

    def __init__(self, run_dir: str = "runs/latest"):
        os.makedirs(run_dir, exist_ok=True)
        self.run_dir = run_dir
        self.decisions_path = os.path.join(run_dir, "decisions.jsonl")
        self.trades_path = os.path.join(run_dir, "trades.csv")
        self._trade_header_written = False
        self.summary: dict = {"run_started": utc_now()}

    def log_decision(self, decision) -> None:
        row = {
            "logged_at": utc_now(),
            "signal_id": decision.signal_id,
            "bar_time": decision.bar_time.isoformat(),
            "symbol": decision.symbol,
            "timeframe": decision.timeframe,
            "prev_state": decision.previous_state.value,
            "state": decision.state.value,
            "type": decision.signal_type.value,
            "side": decision.side.value if decision.side else None,
            "score": decision.score,
            "hard_failures": decision.hard_failures,
            "notes": decision.notes,
            "components": [
                {"key": c.key, "earned": round(c.earned, 2), "max": c.max_points, "detail": c.detail}
                for c in decision.components
            ],
        }
        with open(self.decisions_path, "a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")

    def log_trade(self, trade) -> None:
        exists = os.path.exists(self.trades_path)
        rows = [{
            "trade_id": trade.trade_id,
            "signal_id": trade.signal_id,
            "symbol": trade.symbol,
            "timeframe": trade.timeframe,
            "side": trade.side.value,
            "entry_time": trade.entry_time.isoformat(),
            "entry_price": round(trade.entry_price, 6),
            "quantity": round(trade.quantity, 6),
            "stop_loss": round(trade.stop_loss, 6),
            "take_profits": ";".join(f"{tp:.6f}" for tp in trade.take_profits),
            "realized_pnl": round(trade.realized_pnl, 2),
            "costs": round(trade.costs, 2),
            "exit_reasons": ";".join(trade.exit_reasons),
            "closed_time": trade.closed_time.isoformat() if trade.closed_time else "",
        }]
        with open(self.trades_path, "a", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            if not exists:
                writer.writeheader()
            writer.writerows(rows)

    def write_summary(self, report: dict) -> None:
        with open(os.path.join(self.run_dir, "summary.json"), "w") as fh:
            json.dump(report, fh, indent=2, default=str)
