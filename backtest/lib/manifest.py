"""Run manifest — config_hash, data_window_hash, code_commit, fee_model, slippage_model."""

from __future__ import annotations
import hashlib
import json
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Manifest:
    run_id: str
    strategy_name: str
    strategy_version: str
    symbol: str
    period: str
    config_hash: str
    data_window_hash: str
    code_commit: str
    fee_model: str
    slippage_model: str
    created_at_utc: str
    config: dict | None = None
    known_gaps: list[str] | None = None
    n_bars_15m: int | None = None
    n_bars_1h: int | None = None


def hash_config(config: dict) -> str:
    """Stable SHA-256 of config dict."""
    return hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()


def hash_bars(bars: list[dict]) -> str:
    """SHA-256 of (first_ts, last_ts, count) to identify the data window cheaply."""
    if not bars:
        return "empty"
    key = f"{bars[0]['ts']}-{bars[-1]['ts']}-{len(bars)}"
    return hashlib.sha256(key.encode()).hexdigest()


def git_commit() -> str:
    """Current ~/ibitlabs/ git short SHA, or 'untracked' if unavailable."""
    try:
        out = subprocess.run(
            ["git", "-C", str(Path.home() / "ibitlabs"), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        return out.stdout.strip()
    except Exception:
        return "untracked"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit(manifest: Manifest, run_dir: Path) -> Path:
    """Write manifest.json into run_dir. Creates dir if missing."""
    run_dir.mkdir(parents=True, exist_ok=True)
    p = run_dir / "manifest.json"
    p.write_text(json.dumps(asdict(manifest), indent=2, default=str))
    return p
