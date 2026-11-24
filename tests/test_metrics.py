from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from evalkit.cases import Case
from evalkit.config import EvalConfig, Pricing, load_config
from evalkit.judges import judge_rules
from evalkit.metrics import bootstrap_ci, cost_usd, groundedness, percentile, unsupported_claims
from evalkit.runner import run_cases
from evalkit.trace import ToolCall, Trace, Usage

EXAMPLE = Path(__file__).parent.parent / "examples" / "servicedesk-mcp"


def _case(**kw: object) -> Case:
    return Case.model_validate({"id": "c1", "input": "status of T-1?", **kw})


def test_percentile_interpolates() -> None:
    assert percentile([], 50) == 0.0
    assert percentile([10], 95) == 10
    assert percentile([0, 10, 20, 30], 50) == pytest.approx(15)
    assert percentile([0, 100], 95) == pytest.approx(95)


def test_bootstrap_is_deterministic_and_brackets_mean() -> None:
    vals = [1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0]
    a = bootstrap_ci(vals, 500, seed=1)
    assert a == bootstrap_ci(vals, 500, seed=1)
    assert a[0] <= sum(vals) / len(vals) <= a[1]
    assert bootstrap_ci([], 10) == (0.0, 0.0)


def test_cost_uses_model_price_or_default() -> None:
    cfg = EvalConfig(
        pricing={"m": Pricing(input_per_mtok=2, output_per_mtok=10, cache_read_per_mtok=1)},
        default_pricing=Pricing(input_per_mtok=1),
    )
    usage = Usage(input_tokens=1_000_000, output_tokens=500_000, cache_read_tokens=1_000_000)
    assert cost_usd(Trace(case_id="c", model="m", usage=usage), cfg) == pytest.approx(8.0)
    assert cost_usd(Trace(case_id="c", model="other", usage=usage), cfg) == pytest.approx(1.0)


def test_groundedness_flags_invented_claims() -> None:
    cfg = EvalConfig()
    case = _case()
    ok = Trace(
        case_id="c1",
        final_output="T-1 is open, see KB-12",
        tool_calls=[ToolCall(name="search_kb", result={"results": ["fix. Source: KB-12"]})],
    )
    assert groundedness(case, ok, cfg) == 1.0
    bad = ok.model_copy(update={"final_output": "T-1 is open, see KB-99 and T-7"})
    assert unsupported_claims(case, bad, cfg) == ["KB-99", "T-7"]
    assert groundedness(case, bad, cfg) == pytest.approx(1 / 3)
    assert groundedness(case, Trace(case_id="c1", final_output="no claims here"), cfg) == 1.0


def test_grounding_sources_and_cost_budget_checks() -> None:
    case = _case(expect={"grounding_sources": ["KB-12"]}, budget={"max_cost_usd": 0.001})
    cited_not_retrieved = Trace(case_id="c1", final_output="see KB-12")
    names = {c.name: c for c in judge_rules(case, cited_not_retrieved, cost_usd=0.01)}
    assert not names["grounded:KB-12"].passed
    assert "never retrieved" in names["grounded:KB-12"].detail
    assert not names["budget_cost"].passed
    retrieved = Trace(
        case_id="c1",
        final_output="see KB-12",
        tool_calls=[ToolCall(name="search_kb", result="Source: KB-12")],
    )
    assert all(c.passed for c in judge_rules(case, retrieved, cost_usd=0.0005))


def test_load_config_and_summary_metrics(tmp_path: Path) -> None:
    assert load_config(None) == EvalConfig()
    (tmp_path / "empty.yaml").write_text("")
    assert load_config(tmp_path / "empty.yaml") == EvalConfig()
    cfg = load_config(EXAMPLE / "evalkit.yaml")

    class Fixed:
        name = "fixed"

        async def run(self, case: Case) -> Trace:
            return Trace(
                case_id=case.id,
                model="scripted-1",
                final_output="ok",
                usage=Usage(input_tokens=1000, output_tokens=1000),
                latency_ms=float(100 * (1 + int(case.id[-1]))),
            )

    cases = [_case(id=f"c{i}", tags=["x"]) for i in range(4)]
    res = asyncio.run(run_cases(cases, Fixed(), config=cfg))
    s = res.summary
    assert s.task_success == 1.0
    assert s.cost_total_usd == pytest.approx(4 * 0.018)
    assert s.latency_p50_ms == pytest.approx(250)
    assert s.latency_p95_ms == pytest.approx(385)
    assert s.groundedness_mean == 1.0
    assert s.by_tag == {"x": 1.0}
