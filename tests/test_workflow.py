from __future__ import annotations

import json
import subprocess

from payroll_rule_diff_local.dashboard import build_dashboard
from payroll_rule_diff_local.fixtures import generate_payroll, load_payroll
from payroll_rule_diff_local.models import Country
from payroll_rule_diff_local.replay import export_demo_pack, replay_rule, verify_outputs
from payroll_rule_diff_local.rules import propose_rule, save_rule, sign_rule, verify_rule_signature


def test_fixture_generation_is_synthetic_and_multi_country() -> None:
    generate_payroll(force=True)
    rows = load_payroll()
    assert len(rows) == 1300
    assert {row.country for row in rows} == set(Country)


def test_propose_rule_is_content_addressed() -> None:
    rule = propose_rule(Country.MX, "Mexico raises IMSS minimum salary 12.7% effective 2026-04-01")
    assert rule.content_hash
    assert rule.country == Country.MX
    assert rule.signature is None
    assert rule.parameters["minimum_salary_uplift_pct"] == 12.7


def test_sign_and_verify_rule() -> None:
    rule = propose_rule(Country.IT, "Italy INPS contribution cap becomes 119650 effective 2026-04-01")
    save_rule(rule)
    signed = sign_rule(rule)
    assert signed.signature
    assert verify_rule_signature(signed)


def test_replay_detects_impact_and_passes_gates() -> None:
    generate_payroll(force=True)
    signed = sign_rule(propose_rule(Country.MX, "Mexico raises IMSS minimum salary 12.7% effective 2026-04-01"))
    summary = replay_rule(signed.content_hash)
    assert summary.pass_gates
    assert summary.run_count >= 250
    assert summary.affected_count >= 25
    assert summary.resolved_anomaly_count >= 1


def test_dashboard_demo_pack_and_verify() -> None:
    signed = sign_rule(propose_rule(Country.UK, "UK NIC threshold changes to 12570 effective 2026-04-01"))
    replay_rule(signed.content_hash)
    dashboard = build_dashboard()
    html = dashboard.read_text(encoding="utf-8")
    assert "Payroll Rule Diff Local" in html
    assert "Impact Magnitude" in html
    assert "themeToggle" in html
    pack = export_demo_pack()
    assert (pack / "manifest.json").exists()
    ok, checks = verify_outputs()
    assert ok, checks


def test_jsonl_tool_loop() -> None:
    payloads = [
        {"tool": "propose", "arguments": {"country": "PH", "text": "Philippines contribution table rate 5%"}},
        {"tool": "approve-sign", "arguments": {"rule": "latest"}},
        {"tool": "replay", "arguments": {"rule": "latest"}},
    ]
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            "elite_projects/payroll-rule-diff-local",
            "payroll-rule-diff",
            "tool-loop",
        ],
        input="\n".join(json.dumps(payload) for payload in payloads) + "\n",
        text=True,
        capture_output=True,
        check=True,
    )
    last = json.loads(completed.stdout.splitlines()[-1])
    assert last["pass_gates"]
