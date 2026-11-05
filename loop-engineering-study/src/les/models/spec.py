"""Model specification and role resolution.

Loops ask for a *role* (maker, checker, cheap, strong), never a model name.
The spec layer resolves role -> alias -> ModelSpec, keeping all provider
details out of loop code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "config" / "models.yaml"


@dataclass(frozen=True)
class ModelSpec:
    """Everything needed to instantiate a model client."""

    alias: str
    family: str
    name: str = ""
    base_url: str = ""
    price_in: float = 0.0
    price_out: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost in USD from token counts and per-token prices."""
        return (prompt_tokens * self.price_in + completion_tokens * self.price_out) / 1_000_000


@dataclass
class ModelConfig:
    """Parsed models.yaml: default alias, role mappings, and model specs."""

    default: str
    roles: dict[str, str]
    models: dict[str, ModelSpec]

    def resolve(self, alias_or_role: str) -> ModelSpec:
        """Resolve a role name or alias to a concrete ModelSpec.

        Resolution order:
        1. If it's a role name, map to alias first.
        2. Look up alias in models dict.
        """
        alias = self.roles.get(alias_or_role, alias_or_role)
        if alias not in self.models:
            raise KeyError(
                f"Unknown model alias '{alias}' "
                f"(resolved from '{alias_or_role}'). "
                f"Available: {list(self.models.keys())}"
            )
        return self.models[alias]

    def resolve_default(self) -> ModelSpec:
        """Resolve using LES_MODEL env var, falling back to config default."""
        override = os.environ.get("LES_MODEL", "")
        return self.resolve(override or self.default)


def load_config(path: Path | str | None = None) -> ModelConfig:
    """Load and parse a models.yaml file."""
    config_path = Path(path) if path else _DEFAULT_CONFIG
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    models: dict[str, ModelSpec] = {}
    for alias, spec in raw.get("models", {}).items():
        family = spec.pop("family")
        name = spec.pop("name", "")
        base_url = spec.pop("base_url", "")
        price_in = spec.pop("price_in", 0.0)
        price_out = spec.pop("price_out", 0.0)
        models[alias] = ModelSpec(
            alias=alias,
            family=family,
            name=name,
            base_url=base_url,
            price_in=price_in,
            price_out=price_out,
            extra=spec,
        )

    return ModelConfig(
        default=raw.get("default", "mock"),
        roles=raw.get("roles", {}),
        models=models,
    )
