from __future__ import annotations

import asyncio
import csv
import json
import sys
import types
from pathlib import Path

import pytest

from evalkit.calibration import (
    Item,
    calibrate,
    cohens_kappa,
    confusion,
    interpret,
    load_items,
    load_labels,
)
from evalkit.cases import Case
from evalkit.cli import main
from evalkit.judges.clients import AnthropicClient, SimulatedJudgeClient, make_client
from evalkit.judges.llm import LLMJudge, build_prompt, load_rubric, parse_verdict
from evalkit.runner import run_cases
from evalkit.trace import ToolCall, Trace

EXAMPLE = Path(__file__).parent.parent / "examples" / "servicedesk-mcp"
RUBRIC = EXAMPLE / "rubrics" / "helpfulness.yaml"
ITEMS = EXAMPLE / "calibration" / "items.jsonl"


def test_kappa_known_values() -> None:
    # 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> po=0.7, pe=0.5, kappa=0.4
    a = ["y"] * 25 + ["n"] * 25
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert cohens_kappa(a, b) == pytest.approx(0.4)
    assert cohens_kappa(a, a) == 1.0
    assert cohens_kappa(["y", "n"], ["n", "y"]) == pytest.approx(-1.0)
    assert cohens_kappa(["y", "y"], ["y", "y"]) == 1.0
    with pytest.raises(ValueError, match="equal length"):
        cohens_kappa(["y"], [])
    with pytest.raises(ValueError, match="no ratings"):
        cohens_kappa([], [])
    assert confusion(["y", "y", "n"], ["y", "n", "n"]) == {"y": {"y": 1, "n": 1}, "n": {"n": 1}}
    assert [interpret(k) for k in (-0.1, 0.1, 0.3, 0.5, 0.7, 0.9)] == [
        "poor", "slight", "fair", "moderate", "substantial", "almost perfect",
    ]  # fmt: skip


def test_parse_verdict_tolerates_noise() -> None:
    assert parse_verdict('{"verdict": "pass", "reasoning": "ok"}').verdict == "pass"
    fenced = 'Sure!\n```json\n{"verdict": "fail", "reasoning": "x"}\n```'
    assert parse_verdict(fenced).verdict == "fail"
    for junk in ("no json", '{"verdict": "maybe"}', "{not json}"):
        v = parse_verdict(junk)
        assert v.verdict == "fail"
        assert "unparseable" in v.reasoning


def test_prompt_marks_untrusted_data_and_rubric() -> None:
    rubric = load_rubric(RUBRIC)
    prompt = build_prompt(rubric, "q?", "a!", "ev")
    for tag in ("<rubric", "<question>", "<tool_results>", "<answer>"):
        assert tag in prompt
    assert "PASS only if" in prompt


def _judge() -> LLMJudge:
    return LLMJudge(SimulatedJudgeClient(), load_rubric(RUBRIC))


def test_simulated_client_verdicts() -> None:
    judge = _judge()
    ev = json.dumps([{"results": ["fix. Source: KB-12"]}])

    def verdict(answer: str) -> str:
        return asyncio.run(judge.judge("how?", answer, ev)).verdict

    assert verdict("Do it. Source: KB-12") == "pass"
    assert verdict("See KB-99") == "fail"
    assert verdict("") == "fail"
    assert verdict("I cannot help with that") == "fail"


def test_items_file_is_50_and_template_is_unlabeled() -> None:
    items = load_items(ITEMS)
    assert len(items) == 50
    assert len({i.id for i in items}) == 50
    with (ITEMS.parent / "labels.template.csv").open(encoding="utf-8") as f:
        assert all(r["label"] == "" for r in csv.DictReader(f))


def _write_labels(path: Path, items: list[Item], flip: int) -> None:
    """SYNTHETIC labels for exercising the machinery only: the simulated judge's verdicts with
    ``flip`` of them inverted. Real calibration uses labels a human wrote."""
    judge = _judge()
    rows = [["id", "label"]]
    for n, item in enumerate(items):
        v = asyncio.run(judge.judge(item.question, item.answer, item.evidence)).verdict
        if n < flip:
            v = "pass" if v == "fail" else "fail"
        rows.append([item.id, v])
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)


