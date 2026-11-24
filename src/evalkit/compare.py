"""Baseline vs candidate: per-case transitions, metric deltas and an exact McNemar test."""

from __future__ import annotations

from math import comb
from pathlib import Path

from pydantic import BaseModel

from evalkit.runner import RunResult


class Comparison(BaseModel):
    regressed: list[str]  # passed in baseline, fails in candidate
    fixed: list[str]  # failed in baseline, passes in candidate
    only_in_baseline: list[str]
    only_in_candidate: list[str]
    safety_regressed: list[str]
    p_value: float  # exact two-sided McNemar on the discordant pairs
    task_success_delta: float
    groundedness_delta: float
    cost_change_pct: float | None  # None when the baseline cost is 0
    latency_p95_change_pct: float | None
    baseline: dict[str, float]
    candidate: dict[str, float]


def mcnemar_exact(regressed: int, fixed: int) -> float:
    """Two-sided exact binomial test on discordant pairs (null: both directions equally likely)."""
    n = regressed + fixed
    if n == 0:
        return 1.0
    k = min(regressed, fixed)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2**n
    return float(min(1.0, 2 * tail))


def _pct(old: float, new: float) -> float | None:
    return None if old == 0 else (new - old) / old * 100


def _headline(r: RunResult) -> dict[str, float]:
    s = r.summary
    return {
        "task_success": s.task_success,
        "groundedness": s.groundedness_mean,
        "cost_mean_usd": s.cost_mean_usd,
        "latency_p95_ms": s.latency_p95_ms,
        "safety_failures": float(s.safety_failures),
    }


def compare(baseline: RunResult, candidate: RunResult) -> Comparison:
    base = {r.case_id: r for r in baseline.results}
    cand = {r.case_id: r for r in candidate.results}
    both = sorted(base.keys() & cand.keys())
    regressed = [i for i in both if base[i].passed and not cand[i].passed]
    fixed = [i for i in both if not base[i].passed and cand[i].passed]
    b, c = baseline.summary, candidate.summary
    return Comparison(
        regressed=regressed,
        fixed=fixed,
        only_in_baseline=sorted(base.keys() - cand.keys()),
        only_in_candidate=sorted(cand.keys() - base.keys()),
        safety_regressed=[i for i in regressed if cand[i].safety_critical],
        p_value=mcnemar_exact(len(regressed), len(fixed)),
        task_success_delta=c.task_success - b.task_success,
        groundedness_delta=c.groundedness_mean - b.groundedness_mean,
        cost_change_pct=_pct(b.cost_mean_usd, c.cost_mean_usd),
        latency_p95_change_pct=_pct(b.latency_p95_ms, c.latency_p95_ms),
        baseline=_headline(baseline),
        candidate=_headline(candidate),
    )


def load_run(path: Path) -> RunResult:
    return RunResult.model_validate_json(path.read_text(encoding="utf-8"))
