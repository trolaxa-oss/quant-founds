"""Opportunity scoring (blueprint 5.3) - weights sum to 100, adjustable in config."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScoreComponent:
    key: str
    max_points: float
    earned: float
    detail: str


def score_opportunity(results: dict, side: str, cfg) -> tuple[float, list[ScoreComponent]]:
    w = cfg.weights
    comps: list[ScoreComponent] = []

    market = results.get("market")
    smc = results.get("smc")
    liq = results.get("liquidity")
    of = results.get("orderflow")
    mtf = results.get("mtf")
    news = results.get("news")
    sessions = results.get("sessions")
    data = results.get("data")

    def aligned(r, bias=1.0):
        if r is None:
            return 0.0
        d = getattr(r, "direction", None) or (r.extras or {}).get("direction")
        return bias if d == side else 0.0

    # 1) trend & HTF direction (15)
    trend_pts = 0.0
    detail = []
    trend_state = getattr(market, "state", "unavailable") if market else "unavailable"
    if (side == "buy" and trend_state == "up") or (side == "sell" and trend_state == "down"):
        trend_pts += 0.6
        detail.append("intraday_aligned")
    trend_strength = (getattr(market, "extras", {}).get("strength") or 0.0) / 100.0 if market else 0.0
    trend_pts += 0.4 * trend_strength
    detail.append(f"strength={trend_strength:.2f}")
    comps.append(ScoreComponent("trend", w["trend"], w["trend"] * trend_pts, ";".join(detail)))

    # 2) structure (15)
    struct_pts = 0.0
    if smc and smc.extras.get("events"):
        sdir = smc.extras["events"][-1]["direction"]
        if (side == "buy" and sdir == "up") or (side == "sell" and sdir == "down"):
            struct_pts = 1.0
    comps.append(ScoreComponent("structure", w["structure"], w["structure"] * struct_pts,
                                "BOS/CHOCH aligned" if struct_pts else "no_aligned_event"))

    # 3) liquidity & sweep quality (20)
    liq_pts = 0.0
    ldet = []
    if liq:
        sweeps = liq.extras.get("sweeps") or []
        target_side = liq.extras.get("target_side")
        for s in sweeps:
            # a BSL sweep (buys taken out) supports SELL continuation and vice versa
            if (s["side"] == "BSL" and side == "sell") or \
               (s["side"] == "SSL" and side == "buy"):
                liq_pts = 1.0 if s["confirmed"] else 0.6
                ldet.append(f"sweep_{s['side']}_conf={s['confirmed']}")
                break
        if liq_pts == 0.0 and target_side:
            if (target_side == "BSL" and side == "buy") or (target_side == "SSL" and side == "sell"):
                liq_pts = 0.4
                ldet.append("target_ahead")
    comps.append(ScoreComponent("liquidity", w["liquidity"], w["liquidity"] * liq_pts,
                                ";".join(ldet) or "no_sweep"))

    # 4) order flow (15) - estimated proxy always discounted
    of_pts = 0.0
    if of:
        raw = (of.score or 0.0) / 100.0 * (1.0 if aligned(of) else 0.0)
        of_pts = raw * 0.7 if of.source_mode.value == "estimated" else raw
    comps.append(ScoreComponent("orderflow", w["orderflow"], w["orderflow"] * of_pts,
                                str(getattr(of, "source_mode", None))))

    # 5) momentum & volatility (10)
    mv_pts = 0.0
    if market:
        adx = (market.extras.get("adx") or 0.0)
        atr_pct = (market.extras.get("atr_pct") or 0.0)
        mv_pts = min(1.0, (adx / 40.0))
        if 0.0008 <= atr_pct <= 0.015:
            mv_pts = min(1.0, mv_pts + 0.25)
    comps.append(ScoreComponent("momentum_volatility", w["momentum_volatility"],
                                w["momentum_volatility"] * mv_pts, f"mv={mv_pts:.2f}"))

    # 6) MTF alignment (10)
    mtf_pts = 0.0
    if mtf:
        state = mtf.state
        if (side == "buy" and state == "aligned_buy") or (side == "sell" and state == "aligned_sell"):
            mtf_pts = 1.0
        elif state == "partial":
            mtf_pts = 0.5
    comps.append(ScoreComponent("mtf", w["mtf"], w["mtf"] * mtf_pts, str(getattr(mtf, "state", None))))

    # 7) session / news / data quality (5)
    ctx_pts = 0.0
    if data and data.score == 100.0:
        ctx_pts += 0.4
    if sessions and sessions.extras.get("active"):
        ctx_pts += 0.4 if sessions.extras.get("overlap") else 0.25
    if news and news.state == "clear":
        ctx_pts += 0.2
    comps.append(ScoreComponent("context", w["context"], w["context"] * min(1.0, ctx_pts),
                                f"ctx={ctx_pts:.2f}"))

    # 8) reward-to-risk (10) - filled later by decision engine if plan exists
    rr = results.get("_rr_fraction")
    if rr is not None:
        comps.append(ScoreComponent("risk_reward", w["risk_reward"], w["risk_reward"] * rr, "plan"))
    else:
        comps.append(ScoreComponent("risk_reward", w["risk_reward"], 0.0, "no_plan"))

    total = sum(c.earned for c in comps)
    return round(total, 2), comps
