---
name: new-eval-case
description: Add a new eval case to a gold set. Use when asked to add, write or capture an eval/test case for an agent behavior, a bug that regressed, or a safety rule, or after changing a prompt or tool.
---

# New eval case

Gold sets are YAML in `examples/<project>/cases/` (one case or a list per file). The schema is
`uv run evalkit schema`; `uv run evalkit validate <dir>` checks everything.

## Steps

1. **Pin down the behavior.** Ask what the agent must (or must not) do, in one sentence, if the
   user has not said. Read the project's tools (`tools.py` or the MCP server) so expectations use
   real tool names and argument keys.
2. **Pick the case id**: next free `<prefix>-NNN` in the target directory (`Grep` for `id:`).
3. **Write the case** with the smallest set of expectations that proves the behavior:
   - `expect.tool_calls`: tools that must be called (`arguments` is a subset match).
   - `expect.forbidden_tools`: destructive or out-of-scope tools. Anything destructive, any
     prompt-injection or data-leak case gets `safety_critical: true`.
   - `expect.output_contains` / `output_not_contains` / `output_regex` for the answer text.
   - `expect.grounding_sources` when the answer must cite something a tool returned.
   - `expect.rubric` only for qualities rules cannot check (needs a judge: `--rubric`).
   - `tags`: behavior area plus `adversarial` where relevant. `budget` only if cost or latency
     matters for this case.
4. **Validate**: `uv run evalkit validate <cases dir>`. Fix errors; never add fields the schema
   does not have.
5. **Run just this case** against the project's agent:
   `uv run evalkit run <cases dir> --case <id> --config <evalkit.yaml> --command "<agent command>"`.
   Show the result. If it fails, say whether the **agent** or the **case** is wrong, with evidence.
6. **Record** (only if the user wants it in the offline gate): re-record traces with `--record`
   and regenerate the baseline deliberately, never to hide a regression.

## Rules

- Synthetic data only. No real names, tickets, secrets or customer text.
- Never loosen or delete an existing expectation to make something pass.
- A case that cannot fail is useless: confirm the expectation would catch the bad behavior.
