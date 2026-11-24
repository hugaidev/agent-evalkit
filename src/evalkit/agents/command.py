"""Command agent: run any external program. Case JSON on stdin, Trace JSON on stdout."""

from __future__ import annotations

import asyncio
import shlex
import time

from evalkit.cases import Case
from evalkit.trace import Trace


class CommandAgent:
    name = "command"

    def __init__(self, command: str, timeout_s: float = 120.0) -> None:
        self._argv = shlex.split(command)
        self._timeout = timeout_s

    async def run(self, case: Case) -> Trace:
        start = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(
                proc.communicate(case.model_dump_json().encode()), self._timeout
            )
        except (TimeoutError, OSError) as exc:
            return Trace(case_id=case.id, agent=self.name, error=f"agent failed: {exc!r}")
        if proc.returncode != 0:
            msg = err.decode(errors="replace")[-500:]
            return Trace(case_id=case.id, agent=self.name, error=f"exit {proc.returncode}: {msg}")
        try:
            trace = Trace.model_validate_json(out)
        except ValueError as exc:
            return Trace(case_id=case.id, agent=self.name, error=f"invalid trace: {exc}")
        if trace.latency_ms == 0.0:
            trace.latency_ms = (time.perf_counter() - start) * 1000
        return trace
