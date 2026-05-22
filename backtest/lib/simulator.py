"""Execution simulator — run_single + run_is_oos + run_sweep + run_gate."""

from __future__ import annotations
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

from backtest.lib.strategy import load as load_strategy, StrategySpec
from backtest.lib.data import load_ohlcv
from backtest.lib.jsonl import write_events
from backtest.lib.manifest import (
    Manifest, emit as emit_manifest,
    hash_config, hash_bars, git_commit, now_utc_iso,
)
from backtest.lib.gates import check as check_gates, GateResult


_PERIOD_RE = re.compile(r"^(\d+)([dh])$")


def _parse_period_days(period: str) -> int:
    m = _PERIOD_RE.match(period.strip())
    if not m:
        raise ValueError(f"period must be like '90d' or '720h', got {period!r}")
    n, unit = int(m.group(1)), m.group(2)
    return n if unit == "d" else max(1, n // 24)


def _new_run_id(spec: StrategySpec, symbol: str, period: str, suffix: str = "") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    tag = f"_{suffix}" if suffix else ""
    return f"{spec.name}_{symbol}_{period}_{ts}{tag}"


def _emit_run(
    run_dir: Path, trades: list, bars_15m: list, bars_1h: list,
    spec: StrategySpec, symbol: str, period: str, config_extra: dict | None = None,
) -> Path:
    events_path = run_dir / "events.jsonl"
    write_events(
        events_path, trades,
        symbol=symbol, strategy_name=spec.name, strategy_version=spec.version,
    )
    cfg = dict(spec.config_for_manifest)
    if config_extra:
        cfg.update(config_extra)
    manifest = Manifest(
        run_id=run_dir.name,
        strategy_name=spec.name,
        strategy_version=spec.version,
        symbol=symbol,
        period=period,
        config_hash=hash_config(cfg),
        data_window_hash=hash_bars(bars_15m),
        code_commit=git_commit(),
        fee_model="maker=0.0004 / taker=0.0006 / funding=0.0001 per 8h",
        slippage_model="none (TP at high/low, SL at extreme — engine convention)",
        created_at_utc=now_utc_iso(),
        config=cfg,
        known_gaps=cfg.get("known_gaps"),
        n_bars_15m=len(bars_15m),
        n_bars_1h=len(bars_1h),
    )
    return emit_manifest(manifest, run_dir)


def _print_result(label: str, trades: list, result: GateResult) -> None:
    total_pnl = sum(t.get("pnl", 0) for t in trades)
    print(f"=== {label}: {'PASS' if result.passed else 'FAIL'} ===")
    print(f"  trades: {result.n_trades}  |  total PnL: ${total_pnl:+.2f}")
    print(f"  PF: {result.pf:.2f}  WR: {result.wr_pct:.1f}%  distinct_regimes: {result.distinct_regimes}")
    for r in result.reasons:
        print(f"  [GATE MISS] {r}")


def _gate_trades(trades: list) -> GateResult:
    regimes = [t.get("regime", "?") for t in trades]
    return check_gates(trades, regimes)


def run_single(strategy_path: str, symbol: str, period: str, output_dir: str) -> int:
    """Single full-period backtest."""
    spec = load_strategy(strategy_path)
    print(f"[strategy] {spec.name} v{spec.version} (kind={spec.kind})")

    print(f"[data] loading {symbol} {period} ...")
    try:
        bars_15m, bars_1h = load_ohlcv(symbol, period)
    except Exception as e:
        print(f"[data] FAILED: {e}", file=sys.stderr)
        return 2
    print(f"[data] {len(bars_15m)} x 15m bars, {len(bars_1h)} x 1h bars")

    if spec.kind != "escape_hatch":
        raise NotImplementedError("v0: only escape_hatch strategies supported")

    trades = spec.run(bars_15m, bars_1h)
    run_dir = Path(output_dir).expanduser() / _new_run_id(spec, symbol, period)
    manifest_path = _emit_run(run_dir, trades, bars_15m, bars_1h, spec, symbol, period)
    print(f"[run] -> {run_dir}")
    print(f"[manifest] -> {manifest_path}")

    result = _gate_trades(trades)
    print()
    _print_result("RESULT", trades, result)
    return 0 if result.passed else 1


def run_is_oos(strategy_path: str, symbol: str, is_period: str, oos_period: str, output_dir: str) -> int:
    """IS/OOS split. Fetches IS+OOS days, partitions trades by entry_ts, gates both. Both must pass."""
    is_days = _parse_period_days(is_period)
    oos_days = _parse_period_days(oos_period)
    total = f"{is_days + oos_days}d"

    spec = load_strategy(strategy_path)
    print(f"[strategy] {spec.name} v{spec.version} (kind={spec.kind})")
    print(f"[is-oos] IS={is_days}d  OOS={oos_days}d  total={total}")

    try:
        bars_15m, bars_1h = load_ohlcv(symbol, total)
    except Exception as e:
        print(f"[data] FAILED: {e}", file=sys.stderr)
        return 2
    print(f"[data] {len(bars_15m)} x 15m bars, {len(bars_1h)} x 1h bars")

    if spec.kind != "escape_hatch":
        raise NotImplementedError("v0: only escape_hatch strategies supported")

    trades = spec.run(bars_15m, bars_1h)
    if not trades:
        print("[is-oos] no trades produced")
        return 1

    last_ts = bars_15m[-1]["ts"]
    is_cutoff_ts = last_ts - oos_days * 86400
    is_trades = [t for t in trades if t.get("entry_ts", 0) < is_cutoff_ts]
    oos_trades = [t for t in trades if t.get("entry_ts", 0) >= is_cutoff_ts]

    run_dir = Path(output_dir).expanduser() / _new_run_id(spec, symbol, f"is{is_days}_oos{oos_days}")
    run_dir.mkdir(parents=True, exist_ok=True)

    write_events(
        run_dir / "is_events.jsonl", is_trades,
        symbol=symbol, strategy_name=spec.name, strategy_version=spec.version,
    )
    write_events(
        run_dir / "oos_events.jsonl", oos_trades,
        symbol=symbol, strategy_name=spec.name, strategy_version=spec.version,
    )
    _emit_run(
        run_dir, trades, bars_15m, bars_1h, spec, symbol, total,
        config_extra={"is_days": is_days, "oos_days": oos_days, "is_cutoff_ts": is_cutoff_ts},
    )
    print(f"[is-oos] -> {run_dir}")

    is_result = _gate_trades(is_trades)
    oos_result = _gate_trades(oos_trades)
    print()
    _print_result("IS", is_trades, is_result)
    print()
    _print_result("OOS", oos_trades, oos_result)
    print()
    both_pass = is_result.passed and oos_result.passed
    print(f"=== COMBINED: {'PASS' if both_pass else 'FAIL'} (both IS and OOS must pass — v5.2 lesson) ===")
    return 0 if both_pass else 1


def _coerce(v: str):
    for caster in (int, float):
        try:
            return caster(v)
        except ValueError:
            continue
    return v


def run_sweep(strategy_path: str, symbol: str, period: str, params: list, output_dir: str) -> int:
    """Parameter grid sweep. params is list of 'key=v1,v2,v3'."""
    grid = {}
    for p in params:
        if "=" not in p:
            print(f"[sweep] bad --param: {p!r}, expected key=v1,v2,v3", file=sys.stderr)
            return 2
        k, v_str = p.split("=", 1)
        grid[k.strip()] = [_coerce(v.strip()) for v in v_str.split(",")]

    spec = load_strategy(strategy_path)
    print(f"[strategy] {spec.name} v{spec.version} (kind={spec.kind})")
    keys = list(grid.keys())
    cells = [dict(zip(keys, combo)) for combo in product(*[grid[k] for k in keys])]
    print(f"[sweep] {len(cells)} cells over params: {keys}")

    try:
        bars_15m, bars_1h = load_ohlcv(symbol, period)
    except Exception as e:
        print(f"[data] FAILED: {e}", file=sys.stderr)
        return 2
    print(f"[data] {len(bars_15m)} x 15m bars, {len(bars_1h)} x 1h bars")

    sweep_dir = Path(output_dir).expanduser() / _new_run_id(spec, symbol, period, suffix="sweep")
    sweep_dir.mkdir(parents=True, exist_ok=True)
    summary_path = sweep_dir / "sweep.jsonl"

    rankings = []
    with summary_path.open("w") as f:
        for i, cell in enumerate(cells, 1):
            try:
                trades = spec.run(bars_15m, bars_1h, **cell)
            except TypeError:
                print(f"[sweep] strategy {spec.name} does not accept **overrides — cannot sweep", file=sys.stderr)
                return 2
            result = _gate_trades(trades)
            total_pnl = sum(t.get("pnl", 0) for t in trades)
            row = {
                "cell": cell,
                "n_trades": result.n_trades,
                "total_pnl": total_pnl,
                "pf": result.pf if result.pf != float("inf") else None,
                "wr_pct": result.wr_pct,
                "distinct_regimes": result.distinct_regimes,
                "passed": result.passed,
                "gate_reasons": result.reasons,
            }
            f.write(json.dumps(row, default=str) + "\n")
            rankings.append((total_pnl, cell, result))
            pf_disp = f"{result.pf:.2f}" if result.pf != float("inf") else "inf"
            print(
                f"  [{i}/{len(cells)}] {cell}  n={result.n_trades}  "
                f"PnL=${total_pnl:+.2f}  PF={pf_disp}  WR={result.wr_pct:.1f}%  "
                f"{'PASS' if result.passed else 'FAIL'}"
            )

    rankings.sort(key=lambda x: x[0], reverse=True)
    print()
    print(f"=== TOP 3 BY PnL ===")
    for pnl, cell, result in rankings[:3]:
        print(f"  ${pnl:+.2f}  {cell}  ({'PASS' if result.passed else 'FAIL'})")
    print(f"[sweep] -> {summary_path}")
    return 0


def run_gate(run_dir: str, min_trades: int, min_pf: float, min_wr: float, min_regimes: int) -> int:
    """Re-evaluate a saved run with custom thresholds."""
    run_path = Path(run_dir).expanduser().resolve()
    events_paths = [run_path / "events.jsonl"]
    if not events_paths[0].exists():
        # Try is-oos style: gate the OOS portion (the strict one)
        oos = run_path / "oos_events.jsonl"
        if oos.exists():
            events_paths = [oos]
            print(f"[gate] using {oos.name} (IS/OOS run detected)")
        else:
            print(f"[gate] events.jsonl not found under {run_path}", file=sys.stderr)
            return 2

    trades = []
    for ep in events_paths:
        for line in ep.read_text().splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("kind") == "EXIT":
                trades.append({"pnl": e.get("pnl", 0), "regime": e.get("regime", "?")})

    regimes = [t["regime"] for t in trades]
    thresholds = {
        "min_trades": min_trades,
        "min_pf": min_pf,
        "min_wr_pct": min_wr,
        "min_distinct_regimes": min_regimes,
    }
    result = check_gates(trades, regimes, thresholds)
    print(f"[gate] {run_path.name}")
    print(f"  thresholds: n>={min_trades}  PF>={min_pf}  WR>={min_wr}%  regimes>={min_regimes}")
    _print_result("RESULT", trades, result)
    return 0 if result.passed else 1
