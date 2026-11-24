# agent-evalkit

Open source eval harness for MCP agents, with regression gates in CI.

> Changed a prompt or a model and don't know what you broke? Put your expectations in YAML gold
> sets, run them against your agent, and fail the build when behavior regresses.

**Status: all six milestones implemented** (runner, metrics, calibrated judge, CI gate,
deterministic replay, Claude Code skill and subagent, dashboard). Not yet on PyPI.

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
5. Deterministic replay: traces, stale-trace guard, tool cassettes (done)
6. Claude Code skill and subagent, regression dashboard (done); PyPI release (pending)

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

## Deterministic replay

- **Trace replay** (`--replay`): the agent does not run; recorded traces are judged again. Reports
  are byte-identical across runs. Traces store a hash of the case input, so editing a case makes its
  trace *stale* and the case fails with "re-record" instead of silently judging old behavior.
- **Tool cassettes** (`evalkit cassette traces.jsonl --out cassette.json`): run a *changed* agent
  for real while tool results come from the recording, so only the agent varies. An agent that
  makes a tool call that was never recorded aborts that case with `unrecorded tool call`.
  The example agent reads `EVALKIT_CASSETTE`; see `evalkit.replay.Cassette` for your own agent.
- **Prompt drift**: traces carry a prompt hash; the gate report notes when baseline and candidate
  prompts differ.

## Dashboard, schema and Claude Code

- `evalkit report runs/*.json --html dashboard.html`: self-contained page (task success trend,
  safety failures, cost, latency, regressions between consecutive runs).
- `evalkit schema` prints the JSON Schema for case files (editor validation);
  `evalkit run ... --case sd-006` runs a single case.
- `.claude/skills/new-eval-case`: `/new-eval-case` interviews you, writes and validates a case,
  and runs it. `.claude/agents/adversarial-case-proposer` writes candidate adversarial cases to
  `proposals/` for a human to review and promote.
- `examples/servicedesk-mcp/server.py`: the demo tools as a real MCP server
  (`pip install 'agent-evalkit[mcp]'`).

## Releasing

`release.yml` publishes to PyPI on a `v*` tag using trusted publishing (no token). Configure a
pending publisher on PyPI first (see the comment at the top of the workflow).
