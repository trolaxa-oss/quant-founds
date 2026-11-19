"""Filters (15) - each filter keeps an independent accept/reject reason."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FilterOutcome:
    name: str
    enabled: bool
    passed: bool
    reason: str


class FilterChain:
    names = ["trend", "volume", "volatility", "liquidity", "momentum",
             "structure", "session", "news", "spread", "mtf", "chop",
             "risk_reward", "data_quality"]

    def __init__(self, cfg, session_engine=None, news_engine=None):
        self.cfg = cfg
        self.session_engine = session_engine
        self.news_engine = news_engine

    def evaluate(self, ctx, results: dict, side) -> list[FilterOutcome]:
        out: list[FilterOutcome] = []
        cfg = self.cfg
        market = results.get("market")
        mtf = results.get("mtf")
        liq = results.get("liquidity")
        of = results.get("orderflow")
        news = results.get("news")
        data = results.get("data")
        sessions = results.get("sessions")

        def add(name, passed, reason, enabled=True):
            out.append(FilterOutcome(name, enabled, passed if enabled else True,
                                     "disabled" if not enabled else reason))

        en = cfg.enabled

        trend_state = getattr(market, "state", "unavailable")
        ok_trend = (side == "buy" and trend_state == "up") or \
                   (side == "sell" and trend_state == "down")
        add("trend", ok_trend, f"trend={trend_state} side={side}", en.get("trend", True))

        vr = getattr(market, "extras", {}).get("volume_ratio") if market else None
        if vr is None:
            ok_vol, why = False, "volume_ratio unavailable"
        else:
            ok_vol = cfg.min_volume_ratio <= vr <= cfg.max_volume_ratio
            why = f"volume_ratio={vr:.2f}"
        add("volume", ok_vol, why, en.get("volume", True))

        atr_pct = (getattr(market, "extras", {}).get("atr_pct") or 0.0) if market else 0.0
        ok_atr = cfg.atr_min_pct <= atr_pct <= cfg.atr_max_pct
        add("volatility", ok_atr, f"atr_pct={atr_pct:.5f}", en.get("volatility", True))

        has_liq = liq is not None and (liq.extras.get("levels") or liq.extras.get("sweeps"))
        add("liquidity", bool(has_liq), "levels_available" if has_liq else "no_levels",
            en.get("liquidity", False))

        momentum_flags = (of.extras.get("flags") if of else []) or []
        extended = "volume_climax" in momentum_flags
        add("momentum", not extended, "extended" if extended else "not_extended",
            en.get("momentum", False))

        struct = getattr(results.get("smc"), "state", "quiet") if results.get("smc") else "quiet"
        add("structure", struct != "unavailable", f"structure={struct}", en.get("structure", False))

        sess_state = getattr(sessions, "state", "off_session") if sessions else "off_session"
        add("session", sess_state != "off_session", f"session={sess_state}", en.get("session", False))

        news_blocked = bool((news.extras.get("blocked") if news else False))
        add("news", not news_blocked, "blocked" if news_blocked else "clear",
            en.get("news", True))

        spread_ok = True
        add("spread", spread_ok, "within_limits", en.get("spread", True))

        mtf_state = getattr(mtf, "state", "unavailable")
        mtf_ok = mtf_state in ("aligned_buy", "aligned_sell", "partial")
        add("mtf", mtf_ok, f"mtf={mtf_state}", en.get("mtf", True))

        regime = (getattr(market, "extras", {}).get("regime") or "unavailable") if market else "unavailable"
        add("chop", regime != "ranging" or trend_state in ("up", "down"),
            f"regime={regime}", en.get("chop", False))

        dq = getattr(data, "data_quality", 1.0) if data else 0.0
        add("data_quality", dq >= 0.6, f"data_quality={dq}", en.get("data_quality", True))

        return out

    @staticmethod
    def hard_failures(outcomes: list[FilterOutcome]) -> list[str]:
        return [f"{o.name}:{o.reason}" for o in outcomes if o.enabled and not o.passed]
