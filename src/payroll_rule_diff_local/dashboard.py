# ruff: noqa: E501
from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, select_autoescape

from payroll_rule_diff_local.models import ReplaySummary
from payroll_rule_diff_local.replay import outputs_dir, replay_rule

TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Payroll Rule Diff Local</title>
  <style>
    :root { color-scheme: light; --bg:#f7faf8; --panel:#ffffff; --fg:#17211d; --muted:#5d6e66; --line:#d8e6df; --accent:#0f8b63; --warn:#d3574f; --soft:#e8f3ee; }
    [data-theme="dark"] { color-scheme: dark; --bg:#101614; --panel:#151f1b; --fg:#edf7f2; --muted:#a3b8ae; --line:#294139; --accent:#4cd89f; --warn:#ff8178; --soft:#193229; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--fg); font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { max-width:1180px; margin:0 auto; padding:32px 20px 56px; }
    header { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:24px; }
    h1 { margin:0 0 6px; font-size:clamp(2rem, 4vw, 3.4rem); line-height:1.03; letter-spacing:0; }
    h2 { margin:0 0 16px; font-size:1.08rem; }
    p { margin:0; color:var(--muted); }
    .actions { display:flex; flex-wrap:wrap; gap:10px; justify-content:flex-end; }
    button, .pill { border:1px solid var(--line); background:var(--panel); color:var(--fg); border-radius:999px; padding:9px 13px; font-size:.9rem; }
    .grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:14px; }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; min-width:0; }
    .metric span { display:block; color:var(--muted); font-size:.85rem; margin-bottom:8px; }
    .metric strong { font-size:1.8rem; }
    .wide { grid-column:span 2; }
    .full { grid-column:1 / -1; }
    .bar { display:grid; grid-template-columns:minmax(120px, 1fr) minmax(180px, 2fr) 76px; gap:12px; align-items:center; margin:9px 0; }
    .track { height:13px; background:var(--soft); border-radius:99px; overflow:hidden; }
    .fill { height:100%; background:linear-gradient(90deg, var(--accent), var(--warn)); border-radius:99px; }
    table { width:100%; border-collapse:collapse; }
    th, td { text-align:left; border-bottom:1px solid var(--line); padding:11px 8px; font-size:.92rem; vertical-align:top; }
    th { color:var(--muted); font-weight:650; }
    td, th, p, h1, h2, .bar span { overflow-wrap:anywhere; }
    .pass { color:var(--accent); font-weight:750; }
    .fail { color:var(--warn); font-weight:750; }
    @media (max-width: 840px) { header { flex-direction:column; } .grid { grid-template-columns:1fr; } .wide { grid-column:auto; } .bar { grid-template-columns:1fr; gap:5px; } }
  </style>
  <script>
    function toggleTheme() {
      const root = document.documentElement;
      const next = root.dataset.theme === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      document.querySelector("#themeToggle").textContent = next === "dark" ? "Light" : "Dark";
    }
  </script>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Payroll Rule Diff Local</h1>
      <p>Signed rule artifacts and shadow-payroll replay for statutory change gates.</p>
    </div>
    <div class="actions"><button id="themeToggle" onclick="toggleTheme()" type="button">Dark</button><div class="pill">Replay {{ summary.replay_id }}</div></div>
  </header>
  <section class="grid">
    <div class="panel metric"><span>Runs</span><strong>{{ summary.run_count }}</strong></div>
    <div class="panel metric"><span>Affected</span><strong>{{ summary.affected_count }}</strong></div>
    <div class="panel metric"><span>Resolved</span><strong>{{ summary.resolved_anomaly_count }}</strong></div>
    <div class="panel metric"><span>Gate</span><strong class="{{ 'pass' if summary.pass_gates else 'fail' }}">{{ 'PASS' if summary.pass_gates else 'FAIL' }}</strong></div>
    <div class="panel wide">
      <h2>Impact Magnitude</h2>
      {% for line in bars %}
      <div class="bar"><span>{{ line.worker_id }}</span><div class="track"><div class="fill" style="width:{{ line.width }}%"></div></div><strong>{{ line.amount }}</strong></div>
      {% endfor %}
    </div>
    <div class="panel wide">
      <h2>Release Gates</h2>
      <table>
        <tr><td>Signed artifact</td><td class="pass">required</td></tr>
        <tr><td>Replay coverage</td><td>{{ summary.run_count }} runs</td></tr>
        <tr><td>p95 latency</td><td>{{ summary.p95_latency_ms }} ms</td></tr>
        <tr><td>Aggregate net delta</td><td>{{ net_delta }}</td></tr>
        <tr><td>Aggregate employer delta</td><td>{{ employer_delta }}</td></tr>
      </table>
    </div>
    <div class="panel full">
      <h2>Worker-Level Diff</h2>
      <table>
        <thead><tr><th>Worker</th><th>Net delta</th><th>Employer delta</th><th>Resolved anomalies</th></tr></thead>
        <tbody>
        {% for line in summary.lines[:24] %}
          <tr><td>{{ line.worker_id }}</td><td>{{ '%.2f'|format(line.net_delta_cents / 100) }}</td><td>{{ '%.2f'|format(line.employer_delta_cents / 100) }}</td><td>{{ ', '.join(line.resolved_anomalies) or '-' }}</td></tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </section>
</main>
</body>
</html>
"""


def build_dashboard() -> Path:
    summary_path = outputs_dir() / "summary.json"
    if not summary_path.exists():
        replay_rule()
    summary = ReplaySummary.model_validate_json(summary_path.read_text(encoding="utf-8"))
    strongest = sorted(summary.lines, key=lambda line: abs(line.net_delta_cents) + abs(line.employer_delta_cents), reverse=True)[:10]
    max_amount = max([abs(line.net_delta_cents) + abs(line.employer_delta_cents) for line in strongest] or [1])
    bars = [
        {
            "worker_id": line.worker_id,
            "width": max(8, int((abs(line.net_delta_cents) + abs(line.employer_delta_cents)) / max_amount * 100)),
            "amount": f"{(line.net_delta_cents + line.employer_delta_cents) / 100:,.0f}",
        }
        for line in strongest
    ]
    html = Environment(autoescape=select_autoescape()).from_string(TEMPLATE).render(
        summary=summary,
        bars=bars,
        net_delta=f"{summary.aggregate_net_delta_cents / 100:,.2f}",
        employer_delta=f"{summary.aggregate_employer_delta_cents / 100:,.2f}",
        json=json,
    )
    path = outputs_dir() / "dashboard.html"
    path.write_text(html, encoding="utf-8")
    return path
