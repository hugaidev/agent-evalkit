"""evalkit.yaml: pricing table and metric settings. Nothing model-specific is hardcoded."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CLAIM_PATTERN = r"\b[A-Za-z]+-\w*\d\w*\b|\b\d+(?:\.\d+)?\b"


class Pricing(BaseModel):
    """USD per million tokens."""

    model_config = ConfigDict(extra="forbid")

    input_per_mtok: float = 0.0
    output_per_mtok: float = 0.0
    cache_read_per_mtok: float = 0.0


class GroundednessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_pattern: str = DEFAULT_CLAIM_PATTERN


class EvalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pricing: dict[str, Pricing] = Field(default_factory=dict)
    default_pricing: Pricing = Field(default_factory=Pricing)
    groundedness: GroundednessConfig = Field(default_factory=GroundednessConfig)
    bootstrap_samples: int = 1000
    seed: int = 0

    def pricing_for(self, model: str) -> Pricing:
        return self.pricing.get(model, self.default_pricing)


def load_config(path: Path | None) -> EvalConfig:
    if path is None:
        return EvalConfig()
    return EvalConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
