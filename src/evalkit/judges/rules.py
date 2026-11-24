"""Deterministic rule judge: tool-call expectations, output assertions, budgets."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

from evalkit.cases import Case, ToolExpect
from evalkit.trace import ToolCall, Trace


class Check(BaseModel):
    name: str
    passed: bool
    detail: str = ""


def _subset(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and _subset(v, actual[k]) for k, v in expected.items()
        )
    return bool(expected == actual)


def _matches(exp: ToolExpect, call: ToolCall) -> bool:
    return call.name == exp.name and _subset(exp.arguments, call.arguments)


def _ordered(expected: list[ToolExpect], calls: list[ToolCall]) -> bool:
    it = iter(calls)
    return all(any(_matches(e, c) for c in it) for e in expected)


def judge_rules(case: Case, trace: Trace, cost_usd: float | None = None) -> list[Check]:
    exp = case.expect
    checks: list[Check] = []

    if trace.error:
        return [Check(name="agent_ran", passed=False, detail=trace.error)]

    if exp.ordered and exp.tool_calls:
        ok = _ordered(exp.tool_calls, trace.tool_calls)
        checks.append(Check(name="tool_order", passed=ok))
    else:
        for e in exp.tool_calls:
            ok = any(_matches(e, c) for c in trace.tool_calls)
            checks.append(Check(name=f"tool_called:{e.name}", passed=ok))

    called = {c.name for c in trace.tool_calls}
    for name in exp.forbidden_tools:
        checks.append(
            Check(
                name=f"tool_forbidden:{name}",
                passed=name not in called,
                detail="called" if name in called else "",
            )
        )
    if case.tools_allowed is not None:
        extra = sorted(called - set(case.tools_allowed))
        checks.append(Check(name="tools_allowed", passed=not extra, detail=", ".join(extra)))

    out = trace.final_output
    for s in exp.output_contains:
        checks.append(Check(name=f"contains:{s}", passed=s.lower() in out.lower()))
    for s in exp.output_not_contains:
        checks.append(Check(name=f"not_contains:{s}", passed=s.lower() not in out.lower()))
    for pattern in exp.output_regex:
        checks.append(Check(name=f"regex:{pattern}", passed=re.search(pattern, out) is not None))

    results_text = json.dumps([c.result for c in trace.tool_calls], default=str).lower()
    for src in exp.grounding_sources:
        cited = src.lower() in out.lower()
        retrieved = src.lower() in results_text
        checks.append(
            Check(
                name=f"grounded:{src}",
                passed=cited and retrieved,
                detail="" if retrieved else "source never retrieved by a tool",
            )
        )

    b = case.budget
    if b.max_cost_usd is not None and cost_usd is not None:
        checks.append(Check(name="budget_cost", passed=cost_usd <= b.max_cost_usd))
    tokens = trace.usage.input_tokens + trace.usage.output_tokens
    if b.max_tokens is not None:
        checks.append(Check(name="budget_tokens", passed=tokens <= b.max_tokens))
    if b.max_latency_ms is not None:
        checks.append(Check(name="budget_latency", passed=trace.latency_ms <= b.max_latency_ms))
    return checks
