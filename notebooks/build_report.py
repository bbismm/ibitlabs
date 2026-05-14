#!/usr/bin/env python3
# Generate report.html — three-way (live / shadow / paper) analysis.
# v2: hero KPI cards, sticky TOC, unified plotly theme, colored PnL cells.
import json, sqlite3, urllib.request, time as _time, subprocess, sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

# tz_format lives in scripts/; ensure importable when run from any cwd.
sys.path.insert(0, str(Path.home() / "ibitlabs" / "scripts"))
from tz_format import format_html_time  # noqa: E402

# ============================================================================
# constants
# ============================================================================
ROOT      = Path.home() / "ibitlabs"
NB_DIR    = ROOT / "notebooks"
CACHE_DIR = NB_DIR / ".candles_cache"
CACHE_DIR.mkdir(exist_ok=True)

PUBLIC_MODE = "--public" in sys.argv
if PUBLIC_MODE:
    OUT = ROOT / "web" / "public" / "lab" / "index.html"
    OUT.parent.mkdir(parents=True, exist_ok=True)
else:
    OUT = NB_DIR / "report.html"

DBS = {
    "live":   ROOT / "sol_sniper.db",
    "shadow": ROOT / "sol_sniper_shadow.db",
    "paper":  ROOT / "sol_sniper_eth_paper.db",
}
SYMBOL_MAP   = {"SLP-20DEC30-CDE": "SOL", "ETP-20DEC30-CDE": "ETH"}
STREAM_COLOR = {"live": "#22c55e", "shadow": "#a855f7", "paper": "#0ea5e9"}
STREAMS_ORDER = ["live", "shadow", "paper"]
PRODUCT = {"live": "SOL-USD", "shadow": "SOL-USD", "paper": "ETH-USD"}
INITIAL_CAPITAL = 1000.0
NOW = pd.Timestamp.now(tz="UTC")

# ============================================================================
# plotly theme — unified with page palette
# ============================================================================
pio.templates["ibit"] = go.layout.Template(layout=go.Layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family='ui-monospace, "SF Mono", Menlo, monospace',
              size=12, color="#cbd5e1"),
    xaxis=dict(gridcolor="#1f2937", zerolinecolor="#1f2937", linecolor="#334155",
               tickfont=dict(color="#94a3b8")),
    yaxis=dict(gridcolor="#1f2937", zerolinecolor="#1f2937", linecolor="#334155",
               tickfont=dict(color="#94a3b8")),
    colorway=["#22c55e", "#a855f7", "#0ea5e9", "#f59e0b", "#ef4444", "#8b5cf6"],
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#cbd5e1"),
                bordercolor="#1e293b"),
    margin=dict(t=48, b=40, l=56, r=20),
    title=dict(font=dict(size=13, color="#e2e8f0",
                         family='ui-sans-serif, -apple-system, system-ui, sans-serif')),
    hoverlabel=dict(bgcolor="#0f172a", bordercolor="#334155",
                    font=dict(color="#e2e8f0",
                              family="ui-monospace, Menlo, monospace", size=11)),
))
pio.templates.default = "ibit"


