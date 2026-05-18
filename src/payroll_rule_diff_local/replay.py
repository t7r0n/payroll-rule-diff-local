from __future__ import annotations

import fcntl
import json
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from statistics import quantiles

import duckdb

from payroll_rule_diff_local.fixtures import generate_payroll, load_payroll
from payroll_rule_diff_local.models import (
    ImpactLine,
    PayrollRun,
    ReplaySummary,
    RuleArtifact,
    RuleKind,
    project_root,
)
from payroll_rule_diff_local.rules import load_rule, registry_dir, verify_rule_signature


def runs_dir() -> Path:
    path = project_root() / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def outputs_dir() -> Path:
    path = project_root() / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return runs_dir() / "rule_diff.duckdb"


@contextmanager
def store_lock() -> Iterator[None]:
    lock_path = project_root() / ".payroll-rule-diff.lock"
    with lock_path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db_path()))
    con.execute(
        """
        create table if not exists replay_runs (
          replay_id varchar,
          rule_hash varchar,
          country varchar,
          run_count integer,
          affected_count integer,
          aggregate_net_delta_cents integer,
          aggregate_employer_delta_cents integer,
          resolved_anomaly_count integer,
          p95_latency_ms integer,
          pass_gates boolean
        )
        """
    )
    return con


def _baseline(run: PayrollRun) -> tuple[int, int]:
    net = run.gross_pay_cents - run.base_employee_contrib_cents
    return net, run.base_employer_cost_cents


def _proposed(run: PayrollRun, rule: RuleArtifact) -> tuple[int, int, list[str]]:
    employee = run.base_employee_contrib_cents
    employer = run.base_employer_cost_cents
    resolved: list[str] = []
    if rule.kind == RuleKind.MINIMUM_SALARY:
        floor = int(rule.parameters["floor_monthly_cents"])
        uplift_base = max(run.gross_pay_cents, floor)
        employee = int(uplift_base * 0.077)
        employer = int(run.gross_pay_cents + uplift_base * 0.142)
        if "floor_mismatch" in run.anomaly_flags and run.gross_pay_cents < floor:
            resolved.append("floor_mismatch")
    elif rule.kind == RuleKind.CONTRIBUTION_CAP:
        cap = int(rule.parameters["monthly_cap_cents"])
        capped = min(run.gross_pay_cents, cap)
        employee = int(capped * 0.095)
        employer = int(run.gross_pay_cents + capped * 0.315)
        if "cap_boundary" in run.anomaly_flags and run.gross_pay_cents > cap * 0.9:
            resolved.append("cap_boundary")
    elif rule.kind == RuleKind.THRESHOLD:
        threshold = int(rule.parameters["monthly_threshold_cents"])
        taxable = max(0, run.gross_pay_cents - threshold)
        employee = int(taxable * 0.084)
        employer = int(run.gross_pay_cents + max(0, run.gross_pay_cents - threshold) * 0.141)
        if "threshold_edge" in run.anomaly_flags and abs(run.gross_pay_cents - threshold) < 60_000:
            resolved.append("threshold_edge")
    elif rule.kind == RuleKind.CONTRIBUTION_TABLE:
        employee = int(run.gross_pay_cents * float(rule.parameters["employee_rate"]))
        employer = int(run.gross_pay_cents * (1 + float(rule.parameters["employer_rate"])))
    elif rule.kind == RuleKind.CEILING:
        ceiling = int(rule.parameters["monthly_ceiling_cents"])
        base = min(run.gross_pay_cents, ceiling)
        employee = int(base * 0.092)
        employer = int(run.gross_pay_cents + base * 0.214)
    return run.gross_pay_cents - employee, employer, resolved


def replay_rule(rule_ref: str = "latest") -> ReplaySummary:
    generate_payroll()
    rule = load_rule(rule_ref)
    started = time.perf_counter()
    country_runs = [run for run in load_payroll() if run.country == rule.country]
    lines: list[ImpactLine] = []
    latencies: list[int] = []
    for run in country_runs:
        item_start = time.perf_counter()
        baseline_net, baseline_employer = _baseline(run)
        proposed_net, proposed_employer, resolved = _proposed(run, rule)
        net_delta = proposed_net - baseline_net
        employer_delta = proposed_employer - baseline_employer
        if abs(net_delta) >= 5_000 or abs(employer_delta) >= 8_000 or resolved:
            lines.append(
                ImpactLine(
                    run_id=run.run_id,
                    worker_id=run.worker_id,
                    country=run.country,
                    baseline_net_cents=baseline_net,
                    proposed_net_cents=proposed_net,
                    net_delta_cents=net_delta,
                    employer_delta_cents=employer_delta,
                    resolved_anomalies=resolved,
                )
            )
        latencies.append(max(1, int((time.perf_counter() - item_start) * 1000)))
    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    p95 = max(elapsed_ms, int(quantiles(latencies or [1], n=20)[-1]))
    summary = ReplaySummary(
        replay_id=f"replay-{time.time_ns():x}"[-22:],
        rule_hash=rule.content_hash,
        country=rule.country,
        run_count=len(country_runs),
        affected_count=len(lines),
        aggregate_net_delta_cents=sum(line.net_delta_cents for line in lines),
        aggregate_employer_delta_cents=sum(line.employer_delta_cents for line in lines),
        resolved_anomaly_count=sum(len(line.resolved_anomalies) for line in lines),
        p95_latency_ms=p95,
        pass_gates=len(country_runs) >= 250 and len(lines) >= 25 and p95 < 8000,
        lines=lines[:80],
    )
    write_outputs(summary)
    with store_lock():
        con = _connect()
        try:
            con.execute(
                "insert into replay_runs values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    summary.replay_id,
                    summary.rule_hash,
                    summary.country.value,
                    summary.run_count,
                    summary.affected_count,
                    summary.aggregate_net_delta_cents,
                    summary.aggregate_employer_delta_cents,
                    summary.resolved_anomaly_count,
                    summary.p95_latency_ms,
                    summary.pass_gates,
                ],
            )
        finally:
            con.close()
    return summary


