from __future__ import annotations

import json
import sys

import typer
from rich.console import Console
from rich.table import Table

from payroll_rule_diff_local.dashboard import build_dashboard
from payroll_rule_diff_local.fixtures import generate_payroll
from payroll_rule_diff_local.models import Country, ToolRequest
from payroll_rule_diff_local.replay import benchmark, export_demo_pack, replay_rule, verify_outputs
from payroll_rule_diff_local.rules import load_rule, propose_rule, save_rule, sign_rule

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def init_demo(force: bool = typer.Option(False, "--force")) -> None:
    path = generate_payroll(force=force)
    console.print({"payroll": str(path)})


@app.command()
def propose(
    country: str = typer.Option("MX", "--country"),
    text: str = typer.Option("Mexico raises IMSS minimum salary 12.7% effective 2026-04-01", "--text"),
    period: str = typer.Option("2026-Q2", "--period"),
) -> None:
    rule = propose_rule(Country(country), text, period=period)
    save_rule(rule)
    console.print_json(rule.model_dump_json())


@app.command()
def replay(rule: str = typer.Option("latest", "--rule")) -> None:
    summary = replay_rule(rule)
    console.print_json(summary.model_dump_json())


@app.command("approve-sign")
def approve_sign(rule: str = typer.Option("latest", "--rule")) -> None:
    signed = sign_rule(load_rule(rule))
    console.print_json(signed.model_dump_json())


@app.command()
def verify() -> None:
    ok, checks = verify_outputs()
    table = Table(title="Verification")
    table.add_column("Gate")
    table.add_column("Status")
    for key, value in checks.items():
        table.add_row(key, "PASS" if value else "FAIL")
    console.print(table)
    if not ok:
        raise typer.Exit(1)


@app.command()
def dashboard() -> None:
    path = build_dashboard()
    console.print(f"Dashboard written: {path}")


@app.command("benchmark")
def benchmark_cmd(iterations: int = typer.Option(100, "--iterations", min=1)) -> None:
    summary = benchmark(iterations)
    table = Table(title="Benchmark")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("iterations", str(iterations))
    table.add_row("runs", str(summary.run_count))
    table.add_row("affected", str(summary.affected_count))
    table.add_row("p95 latency", f"{summary.p95_latency_ms} ms")
    table.add_row("pass gates", str(summary.pass_gates))
    console.print(table)


@app.command("export-demo-pack")
def export_demo_pack_cmd() -> None:
    path = export_demo_pack()
    console.print(f"Demo pack written: {path}")


@app.command()
def tool_loop() -> None:
    for line in sys.stdin:
        request = ToolRequest.model_validate_json(line)
        args = request.arguments
        if request.tool == "propose":
            rule = propose_rule(Country(args.get("country", "MX")), args.get("text", ""), args.get("period", "2026-Q2"))
            save_rule(rule)
            print(rule.model_dump_json())
        elif request.tool == "replay":
            print(replay_rule(args.get("rule", "latest")).model_dump_json())
        elif request.tool == "approve-sign":
            print(sign_rule(load_rule(args.get("rule", "latest"))).model_dump_json())
        elif request.tool == "verify":
            ok, checks = verify_outputs()
            print(json.dumps({"ok": ok, "checks": checks}))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
