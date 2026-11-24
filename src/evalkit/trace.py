"""Trace model: everything an agent did for one case. Versioned so replay stays stable."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

TRACE_SCHEMA_VERSION = 1


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    is_error: bool = False
    latency_ms: float = 0.0


class Trace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = TRACE_SCHEMA_VERSION
    case_id: str
    agent: str = "unknown"
    model: str = ""
    prompt_hash: str = ""
    input_hash: str = ""  # hash of the case input this trace answered (stale-trace guard)
    final_output: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    latency_ms: float = 0.0
    error: str | None = None


def hash_prompt(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def write_traces(path: Path, traces: list[Trace]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (json.dumps(t.model_dump(mode="json"), sort_keys=True) for t in traces)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_traces(path: Path) -> dict[str, Trace]:
    out: dict[str, Trace] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            trace = Trace.model_validate_json(line)
            out[trace.case_id] = trace
    return out
