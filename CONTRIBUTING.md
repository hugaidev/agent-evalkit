# Contributing

1. `uv sync --all-extras`
2. Make the change with tests, then run
   `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest`.
3. Add or update eval cases with the `new-eval-case` skill (or by hand; see `uv run evalkit schema`).
4. Never loosen a threshold or regenerate the baseline to make the gate pass; explain intentional
   baseline updates in the PR.

Open an issue before large changes. By contributing you agree your work is MIT licensed.
