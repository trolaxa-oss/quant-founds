"""Risk Engine (13) - final authority: may reject any trade (blueprint 7)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskDecision:
    approved: bool
    reasons: list[str]
    position_size: float = 0.0
    revised_plan: object | None = None


class RiskEngine:
    def __init__(self, cfg, account):
        self.cfg = cfg
        self.account = account
        self.kill_switch = False
        self.cooldown_until_index: int = -1
        self.trades_today: int = 0

    # -- state evaluation -------------------------------------------------
    def limits_ok(self, equity: float, day_pnl: float, week_pnl: float,
                  bar_index: int, open_positions: int) -> list[str]:
        problems: list[str] = []
        if self.kill_switch:
            problems.append("kill_switch_active")
        a = self.account
        if day_pnl <= -a.balance * self.cfg.daily_loss_limit_pct:
            problems.append("daily_loss_limit")
        if week_pnl <= -a.balance * self.cfg.weekly_loss_limit_pct:
            problems.append("weekly_loss_limit")
        peak = max(a.peak_equity, equity)
        if a.peak_equity > 0 and (a.peak_equity - equity) / a.peak_equity \
                >= self.cfg.max_drawdown_stop_pct:
            self.kill_switch = True
            problems.append("max_drawdown_stop")
        if a.consecutive_losses >= self.cfg.max_consecutive_losses and \
                bar_index <= self.cooldown_until_index:
            problems.append("loss_cooldown")
        if open_positions >= self.cfg.max_open_positions:
            problems.append("max_open_positions")
        return problems

    # -- trade evaluation -------------------------------------------------
    def evaluate(self, plan, equity: float, day_pnl: float, week_pnl: float,
                 bar_index: int, open_positions: int) -> RiskDecision:
        reasons: list[str] = []
        limit_problems = self.limits_ok(equity, day_pnl, week_pnl, bar_index, open_positions)
        reasons.extend(limit_problems)

        risk_dist = abs(plan.entry - plan.stop_loss)
        if risk_dist <= 0:
            reasons.append("zero_stop_distance")
        else:
            rr = plan.risk_reward
            if rr < self.cfg.min_risk_reward:
                reasons.append(f"rr_too_low:{rr:.2f}")

            risk_amount = equity * self.cfg.risk_per_trade_pct
            value_per_unit = risk_dist * self.cfg.point_value * self.cfg.contract_size
            if value_per_unit <= 0:
                reasons.append("bad_point_value")
            else:
                size = risk_amount / value_per_unit
                if size <= 0:
                    reasons.append("zero_size")

        if reasons:
            return RiskDecision(False, reasons)

        size = risk_amount / value_per_unit
        return RiskDecision(True, [], position_size=size)

    def register_loss(self, bar_index: int) -> None:
        a = self.account
        a.consecutive_losses += 1
        if a.consecutive_losses >= self.cfg.max_consecutive_losses:
            self.cooldown_until_index = bar_index + self.cfg.cooldown_bars_after_losses

    def register_win(self) -> None:
        self.account.consecutive_losses = 0

    def reset_daily(self) -> None:
        self.trades_today = 0
