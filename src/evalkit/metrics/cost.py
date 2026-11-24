"""Cost: tokens x configurable price table."""

from __future__ import annotations

from evalkit.config import EvalConfig
from evalkit.trace import Trace


def cost_usd(trace: Trace, config: EvalConfig) -> float:
    p = config.pricing_for(trace.model)
    u = trace.usage
    return (
        u.input_tokens * p.input_per_mtok
        + u.output_tokens * p.output_per_mtok
        + u.cache_read_tokens * p.cache_read_per_mtok
    ) / 1_000_000