# ============================================================================
# data loaders
# ============================================================================
def load_raw(name, db_path):
    con = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM trade_log", con)
    con.close()
    df["dt"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df["asset"] = df["symbol"].map(SYMBOL_MAP).fillna(df["symbol"])
    df["stream"] = name
    return df[df["strategy_version"] == "hybrid_v5.1"].copy()


def build_round_trips(raw):
    trips = []
    for (stream, direction), sub in raw.groupby(["stream", "direction"]):
        sub = sub.sort_values("id").reset_index(drop=True)
        open_stack = []
        for r in sub.itertuples():
            if pd.isna(r.exit_price):
                open_stack.append(r)
                continue
            if not open_stack:
                continue
            o = open_stack.pop()
            c = r
            trips.append({
                "stream": stream, "asset": c.asset, "direction": direction,
                "entry_dt": o.dt, "exit_dt": c.dt,
                "entry_price": c.entry_price, "exit_price": c.exit_price,
                "qty": c.quantity,
                "pnl_gross": c.pnl or 0,
                # Sum BOTH sides of the round trip — the open-side row also has
                # its own entry fee + funding that we shouldn't ignore.
                "fees":    (o.fees or 0)    + (c.fees or 0),
                "funding": (o.funding or 0) + (c.funding or 0),
                "exit_reason": c.exit_reason or "unknown",
                "regime": c.regime if c.regime else "unlabeled",
                "trigger_rule": c.trigger_rule,
                "mfe": c.mfe, "mae": c.mae,
            })
    t = pd.DataFrame(trips)
    if t.empty:
        return t
    t["pnl_net"] = t["pnl_gross"] - t["fees"] + t["funding"]
    sign = np.where(t["direction"] == "short", -1, 1)
    t["return_pct"] = (t["exit_price"] / t["entry_price"] - 1) * sign * 100
    t["duration_h"] = (t["exit_dt"] - t["entry_dt"]).dt.total_seconds() / 3600
    t["win"] = t["pnl_net"] > 0
    return t.sort_values("exit_dt").reset_index(drop=True)


def fetch_candles(product, start, end, granularity=3600):
    key = f"{product}_{granularity}_{start.strftime('%Y%m%d%H')}_{end.strftime('%Y%m%d%H')}.csv"
    cache_file = CACHE_DIR / key
    if cache_file.exists():
        df = pd.read_csv(cache_file, parse_dates=["t"])
        df["t"] = pd.to_datetime(df["t"], utc=True)
        return df
    rows, cur, step = [], start, pd.Timedelta(hours=250)
    while cur < end:
        chunk_end = min(cur + step, end)
        url = (f"https://api.exchange.coinbase.com/products/{product}/candles"
               f"?start={cur.isoformat()}&end={chunk_end.isoformat()}"
               f"&granularity={granularity}")
        req = urllib.request.Request(url, headers={"User-Agent": "ibitlabs-report/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows.extend(json.loads(resp.read()))
        cur = chunk_end
        _time.sleep(0.3)
    df = pd.DataFrame(rows, columns=["t", "low", "high", "open", "close", "volume"])
    df["t"] = pd.to_datetime(df["t"], unit="s", utc=True)
    df = df.drop_duplicates(subset=["t"]).sort_values("t").reset_index(drop=True)
    df.to_csv(cache_file, index=False)
    return df


def kpis(df, label):
    n = len(df)
    if n == 0:
        return {"stream": label, "trades": 0, "win_rate_%": None, "PF": None,
                "total_pnl_$": 0, "total_ret_%": 0, "mean_$": None, "median_$": None,
                "best_$": None, "worst_$": None, "stdev_$": None, "max_dd_%": None,
                "avg_dur_h": None, "first": "—", "last": "—"}
    pnl = df["pnl_net"]
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    pf = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else np.inf
    eq = INITIAL_CAPITAL + pnl.cumsum()
    peak = eq.cummax()
    dd_pct = ((eq - peak) / peak * 100).min()
    return {
        "stream": label, "trades": n,
        "win_rate_%": round((pnl > 0).mean() * 100, 1),
        "PF": round(pf, 2) if np.isfinite(pf) else float("inf"),
        "total_pnl_$": round(pnl.sum(), 2),
        "total_ret_%": round(pnl.sum() / INITIAL_CAPITAL * 100, 2),
        "mean_$": round(pnl.mean(), 2),
        "median_$": round(pnl.median(), 2),
        "best_$": round(pnl.max(), 2),
        "worst_$": round(pnl.min(), 2),
        "stdev_$": round(pnl.std(), 2),
        "max_dd_%": round(dd_pct, 2),
        "avg_dur_h": round(df["duration_h"].mean(), 2),
        "first": df["exit_dt"].min().strftime("%Y-%m-%d %H:%M"),
        "last":  df["exit_dt"].max().strftime("%Y-%m-%d %H:%M"),
    }


# ============================================================================
# UI helpers
# ============================================================================
def sparkline_svg(values, color, width=240, height=44):
    if len(values) < 2:
        return ""
    vmin, vmax = min(values), max(values)
    rng = vmax - vmin or 1
    pts = []
    for i, v in enumerate(values):
        x = (i / (len(values) - 1)) * width
        y = (height - 4) - ((v - vmin) / rng) * (height - 6) + 1
        pts.append(f"{x:.1f},{y:.1f}")
    line = "M " + " L ".join(pts)
    area = f"M 0,{height} L " + " L ".join(pts) + f" L {width},{height} Z"
    # Mark the final point
    fx, fy = pts[-1].split(",")
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
        f'<path d="{area}" fill="{color}" opacity="0.18"/>'
        f'<path d="{line}" fill="none" stroke="{color}" stroke-width="1.5" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{fx}" cy="{fy}" r="2.5" fill="{color}"/>'
        '</svg>'
    )


def hero_card(stream, trips_df, raw_df, color, product):
    n = len(trips_df)
    if n == 0:
        equity = INITIAL_CAPITAL
        delta_pct = 0.0
        spark_html = ""
        last_close = "—"
    else:
        equity = INITIAL_CAPITAL + trips_df["pnl_net"].sum()
        delta_pct = (equity / INITIAL_CAPITAL - 1) * 100
        eq_series = [INITIAL_CAPITAL] + (INITIAL_CAPITAL + trips_df["pnl_net"].cumsum()).tolist()
        spark_html = sparkline_svg(eq_series, color)
        last_close = trips_df["exit_dt"].max().strftime("%m-%d %H:%M")

    n_long_open  = (((raw_df["direction"] == "long")  & raw_df["exit_price"].isna()).sum()
                    - ((raw_df["direction"] == "long")  & raw_df["exit_price"].notna()).sum())
    n_short_open = (((raw_df["direction"] == "short") & raw_df["exit_price"].isna()).sum()
                    - ((raw_df["direction"] == "short") & raw_df["exit_price"].notna()).sum())
    badges = []
    if n_long_open > 0:
        badges.append('<span class="badge badge-open">⚡ OPEN long</span>')
    if n_short_open > 0:
        badges.append('<span class="badge badge-open">⚡ OPEN short</span>')
    if not badges:
        badges.append('<span class="badge badge-flat">flat</span>')

    delta_class = "up" if delta_pct >= 0 else "down"
    delta_sign  = "+" if delta_pct >= 0 else ""

    return (
        f'<div class="hero-card" style="--accent: {color}">'
        f'  <div class="hero-top">'
        f'    <span class="stream-name">{stream}</span>'
        f'    <span class="product">{product}</span>'
        f'  </div>'
        f'  <div class="hero-equity">${equity:,.2f}</div>'
        f'  <div class="hero-delta {delta_class}">'
        f'    {delta_sign}{delta_pct:.2f}% <span class="dim">vs $1,000</span>'
        f'  </div>'
        f'  <div class="hero-spark">{spark_html}</div>'
        f'  <div class="hero-meta">'
        f'    <span>{n} closed trades · last {last_close}</span>'
        f'    <span class="badge-row">{" ".join(badges)}</span>'
        f'  </div>'
        f'</div>'
    )


def fmt_cell(v):
    if pd.isna(v) or v is None:
        return '<td class="dim">—</td>'
    if isinstance(v, (int, np.integer)):
        return f'<td class="num">{v:,}</td>'
    if isinstance(v, (float, np.floating)):
        if not np.isfinite(v):
            return '<td class="dim">∞</td>'
        return f'<td class="num">{v:,.2f}</td>'
    return f'<td>{v}</td>'


def fmt_pnl_cell(v, vmax):
    if pd.isna(v) or v is None:
        return '<td class="dim">—</td>'
    if not isinstance(v, (int, float, np.number)) or not np.isfinite(v):
        return f'<td class="num">{v}</td>'
    if v == 0:
        return '<td class="num">0.00</td>'
    a = min(abs(v) / (vmax or 1), 1.0) * 0.5
    color = f"rgba(34,197,94,{a:.2f})" if v > 0 else f"rgba(239,68,68,{a:.2f})"
    sign = "+" if v > 0 else ""
    return f'<td class="num pnl" style="background:{color}">{sign}{v:,.2f}</td>'


def colored_df_html(df, pnl_cols=(), index=False, index_name=None):
    pnl_cols = tuple(pnl_cols)
    vmax = {c: (df[c].abs().max() if c in df.columns else 0) or 1 for c in pnl_cols}
    out = ['<table class="data data-colored">']
    out.append("<thead><tr>")
    if index:
        out.append(f"<th>{index_name or ''}</th>")
    for c in df.columns:
        out.append(f"<th>{c}</th>")
    out.append("</tr></thead><tbody>")
    for idx, row in df.iterrows():
        out.append("<tr>")
        if index:
            label = idx if not isinstance(idx, tuple) else " · ".join(str(x) for x in idx)
            out.append(f'<td class="idx">{label}</td>')
        for c in df.columns:
            v = row[c]
            if c in pnl_cols:
                out.append(fmt_pnl_cell(v, vmax.get(c, 1)))
            else:
                out.append(fmt_cell(v))
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def fig_html(fig, div_id):
    return fig.to_html(include_plotlyjs=False, full_html=False, div_id=div_id,
                       config={"displaylogo": False, "responsive": True,
                               "modeBarButtonsToRemove": ["lasso2d", "select2d"]})


# ============================================================================
# data prep
# ============================================================================
print("loading DBs ...")
raw = {k: load_raw(k, v) for k, v in DBS.items()}
trips_per_stream = {k: build_round_trips(df) for k, df in raw.items()}
trades = pd.concat([t for t in trips_per_stream.values() if not t.empty],
                   ignore_index=True)
kpi_df = pd.DataFrame([kpis(trips_per_stream[s], s) for s in STREAMS_ORDER]).set_index("stream")

print("fetching candles ...")
PRICE = {}
for s in STREAMS_ORDER:
    df = trips_per_stream[s]
    raw_df = raw[s]
    times = list(df["entry_dt"].dropna()) + list(df["exit_dt"].dropna())
    times.extend(raw_df[raw_df["exit_price"].isna()]["dt"].tolist())
    if not times:
        print(f"  {s:7s}: no trades, skip")
        continue
    start = (min(times) - pd.Timedelta(hours=2)).floor("h")
    end   = (max(times) + pd.Timedelta(hours=2)).ceil("h")
    if (raw_df["exit_price"].isna()).any():
        end = max(end, NOW.ceil("h"))
    try:
        PRICE[s] = fetch_candles(PRODUCT[s], start, end)
        print(f"  {s:7s}: {len(PRICE[s])} {PRODUCT[s]} candles")
    except Exception as e:
        print(f"  {s:7s}: fetch FAILED ({e})")


# ============================================================================
# figures
# ============================================================================
print("building figures ...")


def finish(fig, height=420, title=None):
    fig.update_layout(
        height=height, title=title,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    return fig


# ---- equity
fig_equity = go.Figure()
for s in STREAMS_ORDER:
    df = trips_per_stream[s]
    if df.empty:
        continue
    eq = INITIAL_CAPITAL + df["pnl_net"].cumsum()
    x = pd.concat([pd.Series([df["exit_dt"].iloc[0] - pd.Timedelta(minutes=1)]),
                   df["exit_dt"]]).reset_index(drop=True)
    y = pd.concat([pd.Series([INITIAL_CAPITAL]), eq]).reset_index(drop=True)
    fig_equity.add_trace(go.Scatter(
        x=x, y=y, mode="lines+markers", name=f"{s} (n={len(df)})",
        line=dict(color=STREAM_COLOR[s], width=2),
        marker=dict(size=5, color=STREAM_COLOR[s]),
        hovertemplate="%{x|%Y-%m-%d %H:%M}<br>equity=$%{y:.2f}<extra>"+s+"</extra>",
    ))
fig_equity.add_hline(y=INITIAL_CAPITAL, line_dash="dot", line_color="#475569",
                     annotation_text="$1,000 seed",
                     annotation_font=dict(color="#94a3b8"))
finish(fig_equity, 420, "Equity · normalized to $1,000")
fig_equity.update_yaxes(title="Account equity ($)")


# ---- trades on price
fig_price = make_subplots(
    rows=len(STREAMS_ORDER), cols=1, shared_xaxes=False,
    subplot_titles=[f"{s} on {PRODUCT[s]} — {len(trips_per_stream[s])} closed trades"
                    for s in STREAMS_ORDER],
    vertical_spacing=0.08,
)
for i, s in enumerate(STREAMS_ORDER, start=1):
    if s not in PRICE:
        continue
    p = PRICE[s]
    df = trips_per_stream[s]
    raw_df = raw[s]
    fig_price.add_trace(go.Scatter(
        x=p["t"], y=p["close"], mode="lines",
        line=dict(color="#64748b", width=1), showlegend=False,
        hovertemplate="%{x|%Y-%m-%d %H:%M}<br>$%{y:.2f}<extra></extra>",
    ), row=i, col=1)
    if not df.empty:
        win_color = np.where(df["pnl_net"] > 0, "#22c55e", "#ef4444")
        for r in df.itertuples():
            c = "#22c55e" if r.pnl_net > 0 else "#ef4444"
            fig_price.add_trace(go.Scatter(
                x=[r.entry_dt, r.exit_dt], y=[r.entry_price, r.exit_price],
                mode="lines", line=dict(color=c, width=1.5, dash="dot"),
                showlegend=False, hoverinfo="skip",
            ), row=i, col=1)
        fig_price.add_trace(go.Scatter(
            x=df["entry_dt"], y=df["entry_price"], mode="markers",
            marker=dict(symbol="circle-open", size=12, color=win_color,
                        line=dict(width=2.5)),
            name="entry", showlegend=(i == 1),
            text=[f"<b>entry</b> {r.direction}<br>{r.exit_reason} | {r.pnl_net:+.2f}$ "
                  f"| {r.duration_h:.1f}h | {r.regime}"
                  for r in df.itertuples()],
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>$%{y:.4f}<br>%{text}<extra></extra>",
        ), row=i, col=1)
        fig_price.add_trace(go.Scatter(
            x=df["exit_dt"], y=df["exit_price"], mode="markers",
            marker=dict(
                symbol=np.where(df["direction"] == "long", "triangle-up", "triangle-down"),
                size=13, color=win_color, line=dict(color="#0f172a", width=0.5),
            ),
            name="exit", showlegend=(i == 1),
            text=[f"<b>exit</b> {r.direction}<br>{r.exit_reason} | {r.pnl_net:+.2f}$ "
                  f"| {r.duration_h:.1f}h | {r.regime}"
                  for r in df.itertuples()],
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>$%{y:.4f}<br>%{text}<extra></extra>",
        ), row=i, col=1)
    if not PUBLIC_MODE:
        # Snapshot pages would render stale open-positions; only show on the
        # local dashboard. The /signals page is the live-truth source publicly.
        for direction in ["long", "short"]:
            n_open  = ((raw_df["direction"] == direction) & raw_df["exit_price"].isna()).sum()
            n_close = ((raw_df["direction"] == direction) & raw_df["exit_price"].notna()).sum()
            if n_open <= n_close:
                continue
            o = (raw_df[(raw_df["direction"] == direction) & raw_df["exit_price"].isna()]
                      .sort_values("id").tail(1).iloc[0])
            fig_price.add_trace(go.Scatter(
                x=[o["dt"], NOW], y=[o["entry_price"], p["close"].iloc[-1]],
                mode="lines+markers",
                marker=dict(symbol=["circle-open", "x"], size=[12, 14],
                            color="#f59e0b", line=dict(width=2)),
                line=dict(color="#f59e0b", width=2, dash="dash"),
                name=f"OPEN {direction}",
                text=[f"open {direction} @ ${o['entry_price']:.4f}",
                      f"NOW @ ${p['close'].iloc[-1]:.4f}"],
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>$%{y:.4f}<br>%{text}<extra></extra>",
            ), row=i, col=1)
finish(fig_price, 380 * len(STREAMS_ORDER),
       "Trades on price · Coinbase 1h close")
fig_price.update_yaxes(title="Price ($)")
# Style subplot titles
for ann in fig_price.layout.annotations:
    ann.font.color = "#94a3b8"
    ann.font.size = 11


# ---- per-trade timeline
fig_timeline = make_subplots(
    rows=len(STREAMS_ORDER), cols=1, shared_xaxes=True,
    subplot_titles=[f"{s} — {trips_per_stream[s].shape[0]} trades"
                    for s in STREAMS_ORDER],
    vertical_spacing=0.06,
)
for i, s in enumerate(STREAMS_ORDER, start=1):
    df = trips_per_stream[s]
    if df.empty:
        continue
    colors = np.where(df["pnl_net"] > 0, "#22c55e", "#ef4444")
    syms   = np.where(df["direction"] == "long", "triangle-up", "triangle-down")
    fig_timeline.add_trace(go.Scatter(
        x=df["exit_dt"], y=df["pnl_net"], mode="markers",
        marker=dict(color=colors, size=10, symbol=syms,
                    line=dict(color="#0f172a", width=0.5)),
        text=[f"{r.direction} | {r.exit_reason} | {r.regime} | {r.duration_h:.1f}h"
              for r in df.itertuples()],
        hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>PnL=$%{y:.2f}<br>%{text}<extra></extra>",
        showlegend=False,
    ), row=i, col=1)
    fig_timeline.add_hline(y=0, line_color="#475569", line_dash="dot", row=i, col=1)
finish(fig_timeline, 240 * len(STREAMS_ORDER), "Per-trade PnL · timeline")
fig_timeline.update_yaxes(title="PnL ($)")
for ann in fig_timeline.layout.annotations:
    ann.font.color = "#94a3b8"
    ann.font.size = 11


# ---- PnL distribution
fig_dist = go.Figure()
for s in STREAMS_ORDER:
    df = trips_per_stream[s]
    if df.empty:
        continue
    fig_dist.add_trace(go.Histogram(
        x=df["pnl_net"], name=s, opacity=0.65,
        marker_color=STREAM_COLOR[s], nbinsx=30,
    ))
fig_dist.add_vline(x=0, line_dash="dot", line_color="#475569")
fig_dist.update_layout(barmode="overlay")
finish(fig_dist, 360, "Per-trade PnL distribution")
fig_dist.update_xaxes(title="PnL ($)")
fig_dist.update_yaxes(title="# trades")


# ---- exit reason
er = (trades.groupby(["stream", "exit_reason"])
            .agg(n=("pnl_net", "count"), pnl=("pnl_net", "sum"), winrate=("win", "mean"))
            .reset_index())
er["winrate"] = (er["winrate"] * 100).round(1)
er["pnl"] = er["pnl"].round(2)
fig_exit = px.bar(er, x="exit_reason", y="n", color="stream", barmode="group",
                  color_discrete_map=STREAM_COLOR,
                  hover_data={"pnl": ":.2f", "winrate": ":.1f"})
finish(fig_exit, 360, "Closed trades per exit reason")
fig_exit.update_xaxes(title="Exit reason")
fig_exit.update_yaxes(title="# trades")
exit_pivot = er.pivot(index="exit_reason", columns="stream", values="pnl").fillna(0).round(2)
exit_pivot["TOTAL"] = exit_pivot.sum(axis=1)
exit_pivot = exit_pivot.sort_values("TOTAL", ascending=False).reset_index()


# ---- direction
dr = (trades.groupby(["stream", "direction"])
              .agg(n=("pnl_net", "count"), pnl_total=("pnl_net", "sum"),
                   winrate=("win", "mean"), avg=("pnl_net", "mean"))
              .reset_index())
dr["winrate_%"] = (dr["winrate"] * 100).round(1)
dr["pnl_total"] = dr["pnl_total"].round(2)
dr["avg"] = dr["avg"].round(2)
fig_direction = px.bar(dr, x="stream", y="pnl_total", color="direction", barmode="group",
                       color_discrete_map={"long": "#22c55e", "short": "#ef4444"},
                       text=dr["pnl_total"].astype(str))
finish(fig_direction, 320, "Net PnL by direction")
fig_direction.update_yaxes(title="Net PnL ($)")


# ---- regime
rg = (trades.groupby(["stream", "regime"])
              .agg(n=("pnl_net", "count"), pnl=("pnl_net", "sum"),
                   winrate=("win", "mean"), avg=("pnl_net", "mean"))
              .reset_index())
rg["winrate_%"] = (rg["winrate"] * 100).round(1)
rg["pnl"] = rg["pnl"].round(2)
rg["avg"] = rg["avg"].round(2)
dist = (trades.groupby(["stream", "regime"]).size()
            / trades.groupby("stream").size()).mul(100).round(1).reset_index(name="share_%")
fig_regime = make_subplots(rows=1, cols=2,
                           subplot_titles=("Trade share by regime (%)",
                                           "Win rate by regime (%) · label = n trades"))
for s in STREAMS_ORDER:
    sub = dist[dist["stream"] == s]
    if not sub.empty:
        fig_regime.add_trace(go.Bar(x=sub["regime"], y=sub["share_%"], name=s,
                                    marker_color=STREAM_COLOR[s], legendgroup=s),
                             row=1, col=1)
        sub2 = rg[rg["stream"] == s]
        fig_regime.add_trace(go.Bar(x=sub2["regime"], y=sub2["winrate_%"], name=s,
                                    marker_color=STREAM_COLOR[s], legendgroup=s,
                                    showlegend=False,
                                    text=sub2["n"].astype(str),
                                    textposition="outside",
                                    textfont=dict(color="#94a3b8")),
                             row=1, col=2)
fig_regime.update_layout(barmode="group")
finish(fig_regime, 400)
for ann in fig_regime.layout.annotations:
    ann.font.color = "#94a3b8"
    ann.font.size = 11


# ---- MFE/MAE
ml = trades.dropna(subset=["mfe", "mae"]).copy()
fig_mfe = None
if not ml.empty:
    ml["mfe_%"] = ml["mfe"] * 100
    ml["mae_%"] = ml["mae"] * 100
    fig_mfe = px.scatter(
        ml, x="mae_%", y="mfe_%", color="stream", symbol="direction",
        color_discrete_map=STREAM_COLOR,
        size=ml["pnl_net"].abs() + 1, size_max=18,
        hover_data={"pnl_net": ":.2f", "exit_reason": True, "regime": True,
                    "duration_h": ":.1f"},
    )
    fig_mfe.add_hline(y=0, line_color="#475569", line_dash="dot")
    fig_mfe.add_vline(x=0, line_color="#475569", line_dash="dot")
    finish(fig_mfe, 480, "MFE vs MAE (% return) · bubble = |PnL|")
    fig_mfe.update_xaxes(title="MAE (% — adverse)")
    fig_mfe.update_yaxes(title="MFE (% — favorable)")


# ---- duration vs PnL
fig_dur = px.scatter(
    trades, x="duration_h", y="pnl_net", color="stream", symbol="direction",
    color_discrete_map=STREAM_COLOR,
    hover_data={"exit_reason": True, "regime": True,
                "entry_dt": "|%Y-%m-%d %H:%M"},
)
fig_dur.add_hline(y=0, line_color="#475569", line_dash="dot")
finish(fig_dur, 420, "Trade duration vs PnL net")
fig_dur.update_xaxes(title="Duration (hours)")
fig_dur.update_yaxes(title="PnL net ($)")


# ---- recent activity
cutoff = NOW - pd.Timedelta(days=14)
recent = trades[trades["exit_dt"] >= cutoff].sort_values("exit_dt", ascending=False).copy()
recent["exit_dt"]  = recent["exit_dt"].dt.strftime("%Y-%m-%d %H:%M")
recent["entry_dt"] = recent["entry_dt"].dt.strftime("%Y-%m-%d %H:%M")
recent = recent[["stream", "asset", "direction", "entry_dt", "exit_dt", "duration_h",
                 "entry_price", "exit_price", "return_pct", "pnl_net",
                 "exit_reason", "regime"]].round({"duration_h": 2, "return_pct": 2,
                                                  "pnl_net": 2, "entry_price": 4,
                                                  "exit_price": 4})


# ============================================================================
# HTML emit
# ============================================================================
print("rendering HTML ...")

SECTIONS = [
    ("kpi",       "Headline KPIs"),
    ("equity",    "Equity curves"),
    ("price",     "Trades on price"),
    ("timeline",  "PnL timeline"),
    ("dist",      "PnL distribution"),
    ("exit",      "Exit reasons"),
    ("direction", "Long vs short"),
    ("regime",    "Regime"),
    ("mfe",       "MFE × MAE"),
    ("duration",  "Duration vs PnL"),
    ("recent",    "Recent activity"),
]

# Build the hero card row
hero_html = "\n".join(
    hero_card(s, trips_per_stream[s], raw[s], STREAM_COLOR[s], PRODUCT[s])
    for s in STREAMS_ORDER
)

# TOC
toc_items = "\n".join(
    f'<li><a href="#{sid}"><span class="tn">{i+1:02d}</span>{label}</a></li>'
    for i, (sid, label) in enumerate(SECTIONS)
)

# KPI table — drop stringified first/last columns to keep numeric for color
kpi_for_table = kpi_df.copy().reset_index()
kpi_pnl_cols = ["total_pnl_$", "total_ret_%", "mean_$", "median_$",
                "best_$", "worst_$", "max_dd_%"]

# Exit pivot — color all numeric columns
ep_cols = [c for c in exit_pivot.columns if c != "exit_reason"]

# Direction breakdown — pnl_total + avg
dr_for_table = dr[["stream", "direction", "n", "winrate_%", "pnl_total", "avg"]]

# Regime breakdown
rg_for_table = rg[["stream", "regime", "n", "winrate_%", "pnl", "avg"]]

CSS = """
:root {
  --bg: #0a0e1a; --panel: #131826; --panel-2: #1a2236;
  --text: #e2e8f0; --muted: #94a3b8; --dim: #64748b;
  --green: #22c55e; --purple: #a855f7; --blue: #0ea5e9;
  --warn: #f59e0b; --danger: #ef4444;
  --border: #1e293b; --border-2: #243049;
  --tocw: 220px;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--bg); color: var(--text);
  font-family: ui-sans-serif, -apple-system, "SF Pro", "Inter", system-ui, sans-serif;
  font-size: 14px; line-height: 1.55; -webkit-font-smoothing: antialiased; }

/* === Site nav === */
.site-nav { display: flex; justify-content: space-between; align-items: center;
  padding: 10px 36px 10px var(--tocw); border-bottom: 1px solid var(--border);
  background: #0d1220; font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 12px; }
.site-nav .brand { color: var(--muted); text-transform: uppercase;
  letter-spacing: 0.08em; font-size: 11px; }
.site-nav .brand b { color: var(--text); font-weight: 600; letter-spacing: 0; }
.site-nav .brand em { color: var(--green); font-style: normal; font-weight: 600;
  letter-spacing: 0; margin-left: 4px; }
.site-nav .links { display: flex; gap: 20px; }
.site-nav .links a { color: var(--muted); }
.site-nav .links a:hover { color: var(--text); }
.site-nav .links a.active { color: var(--green); }

/* === Top header === */
header.top { padding: 22px 36px 18px var(--tocw); border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, #131826 0%, #0a0e1a 100%); }
header.top h1 { margin: 0; font-size: 22px; font-weight: 600; letter-spacing: -0.01em; }
header.top .mission { color: var(--green); font-size: 13.5px; margin-top: 6px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace; letter-spacing: 0.01em; }
header.top .sub { color: var(--muted); margin-top: 3px; font-size: 12.5px;
  font-family: ui-monospace, Menlo, monospace; }
header.top .meta { color: var(--dim); margin-top: 2px; font-size: 11.5px;
  font-family: ui-monospace, Menlo, monospace; }

/* === Sticky TOC === */
.toc { position: fixed; top: 0; left: 0; bottom: 0; width: var(--tocw);
  padding: 22px 16px; background: #0d1220; border-right: 1px solid var(--border);
  overflow-y: auto; z-index: 50; }
.toc .brand { font-size: 12px; color: var(--muted); letter-spacing: 0.08em;
  text-transform: uppercase; font-family: ui-monospace, Menlo, monospace;
  padding-bottom: 14px; border-bottom: 1px solid var(--border); margin-bottom: 14px; }
.toc .brand b { color: var(--green); font-weight: 600; letter-spacing: 0; }
.toc ol { list-style: none; margin: 0; padding: 0; counter-reset: tn; }
.toc ol li { margin: 0; }
.toc ol li a { display: flex; align-items: baseline; gap: 8px;
  color: var(--muted); padding: 6px 10px; font-size: 12.5px;
  border-left: 2px solid transparent; border-radius: 0 4px 4px 0;
  transition: all 0.12s ease; }
.toc ol li a .tn { font-family: ui-monospace, Menlo, monospace; color: var(--dim);
  font-size: 10.5px; }
.toc ol li a:hover { color: var(--text); background: rgba(255,255,255,0.025); }
.toc ol li a.active { color: var(--green); border-left-color: var(--green);
  background: rgba(34,197,94,0.06); }
.toc ol li a.active .tn { color: var(--green); }
.toc-foot { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--border);
  font-size: 11px; color: var(--dim); font-family: ui-monospace, Menlo, monospace; }
.toc-foot a { color: var(--muted); }
.toc-foot a:hover { color: var(--text); }

/* === Main === */
main { padding: 24px 36px 80px var(--tocw); max-width: 1480px; margin: 0; }
main > div.inner { padding-left: 28px; }

/* === Hero cards === */
.hero-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;
  margin: 8px 0 24px; padding: 0; }
.hero-card { position: relative; background: var(--panel);
  border: 1px solid var(--border); border-radius: 8px; padding: 16px 18px;
  overflow: hidden; }
.hero-card::before { content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--accent); }
.hero-top { display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 8px; }
.stream-name { font-size: 11px; text-transform: uppercase; letter-spacing: 0.12em;
  color: var(--accent); font-weight: 600;
  font-family: ui-monospace, Menlo, monospace; }
.product { font-size: 10.5px; color: var(--dim);
  font-family: ui-monospace, Menlo, monospace; }
.hero-equity { font-size: 28px; font-weight: 600;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  color: var(--text); letter-spacing: -0.01em; }
.hero-delta { font-size: 12.5px; margin-top: 2px;
  font-family: ui-monospace, Menlo, monospace; }
.hero-delta.up   { color: var(--green); }
.hero-delta.down { color: var(--danger); }
.hero-delta .dim { color: var(--dim); font-weight: 400; }
.hero-spark { margin: 10px 0 8px; }
.hero-spark svg.spark { width: 100%; height: 44px; display: block; }
.hero-meta { display: flex; justify-content: space-between; align-items: center;
  font-size: 11.5px; color: var(--muted);
  font-family: ui-monospace, Menlo, monospace;
  padding-top: 10px; border-top: 1px solid var(--border); margin-top: 6px; }
.badge-row { display: inline-flex; gap: 6px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 3px;
  font-size: 10.5px; font-family: ui-monospace, Menlo, monospace;
  letter-spacing: 0.04em; }
.badge-open { background: rgba(245,158,11,0.15); color: var(--warn);
  border: 1px solid rgba(245,158,11,0.35); }
.badge-flat { background: rgba(100,116,139,0.15); color: var(--dim);
  border: 1px solid var(--border-2); }

/* === Sections === */
section { margin: 36px 0; scroll-margin-top: 16px; }
section h2 { font-size: 16.5px; font-weight: 600; margin: 0 0 4px;
  color: var(--text); padding-bottom: 9px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: baseline; gap: 10px; }
section h2 .sn { color: var(--green); font-family: ui-monospace, Menlo, monospace;
  font-size: 13px; font-weight: 500; opacity: 0.9; }
section h2 .tag { font-size: 11.5px; font-weight: 400; color: var(--muted);
  font-family: ui-monospace, Menlo, monospace; margin-left: auto; }
section .lede { color: var(--muted); margin: 8px 0 14px; font-size: 13px;
  max-width: 880px; }

/* === Plot container === */
.plot { background: var(--panel); border-radius: 8px; padding: 4px 8px 8px;
  border: 1px solid var(--border); }

/* === Tables === */
table.data { border-collapse: collapse; margin: 8px 0; width: 100%;
  font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 12px;
  background: var(--panel); border-radius: 8px; overflow: hidden;
  border: 1px solid var(--border); }
table.data th, table.data td { padding: 7px 12px;
  border-bottom: 1px solid var(--border); text-align: right; }
table.data th { background: var(--panel-2); color: var(--muted);
  font-weight: 500; text-align: right; font-size: 10.5px;
  text-transform: uppercase; letter-spacing: 0.05em; }
table.data th:first-child, table.data td:first-child {
  text-align: left; color: var(--text); font-weight: 500; }
table.data td.idx { color: var(--text); font-weight: 500; }
table.data td.num { color: var(--text); font-variant-numeric: tabular-nums; }
table.data td.dim { color: var(--dim); }
table.data td.pnl { font-weight: 500; }
table.data tr:hover td { background: rgba(255,255,255,0.025); }
table.data tr:hover td.pnl { filter: brightness(1.25); }
table.data tr:last-child td { border-bottom: none; }
table.data.data-colored td.pnl[style*="background"] { color: var(--text); }

/* === Footer === */
footer { color: var(--dim); padding: 22px 36px 22px var(--tocw); font-size: 11.5px;
  border-top: 1px solid var(--border); font-family: ui-monospace, Menlo, monospace; }
footer code { background: var(--panel); padding: 1.5px 6px; border-radius: 3px;
  color: var(--muted); }

a { color: var(--green); text-decoration: none; }
a:hover { text-decoration: underline; }

/* === Responsive === */
@media (max-width: 900px) {
  :root { --tocw: 0px; }
  .toc { display: none; }
  header.top, main, footer { padding-left: 16px; padding-right: 16px; }
  .site-nav { padding-left: 16px; padding-right: 16px; flex-wrap: wrap; gap: 8px; }
  .site-nav .links { gap: 12px; flex-wrap: wrap; }
  .hero-row { grid-template-columns: 1fr; }
}
"""

JS = """
(function() {
  const sections = document.querySelectorAll('section[id]');
  const links = document.querySelectorAll('.toc ol li a');
  if (!sections.length || !links.length) return;
  const byId = {};
  links.forEach(a => { byId[a.getAttribute('href').slice(1)] = a; });
  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        links.forEach(a => a.classList.remove('active'));
        const a = byId[e.target.id];
        if (a) a.classList.add('active');
      }
    });
  }, { rootMargin: '-25% 0px -65% 0px', threshold: 0 });
  sections.forEach(s => obs.observe(s));
})();
"""

if PUBLIC_MODE:
    page_title  = "iBitLabs · The Lab"
    page_h1     = "The Lab"
    description = ("The kitchen of the $1,000 → $10,000 automated trading experiment. "
                   "Live, shadow, and paper streams · every trade in the open.")
    mission_html = ('<div class="mission">We run this in public. '
                    '$1,000 → $10,000 · every trade, every dollar.</div>')
    meta_line   = (f'Snapshot {format_html_time(NOW.to_pydatetime(), mode="local")} · regenerated daily · '
                   f'live state at <a href="/signals">/signals</a>')
    site_nav_html = (
        '<nav class="site-nav">'
        '<a href="/" class="brand"><b>iBitLabs</b> <em>Lab</em></a>'
        '<div class="links">'
        '<a href="/signals">Signals</a>'
        '<a href="/lab" class="active">Lab</a>'
        '<a href="/office">Office</a>'
        '<a href="/writing">Writing</a>'
        '<a href="/contributors">Contributors</a>'
        '</div>'
        '</nav>'
    )
    site_footer_html = (
        '<style>.site-footer{text-align:center;padding:2.5rem 1.5rem;border-top:1px solid rgba(139,92,246,0.18);color:#9898b0;font-size:0.85rem;font-family:"Inter",-apple-system,sans-serif}'
        '.site-footer p{margin:0.4rem 0}'
        '.site-footer a{color:#a8a8be;text-decoration:none;transition:color 0.2s}'
        '.site-footer a:hover{color:#a78bfa}'
        '.site-footer strong{color:#d0d0dc;font-weight:600}'
        '.site-footer .sf-row{font-size:0.78rem}'
        '.site-footer .sf-fine{font-size:0.72rem;max-width:600px;margin:1rem auto 0;line-height:1.6}</style>'
        '<footer class="site-footer">'
        '<p>iBitLabs &mdash; A 0-to-N Startup, In Public &mdash; by <strong>Bonnybb</strong></p>'
        '<p class="sf-row"><a href="/signals">Signals</a> &middot; <a href="/lab">Lab</a> &middot; <a href="/office">Office</a> &middot; <a href="/writing">Writing</a> &middot; <a href="/contributors">Contributors</a></p>'
        '<p class="sf-row"><a href="https://twitter.com/BonnyOuyang" target="_blank" rel="noopener">X</a> &middot; <a href="https://www.moltbook.com/u/ibitlabs_agent" target="_blank" rel="noopener">Moltbook</a> &middot; <a href="https://github.com/bbismm/ibitlabs" target="_blank" rel="noopener">GitHub</a> &middot; <a href="https://t.me/ibitlabs_sniper" target="_blank" rel="noopener">Telegram</a></p>'
        f'<p class="sf-fine">Snapshot regenerated daily &middot; $1,000 seed since 2026-04-20 (hybrid_v5.1 go-live). Educational experiment, not financial advice. '
        '<a href="/terms">Terms</a> &middot; <a href="/privacy">Privacy</a></p>'
        '</footer>'
    )
else:
    page_title  = "iBitLabs · live / shadow / paper"
    page_h1     = "Live · Shadow · Paper"
    description = ""
    mission_html = ""
    meta_line = (f'Generated {format_html_time(NOW.to_pydatetime(), mode="local")} · '
                 f'data through {format_html_time(trades["exit_dt"].max().to_pydatetime(), mode="local")}')
    site_nav_html = ""
    site_footer_html = (
        '<footer style="color:var(--dim);padding:22px 36px 22px var(--tocw);font-size:11.5px;'
        'border-top:1px solid var(--border);font-family:ui-monospace,Menlo,monospace">'
        'Source <code>~/ibitlabs/notebooks/build_report.py</code> &middot; '
        'Served by <code>com.ibitlabs.three-way-report</code> on port 8092 &middot; '
        'Auto-regen every 5 min &middot; '
        'Price cache <code>.candles_cache/</code> (rm to refresh).'
        '</footer>'
    )

html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{page_title}</title>
  <meta name="description" content="{description}">
  <meta name="theme-color" content="#0a0e1a">
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
  <script src="/tz.js" defer></script>
  <style>{CSS}</style>
</head>
<body id="top">
  <aside class="toc">
    <div class="brand"><b>iBitLabs</b> · trading</div>
    <ol>{toc_items}</ol>
    <div class="toc-foot">
      <a href="#top">↑ top</a> ·
      generated {format_html_time(NOW.to_pydatetime(), mode='time-local')}
    </div>
  </aside>

  {site_nav_html}

  <header class="top">
    <h1>{page_h1}</h1>
    {mission_html}
    <div class="sub">hybrid_v5.1 · SOL sniper (live + shadow) + ETH sniper (paper)</div>
    <div class="meta">{meta_line}</div>
  </header>

  <main><div class="inner">

    <div class="hero-row">{hero_html}</div>

    <section id="kpi">
      <h2><span class="sn">01</span>Headline KPIs<span class="tag">all v5.1 closed trades</span></h2>
      <div class="lede">PF &gt; 1.0 = profitable. &gt; 1.5 = good. &gt; 2.0 = rare. Max DD is peak-to-trough on the equity curve.</div>
      {colored_df_html(kpi_for_table, pnl_cols=kpi_pnl_cols, index=False)}
    </section>

    <section id="equity">
      <h2><span class="sn">02</span>Equity curves<span class="tag">normalized to $1,000</span></h2>
      <div class="lede">All three streams started with $1k. Flat stretches = bot idle. Slope &gt; 0 = winning.</div>
      <div class="plot">{fig_html(fig_equity, 'fig-equity')}</div>
    </section>

    <section id="price">
      <h2><span class="sn">03</span>Trades on real price<span class="tag">Coinbase 1h close</span></h2>
      <div class="lede">Open circle = entry; ▲/▼ = exit pointing the way the bot was facing. Dotted line = round trip · <span style="color: var(--green)">green</span> = net win, <span style="color: var(--danger)">red</span> = net loss. Amber dashed = currently-open position extending to now.</div>
      <div class="plot">{fig_html(fig_price, 'fig-price')}</div>
    </section>

    <section id="timeline">
      <h2><span class="sn">04</span>Per-trade PnL · timeline</h2>
      <div class="lede">Same trades, plotted as $ outcome vs time. Streaks and clusters jump out faster than on the equity view.</div>
      <div class="plot">{fig_html(fig_timeline, 'fig-timeline')}</div>
    </section>

    <section id="dist">
      <h2><span class="sn">05</span>PnL distribution</h2>
      <div class="lede">Fat right tail with thin left tail = good. Symmetric or fat left = the strategy is sampling noise.</div>
      <div class="plot">{fig_html(fig_dist, 'fig-dist')}</div>
      {colored_df_html(
          trades.groupby("stream")["pnl_net"].describe(percentiles=[.1, .25, .5, .75, .9])[
              ["count", "mean", "std", "min", "10%", "25%", "50%", "75%", "90%", "max"]
          ].round(2).reset_index(),
          pnl_cols=["mean", "min", "10%", "25%", "50%", "75%", "90%", "max"], index=False)}
    </section>

    <section id="exit">
      <h2><span class="sn">06</span>Exit reason × stream</h2>
      <div class="lede">Which exit type is doing the most work — and which is bleeding money?</div>
      <div class="plot">{fig_html(fig_exit, 'fig-exit')}</div>
      {colored_df_html(exit_pivot, pnl_cols=ep_cols, index=False)}
    </section>

    <section id="direction">
      <h2><span class="sn">07</span>Long vs short × stream</h2>
      <div class="lede">Symmetry check. If one side drags the numbers, that's a regime issue rather than a strategy issue.</div>
      <div class="plot">{fig_html(fig_direction, 'fig-direction')}</div>
      {colored_df_html(dr_for_table, pnl_cols=["pnl_total", "avg"], index=False)}
    </section>

    <section id="regime">
      <h2><span class="sn">08</span>Regime × stream<span class="tag">shadow's primary signal</span></h2>
      <div class="lede">Shadow exists to test whether the regime-window classifier improves entry quality. Promotion bar: ≥ 30 entries/bucket with ≥ 15pp WR spread (per 2026-05-06 reset memo). Not there yet — this is the diagnostic.</div>
      <div class="plot">{fig_html(fig_regime, 'fig-regime')}</div>
      {colored_df_html(rg_for_table, pnl_cols=["pnl", "avg"], index=False)}
    </section>

    <section id="mfe">
      <h2><span class="sn">09</span>MFE × MAE<span class="tag">risk profile per trade</span></h2>
      <div class="lede">Upper-left = clean winners with shallow drawdown. Lower-right = trades that touched profit but ended losing (give-back). Cloud shape tells you how much of the move the exit logic converts.</div>
      <div class="plot">{fig_html(fig_mfe, 'fig-mfe') if fig_mfe else '<div class="lede">No MFE/MAE data yet</div>'}</div>
    </section>

    <section id="duration">
      <h2><span class="sn">10</span>Duration vs PnL</h2>
      <div class="lede">Short-and-winning vs long-and-losing? Tells you if the bot is cutting too early or riding too long.</div>
      <div class="plot">{fig_html(fig_dur, 'fig-dur')}</div>
    </section>

    <section id="recent">
      <h2><span class="sn">11</span>Recent activity<span class="tag">last 14 days · most recent first</span></h2>
      <div class="lede">Skim this when reopening the dashboard.</div>
      {colored_df_html(recent, pnl_cols=["pnl_net", "return_pct"], index=False)}
    </section>

  </div></main>

  {site_footer_html}

  <script>{JS}</script>
</body>
</html>
"""

OUT.write_text(html)
print(f"\nwrote {OUT}  ({OUT.stat().st_size // 1024} KB)")

if "--open" in sys.argv or "-o" in sys.argv:
    subprocess.run(["open", str(OUT)])
    print("opened in default browser")
