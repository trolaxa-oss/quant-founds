"""MT5 HTTP bridge - reference implementation (blueprint 12).

Run this on a machine that has the MetaTrader5 terminal and python package
installed (Windows). It serves closed OHLCV bars over HTTP for
quant_founds.providers.mt5_bridge.Mt5BridgeProvider:

    python scripts/mt5_bridge_server.py --host 127.0.0.1 --port 8770

Optional auth: set QF_BRIDGE_TOKEN and pass the same token to the client
environment (Authorization: Bearer <token>).

Binds loopback only by default - never expose the bridge to the public
internet; put it behind a VPN/SSH tunnel if remote access is needed.
"""
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TIMEFRAME_MINUTES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440,
}


def fetch_candles_mt5(symbol: str, timeframe: str, bars: int) -> list[dict]:
    """Read closed bars from a running MetaTrader5 terminal.

    Kept in one function so tests can monkeypatch it without MT5 installed.
    """
    import MetaTrader5 as mt5

    tf = getattr(mt5, f"TIMEFRAME_{timeframe}", None)
    if tf is None:
        raise ValueError(f"unsupported timeframe {timeframe}")
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars + 1)
    finally:
        mt5.shutdown()
    if rates is None:
        raise RuntimeError(f"no rates for {symbol}: {mt5.last_error()}")

    import time as _time

    now = int(_time.time())
    rows = []
    for r in rates:
        close_ts = int(r["time"]) + TIMEFRAME_MINUTES[timeframe] * 60
        rows.append({
            "timestamp": int(r["time"]),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r["tick_volume"]),
            "closed": close_ts <= now,
        })
    return rows


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "QuantFoundsBridge/1.0"

    def do_GET(self):  # noqa: N802 - stdlib API
        if self.path.startswith("/candles"):
            self._serve_candles()
        else:
            self._json(404, {"error": "not_found"})

    def _serve_candles(self):
        expected = os.environ.get("QF_BRIDGE_TOKEN", "")
        if expected:
            got = self.headers.get("Authorization", "")
            if got != f"Bearer {expected}":
                self._json(401, {"error": "unauthorized"})
                return
        from urllib.parse import parse_qs, urlparse

        q = parse_qs(urlparse(self.path).query)
        symbol = (q.get("symbol") or [""])[0]
        timeframe = (q.get("timeframe") or [""])[0]
        bars = int((q.get("bars") or ["100"])[0])
        if timeframe not in TIMEFRAME_MINUTES or not symbol:
            self._json(400, {"error": "bad_request"})
            return
        try:
            rows = fetch_candles_mt5(symbol, timeframe, min(max(bars, 1), 5000))
        except Exception as exc:
            self._json(503, {"error": str(exc)})
            return
        self._json(200, rows)

    def _json(self, code: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args) -> None:
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="MT5 -> HTTP bridge for QUANT FOUNDS")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), BridgeHandler)
    print(f"bridge listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
