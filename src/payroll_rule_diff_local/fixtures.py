from __future__ import annotations

import json
import random
from pathlib import Path

from payroll_rule_diff_local.models import Country, PayrollRun, project_root


def data_dir() -> Path:
    path = project_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def payroll_path() -> Path:
    return data_dir() / "payroll_runs.jsonl"


COUNTRY_BASE = {
    Country.MX: (22_000_00, 0.072, 0.128),
    Country.IT: (3_900_00, 0.0919, 0.302),
    Country.UK: (4_200_00, 0.080, 0.138),
    Country.PH: (78_000_00, 0.045, 0.095),
    Country.BR: (9_500_00, 0.090, 0.205),
}


def generate_payroll(count_per_country: int = 260, force: bool = False) -> Path:
    path = payroll_path()
    if path.exists() and not force:
        return path
    rng = random.Random(424242)
    rows: list[PayrollRun] = []
    for country, (base_gross, employee_rate, employer_rate) in COUNTRY_BASE.items():
        for idx in range(count_per_country):
            multiplier = 0.56 + (idx % 37) * 0.033 + rng.random() * 0.12
            gross = int(base_gross * multiplier)
            employee = int(gross * employee_rate)
            employer = int(gross * (1 + employer_rate))
            anomalies: list[str] = []
            if idx % 41 == 0:
                anomalies.append("floor_mismatch")
            if idx % 53 == 0:
                anomalies.append("cap_boundary")
            if idx % 67 == 0:
                anomalies.append("threshold_edge")
            rows.append(
                PayrollRun(
                    run_id=f"{country.value}-run-{idx:04d}",
                    worker_id=f"{country.value}-worker-{idx:04d}",
                    country=country,
                    period="2026-Q1",
                    gross_pay_cents=gross,
                    base_employee_contrib_cents=employee,
                    base_employer_cost_cents=employer,
                    anomaly_flags=anomalies,
                )
            )
    path.write_text("\n".join(row.model_dump_json() for row in rows) + "\n", encoding="utf-8")
    (data_dir() / "manifest.json").write_text(
        json.dumps(
            {
                "countries": [country.value for country in Country],
                "rows": len(rows),
                "count_per_country": count_per_country,
                "synthetic": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def load_payroll() -> list[PayrollRun]:
    if not payroll_path().exists():
        generate_payroll()
    return [PayrollRun.model_validate_json(line) for line in payroll_path().read_text(encoding="utf-8").splitlines()]
