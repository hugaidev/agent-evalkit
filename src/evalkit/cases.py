"""Gold-set case format (YAML) and loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ToolExpect(BaseModel):
    """A tool the agent must call; ``arguments`` is a subset match."""

    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_tokens: int | None = None
    max_latency_ms: float | None = None
    max_cost_usd: float | None = None


class Expect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_calls: list[ToolExpect] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    ordered: bool = False
    output_contains: list[str] = Field(default_factory=list)
    output_not_contains: list[str] = Field(default_factory=list)
    output_regex: list[str] = Field(default_factory=list)
    rubric: str | None = None
    grounding_sources: list[str] = Field(default_factory=list)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    input: str
    tags: list[str] = Field(default_factory=list)
    tools_allowed: list[str] | None = None
    expect: Expect = Field(default_factory=Expect)
    safety_critical: bool = False
    budget: Budget = Field(default_factory=Budget)


class CaseError(ValueError):
    pass


def load_cases(path: Path) -> list[Case]:
    """Load cases from a YAML file (one case or a list) or a directory of YAML files."""
    if not path.exists():
        raise CaseError(f"no cases found under {path}")
    files = sorted(path.rglob("*.y*ml")) if path.is_dir() else [path]
    cases: list[Case] = []
    seen: set[str] = set()
    for file in files:
        raw = yaml.safe_load(file.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            try:
                case = Case.model_validate(item)
            except ValueError as exc:
                raise CaseError(f"{file}: {exc}") from exc
            if case.id in seen:
                raise CaseError(f"{file}: duplicate case id {case.id!r}")
            seen.add(case.id)
            cases.append(case)
    if not cases:
        raise CaseError(f"no cases found under {path}")
    return cases
