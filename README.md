# agent-evalkit

Open source eval harness for MCP agents, with regression gates in CI.

> Changed a prompt or a model and don't know what you broke? Put your expectations in YAML gold
> sets, run them against your agent, and fail the build when behavior regresses.

**Status: milestone 1 (case format + runner).** Metrics, calibrated LLM judge, CI gate and
deterministic replay of live runs are next; see the roadmap below.

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
2. Metrics: task success, groundedness, cost, latency
3. LLM judge calibrated against 50 human labels (Cohen's kappa)
4. CI gate comparing prompt versions
5. Deterministic replay in CI, PyPI release, regression dashboard

MIT licensed.
