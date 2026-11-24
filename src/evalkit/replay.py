"""Tool cassettes: replay recorded tool results to a *live* agent, deterministically.

``ReplayAgent`` replays whole traces (the agent does not run). A cassette instead lets a changed
agent (new prompt, new model) run for real while its tools answer from a recording, so tool
behavior is held constant and any difference comes from the agent. A tool call that was never
recorded raises ``MissingRecording``: new agent behavior is surfaced, never silently invented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evalkit.trace import Trace


class MissingRecording(KeyError):
    """The agent made a tool call that is not in the cassette."""


def _key(name: str, arguments: dict[str, Any]) -> str:
    return name + json.dumps(arguments, sort_keys=True, default=str)


class Cassette:
    def __init__(self, entries: dict[str, Any] | None = None) -> None:
        self._entries: dict[str, Any] = entries or {}

    @classmethod
    def from_traces(cls, traces: list[Trace]) -> Cassette:
        entries: dict[str, Any] = {}
        for trace in traces:
            for call in trace.tool_calls:
                entries[_key(call.name, call.arguments)] = call.result
        return cls(entries)

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        try:
            return self._entries[_key(name, arguments)]
        except KeyError:
            raise MissingRecording(f"unrecorded tool call: {name}({arguments})") from None

    def __len__(self) -> int:
        return len(self._entries)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self._entries, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> Cassette:
        return cls(json.loads(path.read_text(encoding="utf-8")))
