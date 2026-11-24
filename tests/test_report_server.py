from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from evalkit.cli import main
from evalkit.compare import load_run
from evalkit.report import render_dashboard

EXAMPLE = Path(__file__).parent.parent / "examples" / "servicedesk-mcp"
CONFIG = str(EXAMPLE / "evalkit.yaml")
CASES = str(EXAMPLE / "cases")


def _replay(name: str, out: Path) -> Path:
    args = ["run", CASES, "--config", CONFIG, "--replay", str(EXAMPLE / "traces" / f"{name}.jsonl")]
    assert main([*args, "--out", str(out), "--allow-failures"]) == 0
    return out


def test_dashboard_lists_runs_and_regressions(tmp_path: Path) -> None:
    v1 = _replay("v1", tmp_path / "01-v1.json")
    v2 = _replay("v2", tmp_path / "02-v2.json")
    html = tmp_path / "out" / "dash.html"
    assert main(["report", str(v1), str(v2), "--html", str(html), "--title", "demo"]) == 0
    text = html.read_text(encoding="utf-8")
    assert "<title>demo</title>" in text
    assert "01-v1" in text
    assert "02-v2" in text
    assert "<polyline" in text
    assert "sd-006" in text
    assert "safety-critical" in text
    only = render_dashboard([("solo", load_run(v1))])
    assert "No regressions." in only
    assert "<polyline" not in only


def test_dashboard_escapes_labels() -> None:
    run = load_run(EXAMPLE / "baselines" / "main.json")
    assert "&lt;script&gt;" in render_dashboard([("<script>", run)])


def test_run_case_filter(capsys: pytest.CaptureFixture[str]) -> None:
    replay = str(EXAMPLE / "traces" / "v1.jsonl")
    assert main(["run", CASES, "--replay", replay, "--case", "sd-001"]) == 0
    assert "cases=1 passed=1" in capsys.readouterr().out
    assert main(["run", CASES, "--replay", replay, "--case", "nope"]) == 2


def test_schema_is_valid_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert "id" in schema["properties"]
    assert schema["additionalProperties"] is False


def test_mcp_server_exposes_the_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("mcp")
    monkeypatch.syspath_prepend(str(EXAMPLE))
    sys.modules.pop("server", None)
    import server  # type: ignore[import-not-found]

    mcp = server.build_server()
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == {"get_ticket", "search_kb", "assign_ticket", "delete_ticket"}