def test_calibrate_report_and_gate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    items = load_items(ITEMS)
    good, bad = tmp_path / "good.csv", tmp_path / "bad.csv"
    _write_labels(good, items, flip=3)
    _write_labels(bad, items, flip=25)

    ok = asyncio.run(calibrate(_judge(), items, load_labels(good)))
    assert ok.n == 50
    assert ok.calibrated
    assert len(ok.disagreements) == 3
    nope = asyncio.run(calibrate(_judge(), items, load_labels(bad)))
    assert not nope.calibrated

    base = ["calibrate", "--items", str(ITEMS), "--rubric", str(RUBRIC)]
    out = tmp_path / "report.json"
    assert main([*base, "--labels", str(good), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["calibrated"] is True
    assert "kappa=" in capsys.readouterr().out
    assert main([*base, "--labels", str(bad)]) == 1


def test_label_validation(tmp_path: Path) -> None:
    p = tmp_path / "l.csv"
    p.write_text("id,label\na,maybe\n")
    with pytest.raises(ValueError, match="pass\\|fail"):
        load_labels(p)
    p.write_text("id,label\na,\nb,Pass\n")
    assert load_labels(p) == {"b": "pass"}
    with pytest.raises(ValueError, match="no items"):
        asyncio.run(calibrate(_judge(), [Item(id="a", question="q", answer="x")], {}))
    assert (
        main(["calibrate", "--items", str(ITEMS), "--labels", str(p), "--rubric", str(RUBRIC)]) == 2
    )


def test_rubric_check_in_runner() -> None:
    class Fixed:
        name = "fixed"

        async def run(self, case: Case) -> Trace:
            return Trace(
                case_id=case.id,
                final_output="Source: KB-12 and KB-77",
                tool_calls=[ToolCall(name="search_kb", result="Source: KB-12")],
            )

    case = Case.model_validate({"id": "c1", "input": "q", "expect": {"rubric": "helpful"}})
    no_judge = asyncio.run(run_cases([case], Fixed()))
    assert not no_judge.results[0].passed
    assert no_judge.results[0].checks[-1].detail == "no judge"
    judged = asyncio.run(run_cases([case], Fixed(), judge=_judge()))
    check = judged.results[0].checks[-1]
    assert check.name == "rubric:helpful_and_grounded"
    assert not check.passed
    assert "KB-77" in check.detail


def test_make_client_and_anthropic_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    assert make_client("simulated").name == "simulated"
    assert make_client("agent-sdk").name == "agent-sdk"
    with pytest.raises(ValueError, match="judge-model"):
        make_client("anthropic")
    with pytest.raises(ValueError, match="unknown"):
        make_client("nope")

    seen: dict[str, object] = {}

    class FakeMessages:
        async def create(self, **kw: object) -> object:
            seen.update(kw)
            block = types.SimpleNamespace(type="text", text='{"verdict": "pass"}')
            return types.SimpleNamespace(content=[block])

    fake = types.ModuleType("anthropic")
    fake.AsyncAnthropic = lambda: types.SimpleNamespace(messages=FakeMessages())  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    out = asyncio.run(AnthropicClient("some-model").complete("sys", "usr"))
    assert out == '{"verdict": "pass"}'
    assert seen["model"] == "some-model"


def test_agent_sdk_backend_collects_result_and_raises_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import claude_agent_sdk as sdk

    from evalkit.judges.clients import AgentSDKClient

    captured: dict[str, object] = {}

    def result(*, is_error: bool, text: str | None) -> sdk.ResultMessage:
        return sdk.ResultMessage(
            subtype="error" if is_error else "success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=is_error,
            num_turns=1,
            session_id="s",
            result=text,
        )

    def fake_query(*, prompt: str, options: sdk.ClaudeAgentOptions) -> object:
        captured["options"] = options
        captured["prompt"] = prompt

        async def gen() -> object:
            yield sdk.AssistantMessage(content=[sdk.TextBlock(text="draft")], model="m")
            yield result(is_error=captured.get("fail") is True, text='{"verdict": "pass"}')

        return gen()

    monkeypatch.setattr(sdk, "query", fake_query)
    client = AgentSDKClient(model="some-model")
    assert asyncio.run(client.complete("sys", "usr")) == '{"verdict": "pass"}'
    opts = captured["options"]
    assert isinstance(opts, sdk.ClaudeAgentOptions)
    assert opts.tools == []
    assert opts.max_turns == 1
    assert opts.setting_sources == []
    assert opts.system_prompt == "sys"
    captured["fail"] = True
    with pytest.raises(RuntimeError, match="agent-sdk judge failed"):
        asyncio.run(client.complete("sys", "usr"))
