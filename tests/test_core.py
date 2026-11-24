from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from evalkit.agents import ReplayAgent
from evalkit.cases import Case, CaseError, load_cases
from evalkit.cli import main
from evalkit.judges import judge_rules
from evalkit.runner import run_cases
from evalkit.trace import ToolCall, Trace, write_traces

EXAMPLE = Path(__file__).parent.parent / "examples" / "servicedesk-mcp"


def _case(**kw: object) -> Case:
    return Case.model_validate({"id": "c1", "input": "hi", **kw})


def test_load_cases_example() -> None:
    cases = load_cases(EXAMPLE / "cases")
    assert len(cases) == 6
    assert any(c.safety_critical for c in cases)


def test_load_rejects_duplicates_and_unknown_fields(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("- {id: x, input: a}\n- {id: x, input: b}\n")
    with pytest.raises(CaseError, match="duplicate"):
        load_cases(tmp_path)
    (tmp_path / "a.yaml").write_text("- {id: x, input: a, bogus: 1}\n")
    with pytest.raises(CaseError):
        load_cases(tmp_path)
    with pytest.raises(CaseError, match="no cases"):
        load_cases(tmp_path / "z")


def test_rules_tool_subset_forbidden_and_output() -> None:
    case = _case(
        expect={
            "tool_calls": [{"name": "get_ticket", "arguments": {"ticket_id": "T-1"}}],
            "forbidden_tools": ["delete_ticket"],
            "output_contains": ["Open"],
            "output_not_contains": ["secret"],
            "output_regex": [r"T-\d"],
        },
        budget={"max_tokens": 10, "max_latency_ms": 5},
    )
    trace = Trace(
        case_id="c1",
        final_output="T-1 is open",
        tool_calls=[ToolCall(name="get_ticket", arguments={"ticket_id": "T-1", "x": 1})],
    )
    assert all(c.passed for c in judge_rules(case, trace))
    trace.tool_calls.append(ToolCall(name="delete_ticket"))
    assert not all(c.passed for c in judge_rules(case, trace))


def test_rules_order_allowed_and_error() -> None:
    case = _case(
        tools_allowed=["a"],
        expect={"ordered": True, "tool_calls": [{"name": "a"}, {"name": "b"}]},
    )
    ok = Trace(case_id="c1", tool_calls=[ToolCall(name="a"), ToolCall(name="b")])
    names = {c.name: c.passed for c in judge_rules(case, ok)}
    assert names["tool_order"]
    assert not names["tools_allowed"]
    bad = Trace(case_id="c1", tool_calls=[ToolCall(name="b"), ToolCall(name="a")])
    assert not {c.name: c.passed for c in judge_rules(case, bad)}["tool_order"]
    err = judge_rules(case, Trace(case_id="c1", error="boom"))
    assert err[0].name == "agent_ran"
    assert not err[0].passed


def _run_cli(*args: str) -> int:
    return main(list(args))


def test_cli_end_to_end_and_replay_is_deterministic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(EXAMPLE))
    agent = EXAMPLE / "scripted_agent.py"
    cmd = f'"{Path(sys.executable).as_posix()}" "{agent.as_posix()}"'
    traces = tmp_path / "traces.jsonl"
    cases = str(EXAMPLE / "cases")
    src = EXAMPLE.parent.parent / "src"
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(EXAMPLE), str(src)]))
    conf = str(EXAMPLE / "evalkit.yaml")
    assert _run_cli("run", cases, "--command", cmd, "--record", str(traces), "--config", conf) == 0
    out = capsys.readouterr().out
    assert "passed=6" in out
    assert "groundedness=" in out

    out1, out2 = tmp_path / "r1.json", tmp_path / "r2.json"
    assert _run_cli("run", cases, "--replay", str(traces), "--out", str(out1)) == 0
    assert _run_cli("run", cases, "--replay", str(traces), "--out", str(out2)) == 0
    assert out1.read_bytes() == out2.read_bytes()

    # v2 prompt regression: obeys the injection and fails the safety-critical case
    monkeypatch.setenv("PROMPT_VERSION", "v2")
    assert _run_cli("run", cases, "--command", cmd) == 1
    assert "FAIL sd-006" in capsys.readouterr().out
    assert json.loads(out1.read_text())["summary"]["safety_failures"] == 0


def test_replay_missing_trace_and_cli_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_traces(tmp_path / "t.jsonl", [Trace(case_id="other")])
    res = asyncio.run(run_cases([_case()], ReplayAgent(tmp_path / "t.jsonl")))
    assert res.summary.passed == 0
    assert res.summary.safety_failures == 0
    assert _run_cli("validate", str(EXAMPLE / "cases")) == 0
    assert _run_cli("validate", str(tmp_path / "nope")) == 2
    with pytest.raises(SystemExit):
        _run_cli("run", str(EXAMPLE / "cases"))
