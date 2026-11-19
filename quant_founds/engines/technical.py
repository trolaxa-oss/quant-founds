"""Technical Intelligence (engine 07) - indicator math, pure stdlib.

Indicators are descriptive assistants, never standalone signals:
pairs like EMA/MACD must not be treated as fully independent evidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean
from typing import Optional


@dataclass
class IndicatorSnapshot:
    ema_fast: Optional[float] = None
    ema_slow: Optional[float] = None
    ema_fast_prev: Optional[float] = None
    atr: Optional[float] = None
    atr_pct: Optional[float] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    bb_mid: Optional[float] = None
    vwap: Optional[float] = None
    adx: Optional[float] = None
    volume_ratio: Optional[float] = None
    supertrend_dir: Optional[int] = None


def ema_series(values: list[float], period: int) -> list[float]:
    if period <= 0 or len(values) < period:
        return []
    k = 2.0 / (period + 1.0)
    seed = fmean(values[:period])
    out = [seed]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


def ema(values: list[float], period: int) -> Optional[float]:
    s = ema_series(values, period)
    return s[-1] if s else None


def true_ranges(candles) -> list[float]:
    trs: list[float] = []
    for i, c in enumerate(candles):
        if i == 0:
            trs.append(c.high - c.low)
        else:
            prev = candles[i - 1].close
            trs.append(max(c.high - c.low, abs(c.high - prev), abs(c.low - prev)))
    return trs


def atr(candles, period: int = 14) -> Optional[float]:
    trs = true_ranges(candles)
    if len(trs) < period + 1:
        return None
    window = trs[-(period + 1):]
    return fmean(window)


def rsi(values: list[float], period: int = 14) -> Optional[float]:
    if len(values) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-(period), 0):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0 and avg_gain == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    if len(values) < slow + signal:
        return None, None
    fast_s = ema_series(values, fast)
    slow_s = ema_series(values, slow)
    off = len(fast_s) - len(slow_s)
    macd_line = [f - s for f, s in zip(fast_s[off:], slow_s)]
    if len(macd_line) < signal + 1:
        return None, None
    sig = ema_series(macd_line, signal)
    return macd_line[-1], sig[-1] if sig else None


def bollinger(values: list[float], period: int = 20, mult: float = 2.0):
    if len(values) < period:
        return None, None, None
    window = values[-period:]
    mid = fmean(window)
    var = sum((v - mid) ** 2 for v in window) / period
    sd = math.sqrt(var)
    return mid, mid - mult * sd, mid + mult * sd


def vwap(candles) -> Optional[float]:
    if not candles:
        return None
    pv = 0.0
    vol = 0.0
    for c in candles:
        if c.volume <= 0:
            return None
        typical = (c.high + c.low + c.close) / 3.0
        pv += typical * c.volume
        vol += c.volume
    if vol <= 0:
        return None
    return pv / vol


def adx(candles, period: int = 14) -> Optional[float]:
    if len(candles) < period * 2 + 1:
        return None
    trs = true_ranges(candles)
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for i in range(1, len(candles)):
        up = candles[i].high - candles[i - 1].high
        down = candles[i - 1].low - candles[i].low
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    dxs: list[float] = []
    for i in range(period, len(candles)):
        tr = fmean(trs[1:i + 1][-period:])
        if tr <= 0:
            continue
        pdi = fmean(plus_dm[i - period:i]) / tr * 100.0
        mdi = fmean(minus_dm[i - period:i]) / tr * 100.0
        denom = max(pdi + mdi, 1e-12)
        dxs.append(abs(pdi - mdi) / denom * 100.0)
    if len(dxs) < 1:
        return None
    return fmean(dxs[-period:]) if len(dxs) >= period else fmean(dxs)


def supertrend_dir(candles, period: int = 10, mult: float = 3.0) -> Optional[int]:
    if len(candles) < period + 2:
        return None
    a = atr(candles, period)
    if a is None:
        return None
    close = candles[-1].close
    mid = (candles[-1].high + candles[-1].low) / 2.0
    upper = mid + mult * a
    lower = mid - mult * a
    prev = candles[-2].close
    if close > upper:
        return 1
    if close < lower:
        return -1
    return 1 if close >= prev else -1


def swing_points(candles, left: int = 2, right: int = 2, tol: float = 1e-12):
    """Return (swing_high_idx, swing_low_idx) for completed bars only."""
    highs: list[int] = []
    lows: list[int] = []
    n = len(candles)
    for i in range(left, n - right):
        h = candles[i].high
        l = candles[i].low
        if all(h >= candles[i - k].high - tol for k in range(1, left + 1)) and \
           all(h >= candles[i + k].high - tol for k in range(1, right + 1)):
            highs.append(i)
        if all(l <= candles[i - k].low + tol for k in range(1, left + 1)) and \
           all(l <= candles[i + k].low + tol for k in range(1, right + 1)):
            lows.append(i)
    return highs, lows


def volume_ratio(candles, period: int = 20) -> Optional[float]:
    if len(candles) < period + 1:
        return None
    window = candles[-period - 1:-1]
    vols = [c.volume for c in window]
    avg = fmean(vols)
    if avg <= 0:
        return None
    return candles[-1].volume / avg


def snapshot(candles, ema_fast_len: int = 20, ema_slow_len: int = 50,
             atr_len: int = 14) -> IndicatorSnapshot:
    closes = [c.close for c in candles]
    snap = IndicatorSnapshot()
    if len(candles) < 5:
        return snap
    snap.ema_fast = ema(closes, ema_fast_len)
    snap.ema_fast_prev = ema(closes[:-1], ema_fast_len)
    snap.ema_slow = ema(closes, ema_slow_len)
    a = atr(candles, atr_len)
    if a is not None and candles[-1].close:
        snap.atr = a
        snap.atr_pct = a / candles[-1].close
    snap.rsi = rsi(closes, 14)
    snap.macd, snap.macd_signal = macd(closes)
    snap.bb_mid, snap.bb_lower, snap.bb_upper = bollinger(closes, 20)
    snap.vwap = vwap(candles)
    snap.adx = adx(candles, 14)
    snap.volume_ratio = volume_ratio(candles, 20)
    snap.supertrend_dir = supertrend_dir(candles, 10)
    return snap


def htf_trend(candles, ema_len: int = 20) -> Optional[str]:
    closes = [c.close for c in candles]
    e = ema(closes, ema_len)
    if e is None:
        return None
    return "up" if candles[-1].close > e else "down"
