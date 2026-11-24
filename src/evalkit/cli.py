"""evalkit CLI."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from evalkit import __version__
from evalkit.agents import Agent, CommandAgent, ReplayAgent
from evalkit.cases import CaseError, load_cases
from evalkit.config import load_config
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
    result = asyncio.run(run_cases(cases, _build_agent(args), args.concurrency, config))
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
    r.set_defaults(fn=_cmd_run)

    args = p.parse_args(argv)
    try:
        return int(args.fn(args))
    except CaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
