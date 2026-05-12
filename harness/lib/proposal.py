"""Proposal: standardized input form for new rules on the iBitLabs harness.

Loads a YAML file, validates against the JSON schema, then runs the 5 contributor-funnel
constraint checks. Each violation carries the memory-rule citation so the caller can
route the rejection message back to the contributor or operator.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
import jsonschema

HARNESS_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = HARNESS_ROOT / "schemas" / "proposal.schema.json"


class ConstraintViolation(Exception):
    def __init__(self, constraint: str, memory_rule: str, detail: str):
        self.constraint = constraint
        self.memory_rule = memory_rule
        self.detail = detail
        super().__init__(f"[{constraint}] {detail} (see {memory_rule})")


@dataclass
class Proposal:
    data: dict[str, Any]
    source_path: Path

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Proposal":
        path = Path(path)
        with path.open() as f:
            data = yaml.safe_load(f)
        return cls(data=data, source_path=path)

    def validate_schema(self) -> None:
        with SCHEMA_PATH.open() as f:
            schema = json.load(f)
        jsonschema.validate(instance=self.data, schema=schema)

    def check_real_data_gate(self) -> None:
        gate = self.data["real_data_gate"]
        if gate["evidence_seen"] < gate["evidence_threshold"]:
            raise ConstraintViolation(
                constraint="real_data_gate",
                memory_rule="feedback_real_data_before_features.md",
                detail=(
                    f"evidence_seen={gate['evidence_seen']} < "
                    f"evidence_threshold={gate['evidence_threshold']}. "
                    "Archive as hypothesis-with-trigger instead of opening shadow."
                ),
            )

    def check_shadow_budget(self) -> None:
        budget = self.data["shadow_budget"]
        if budget["current_active"] >= budget["cap"]:
            raise ConstraintViolation(
                constraint="shadow_budget",
                memory_rule="feedback_shadow_budget.md",
                detail=(
                    f"current_active={budget['current_active']} >= cap={budget['cap']}. "
                    "Retire one shadow before adding another."
                ),
            )

    def check_contributor_ping(self) -> None:
        credit = self.data["contributor_credit"]
        proposed_by = self.data.get("proposed_by")
        if not proposed_by:
            return
        if credit.get("ack_received"):
            return
        pinged_at = credit.get("pinged_at")
        if not pinged_at:
            raise ConstraintViolation(
                constraint="contributor_credit",
                memory_rule="feedback_contributor_rule_calibration.md",
                detail=(
                    f"proposed_by={proposed_by} but pinged_at is null. "
                    "Ping contributor and wait >=48h, or get ack first."
                ),
            )
        pinged_dt = datetime.fromisoformat(pinged_at.replace("Z", "+00:00"))
        wait = credit.get("ping_wait_hours", 48)
        elapsed = (datetime.now(timezone.utc) - pinged_dt).total_seconds() / 3600
        if elapsed < wait:
            raise ConstraintViolation(
                constraint="contributor_credit",
                memory_rule="feedback_contributor_rule_calibration.md",
                detail=f"contributor pinged {elapsed:.1f}h ago; need >={wait}h.",
            )

    def check_control_flow(self) -> None:
        impact = self.data["control_flow_impact"]
        if impact != "log_only":
            raise ConstraintViolation(
                constraint="control_flow_impact",
                memory_rule="CLAUDE.md observation-period contract",
                detail=(
                    f"control_flow_impact={impact}. At proposal stage MUST be log_only. "
                    "Promotion to entry gate requires explicit re-spec post-observation."
                ),
            )

    def check_promotion_bar(self) -> None:
        bar = self.data["promotion_bar"]
        if bar["min_entries"] < 30:
            raise ConstraintViolation(
                constraint="promotion_bar",
                memory_rule="project_rule_f_promotion_criteria.md",
                detail=f"min_entries={bar['min_entries']} < 30 (Rule F template).",
            )
        if bar["min_observation_days"] < 30:
            raise ConstraintViolation(
                constraint="promotion_bar",
                memory_rule="project_rule_f_promotion_criteria.md",
                detail=f"min_observation_days={bar['min_observation_days']} < 30.",
            )

    def validate_all(self) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []
        try:
            self.validate_schema()
        except jsonschema.ValidationError as e:
            violations.append(ConstraintViolation(
                constraint="schema",
                memory_rule="schemas/proposal.schema.json",
                detail=f"{e.message} at {list(e.absolute_path)}",
            ))
            return violations
        for check in (
            self.check_real_data_gate,
            self.check_shadow_budget,
            self.check_contributor_ping,
            self.check_control_flow,
            self.check_promotion_bar,
        ):
            try:
                check()
            except ConstraintViolation as v:
                violations.append(v)
        return violations
