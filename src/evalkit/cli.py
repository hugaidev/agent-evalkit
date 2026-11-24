"""evalkit CLI."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from evalkit import __version__
from evalkit.agents import Agent, CommandAgent, ReplayAgent
from evalkit.calibration import calibrate, load_items, load_labels, write_report
from evalkit.cases import CaseError, load_cases
from evalkit.config import load_config
from evalkit.judges.clients import make_client
from evalkit.judges.llm import LLMJudge, load_rubric
from evalkit.runner import run_cases
from evalkit.trace import write_traces


def _build_agent(args: argparse.Namespace) -> Agent:
    if args.replay:
        return ReplayAgent(Path(args.replay))
    if args.command:
        return CommandAgent(args.command)
    raise SystemExit("evalkit run: pass --replay TRACES.jsonl or --command 'CMD'")


def _cmd_validate(args: argparse.Namespace) -> int:
    cases = load_cases(Path(args.cases))
    print(f"ok: {len(cases)} cases")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    cases = load_cases(Path(args.cases))
    config = load_config(Path(args.config) if args.config else None)
    result = asyncio.run(
        run_cases(cases, _build_agent(args), args.concurrency, config, _make_judge(args))
    )
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    if args.record:
        write_traces(Path(args.record), [r.trace for r in result.results])
    s = result.summary
    print(
        f"cases={s.total} passed={s.passed} task_success={s.task_success:.1%} "
        f"safety_failures={s.safety_failures}"
    )
    print(
        f"groundedness={s.groundedness_mean:.2f} cost=${s.cost_total_usd:.4f} "
        f"latency_p50={s.latency_p50_ms:.0f}ms p95={s.latency_p95_ms:.0f}ms"
    )
    for r in result.results:
        if not r.passed:
            bad = ", ".join(c.name for c in r.checks if not c.passed)
            print(f"  FAIL {r.case_id}: {bad}")
    return 0 if s.passed == s.total else 1


def _judge_args(p: argparse.ArgumentParser, required: bool = False) -> None:
    p.add_argument("--rubric", required=required, help="rubric YAML for the LLM judge")
    p.add_argument(
        "--judge",
        choices=["simulated", "agent-sdk", "anthropic"],
        default="simulated",
        help="judge backend: simulated (offline heuristic), agent-sdk (Claude Code login, "
        "no API key) or anthropic (API key)",
    )
    p.add_argument("--judge-model", help="model id for the judge backend")


def _make_judge(args: argparse.Namespace) -> LLMJudge | None:
    if not args.rubric:
        return None
    return LLMJudge(make_client(args.judge, args.judge_model), load_rubric(Path(args.rubric)))


def _cmd_calibrate(args: argparse.Namespace) -> int:
    judge = _make_judge(args)
    assert judge is not None
    report = asyncio.run(
        calibrate(
            judge,
            load_items(Path(args.items)),
            load_labels(Path(args.labels)),
            args.min_kappa,
        )
    )
    if args.out:
        write_report(Path(args.out), report)
    print(
        f"judge={args.judge} n={report.n} kappa={report.kappa:.2f} ({report.band}) "
        f"accuracy={report.accuracy:.1%} calibrated={report.calibrated}"
    )
    for d in report.disagreements:
        print(f"  {d.id}: human={d.human} judge={d.judge} ({d.reasoning})")
    return 0 if report.calibrated else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="evalkit", description="Evals for MCP agents.")
    p.add_argument("--version", action="version", version=f"evalkit {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate gold-set YAML")
    v.add_argument("cases")
    v.set_defaults(fn=_cmd_validate)

    r = sub.add_parser("run", help="run cases against an agent")
    r.add_argument("cases", help="YAML file or directory")
    r.add_argument("--replay", help="recorded traces JSONL (offline, deterministic)")
    r.add_argument("--command", help="external agent command (case JSON in, trace JSON out)")
    r.add_argument("--out", help="write full result JSON here")
    r.add_argument("--record", help="write traces JSONL here (for later replay)")
    r.add_argument("--concurrency", type=int, default=4)
    r.add_argument("--config", help="evalkit.yaml (pricing, groundedness settings)")
    _judge_args(r)
    r.set_defaults(fn=_cmd_run)

    c = sub.add_parser("calibrate", help="measure judge-vs-human agreement (Cohen's kappa)")
    c.add_argument("--items", required=True, help="items.jsonl (id, question, answer, evidence)")
    c.add_argument("--labels", required=True, help="human labels CSV (id,label)")
    c.add_argument("--min-kappa", type=float, default=0.6)
    c.add_argument("--out", help="write report JSON here")
    _judge_args(c, required=True)
    c.set_defaults(fn=_cmd_calibrate)

    args = p.parse_args(argv)
    try:
        return int(args.fn(args))
    except (CaseError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
