# Payroll Rule Diff Local

Payroll Rule Diff Local is an offline compliance-rule replay gate for payroll systems. It converts statutory text into typed local rule artifacts, replays the proposed rule against synthetic historical payroll runs, signs approved artifacts into a content-addressed registry, and verifies that unsigned or malformed rules cannot pass release gates.

The project uses synthetic payroll data only. It does not call external payroll systems, model APIs, cloud signing services, or hosted databases.

## Decision surface

Offline payroll rule diff and replay gate with signed local artifacts.

## Evaluator shape

- Deterministic fixtures for Mexico, Italy, United Kingdom, Philippines, and Brazil-style payroll scenarios.
- Typed rule artifacts with provenance hashes, interpreter versioning, parent hashes, content hashes, and local Ed25519 signatures.
- Shadow-payroll replay that reports affected workers, aggregate net-pay delta, employer-cost delta, resolved anomalies, and p95 replay latency.
- DuckDB run store with a local file lock.
- Static light/dark dashboard, Markdown impact report, JSONL tool loop, benchmark, and demo-pack export.
- Verifier that checks registry signatures, replay coverage, performance gates, dashboard/report artifacts, and database persistence.

## Quick path

```bash
uv sync
uv run payroll-rule-diff init-demo
uv run payroll-rule-diff propose --country MX --text "Mexico raises IMSS minimum salary 12.7% effective 2026-04-01"
uv run payroll-rule-diff replay --rule latest
uv run payroll-rule-diff approve-sign --rule latest
uv run payroll-rule-diff verify
uv run payroll-rule-diff dashboard
uv run payroll-rule-diff benchmark --iterations 100
```

## Materialized results

- `outputs/summary.json` for headline metrics and gate status
- `outputs/reports.json` for per-case results
- `outputs/dashboard.html` for visual inspection
- `outputs/demo-pack.zip` or `outputs/demo_pack/` for portable review

## Acceptance checks

```bash
uv run ruff check .
uv run pytest -q
uv run payroll-rule-diff verify
uv run payroll-rule-diff benchmark --iterations 100
```

## Repo boundary

`Payroll Rule Diff Local` is built for local reproduction: deterministic inputs enter the run, deterministic evidence comes out, and private data stays outside the repo.
