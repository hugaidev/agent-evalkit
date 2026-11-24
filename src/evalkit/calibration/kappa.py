"""Cohen's kappa for judge-vs-human agreement."""

from __future__ import annotations

from collections import Counter


def cohens_kappa(a: list[str], b: list[str]) -> float:
    """Agreement beyond chance between two raters over the same items.

    Returns 1.0 when both raters use one identical constant label (no chance correction possible).
    """
    if len(a) != len(b):
        raise ValueError("rating lists must have equal length")
    if not a:
        raise ValueError("no ratings")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in ca.keys() | cb.keys()) / (n * n)
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1 - expected)


def confusion(human: list[str], judge: list[str]) -> dict[str, dict[str, int]]:
    """matrix[human_label][judge_label] -> count."""
    out: dict[str, dict[str, int]] = {}
    for h, j in zip(human, judge, strict=True):
        out.setdefault(h, {}).setdefault(j, 0)
        out[h][j] += 1
    return out


def interpret(kappa: float) -> str:
    """Landis & Koch bands."""
    for limit, label in (
        (0.0, "poor"),
        (0.2, "slight"),
        (0.4, "fair"),
        (0.6, "moderate"),
        (0.8, "substantial"),
    ):
        if kappa <= limit:
            return label
    return "almost perfect"
