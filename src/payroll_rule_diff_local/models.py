from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class Country(StrEnum):
    MX = "MX"
    IT = "IT"
    UK = "UK"
    PH = "PH"
    BR = "BR"


class RuleKind(StrEnum):
    MINIMUM_SALARY = "minimum_salary"
    CONTRIBUTION_CAP = "contribution_cap"
    THRESHOLD = "threshold"
    CONTRIBUTION_TABLE = "contribution_table"
    CEILING = "ceiling"


class PayrollRun(BaseModel):
    run_id: str
    worker_id: str
    country: Country
    period: str
    gross_pay_cents: int
    base_employee_contrib_cents: int
    base_employer_cost_cents: int
    anomaly_flags: list[str] = Field(default_factory=list)


class RuleArtifact(BaseModel):
    rule_id: str
    country: Country
    period: str
    kind: RuleKind
    effective_date: str
    parameters: dict[str, float | int | str]
    source_text_hash: str
    interpreter_version: str
    parent_hash: str
    content_hash: str
    signature: str | None = None


class ImpactLine(BaseModel):
    run_id: str
    worker_id: str
    country: Country
    baseline_net_cents: int
    proposed_net_cents: int
    net_delta_cents: int
    employer_delta_cents: int
    resolved_anomalies: list[str]


class ReplaySummary(BaseModel):
    replay_id: str
    rule_hash: str
    country: Country
    run_count: int
    affected_count: int
    aggregate_net_delta_cents: int
    aggregate_employer_delta_cents: int
    resolved_anomaly_count: int
    p95_latency_ms: int
    pass_gates: bool
    lines: list[ImpactLine]


class VerificationReport(BaseModel):
    ok: bool
    checks: dict[str, bool]


class ToolRequest(BaseModel):
    tool: Literal["propose", "replay", "approve-sign", "verify"]
    arguments: dict[str, Any] = Field(default_factory=dict)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]
