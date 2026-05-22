#!/usr/bin/env python3
"""ibit-backtest CLI dispatcher.

v0 active subcommands: run, is-oos, sweep, gate
v0 stubs:              walk-fwd, compare, regime, anchor
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def cmd_run(args: argparse.Namespace) -> int:
    from backtest.lib.simulator import run_single
    return run_single(
        strategy_path=args.strategy,
        symbol=args.symbol,
        period=args.period,
        output_dir=args.output,
    )


def cmd_is_oos(args: argparse.Namespace) -> int:
    from backtest.lib.simulator import run_is_oos
    return run_is_oos(
        strategy_path=args.strategy,
        symbol=args.symbol,
        is_period=args.is_period,
        oos_period=args.oos_period,
        output_dir=args.output,
    )


def cmd_sweep(args: argparse.Namespace) -> int:
    from backtest.lib.simulator import run_sweep
    return run_sweep(
        strategy_path=args.strategy,
        symbol=args.symbol,
        period=args.period,
        params=args.param,
        output_dir=args.output,
    )


def cmd_gate(args: argparse.Namespace) -> int:
    from backtest.lib.simulator import run_gate
    return run_gate(
        run_dir=args.run_dir,
        min_trades=args.min_trades,
        min_pf=args.min_pf,
        min_wr=args.min_wr,
        min_regimes=args.min_regimes,
    )


def _stub(name: str):
    def _impl(_args: argparse.Namespace) -> int:
        print(f"ibit-backtest {name}: not implemented in v0", file=sys.stderr)
        return 2
    return _impl


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ibit-backtest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    default_out = str(Path.home() / "ibitlabs" / "backtest" / "runs")

    # run
    p = sub.add_parser("run", help="single full-period backtest")
    p.add_argument("--strategy", required=True, help="path to strategy .py")
    p.add_argument("--symbol", required=True, help="e.g. SOL")
    p.add_argument("--period", required=True, help="e.g. 90d, 30d")
    p.add_argument("--output", default=default_out, help="output dir")
    p.set_defaults(func=cmd_run)

    # is-oos
    p = sub.add_parser("is-oos", help="IS/OOS split (both must pass per v5.2 lesson)")
    p.add_argument("--strategy", required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--is-period", default="60d", help="in-sample window")
    p.add_argument("--oos-period", default="30d", help="out-of-sample window")
    p.add_argument("--output", default=default_out)
    p.set_defaults(func=cmd_is_oos)

    # sweep
    p = sub.add_parser("sweep", help="parameter grid sweep")
    p.add_argument("--strategy", required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--period", required=True)
    p.add_argument(
        "--param", action="append", required=True,
        help="key=v1,v2,v3 (repeat for multi-dim grid)",
    )
    p.add_argument("--output", default=default_out)
    p.set_defaults(func=cmd_sweep)

    # gate
    p = sub.add_parser("gate", help="re-evaluate a saved run with custom thresholds")
    p.add_argument("run_dir", help="path to a previous run directory")
    p.add_argument("--min-trades", type=int, default=30)
    p.add_argument("--min-pf", type=float, default=1.2)
    p.add_argument("--min-wr", type=float, default=60.0)
    p.add_argument("--min-regimes", type=int, default=2)
    p.set_defaults(func=cmd_gate)

    # stubs
    for name in ("walk-fwd", "compare", "regime", "anchor"):
        sp = sub.add_parser(name, help=f"{name} (not implemented in v0)")
        sp.set_defaults(func=_stub(name))

    return ap


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
