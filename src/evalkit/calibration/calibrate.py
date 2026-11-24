"""Judge-vs-human calibration: run the judge on labeled items and measure agreement."""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path

from pydantic import BaseModel

from evalkit.calibration.kappa import cohens_kappa, confusion, interpret
from evalkit.judges.llm import LLMJudge


class Item(BaseModel):
    id: str
    question: str
    answer: str
    evidence: str = ""


class Disagreement(BaseModel):
    id: str
    human: str
    judge: str
    reasoning: str


class CalibrationReport(BaseModel):
    n: int
    kappa: float
    band: str
    accuracy: float
    confusion: dict[str, dict[str, int]]
    disagreements: list[Disagreement]
    min_kappa: float
    calibrated: bool


def load_items(path: Path) -> list[Item]:
    return [
        Item.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_labels(path: Path) -> dict[str, str]:
    """CSV with columns ``id,label`` (label: pass|fail). Rows with an empty label are skipped."""
    with path.open(encoding="utf-8", newline="") as f:
        rows = {r["id"]: r["label"].strip().lower() for r in csv.DictReader(f)}
    bad = {v for v in rows.values() if v not in ("", "pass", "fail")}
    if bad:
        raise ValueError(f"labels must be pass|fail, got {sorted(bad)}")
    return {k: v for k, v in rows.items() if v}


async def calibrate(
    judge: LLMJudge,
    items: list[Item],
    labels: dict[str, str],
    min_kappa: float = 0.6,
    concurrency: int = 4,
) -> CalibrationReport:
    labeled = [i for i in items if i.id in labels]
    if not labeled:
        raise ValueError("no items have a human label yet")
    sem = asyncio.Semaphore(concurrency)

    async def one(item: Item) -> tuple[str, str]:
        async with sem:
            v = await judge.judge(item.question, item.answer, item.evidence)
        return v.verdict, v.reasoning

    verdicts = await asyncio.gather(*(one(i) for i in labeled))
    human = [labels[i.id] for i in labeled]
    pred = [v for v, _ in verdicts]
    kappa = cohens_kappa(human, pred)
    return CalibrationReport(
        n=len(labeled),
        kappa=kappa,
        band=interpret(kappa),
        accuracy=sum(h == p for h, p in zip(human, pred, strict=True)) / len(labeled),
        confusion=confusion(human, pred),
        disagreements=[
            Disagreement(id=i.id, human=h, judge=v, reasoning=why)
            for i, h, (v, why) in zip(labeled, human, verdicts, strict=True)
            if h != v
        ],
        min_kappa=min_kappa,
        calibrated=kappa >= min_kappa,
    )


def write_report(path: Path, report: CalibrationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(), indent=2) + "\n", encoding="utf-8")
