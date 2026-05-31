from __future__ import annotations

from pathlib import Path
from typing import Protocol

from founderflow.models import AgentUsage


class Runner(Protocol):
    async def headless(
        self,
        prompt: str,
        task: str,
        cwd: Path,
        *,
        timeout: float,
        model: str | None = None,
    ) -> tuple[str, int, AgentUsage | None]: ...
