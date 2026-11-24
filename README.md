# agent-evalkit

Open source eval harness for MCP agents, with regression gates in CI.

> Changed a prompt or a model and don't know what you broke? Put your expectations in YAML gold
> sets, run them against your agent, and fail the build when behavior regresses.

**Status: milestones 1-4 (runner, metrics, calibrated LLM judge, CI gate).** Deterministic
replay hardening, PyPI release and the dashboard are next; see the roadmap below.

## Quick start

```bash
uv sync
uv run evalkit validate examples/servicedesk-mcp/cases
uv run evalkit run examples/servicedesk-mcp/cases \
  --command "python examples/servicedesk-mcp/scripted_agent.py" --record runs/v1.jsonl
uv run evalkit run examples/servicedesk-mcp/cases --replay runs/v1.jsonl   # offline, deterministic
```

An agent is any program that reads a case as JSON on stdin and prints a trace as JSON
(`evalkit.trace.Trace`) on stdout. Cases are YAML (`evalkit.cases.Case`).

## Roadmap

1. Case format and runner (done)
2. Metrics: task success, groundedness, cost, latency (done)
3. LLM judge + calibration against human labels with Cohen's kappa (done; needs your 50 labels)
4. CI gate comparing prompt versions (done)
5. Deterministic replay in CI, PyPI release, regression dashboard

MIT licensed.

## LLM judge and calibration

Judges use a YAML rubric and a pluggable backend, so you can run with or without an API key:

| `--judge` | Needs | Notes |
|---|---|---|
| `simulated` | nothing | deterministic heuristic, **not an LLM**; for tests and offline demos |
| `agent-sdk` | Claude Code login (`pip install 'agent-evalkit[agent-sdk]'`) | real Claude, no API key |
| `anthropic` | `ANTHROPIC_API_KEY` + `--judge-model` (`[llm]` extra) | direct API |

Calibrate before trusting a judge: label the 50 items in
`examples/servicedesk-mcp/calibration/` (copy `labels.template.csv` to `labels.csv`, fill `label`
with `pass|fail`), then:

```bash
uv run evalkit calibrate --items examples/servicedesk-mcp/calibration/items.jsonl \
  --labels examples/servicedesk-mcp/calibration/labels.csv \
  --rubric examples/servicedesk-mcp/rubrics/helpfulness.yaml --judge agent-sdk
```

It prints Cohen's kappa, accuracy and every disagreement, and exits non-zero below `--min-kappa`
(default 0.6).

## Regression gate in CI

```bash
# 1. record the baseline once (committed as examples/servicedesk-mcp/baselines/main.json)
uv run evalkit run CASES --config evalkit.yaml --command "python agent.py" --out baselines/main.json
# 2. on every change, record the candidate's traces, replay them offline and gate
uv run evalkit run CASES --config evalkit.yaml --replay traces/candidate.jsonl --out runs/c.json --allow-failures
uv run evalkit gate baselines/main.json runs/c.json --config evalkit.yaml --markdown gate.md
```

The gate fails (exit 1) on: any failing safety-critical case or a safety-critical case that
regressed, a task-success drop beyond `max_task_success_drop` (optionally only when an exact
McNemar test is significant, `significance_alpha`), a groundedness drop, cost or p95 latency
increases, missing baseline cases, and (optionally) an uncalibrated judge. Thresholds live under
`gate:` in `evalkit.yaml`. `.github/workflows/eval-gate.yml` runs this on pull requests with no
API key and comments the markdown report on the PR; `eval-live.yml` is the manual/nightly live run.
