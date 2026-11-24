"""Replay agent: serves recorded traces. No network, no clock, fully deterministic."""

from __future__ import annotations

from pathlib import Path

from evalkit.cases import Case
from evalkit.trace import Trace, read_traces


class ReplayAgent:
    name = "replay"

    def __init__(self, traces_path: Path) -> None:
        self._traces = read_traces(traces_path)

    async def run(self, case: Case) -> Trace:
        trace = self._traces.get(case.id)
        if trace is None:
            return Trace(case_id=case.id, agent=self.name, error="no recorded trace for case")
        return trace
