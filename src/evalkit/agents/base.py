"""Agent interface: anything that turns a case into a trace."""

from __future__ import annotations

from typing import Protocol

from evalkit.cases import Case
from evalkit.trace import Trace


class Agent(Protocol):
    name: str

    async def run(self, case: Case) -> Trace: ...
