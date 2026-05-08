#!/usr/bin/env python3
"""
Shadow Viewer — tiny local web page that shows the shadow paper instance in
real time. Reads the shadow SQLite + state files directly; no Coinbase calls,
no writes. Auto-refreshes every 5s.

Run:
    python3 scripts/shadow_viewer.py
    open http://localhost:8087
"""

import json
import os
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("SHADOW_VIEWER_PORT", "8087"))
LABEL = os.environ.get("VIEWER_LABEL", "SHADOW VIEWER")
SHADOW_DB = os.environ.get(
    "VIEWER_DB", "/Users/bonnyagent/ibitlabs/sol_sniper_shadow.db")
SHADOW_STATE = os.environ.get(
    "VIEWER_STATE", "/Users/bonnyagent/ibitlabs/sol_sniper_state_shadow.json")
SHADOW_LOG = os.environ.get(
    "VIEWER_LOG", "/Users/bonnyagent/ibitlabs/logs/sniper_shadow_launchd_err.log")
# The "compare" DB is whichever sister instance you want to delta against.
# When the viewer is showing live, this points at shadow; vice versa.
LIVE_DB = os.environ.get(
    "VIEWER_COMPARE_DB", "/Users/bonnyagent/ibitlabs/sol_sniper.db")
COMPARE_LABEL = os.environ.get("VIEWER_COMPARE_LABEL", "Live")

# Strategy params for THIS instance — defaults match shadow plist.
# Live sets these via env in com.ibitlabs.live-viewer.plist (trail 0.008/0.005).
TP_PCT = float(os.environ.get("VIEWER_TP_PCT", "0.030"))
SL_PCT = float(os.environ.get("VIEWER_SL_PCT", "0.035"))
TRAIL_ACTIVATE = float(os.environ.get("VIEWER_TRAIL_ACTIVATE", "0.004"))
TRAIL_STOP = float(os.environ.get("VIEWER_TRAIL_STOP", "0.005"))


def safe_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        return {"_error": str(e)}


def tail(path, n=40):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            block = 8192
            data = b""
            while size > 0 and data.count(b"\n") <= n:
                step = min(block, size)
                size -= step
                f.seek(size)
                data = f.read(step) + data
            return b"\n".join(data.splitlines()[-n:]).decode("utf-8", "replace")
    except Exception as e:
        return f"(log unreadable: {e})"


def db_rows(db_path, sql, args=()):
    if not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path, timeout=3)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]
        finally:
            conn.close()
    except Exception:
        return []


