"""Rule-based groundedness: every checkable claim in the answer must trace to evidence.

A "claim" is a token matched by ``claim_pattern`` (identifiers, versions, numbers). It is
supported if it appears in the user input or in any tool result. Score = supported / claims
(1.0 when there are no checkable claims). A semantic LLM groundedness judge is layered on later.
"""

from __future__ import annotations

import json
import re

from evalkit.cases import Case
from evalkit.config import EvalConfig
from evalkit.trace import Trace


def _evidence(case: Case, trace: Trace) -> str:
    parts = [case.input] + [json.dumps(c.result, default=str) for c in trace.tool_calls]
    return "\n".join(parts).lower()


def unsupported_claims(case: Case, trace: Trace, config: EvalConfig) -> list[str]:
    evidence = _evidence(case, trace)
    claims = re.findall(config.groundedness.claim_pattern, trace.final_output)
    return sorted({c for c in claims if c.lower() not in evidence})


def groundedness(case: Case, trace: Trace, config: EvalConfig) -> float:
    claims = set(re.findall(config.groundedness.claim_pattern, trace.final_output))
    if not claims:
        return 1.0
    bad = unsupported_claims(case, trace, config)
    return 1 - len(bad) / len(claims)