def write_outputs(summary: ReplaySummary) -> None:
    out = outputs_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    (out / "impact_lines.json").write_text(
        json.dumps([line.model_dump(mode="json") for line in summary.lines], indent=2),
        encoding="utf-8",
    )
    (out / "report.md").write_text(render_report(summary), encoding="utf-8")


def render_report(summary: ReplaySummary) -> str:
    lines = [
        "# Payroll Rule Diff Impact Report",
        "",
        f"- Replay: `{summary.replay_id}`",
        f"- Rule hash: `{summary.rule_hash}`",
        f"- Country: {summary.country.value}",
        f"- Historical runs: {summary.run_count}",
        f"- Affected workers: {summary.affected_count}",
        f"- Aggregate net delta: {summary.aggregate_net_delta_cents / 100:,.2f}",
        f"- Aggregate employer delta: {summary.aggregate_employer_delta_cents / 100:,.2f}",
        f"- Resolved anomalies: {summary.resolved_anomaly_count}",
        f"- Gates: {'PASS' if summary.pass_gates else 'FAIL'}",
        "",
        "| Worker | Net delta | Employer delta | Resolved anomalies |",
        "| --- | ---: | ---: | --- |",
    ]
    for line in summary.lines[:24]:
        lines.append(
            f"| {line.worker_id} | {line.net_delta_cents / 100:,.2f} | "
            f"{line.employer_delta_cents / 100:,.2f} | {', '.join(line.resolved_anomalies) or '-'} |"
        )
    return "\n".join(lines) + "\n"


def verify_outputs() -> tuple[bool, dict[str, bool]]:
    summary_path = outputs_dir() / "summary.json"
    checks = {
        "payroll_exists": (project_root() / "data" / "payroll_runs.jsonl").exists(),
        "manifest_exists": (project_root() / "data" / "manifest.json").exists(),
        "registry_exists": registry_dir().exists(),
        "latest_rule_exists": (registry_dir() / "latest").exists(),
        "summary_exists": summary_path.exists(),
        "impact_lines_exists": (outputs_dir() / "impact_lines.json").exists(),
        "report_exists": (outputs_dir() / "report.md").exists(),
        "dashboard_exists": (outputs_dir() / "dashboard.html").exists(),
        "store_exists": db_path().exists(),
    }
    if not summary_path.exists() or not checks["latest_rule_exists"]:
        return False, checks
    summary = ReplaySummary.model_validate_json(summary_path.read_text(encoding="utf-8"))
    rule = load_rule(summary.rule_hash)
    checks.update(
        {
            "rule_hash_valid": rule.content_hash == summary.rule_hash,
            "signature_valid": verify_rule_signature(rule),
            "run_count": summary.run_count >= 250,
            "affected_count": summary.affected_count >= 25,
            "impact_lines_present": bool(summary.lines),
            "p95_latency": summary.p95_latency_ms < 8000,
            "pass_gates": summary.pass_gates,
        }
    )
    with store_lock():
        con = _connect()
        try:
            rows = con.execute(
                "select count(*) from replay_runs where replay_id = ?",
                [summary.replay_id],
            ).fetchone()[0]
        finally:
            con.close()
    checks["store_row_present"] = rows == 1
    return all(checks.values()), checks


def benchmark(iterations: int = 100) -> ReplaySummary:
    last = replay_rule("latest")
    for _ in range(iterations - 1):
        last = replay_rule("latest")
    return last


def export_demo_pack() -> Path:
    pack = outputs_dir() / "demo_pack"
    if pack.exists():
        shutil.rmtree(pack)
    pack.mkdir(parents=True)
    for name in ["summary.json", "impact_lines.json", "report.md", "dashboard.html"]:
        shutil.copy2(outputs_dir() / name, pack / name)
    (pack / "manifest.json").write_text(
        json.dumps(
            {
                "name": "payroll-rule-diff-demo-pack",
                "files": sorted(path.name for path in pack.iterdir()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return pack