def fetch_state():
    state = safe_json(SHADOW_STATE)

    closes = db_rows(
        SHADOW_DB,
        """SELECT timestamp, side, direction, entry_price, exit_price,
                  pnl, exit_reason, strategy_intent
           FROM trade_log
           WHERE pnl IS NOT NULL AND pnl != 0
           ORDER BY timestamp DESC LIMIT 20""",
    )
    opens = db_rows(
        SHADOW_DB,
        """SELECT timestamp, side, direction, entry_price, strategy_intent
           FROM trade_log
           WHERE pnl IS NULL OR pnl = 0
           ORDER BY timestamp DESC LIMIT 5""",
    )

    cutoff_24h = time.time() - 86400
    pnl_24h_rows = db_rows(
        SHADOW_DB,
        "SELECT pnl FROM trade_log WHERE timestamp >= ? AND pnl IS NOT NULL",
        (cutoff_24h,),
    )
    pnl_24h = sum(float(r["pnl"] or 0) for r in pnl_24h_rows)
    n_24h = len([r for r in pnl_24h_rows if float(r["pnl"] or 0) != 0])

    live_pnl_rows = db_rows(
        LIVE_DB,
        "SELECT pnl FROM trade_log WHERE timestamp >= ? AND pnl IS NOT NULL",
        (cutoff_24h,),
    )
    live_pnl_24h = sum(float(r["pnl"] or 0) for r in live_pnl_rows)
    live_n_24h = len([r for r in live_pnl_rows if float(r["pnl"] or 0) != 0])

    log_age_min = None
    if os.path.exists(SHADOW_LOG):
        log_age_min = (time.time() - os.path.getmtime(SHADOW_LOG)) / 60

    return {
        "state": state,
        "closes": closes,
        "opens": opens,
        "pnl_24h": pnl_24h,
        "n_24h": n_24h,
        "live_pnl_24h": live_pnl_24h,
        "live_n_24h": live_n_24h,
        "log_age_min": log_age_min,
        "log_tail": tail(SHADOW_LOG, 30),
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def fmt_ts(ts):
    try:
        return time.strftime("%m-%d %H:%M:%S", time.localtime(float(ts)))
    except Exception:
        return str(ts)


def fmt_money(v):
    try:
        return f"${float(v):+,.2f}"
    except Exception:
        return "—"


def render_html(d):
    s = d["state"]
    pos = s.get("position") if isinstance(s, dict) else None
    grid = s.get("grid") or {} if isinstance(s, dict) else {}
    cash = s.get("cash") if isinstance(s, dict) else None

    health_color = "#22d36e"
    health_text = "ALIVE"
    if d["log_age_min"] is None:
        health_color = "#888"
        health_text = "NO LOG"
    elif d["log_age_min"] > 5:
        health_color = "#ff5577"
        health_text = f"STALE {d['log_age_min']:.0f}m"

    pos_html = "<div class=muted>no position</div>"
    if pos:
        direction = (pos.get("direction") or "").lower()
        entry = pos.get("entry_price")
        try:
            entry_f = float(entry)
        except (TypeError, ValueError):
            entry_f = None
        if entry_f and direction in ("long", "short"):
            sign = 1 if direction == "long" else -1
            tp_price = entry_f * (1 + sign * TP_PCT)
            sl_price = entry_f * (1 - sign * SL_PCT)
            trail_arm_price = entry_f * (1 + sign * TRAIL_ACTIVATE)
            tp_str = f"<b class=green>${tp_price:.2f}</b> <span class=muted>(+{TP_PCT*100:.1f}%)</span>"
            sl_str = f"<b class=red>${sl_price:.2f}</b> <span class=muted>(-{SL_PCT*100:.1f}%)</span>"
            trail_str = f"<b>${trail_arm_price:.2f}</b> <span class=muted>(+{TRAIL_ACTIVATE*100:.1f}%)</span>"
        else:
            tp_str = sl_str = trail_str = "<b>—</b>"
        pos_html = f"""
        <div class=row><span>Direction</span><b>{pos.get('direction','?')}</b></div>
        <div class=row><span>Entry</span><b>${entry if entry is not None else '?'}</b></div>
        <div class=row><span>TP</span>{tp_str}</div>
        <div class=row><span>SL</span>{sl_str}</div>
        <div class=row><span>Trail arms at</span>{trail_str}</div>
        <div class=row><span>Trailing active</span><b>{s.get('trailing_active')}</b></div>
        <div class=row><span>High PnL %</span><b>{s.get('highest_pnl_pct',0):.2f}%</b></div>
        <div class=row><span>Size</span><b>{pos.get('quantity', pos.get('size','?'))}</b></div>
        """

    grid_orders = grid.get("orders", []) if isinstance(grid, dict) else []
    grid_rows = ""
    for o in grid_orders:
        filled = o.get("filled")
        cls = "filled" if filled else "pending"
        tp_val = o.get("tp")
        tp_cell = f"${tp_val}" if tp_val is not None else "<span class=muted>—</span>"
        grid_rows += (
            f"<tr class={cls}><td>{o.get('level')}</td>"
            f"<td>${o.get('price')}</td><td>{o.get('side')}</td>"
            f"<td>${o.get('size')}</td><td>{tp_cell}</td>"
            f"<td>{'✓' if filled else '·'}</td></tr>"
        )

    closes_rows = ""
    for c in d["closes"]:
        pnl = float(c.get("pnl") or 0)
        cls = "win" if pnl > 0 else "loss"
        closes_rows += (
            f"<tr class={cls}><td>{fmt_ts(c['timestamp'])}</td>"
            f"<td>{c.get('direction') or c.get('side')}</td>"
            f"<td>${c.get('entry_price') or '—'}</td>"
            f"<td>${c.get('exit_price') or '—'}</td>"
            f"<td>{fmt_money(pnl)}</td>"
            f"<td>{c.get('exit_reason') or '—'}</td>"
            f"<td class=muted>{c.get('strategy_intent') or '—'}</td></tr>"
        )
    if not closes_rows:
        closes_rows = "<tr><td colspan=7 class=muted style='text-align:center'>no closes yet</td></tr>"

    opens_rows = ""
    for o in d["opens"]:
        opens_rows += (
            f"<tr><td>{fmt_ts(o['timestamp'])}</td>"
            f"<td>{o.get('direction') or o.get('side')}</td>"
            f"<td>${o.get('entry_price') or '—'}</td>"
            f"<td class=muted>{o.get('strategy_intent') or '—'}</td></tr>"
        )
    if not opens_rows:
        opens_rows = "<tr><td colspan=4 class=muted style='text-align:center'>no opens</td></tr>"

    return f"""<!doctype html>
<html><head>
<meta charset=utf-8>
<meta http-equiv=refresh content=5>
<title>{LABEL}</title>
<style>
  body {{ background:#0a0612; color:#e8e0ff; font-family:-apple-system,Menlo,monospace;
         margin:0; padding:24px; }}
  h1 {{ font-size:18px; margin:0 0 4px; color:#c9a3ff; letter-spacing:1px; }}
  .sub {{ color:#7a6c95; font-size:12px; margin-bottom:20px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
          gap:16px; margin-bottom:20px; }}
  .card {{ background:#15102a; border:1px solid #2a1f4a; border-radius:8px;
          padding:16px; }}
  .card h2 {{ margin:0 0 12px; font-size:11px; color:#a78bda;
             letter-spacing:1.5px; text-transform:uppercase; }}
  .row {{ display:flex; justify-content:space-between; padding:4px 0;
         border-bottom:1px dashed #251a40; font-size:13px; }}
  .row:last-child {{ border-bottom:none; }}
  .row span {{ color:#7a6c95; }}
  .row b {{ color:#e8e0ff; font-weight:600; }}
  .big {{ font-size:24px; font-weight:700; }}
  .green {{ color:#22d36e; }} .red {{ color:#ff5577; }}
  .muted {{ color:#5d527a; font-size:12px; }}
  .pill {{ display:inline-block; padding:3px 10px; border-radius:12px;
          font-size:11px; font-weight:700; letter-spacing:1px; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  th {{ text-align:left; color:#7a6c95; font-weight:500; padding:6px 8px;
       border-bottom:1px solid #2a1f4a; font-size:10px; letter-spacing:1px; }}
  td {{ padding:6px 8px; border-bottom:1px dashed #1d142e; }}
  tr.win td:nth-child(5) {{ color:#22d36e; font-weight:600; }}
  tr.loss td:nth-child(5) {{ color:#ff5577; font-weight:600; }}
  tr.filled {{ background:#1a1234; }}
  pre {{ background:#0a0612; color:#9d8bc7; font-size:11px; padding:12px;
        border-radius:6px; max-height:280px; overflow:auto; margin:0;
        border:1px solid #2a1f4a; line-height:1.5; }}
</style>
</head><body>

<h1>{LABEL}</h1>
<div class=sub>
  TP <b style="color:#22d36e">+{TP_PCT*100:.1f}%</b> ·
  SL <b style="color:#ff5577">-{SL_PCT*100:.1f}%</b> ·
  Trail arm +{TRAIL_ACTIVATE*100:.1f}% / pull -{TRAIL_STOP*100:.1f}% ·
  paper · {d['ts']} · auto-refresh 5s ·
  <span class=pill style="background:{health_color};color:#0a0612">{health_text}</span>
</div>

<div class=grid>
  <div class=card>
    <h2>Cash</h2>
    <div class="big">{fmt_money(cash)}</div>
    <div class=muted>starting $1000</div>
  </div>
  <div class=card>
    <h2>24h PnL — This instance</h2>
    <div class="big {'green' if d['pnl_24h']>=0 else 'red'}">{fmt_money(d['pnl_24h'])}</div>
    <div class=muted>{d['n_24h']} closes</div>
  </div>
  <div class=card>
    <h2>24h PnL — {COMPARE_LABEL} (compare)</h2>
    <div class="big {'green' if d['live_pnl_24h']>=0 else 'red'}">{fmt_money(d['live_pnl_24h'])}</div>
    <div class=muted>{d['live_n_24h']} closes · Δ {fmt_money(d['pnl_24h']-d['live_pnl_24h'])}</div>
  </div>
  <div class=card>
    <h2>Sniper Position</h2>
    {pos_html}
  </div>
</div>

<div class=grid>
  <div class=card>
    <h2>Grid State</h2>
    <div class=row><span>Active</span><b>{grid.get('active')}</b></div>
    <div class=row><span>Mid</span><b>${grid.get('mid_price','—')}</b></div>
    <div class=row><span>Filled</span><b>{grid.get('filled',0)} / {grid.get('levels',0)}</b></div>
    <div class=row><span>Trades</span><b>{grid.get('trades',0)}</b></div>
    <div class=row><span>Wins</span><b>{grid.get('wins',0)}</b></div>
    <div class=row><span>PnL</span><b class="{'green' if grid.get('pnl',0)>=0 else 'red'}">{fmt_money(grid.get('pnl',0))}</b></div>
  </div>
  <div class=card style="grid-column:span 2">
    <h2>Grid Orders</h2>
    <table>
      <tr><th>Lvl</th><th>Price</th><th>Side</th><th>Size</th><th>TP</th><th>Filled</th></tr>
      {grid_rows}
    </table>
  </div>
</div>

<div class=card style="margin-bottom:16px">
  <h2>Recent Closes (shadow)</h2>
  <table>
    <tr><th>Time</th><th>Dir</th><th>Entry</th><th>Exit</th><th>PnL</th><th>Reason</th><th>Intent</th></tr>
    {closes_rows}
  </table>
</div>

<div class=card style="margin-bottom:16px">
  <h2>Open Positions (shadow)</h2>
  <table>
    <tr><th>Time</th><th>Dir</th><th>Entry</th><th>Intent</th></tr>
    {opens_rows}
  </table>
</div>

<div class=card>
  <h2>Live Log Tail</h2>
  <pre>{d['log_tail']}</pre>
</div>

</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        if self.path == "/json":
            d = fetch_state()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(d, default=str).encode())
            return
        try:
            d = fetch_state()
            html = render_html(d)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"error: {e}".encode())


def main():
    print(f"Shadow viewer → http://localhost:{PORT}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
