from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class FounderFlowConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    max_rounds: int = 3
    model: str = "sonnet"
    integrator_model: str | None = None
    per_agent_timeout: int = 600
    per_agent_budget: float | None = None

    def get_integrator_model(self) -> str:
        return self.integrator_model or self.model


def load_config(project_path: Path | None = None) -> FounderFlowConfig:
    if project_path is None:
        project_path = Path.cwd()

    config_file = project_path / ".founderflow" / "config.toml"
    if not config_file.exists():
        return FounderFlowConfig()

    with config_file.open("rb") as f:
        data = tomllib.load(f)

    return FounderFlowConfig(**data)
