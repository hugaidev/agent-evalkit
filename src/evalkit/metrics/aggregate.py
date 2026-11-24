"""Percentiles and a seeded bootstrap CI (deterministic, so reports are reproducible)."""

from __future__ import annotations

import random


def percentile(values: list[float], p: float) -> float:
    """Linear-interpolated percentile, p in [0, 100]. Empty input gives 0."""
    if not values:
        return 0.0
    xs = sorted(values)
    k = (len(xs) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def bootstrap_ci(
    values: list[float], samples: int = 1000, seed: int = 0, alpha: float = 0.05
) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean."""
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)  # noqa: S311  (statistics, not security)
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(samples))
    return (percentile(means, 100 * alpha / 2), percentile(means, 100 * (1 - alpha / 2)))
