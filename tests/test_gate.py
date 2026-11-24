from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalkit.calibration.calibrate import CalibrationReport
from evalkit.cli import main
from evalkit.compare import compare, load_run, mcnemar_exact
from evalkit.config import EvalConfig, GateConfig
from evalkit.gate import evaluate, render_markdown
from evalkit.runner import CaseResult, RunResult, summarize
from evalkit.trace import Trace

EXAMPLE = Path(__file__).parent.parent / "examples" / "servicedesk-mcp"
CONFIG = EXAMPLE / "evalkit.yaml"
CASES = str(EXAMPLE / "cases")


def _res(
    case_id: str, passed: bool, *, safety: bool = False, cost: float = 1.0, lat: float = 100.0
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        tags=[],
        safety_critical=safety,
        passed=passed,
        checks=[],
        groundedness=1.0,
        unsupported_claims=[],
        cost_usd=cost,
        latency_ms=lat,
        trace=Trace(case_id=case_id),
    )


def _run(results: list[CaseResult]) -> RunResult:
    return RunResult(summary=summarize(results, EvalConfig()), results=results)


def test_mcnemar_exact() -> None:
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(5, 5) == 1.0
    assert mcnemar_exact(0, 5) == pytest.approx(2 / 32)
    assert mcnemar_exact(1, 0) == 1.0  # capped at 1


def test_compare_transitions_and_deltas() -> None:
    base = _run(
        [_res("a", True), _res("b", False), _res("c", True, safety=True), _res("old", True)]
    )
    cand = _run(
        [
            _res("a", True),
            _res("b", True),
            _res("c", False, safety=True, cost=2.0, lat=200.0),
            _res("new", True),
        ]
    )
    cmp = compare(base, cand)
    assert cmp.regressed == ["c"]
    assert cmp.fixed == ["b"]
    assert cmp.safety_regressed == ["c"]
    assert cmp.only_in_baseline == ["old"]
    assert cmp.only_in_candidate == ["new"]
    assert cmp.cost_change_pct == pytest.approx(25.0)
    assert cmp.latency_p95_change_pct is not None


def test_gate_rules_pass_and_fail() -> None:
    same = _run([_res("a", True), _res("b", True)])
    ok = evaluate(compare(same, same), GateConfig())
    assert ok.passed
    assert "passed" in render_markdown(compare(same, same), ok)

    worse = _run([_res("a", True), _res("b", False)])
    cmp = compare(same, worse)
    failed = evaluate(cmp, GateConfig())
    assert not failed.passed
    assert not {r.name: r for r in failed.rules}["task_success_drop"].passed
    md = render_markdown(cmp, failed)
    assert "FAILED" in md
    assert "Regressed cases" in md
    # with a significance requirement, one discordant pair is not enough evidence
    lenient = evaluate(cmp, GateConfig(significance_alpha=0.05))
    assert {r.name: r for r in lenient.rules}["task_success_drop"].passed


def test_gate_cost_latency_missing_and_calibration() -> None:
    base = _run([_res("a", True), _res("b", True)])
    cand = _run([_res("a", True, cost=3.0, lat=300.0)])
    cmp = compare(base, cand)
    rules = {r.name: r for r in evaluate(cmp, GateConfig()).rules}
    assert not rules["cost_increase"].passed
    assert not rules["latency_p95_increase"].passed
    assert not rules["cases_present"].passed
    off = {r.name for r in evaluate(cmp, GateConfig(max_cost_increase_pct=None)).rules}
    assert "cost_increase" not in off

    need = GateConfig(require_calibrated_judge=True)
    assert not {r.name: r for r in evaluate(cmp, need).rules}["judge_calibrated"].passed
    bad = CalibrationReport(
        n=50, kappa=0.3, band="fair", accuracy=0.7, confusion={}, disagreements=[],
        min_kappa=0.6, calibrated=False,
    )  # fmt: skip
    assert (
        "kappa=0.30"
        in {r.name: r for r in evaluate(cmp, need, bad).rules}["judge_calibrated"].detail
    )
    zero = compare(_run([_res("a", True, cost=0.0)]), _run([_res("a", True, cost=5.0)]))
    assert zero.cost_change_pct is None
    assert {r.name: r for r in evaluate(zero, GateConfig()).rules}["cost_increase"].passed


def test_cli_gate_on_recorded_traces(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def replay(name: str) -> Path:
        out = tmp_path / f"{name}.json"
        code = main(
            ["run", CASES, "--config", str(CONFIG), "--allow-failures", "--out", str(out),
             "--replay", str(EXAMPLE / "traces" / f"{name}.jsonl")]
        )  # fmt: skip
        assert code == 0
        return out

    baseline = EXAMPLE / "baselines" / "main.json"
    md = tmp_path / "gate.md"
    # candidate.jsonl is what CI replays on PRs: it must pass the gate
    assert main(["gate", str(baseline), str(replay("candidate")), "--config", str(CONFIG)]) == 0
    # v2 simulates a prompt regression that obeys an injection: the gate must block it
    v2 = replay("v2")
    assert (
        main(["gate", str(baseline), str(v2), "--config", str(CONFIG), "--markdown", str(md)]) == 1
    )
    assert "sd-006" in md.read_text(encoding="utf-8")
    assert main(["compare", str(baseline), str(v2)]) == 0
    assert "regressed=['sd-006']" in capsys.readouterr().out
    assert len(load_run(v2).results) == 6
    assert json.loads(v2.read_text())["summary"]["safety_failures"] == 1
