"""RollbackLadder: unified status interface over the three rollback layers.

Layer 1 - Realtime (minute scale):
  - ghost-watchdog (60s loop)
  - close_verify post-submit (3s)
  - auth_fail_streak 1/3/5 escalation
  Each probed via launchctl + log-file existence.

Layer 2 - Observation (month scale):
  - shadow rule 30d review → delegates to PromotionBar
  - retire-by-deadline → routes to archive_falsified

Layer 3 - Proposal (second-to-day scale):
  - anti-patterns currently armed to reject lookalike proposals
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml

IBITLABS_ROOT = Path("/Users/bonnyagent/ibitlabs")

Layer = Literal["realtime", "observation", "proposal"]
Status = Literal["healthy", "degraded", "alarm", "unknown"]


@dataclass
class Monitor:
    id: str
    layer: Layer
    description: str
    status: Status
    last_check: str
    detail: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RealtimeLayer:
    REALTIME_JOBS = {
        "com.ibitlabs.ghost-watchdog": "ghost-position tri-check (60s loop)",
    }

    def list_monitors(self) -> list[Monitor]:
        out: list[Monitor] = []
        for label, desc in self.REALTIME_JOBS.items():
            status, detail = self._probe_launchd(label)
            out.append(Monitor(
                id=label, layer="realtime", description=desc,
                status=status, last_check=_now_iso(), detail=detail,
            ))
        out.append(self._probe_close_verify())
        out.append(self._probe_auth_fail_streak())
        return out

    @staticmethod
    def _probe_launchd(label: str) -> tuple[Status, str]:
        try:
            result = subprocess.run(
                ["launchctl", "list", label],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return "degraded", f"launchctl rc={result.returncode}: {result.stderr.strip()[:80]}"
            fields: dict[str, str] = {}
            for line in result.stdout.splitlines():
                line = line.strip().rstrip(";")
                if "=" in line and line.startswith('"'):
                    k, _, v = line.partition("=")
                    fields[k.strip().strip('"')] = v.strip()
            pid = fields.get("PID", "").strip().rstrip(";")
            on_demand = fields.get("OnDemand", "").lower() == "true"
            last_exit = fields.get("LastExitStatus", "").strip()
            if pid and pid != "0":
                return "healthy", f"PID={pid}"
            if on_demand and last_exit == "0":
                return "healthy", "periodic; LastExitStatus=0"
            if on_demand and last_exit and last_exit != "0":
                return "degraded", f"periodic; LastExitStatus={last_exit}"
            return "degraded", "loaded but no PID (continuous job not running)"
        except FileNotFoundError:
            return "unknown", "launchctl not available"
        except subprocess.TimeoutExpired:
            return "unknown", "launchctl timeout"

    @staticmethod
    def _probe_close_verify() -> Monitor:
        log = IBITLABS_ROOT / "logs" / "close_verify_failures.jsonl"
        if not log.exists():
            return Monitor(
                id="close_verify", layer="realtime",
                description="post-submit close verifier (3s)",
                status="healthy", last_check=_now_iso(),
                detail="close_verify_failures.jsonl absent = no failures yet",
            )
        size = log.stat().st_size
        return Monitor(
            id="close_verify", layer="realtime",
            description="post-submit close verifier (3s)",
            status="alarm" if size > 0 else "healthy",
            last_check=_now_iso(),
            detail=f"close_verify_failures.jsonl size={size}B",
        )

    @staticmethod
    def _probe_auth_fail_streak() -> Monitor:
        log = IBITLABS_ROOT / "logs" / "auth_fail_streak.jsonl"
        present = log.exists() and log.stat().st_size > 0
        return Monitor(
            id="auth_fail_streak", layer="realtime",
            description="Coinbase 401 1/3/5 escalation (ghost-watchdog commit 7aef4b3)",
            status="degraded" if present else "healthy",
            last_check=_now_iso(),
            detail="alerts via ntfy / iMessage / bootout",
        )


class ObservationLayer:
    def __init__(self, proposals_dir: Path | None = None):
        self.proposals_dir = proposals_dir or (
            Path(__file__).resolve().parent.parent / "examples"
        )

    def list_monitors(self) -> list[Monitor]:
        from .proposal import Proposal
        from .promotion_bar import PromotionBar

        out: list[Monitor] = []
        for yaml_file in sorted(self.proposals_dir.glob("*.yaml")):
            with yaml_file.open() as f:
                raw = yaml.safe_load(f)
            if not isinstance(raw, dict) or "proposal_id" not in raw:
                continue
            try:
                p = Proposal.from_yaml(yaml_file)
                bar = PromotionBar(p)
                decision = bar.evaluate()
                status_map: dict[str, Status] = {
                    "PROMOTE": "healthy",
                    "KEEP_OBSERVING": "healthy",
                    "RETIRE": "alarm",
                    "RETIRE_BY_DEADLINE": "alarm",
                }
                out.append(Monitor(
                    id=p.data["proposal_id"],
                    layer="observation",
                    description=p.data["hypothesis"].strip().splitlines()[0][:80],
                    status=status_map.get(decision.decision, "unknown"),
                    last_check=_now_iso(),
                    detail=f"{decision.decision}: {decision.receipt}",
                ))
            except Exception as e:
                out.append(Monitor(
                    id=yaml_file.stem, layer="observation",
                    description=f"failed to evaluate {yaml_file.name}",
                    status="unknown", last_check=_now_iso(), detail=str(e),
                ))
        return out


class ProposalLayer:
    """Lists anti-patterns currently armed to reject lookalike proposals."""

    def __init__(self, archives_dir: Path | None = None):
        self.archives_dir = archives_dir or (
            Path(__file__).resolve().parent.parent / "examples"
        )

    def list_monitors(self) -> list[Monitor]:
        out: list[Monitor] = []
        for yaml_file in sorted(self.archives_dir.glob("*.yaml")):
            with yaml_file.open() as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict) or "anti_pattern_id" not in data:
                continue
            aliases = ", ".join(data.get("aliases_blocked", []) or [])
            out.append(Monitor(
                id=data["anti_pattern_id"],
                layer="proposal",
                description=data["why_falsified"].strip().splitlines()[0][:80],
                status="healthy",
                last_check=_now_iso(),
                detail=f"blocks {len(data.get('aliases_blocked', []))} aliases; memory: {data.get('memory_file')}",
            ))
        return out


class RollbackLadder:
    def __init__(self):
        self.realtime = RealtimeLayer()
        self.observation = ObservationLayer()
        self.proposal = ProposalLayer()

    def list_all(self) -> list[Monitor]:
        return (
            self.realtime.list_monitors()
            + self.observation.list_monitors()
            + self.proposal.list_monitors()
        )
