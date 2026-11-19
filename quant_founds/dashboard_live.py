"""Live dashboard (blueprint 18): local HTML view of the paper runtime.

Serves on loopback only (127.0.0.1) - never a public interface. Reads state
directly from the LivePaperRunner: account, open trade, closed paper trades,
recent decisions and alerts, plus an SVG equity curve of paper P&L.
"""
from __future__ import annotations

import html
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from quant_founds.journal import utc_now

MAX_DECISION_ROWS = 15
MAX_TRADE_ROWS = 20


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def collect_state(runner) -> dict:
    account = runner.account
    rep = runner.snapshot_summary()
    open_trade = None
    if runner.broker.open is not None:
        t = runner.broker.open
        open_trade = {
            "side": t.side.value, "entry_price": t.entry_price,
            "stop_loss": t.stop_loss, "quantity": t.quantity,
            "take_profits": t.take_profits, "entry_time": t.entry_time.isoformat(),
        }
    trades = [{
        "trade_id": t.trade_id[:8], "side": t.side.value,
        "entry_time": t.entry_time.isoformat(), "entry_price": t.entry_price,
        "realized_pnl": t.realized_pnl, "exit_reasons": ";".join(t.exit_reasons),
    } for t in runner.trades[-MAX_TRADE_ROWS:]][::-1]
    decisions = []
    try:
        with open(runner.journal_path) as fh:
            for line in fh.readlines()[-MAX_DECISION_ROWS:]:
                try:
                    decisions.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    ai = None
    model = getattr(runner, "ai_model", None)
    if model is not None:
        ai = {"version": model.version, "n_updates": model.n_updates,
              "n_wins": model.n_wins, "gate": runner.ai_gate}
    cumulative = []
    acc = 0.0
    for t in runner.trades:
        acc += t.realized_pnl
        cumulative.append(acc)
    return {
        "now": utc_now(),
        "symbol": runner.cfg.data.symbol,
        "timeframe": runner.cfg.data.timeframe,
        "balance": account.balance,
        "equity": account.equity,
        "peak_equity": account.peak_equity,
        "day_pnl": account.day_pnl,
        "n_bars_seen": runner.n_bars_seen,
        "open_trade": open_trade,
        "trades": trades,
        "decisions": decisions,
        "metrics": {k: v for k, v in rep.items()
                    if isinstance(v, (int, float, str, bool))},
        "ai": ai,
        "cumulative_pnl": cumulative,
    }


def _svg_equity(cumulative: list[float]) -> str:
    if not cumulative:
        return "<p class=muted>لا توجد صفقات مغلقة بعد.</p>"
    lo, hi = min(cumulative), max(cumulative)
    if hi - lo < 1e-9:
        hi = lo + 1.0
    w, h, pad = 640, 180, 8
    n = len(cumulative)
    pts = []
    for i, v in enumerate(cumulative):
        x = pad + (w - 2 * pad) * (i / max(1, n - 1))
        y = h - pad - (h - 2 * pad) * ((v - lo) / (hi - lo))
        pts.append(f"{x:.1f},{y:.1f}")
    zero_y = h - pad - (h - 2 * pad) * ((0.0 - lo) / (hi - lo)) \
        if lo <= 0 <= hi else None
    zero = (f'<line x1="{pad}" y1="{zero_y:.1f}" x2="{w - pad}" '
            f'y2="{zero_y:.1f}" stroke="#999" stroke-dasharray="4,4"/>'
            if zero_y is not None else "")
    return (f'<svg width="{w}" height="{h}" role="img">'
            f'<rect width="{w}" height="{h}" fill="#fafafa" rx="6"/>'
            f'{zero}<polyline fill="none" stroke="#0a7" stroke-width="2" '
            f'points="{" ".join(pts)}"/></svg>')


