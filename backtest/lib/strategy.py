"""Strategy spec — modules expose either {entry, exit, sizing} (ideal) OR {run} (escape hatch)."""

from __future__ import annotations
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

EntryFn = Callable[[dict, dict], Optional[dict]]
ExitFn = Callable[[dict, dict, dict], Optional[dict]]
SizingFn = Callable[[float, float, float], float]
RunFn = Callable[[list, list], list]


@dataclass(frozen=True)
class StrategySpec:
    name: str
    version: str
    kind: str  # "ideal" or "escape_hatch"
    entry: Optional[Callable] = None
    exit: Optional[Callable] = None
    sizing: Optional[Callable] = None
    run: Optional[Callable] = None
    config_for_manifest: dict = field(default_factory=dict)


def load(path: str) -> StrategySpec:
    """Import strategy module by file path; auto-detect kind from exposed attributes."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"strategy file not found: {p}")

    spec = importlib.util.spec_from_file_location(p.stem, p)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load strategy: {p}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    name = getattr(mod, "name", p.stem)
    version = getattr(mod, "version", "0.0.0")
    cfg = dict(getattr(mod, "config_for_manifest", {}) or {})

    run = getattr(mod, "run", None)
    entry = getattr(mod, "entry", None)
    exit_fn = getattr(mod, "exit", None)
    sizing = getattr(mod, "sizing", None)

    if callable(run):
        return StrategySpec(name=name, version=version, kind="escape_hatch", run=run, config_for_manifest=cfg)
    if all(callable(f) for f in (entry, exit_fn, sizing)):
        return StrategySpec(
            name=name, version=version, kind="ideal",
            entry=entry, exit=exit_fn, sizing=sizing, config_for_manifest=cfg,
        )
    raise ValueError(
        f"strategy {p.name} must expose either `run(bars_15m, bars_1h)` (escape hatch) "
        f"or all of `entry` / `exit` / `sizing` (ideal protocol)"
    )
