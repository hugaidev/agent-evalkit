"""Static regression dashboard: one self-contained HTML file from a series of run results."""

from __future__ import annotations

from html import escape
from itertools import pairwise
from pathlib import Path

from evalkit.compare import compare, load_run
from evalkit.runner import RunResult

_CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--ok:#1a7f37;--bad:#cf222e;--line:#d0d7de;--card:#f6f8fa}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--ok:#3fb950;
--bad:#f85149;--line:#30363d;--card:#161b22}}
body{font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg);margin:0 auto;
max-width:960px;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px}.mut{color:var(--mut)}
table{border-collapse:collapse;width:100%;margin:16px 0}
th,td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:left}
th{font-size:12px;text-transform:uppercase;color:var(--mut)}
.ok{color:var(--ok)}.bad{color:var(--bad);font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;
margin:12px 0}
svg{width:100%;height:80px}
"""


def _spark(values: list[float]) -> str:
    if len(values) < 2:
        return ""
    w, h, pad = 600.0, 80.0, 8.0
    step = (w - 2 * pad) / (len(values) - 1)
    pts = [(pad + i * step, h - pad - v * (h - 2 * pad)) for i, v in enumerate(values)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="currentColor"/>' for x, y in pts)
    return (
        f'<svg viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="task success over runs">'
        f'<polyline fill="none" stroke="currentColor" stroke-width="2" points="{path}"/>'
        f"{dots}</svg>"
    )


def render_dashboard(runs: list[tuple[str, RunResult]], title: str = "evalkit dashboard") -> str:
    rows = []
    for label, run in runs:
        s = run.summary
        safety = f'<span class="{"bad" if s.safety_failures else "ok"}">{s.safety_failures}</span>'
        rows.append(
            f"<tr><td>{escape(label)}</td><td>{s.task_success:.1%}</td><td>{safety}</td>"
            f"<td>{s.groundedness_mean:.2f}</td><td>${s.cost_mean_usd:.5f}</td>"
            f"<td>{s.latency_p95_ms:.0f} ms</td></tr>"
        )
    regressions = []
    for (_, prev), (label, cur) in pairwise(runs):
        cmp = compare(prev, cur)
        if cmp.regressed:
            ids = ", ".join(escape(i) for i in cmp.regressed)
            crit = " (safety-critical: " + ", ".join(map(escape, cmp.safety_regressed)) + ")"
            note = crit if cmp.safety_regressed else ""
            regressions.append(
                f'<li><b>{escape(label)}</b>: <span class="bad">{ids}</span>{note}</li>'
            )
    reg_html = (
        f"<ul>{''.join(regressions)}</ul>" if regressions else '<p class="ok">No regressions.</p>'
    )
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_CSS}</style></head><body>"
        f'<h1>{escape(title)}</h1><div class="mut">{len(runs)} runs, oldest first</div>'
        f'<div class="card">{_spark([r.summary.task_success for _, r in runs])}'
        f'<div class="mut">Task success per run</div></div>'
        "<table><tr><th>Run</th><th>Task success</th><th>Safety failures</th>"
        "<th>Groundedness</th><th>Mean cost</th><th>p95 latency</th></tr>"
        f"{''.join(rows)}</table><h2>Regressions between consecutive runs</h2>{reg_html}"
        "</body></html>"
    )


def build_dashboard(paths: list[Path], out: Path, title: str = "evalkit dashboard") -> None:
    runs = [(p.stem, load_run(p)) for p in paths]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_dashboard(runs, title), encoding="utf-8")
