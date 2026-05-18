# Security Review

## Scope

Local CLI, synthetic payroll fixtures, deterministic rule proposer, local signing registry, shadow-payroll replay, DuckDB run store, JSONL tool loop, static dashboard, and demo-pack export.

## Assessment

Complete. No reportable security findings were identified.

## Controls

- Synthetic payroll runs only; no real worker, employer, payroll, or customer data.
- No network clients or hosted services in the runtime path.
- Rule artifacts and tool-loop payloads are parsed through Pydantic models.
- Rule hashes are content-addressed from canonical JSON.
- Approved artifacts use local Ed25519 signatures stored under ignored runtime state.
- DuckDB writes use parameterized inserts and a local file lock.
- Dashboard rendering uses Jinja autoescaping.
- Runtime data, outputs, registry artifacts, signing keys, caches, and virtual environments are ignored by git.

## Validation Evidence

- `ruff check` passed for the full project.
- `pytest -q` passed all workflow tests.
- CLI verification passed every gate, including signed rule validation, replay coverage, impact lines, p95 latency, report/dashboard artifacts, and DuckDB persistence.
- A 100-iteration benchmark passed with 260 replayed runs, 260 affected workers, and 1 ms p95 replay latency in the synthetic fixture.
- Browser validation confirmed expected dashboard content, visual impact bars, theme control, no horizontal overflow, and no panel overlap.

## Focused Scan Results

- Public hygiene scan found no sensitive, private-targeting, or credential material in publishable files.
- Runtime surface scan found no application network clients, shell execution, dynamic code execution, unsafe deserialization, or credential handling.
- The only `subprocess` usage is in tests, where it invokes the local CLI through the project-managed `uv` environment.
- Local signing material is generated under ignored runtime state and is not part of the publishable source set.
