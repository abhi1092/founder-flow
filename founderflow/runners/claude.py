from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import structlog

from founderflow.models import AgentUsage
from founderflow.runners.usage import _parse_usage

log = structlog.get_logger()


class ClaudeRunner:
    async def headless(
        self,
        prompt: str,
        task: str,
        cwd: Path,
        *,
        timeout: float,
        model: str | None = None,
        max_budget_usd: float | None = None,
        json_schema: dict | None = None,
    ) -> tuple[str, int, AgentUsage | None]:
        cmd = [
            "claude",
            "-p",
            "--output-format", "json",
            "--dangerously-skip-permissions",
            "--no-session-persistence",
        ]

        if model:
            cmd.extend(["--model", model])
        if max_budget_usd is not None:
            cmd.extend(["--max-budget-usd", str(max_budget_usd)])
        if json_schema is not None:
            cmd.extend(["--json-schema", json.dumps(json_schema)])

        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        if "VIRTUAL_ENV" in os.environ and "PATH" in env:
            venv_bin = os.path.join(os.environ["VIRTUAL_ENV"], "bin")
            env["PATH"] = os.pathsep.join(
                p for p in env["PATH"].split(os.pathsep) if p != venv_bin
            )

        log.info(
            "claude_runner.start",
            model=model,
            cwd=str(cwd),
            prompt_len=len(prompt),
            task_len=len(task),
        )

        full_input = f"{prompt}\n\n---\n\nTask:\n{task}"

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=full_input.encode()),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            log.warning("claude_runner.timeout", timeout=timeout)
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return "", 1, None

        return_code = proc.returncode or 0
        raw_output = stdout.decode()

        if return_code != 0:
            log.warning(
                "claude_runner.failed",
                return_code=return_code,
                stderr=stderr.decode()[:500],
            )
            return raw_output, return_code, None

        usage = None
        result_text = raw_output
        try:
            data = json.loads(raw_output)
            result_text = data.get("result", raw_output)
            if "usage" in data:
                usage = _parse_usage(data)
        except (json.JSONDecodeError, Exception):
            log.warning("claude_runner.parse_error", output_len=len(raw_output))

        return result_text, return_code, usage
