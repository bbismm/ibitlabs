#!/usr/bin/env python3
"""Smoke test — locks 30d SOL v5.3 `run` as regression baseline.

Run: python3 backtest/tests/test_smoke.py
Hits Coinbase API (network required). Fast path validation only — semantic regression
(trade count drift, PnL drift) needs a fixed-data fixture, deferred to v0.1.
"""

from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin" / "ibit_backtest.py"
STRATEGY = ROOT / "strategies" / "sol_v5_3.py"
IBITLABS = ROOT.parent


def _check(failures: list, cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def main() -> int:
    failures: list = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        result = subprocess.run(
            [sys.executable, str(BIN), "run",
             "--strategy", str(STRATEGY),
             "--symbol", "SOL",
             "--period", "30d",
             "--output", str(tmp)],
            cwd=str(IBITLABS),
            capture_output=True, text=True, timeout=180,
        )
        _check(failures, result.returncode in (0, 1),
               f"unexpected exit code {result.returncode}\nstderr: {result.stderr[-500:]}")

        run_dirs = list(tmp.glob("sol_v5_3_SOL_30d_*"))
        _check(failures, len(run_dirs) == 1, f"expected 1 run dir, got {len(run_dirs)}")

        if run_dirs:
            run_dir = run_dirs[0]
            events_path = run_dir / "events.jsonl"
            manifest_path = run_dir / "manifest.json"

            _check(failures, events_path.exists(), "events.jsonl not created")
            if events_path.exists():
                events = [l for l in events_path.read_text().splitlines() if l.strip()]
                _check(failures, len(events) > 0, "events.jsonl is empty")
                _check(failures, len(events) % 2 == 0,
                       f"events should be paired ENTRY+EXIT, got {len(events)} lines")
                if events:
                    first = json.loads(events[0])
                    _check(failures, first.get("kind") == "ENTRY",
                           f"first event should be ENTRY, got {first.get('kind')!r}")
                    _check(failures, first.get("schema_version") == 1,
                           f"schema_version should be 1, got {first.get('schema_version')!r}")
                    _check(failures, first.get("strategy_name") == "sol_v5_3",
                           f"strategy_name should be sol_v5_3, got {first.get('strategy_name')!r}")

            _check(failures, manifest_path.exists(), "manifest.json not created")
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text())
                for field in ("run_id", "strategy_name", "config_hash",
                              "data_window_hash", "code_commit", "fee_model"):
                    _check(failures, bool(manifest.get(field)),
                           f"manifest.{field} missing or empty")
                _check(failures, manifest.get("strategy_name") == "sol_v5_3",
                       f"strategy_name expected sol_v5_3, got {manifest.get('strategy_name')!r}")
                _check(failures, manifest.get("symbol") == "SOL", "manifest.symbol != SOL")
                _check(failures, manifest.get("period") == "30d", "manifest.period != 30d")
                _check(failures, bool(manifest.get("known_gaps")),
                       "expected known_gaps (reverse_exit_C)")

    if failures:
        print("[smoke] FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[smoke] PASS — 30d SOL v5.3 run produces valid events.jsonl + manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
