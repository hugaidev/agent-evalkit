"""Runner: cases -> agent traces -> judges + metrics -> run result."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from pydantic import BaseModel

from evalkit.agents.base import Agent
from evalkit.cases import Case
from evalkit.config import EvalConfig
from evalkit.judges.rules import Check, judge_rules
from evalkit.metrics import bootstrap_ci, cost_usd, groundedness, percentile, unsupported_claims
from evalkit.trace import Trace


class CaseResult(BaseModel):
    case_id: str
    tags: list[str]
    safety_critical: bool
    passed: bool
    checks: list[Check]
    groundedness: float
    unsupported_claims: list[str]
    cost_usd: float
    latency_ms: float
    trace: Trace


class Summary(BaseModel):
    total: int
    passed: int
    task_success: float
    task_success_ci: tuple[float, float]
    safety_failures: int
    groundedness_mean: float
    cost_total_usd: float
    cost_mean_usd: float
    latency_p50_ms: float
    latency_p95_ms: float
    by_tag: dict[str, float]


class RunResult(BaseModel):
    summary: Summary
    results: list[CaseResult]


def summarize(results: list[CaseResult], config: EvalConfig) -> Summary:
    total = len(results)
    outcomes = [1.0 if r.passed else 0.0 for r in results]
    tags: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        for t in r.tags:
            tags[t].append(r.passed)
    costs = [r.cost_usd for r in results]
    lats = [r.latency_ms for r in results]
    return Summary(
        total=total,
        passed=sum(r.passed for r in results),
        task_success=sum(outcomes) / total if total else 0.0,
        task_success_ci=bootstrap_ci(outcomes, config.bootstrap_samples, config.seed),
        safety_failures=sum(1 for r in results if r.safety_critical and not r.passed),
        groundedness_mean=sum(r.groundedness for r in results) / total if total else 0.0,
        cost_total_usd=sum(costs),
        cost_mean_usd=sum(costs) / total if total else 0.0,
        latency_p50_ms=percentile(lats, 50),
        latency_p95_ms=percentile(lats, 95),
        by_tag={t: sum(v) / len(v) for t, v in sorted(tags.items())},
    )


async def run_cases(
    cases: list[Case], agent: Agent, concurrency: int = 4, config: EvalConfig | None = None
) -> RunResult:
    cfg = config or EvalConfig()
    sem = asyncio.Semaphore(concurrency)

    async def one(case: Case) -> CaseResult:
        async with sem:
            trace = await agent.run(case)
        cost = cost_usd(trace, cfg)
        checks = judge_rules(case, trace, cost)
        return CaseResult(
            case_id=case.id,
            tags=case.tags,
            safety_critical=case.safety_critical,
            passed=all(c.passed for c in checks),
            checks=checks,
            groundedness=groundedness(case, trace, cfg),
            unsupported_claims=unsupported_claims(case, trace, cfg),
            cost_usd=cost,
            latency_ms=trace.latency_ms,
            trace=trace,
        )

    results = list(await asyncio.gather(*(one(c) for c in cases)))
    return RunResult(summary=summarize(results, cfg), results=results)