def render_dashboard(state: dict) -> str:
    rows_t = "".join(
        f"<tr><td><code>{_esc(t['trade_id'])}</code></td><td>{_esc(t['side'])}</td>"
        f"<td>{_esc(t['entry_time'])}</td><td>{_esc(t['entry_price'])}</td>"
        f"<td class=\"{'up' if t['realized_pnl'] >= 0 else 'down'}\">"
        f"{t['realized_pnl']:+.2f}</td><td>{_esc(t['exit_reasons'])}</td></tr>"
        for t in state["trades"]) or "<tr><td colspan=6 class=muted>لا صفقات بعد</td></tr>"
    rows_d = "".join(
        f"<tr><td>{_esc(d.get('bar_time'))}</td><td>{_esc(d.get('state'))}</td>"
        f"<td>{_esc(d.get('side'))}</td><td>{_esc(d.get('score'))}</td>"
        f"<td>{_esc(', '.join(d.get('notes', [])))}</td></tr>"
        for d in state["decisions"]) or "<tr><td colspan=5 class=muted>لا قرارات بعد</td></tr>"
    ot = state["open_trade"]
    open_html = (f"<p>اتجاه: <b>{_esc(ot['side'])}</b> — دخول {_esc(ot['entry_price'])} "
                 f"| SL {_esc(ot['stop_loss'])} | حجم {_esc(ot['quantity'])} "
                 f"| TP {', '.join(_esc(x) for x in ot['take_profits'])}</p>"
                 if ot else "<p class=muted>لا توجد صفقة مفتوحة.</p>")
    metrics = "".join(f"<tr><th>{_esc(k)}</th><td>{_esc(round(v, 4) if isinstance(v, float) else v)}</td></tr>"
                      for k, v in sorted(state["metrics"].items()))
    ai_html = (f"<p>نموذج AI: {_esc(state['ai']['version'])} — تحديثات "
               f"{state['ai']['n_updates']} (ناجحة {state['ai']['n_wins']}), "
               f"بوابة AI: {'مفعّلة' if state['ai']['gate'] else 'غير مفعّلة'}</p>"
               if state.get("ai") else "<p class=muted>AI غير مفعّل (بدون نموذج).</p>")
    return f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="30">
<title>QUANT FOUNDS — Live Paper Dashboard</title>
<style>
body{{font-family:sans-serif;margin:24px;color:#222}}
table{{border-collapse:collapse;margin:12px 0}}
th,td{{border:1px solid #ddd;padding:4px 10px}}
td.up{{color:#0a7}}td.down{{color:#c33}}
.muted{{color:#888}}
h2{{border-bottom:2px solid #eee;padding-bottom:4px}}
</style></head><body>
<h1>QUANT FOUNDS — لوحة التداول الورقي</h1>
<p>{_esc(state['symbol'])} {_esc(state['timeframe'])} — آخر تحديث {_esc(state['now'])}
| شموع معالَجة: {state['n_bars_seen']}</p>
<h2>الحساب (ورقي)</h2>
<table><tr><th>الرصيد</th><td>{state['balance']:.2f}</td></tr>
<tr><th>حقوق الملكية</th><td>{state['equity']:.2f}</td></tr>
<tr><th>أعلى قمة</th><td>{state['peak_equity']:.2f}</td></tr>
<tr><th>ربح اليوم</th><td>{state['day_pnl']:+.2f}</td></tr></table>
<h2>الصفقة المفتوحة</h2>{open_html}
<h2>منحنى الربح التراكمي</h2>{_svg_equity(state['cumulative_pnl'])}
<h2>آخر الصفقات المغلقة</h2>
<table><tr><th>معرف</th><th>اتجاه</th><th>وقت الدخول</th><th>الدخول</th><th>الربح</th><th>عمليات الإغلاق</th></tr>{rows_t}</table>
<h2>آخر القرارات</h2>
<table><tr><th>وقت الشمعة</th><th>الحالة</th><th>الاتجاه</th><th>الدرجة</th><th>ملاحظات</th></tr>{rows_d}</table>
<h2>مقاييس الأداء</h2><table>{metrics}</table>
<h2>محرك AI</h2>{ai_html}
<p class=muted>تشغيل ورقي فقط — تُعرض بيانات محلية عبر loopback، ولا أمر حقيقي.</p>
</body></html>"""


class _DashboardHandler(BaseHTTPRequestHandler):
    runner = None

    def do_GET(self):
        state = collect_state(self.runner)
        page = render_dashboard(state).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, *args):
        pass


def start_dashboard(runner, host: str = "127.0.0.1", port: int = 8771):
    """Bind loopback-only and serve in a daemon thread; returns the server."""
    handler = type("_Handler", (_DashboardHandler,), {"runner": runner})
    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
