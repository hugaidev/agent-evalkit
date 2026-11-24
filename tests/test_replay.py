from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from evalkit.agents import ReplayAgent
from evalkit.cases import Case, load_cases
from evalkit.cli import main
from evalkit.replay import Cassette, MissingRecording
from evalkit.runner import run_cases
from evalkit.trace import ToolCall, Trace, read_traces, write_traces

EXAMPLE = Path(__file__).parent.parent / "examples" / "servicedesk-mcp"
CASES = str(EXAMPLE / "cases")
CONFIG = str(EXAMPLE / "evalkit.yaml")


def test_recorded_traces_carry_input_hash() -> None:
    traces = read_traces(EXAMPLE / "traces" / "v1.jsonl")
    assert len(traces) == 6
    assert all(t.input_hash for t in traces.values())


def test_stale_trace_is_rejected_after_case_changes(tmp_path: Path) -> None:
    cases = load_cases(EXAMPLE / "cases")
    agent = ReplayAgent(EXAMPLE / "traces" / "v1.jsonl")
    assert asyncio.run(run_cases(cases, agent)).summary.passed >= 1
    edited = [c.model_copy(update={"input": c.input + " (edited)"}) for c in cases]
    res = asyncio.run(run_cases(edited, agent))
    assert res.summary.passed == 0
    assert "stale trace" in (res.results[0].trace.error or "")


def test_old_traces_without_input_hash_still_replay(tmp_path: Path) -> None:
    write_traces(tmp_path / "t.jsonl", [Trace(case_id="c1", final_output="hi")])
    case = Case.model_validate({"id": "c1", "input": "q", "expect": {"output_contains": ["hi"]}})
    assert asyncio.run(run_cases([case], ReplayAgent(tmp_path / "t.jsonl"))).summary.passed == 1


def test_cassette_roundtrip_and_strict_lookup(tmp_path: Path) -> None:
    trace = Trace(
        case_id="c",
        tool_calls=[ToolCall(name="get_ticket", arguments={"b": 1, "a": 2}, result={"ok": 1})],
    )
    cassette = Cassette.from_traces([trace])
    assert len(cassette) == 1
    assert cassette.call("get_ticket", {"a": 2, "b": 1}) == {"ok": 1}  # key order is irrelevant
    with pytest.raises(MissingRecording, match="unrecorded tool call"):
        cassette.call("get_ticket", {"a": 3})
    cassette.save(tmp_path / "c.json")
    assert Cassette.load(tmp_path / "c.json").call("get_ticket", {"a": 2, "b": 1}) == {"ok": 1}


def test_cassette_holds_tools_constant_and_flags_new_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cassette = tmp_path / "cassette.json"
    assert main(["cassette", str(EXAMPLE / "traces" / "v1.jsonl"), "--out", str(cassette)]) == 0
    agent = EXAMPLE / "scripted_agent.py"
    cmd = f'"{Path(sys.executable).as_posix()}" "{agent.as_posix()}"'
    monkeypatch.setenv("EVALKIT_CASSETTE", str(cassette))
    base = ["run", CASES, "--config", CONFIG, "--command", cmd]

    # same prompt, tools from the recording: identical behavior, byte-identical reports
    r1, r2 = tmp_path / "r1.json", tmp_path / "r2.json"
    assert main([*base, "--out", str(r1)]) == 0
    assert main([*base, "--out", str(r2)]) == 0
    assert r1.read_bytes() == r2.read_bytes()

    # a regressed prompt makes a tool call that was never recorded: surfaced, not invented
    monkeypatch.setenv("PROMPT_VERSION", "v2")
    out = tmp_path / "v2.json"
    assert main([*base, "--out", str(out)]) == 1
    assert "unrecorded tool call: delete_ticket" in out.read_text(encoding="utf-8")
    assert os.environ["PROMPT_VERSION"] == "v2"


def test_prompt_change_is_reported_in_gate_markdown(tmp_path: Path) -> None:
    out = tmp_path / "v2.json"
    traces = str(EXAMPLE / "traces" / "v2.jsonl")
    assert main(["run", CASES, "--config", CONFIG, "--replay", traces, "--out", str(out),
                 "--allow-failures"]) == 0  # fmt: skip
    md = tmp_path / "gate.md"
    baseline = str(EXAMPLE / "baselines" / "main.json")
    assert main(["gate", baseline, str(out), "--config", CONFIG, "--markdown", str(md)]) == 1
    assert "Prompt changed" in md.read_text(encoding="utf-8")
