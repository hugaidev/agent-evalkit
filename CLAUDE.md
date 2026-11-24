# agent-evalkit

Eval harness for MCP agents: YAML gold sets, runner, rule + LLM judges, kappa calibration,
regression gate, deterministic replay. Python 3.12, uv, pydantic v2.

## Commands

- `uv sync --all-extras`, then `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`,
  `uv run pytest` (coverage gate 85%). All four must pass before a commit.
- `python` is not on PATH on the dev machine: always go through `uv run`.

## Rules

- Never weaken a gate threshold, delete a case or regenerate a baseline to turn a run green.
  Regressions are fixed in the agent, or the baseline is updated deliberately in its own commit.
- The `simulated` judge is a heuristic, not an LLM. Never describe it as one. Real calibration
  needs human labels written by a person; never fabricate labels or kappa results.
- No API keys in the repo or logs. PR workflows must not need secrets (fork-safe); live runs live
  in `eval-live.yml`.
- Reports must stay deterministic: no timestamps or random seeds outside `config.seed`.
- Synthetic data only in examples.

## Layout

`src/evalkit/` core; `examples/servicedesk-mcp/` demo (tools, scripted agent, MCP server, cases,
rubrics, calibration items, recorded traces, baseline); `.claude/` skill `new-eval-case` and
subagent `adversarial-case-proposer`; `proposals/` is where proposed cases wait for review.
