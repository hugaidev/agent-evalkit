"""Regression gate: turn a Comparison into pass/fail rules and a markdown report for the PR."""

from __future__ import annotations

from pydantic import BaseModel

from evalkit.calibration.calibrate import CalibrationReport
from evalkit.compare import Comparison
from evalkit.config import GateConfig


class Rule(BaseModel):
    name: str
    passed: bool
    detail: str


class GateResult(BaseModel):
    passed: bool
    rules: list[Rule]


def evaluate(
    cmp: Comparison, cfg: GateConfig, calibration: CalibrationReport | None = None
) -> GateResult:
    rules: list[Rule] = []

    def add(name: str, passed: bool, detail: str) -> None:
        rules.append(Rule(name=name, passed=passed, detail=detail))

    cand_safety = int(cmp.candidate["safety_failures"])
    add(
        "safety_failures",
        cand_safety <= cfg.max_safety_failures,
        f"{cand_safety} failing safety-critical case(s), max {cfg.max_safety_failures}",
    )
    add(
        "safety_regressions",
        not cmp.safety_regressed,
        ", ".join(cmp.safety_regressed) or "none",
    )

    drop = -cmp.task_success_delta
    drop_exceeds = drop > cfg.max_task_success_drop
    significant = cfg.significance_alpha is None or cmp.p_value < cfg.significance_alpha
    add(
        "task_success_drop",
        not (drop_exceeds and significant),
        f"{cmp.baseline['task_success']:.1%} -> {cmp.candidate['task_success']:.1%} "
        f"(drop {max(drop, 0):.1%}, max {cfg.max_task_success_drop:.1%}, p={cmp.p_value:.3f})",
    )

    g_drop = -cmp.groundedness_delta
    add(
        "groundedness_drop",
        g_drop <= cfg.max_groundedness_drop,
        f"{cmp.baseline['groundedness']:.2f} -> {cmp.candidate['groundedness']:.2f}",
    )

    for name, change, limit in (
        ("cost_increase", cmp.cost_change_pct, cfg.max_cost_increase_pct),
        ("latency_p95_increase", cmp.latency_p95_change_pct, cfg.max_latency_p95_increase_pct),
    ):
        if limit is None:
            continue
        ok = change is None or change <= limit
        shown = "n/a (baseline is 0)" if change is None else f"{change:+.1f}%"
        add(name, ok, f"{shown}, max +{limit:.0f}%")

    if cfg.fail_on_missing_cases:
        missing = cmp.only_in_baseline
        add("cases_present", not missing, ", ".join(missing) or "all baseline cases ran")

    if cfg.require_calibrated_judge:
        if calibration is None:
            add("judge_calibrated", False, "no calibration report provided")
        else:
            add(
                "judge_calibrated",
                calibration.calibrated,
                f"kappa={calibration.kappa:.2f}, min {calibration.min_kappa:.2f}",
            )

    return GateResult(passed=all(r.passed for r in rules), rules=rules)


def render_markdown(cmp: Comparison, result: GateResult, title: str = "evalkit gate") -> str:
    icon = "✅" if result.passed else "❌"
    lines = [f"## {icon} {title}: {'passed' if result.passed else 'FAILED'}", ""]
    lines += ["| Rule | Result | Detail |", "|---|---|---|"]
    lines += [f"| {r.name} | {'✅' if r.passed else '❌'} | {r.detail} |" for r in result.rules]
    lines += ["", "| Metric | Baseline | Candidate |", "|---|---|---|"]
    for key in cmp.baseline:
        lines.append(f"| {key} | {cmp.baseline[key]:.4g} | {cmp.candidate[key]:.4g} |")
    if cmp.regressed:
        lines += ["", f"**Regressed cases:** {', '.join(cmp.regressed)}"]
    if cmp.fixed:
        lines += ["", f"**Fixed cases:** {', '.join(cmp.fixed)}"]
    return "\n".join(lines) + "\n"
