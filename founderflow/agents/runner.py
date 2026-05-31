from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
from pydantic import ValidationError

from founderflow.agents.protocol import Runner
from founderflow.config import FounderFlowConfig
from founderflow.models import (
    AgentRole,
    AgentUsage,
    CompetitorAnalysis,
    CustomerDiscovery,
    FollowUpDirective,
    IdeaValidation,
    ResearchDirective,
)

log = structlog.get_logger()

ROLE_TO_MODEL: dict[AgentRole, type] = {
    AgentRole.idea_validator: IdeaValidation,
    AgentRole.competitor_analyst: CompetitorAnalysis,
    AgentRole.customer_discovery: CustomerDiscovery,
}

_SECTION_PATTERN = re.compile(r"\{\{section:(\w+)\}\}")
_PRIOR_WORK_VARS = re.compile(r"\{\{(\w+)\}\}")


@dataclass
class AgentResult:
    role: AgentRole
    text: str
    parsed_output: Any = None
    return_code: int = 0
    usage: AgentUsage | None = None
    error: str | None = None


def _prompts_dir() -> Path:
    return Path(__file__).parent / "prompts"


def _sections_dir() -> Path:
    return _prompts_dir() / "sections"


def _compose_sections(prompt_text: str) -> str:
    """Replace {{section:name}} markers with content from sections/ directory."""
    sections_path = _sections_dir()

    def _replacer(match: re.Match) -> str:
        section_name = match.group(1)
        section_file = sections_path / f"{section_name}.md"
        if section_file.exists():
            return section_file.read_text().strip()
        log.warning("section_not_found", section=section_name)
        return match.group(0)

    return _SECTION_PATTERN.sub(_replacer, prompt_text)


def resolve_prompt(role: AgentRole, project_path: Path | None = None) -> str:
    """Two-tier prompt resolution: project override first, then package default."""
    if project_path is not None:
        override = project_path / ".founderflow" / "agents" / f"{role.value}.md"
        if override.exists():
            raw = override.read_text()
            return _compose_sections(raw)

    builtin = _prompts_dir() / f"{role.value}.md"
    if not builtin.exists():
        raise FileNotFoundError(f"No prompt found for agent role: {role.value}")

    raw = builtin.read_text()
    return _compose_sections(raw)


def _render_prior_work(
    prior_output: str,
    follow_up_question: str,
    round_num: int,
) -> str:
    """Render the prior_work section template with concrete values."""
    template_file = _sections_dir() / "prior_work.md"
    if not template_file.exists():
        return ""

    template = template_file.read_text()
    replacements = {
        "round_num": str(round_num),
        "prior_output": prior_output,
        "follow_up_question": follow_up_question,
    }

    def _var_replacer(match: re.Match) -> str:
        var_name = match.group(1)
        return replacements.get(var_name, match.group(0))

    return _PRIOR_WORK_VARS.sub(_var_replacer, template)


def build_task_prompt(
    role: AgentRole,
    idea: str,
    round_num: int,
    prior_output: str | None = None,
    directive: FollowUpDirective | None = None,
) -> str:
    """Build the task message sent to the agent.

    Round 1: just the idea.
    Round 2+: idea + prior work section + follow-up question.
    """
    parts = [f"Startup idea to analyze:\n\n{idea}"]

    if round_num > 1 and prior_output and directive:
        prior_section = _render_prior_work(
            prior_output=prior_output,
            follow_up_question=directive.follow_up_question,
            round_num=round_num,
        )
        parts.append(prior_section)

    return "\n\n---\n\n".join(parts)


def _find_all_json_objects(text: str) -> list[dict]:
    """Scan *text* and extract all top-level JSON objects by brace matching.

    Returns a list of parsed dicts (in order of appearance).  Ignores
    braces that appear inside JSON strings.
    """
    results: list[dict] = []
    i = 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_string = False
        escape = False
        start = i
        for j in range(i, len(text)):
            ch = text[j]
            if escape:
                escape = False
                continue
            if ch == "\\":
                if in_string:
                    escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : j + 1]
                    try:
                        results.append(json.loads(candidate))
                    except json.JSONDecodeError:
                        pass
                    i = j + 1
                    break
        else:
            break
    return results


def _extract_json(text: str) -> dict:
    """Extract JSON from agent response.

    Handles: pure JSON, markdown-fenced JSON, and JSON embedded in prose.
    """
    stripped = text.strip()

    # 1. Markdown fences
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        start = 1
        end = len(lines)
        for i in range(1, len(lines)):
            if lines[i].strip() == "```":
                end = i
                break
        stripped = "\n".join(lines[start:end])

    # 2. Try direct parse (pure JSON)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 3. Brace-matching: find first JSON object embedded in prose
    objects = _find_all_json_objects(stripped)
    if objects:
        return objects[0]

    raise json.JSONDecodeError("No JSON object found in text", text, 0)


def _parse_agent_output(
    role: AgentRole,
    text: str,
) -> Any:
    """Parse agent text output into the appropriate Pydantic model.

    Uses strict=False because agent JSON contains string enum values, not
    Python enum instances.
    """
    if role == AgentRole.evidence_integrator:
        return _parse_integrator_output(text)

    data = _extract_json(text)
    model_cls = ROLE_TO_MODEL.get(role)
    if model_cls is None:
        return data

    return model_cls.model_validate(data, strict=False)


def _parse_integrator_output(text: str) -> dict | ResearchDirective:
    """Parse integrator output, finding both research_directive and validation_thesis.

    The integrator may return:
    - A single JSON with both keys: {"research_directive": {...}, "validation_thesis": {...}}
    - Two separate JSON blocks in the text
    - A single research_directive JSON (non-terminal rounds)

    Returns a dict with both keys when both are found, otherwise a
    ResearchDirective for backward compatibility.
    """
    # Try the standard extraction first (handles fences, pure JSON, first-object)
    try:
        data = _extract_json(text)
    except (json.JSONDecodeError, ValueError):
        data = {}

    # Single wrapper with both keys
    if "research_directive" in data and "validation_thesis" in data:
        return data

    # Single wrapper with just research_directive
    if "research_directive" in data and "validation_thesis" not in data:
        return ResearchDirective.model_validate(
            data["research_directive"], strict=False
        )

    # The first object might BE a research_directive (no wrapper key)
    # Before falling back, try to find multiple JSON objects in the text
    all_objects = _find_all_json_objects(text)

    if len(all_objects) >= 2:
        result: dict[str, Any] = {}
        for obj in all_objects:
            if "research_directive" in obj:
                result["research_directive"] = obj["research_directive"]
            elif "validation_thesis" in obj:
                result["validation_thesis"] = obj["validation_thesis"]
            elif "verdict" in obj and "directives" in obj:
                result["research_directive"] = obj
            elif "thesis_statement" in obj:
                result["validation_thesis"] = obj
        if "research_directive" in result:
            return result

    # Fallback: single object is the directive itself
    if data and "verdict" in data:
        return ResearchDirective.model_validate(data, strict=False)

    # Last resort: first extracted object
    if all_objects:
        raw = all_objects[0]
        rd = raw.get("research_directive", raw)
        return ResearchDirective.model_validate(rd, strict=False)

    raise json.JSONDecodeError("No JSON object found in integrator output", text, 0)


async def run_agent(
    role: AgentRole,
    idea: str,
    round_num: int,
    runner: Runner,
    config: FounderFlowConfig,
    *,
    project_path: Path | None = None,
    prior_output: str | None = None,
    directive: FollowUpDirective | None = None,
    is_terminal: bool = False,
) -> AgentResult:
    """Resolve prompt, build task, invoke runner, parse response."""
    system_prompt = resolve_prompt(role, project_path)

    if role == AgentRole.evidence_integrator and is_terminal:
        system_prompt += (
            "\n\nThis is the FINAL round. You MUST produce both a "
            "`research_directive` and a `validation_thesis` in your response."
        )

    task_prompt = build_task_prompt(role, idea, round_num, prior_output, directive)

    model = (
        config.get_integrator_model()
        if role == AgentRole.evidence_integrator
        else config.model
    )

    start_ms = int(time.time() * 1000)
    text, return_code, usage = await runner.headless(
        prompt=system_prompt,
        task=task_prompt,
        cwd=project_path or Path.cwd(),
        timeout=float(config.per_agent_timeout),
        model=model,
    )
    duration_ms = int(time.time() * 1000) - start_ms

    if return_code != 0:
        return AgentResult(
            role=role,
            text=text,
            return_code=return_code,
            usage=usage,
            error=f"Agent exited with code {return_code}",
        )

    try:
        parsed = _parse_agent_output(role, text)
    except (json.JSONDecodeError, ValidationError, KeyError) as exc:
        log.warning(
            "agent_output_parse_error",
            role=role.value,
            error=str(exc),
            text_len=len(text),
        )
        return AgentResult(
            role=role,
            text=text,
            return_code=return_code,
            usage=usage,
            error=f"Parse error: {exc}",
        )

    if usage and duration_ms > 0:
        usage = AgentUsage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_creation_tokens=usage.cache_creation_tokens,
            total_cost_usd=usage.total_cost_usd,
            duration_ms=duration_ms,
            num_turns=usage.num_turns,
            model=usage.model,
        )

    return AgentResult(
        role=role,
        text=text,
        parsed_output=parsed,
        return_code=return_code,
        usage=usage,
    )


async def run_agent_safe(
    role: AgentRole,
    idea: str,
    round_num: int,
    runner: Runner,
    config: FounderFlowConfig,
    *,
    project_path: Path | None = None,
    prior_output: str | None = None,
    directive: FollowUpDirective | None = None,
    is_terminal: bool = False,
) -> AgentResult:
    """Wraps run_agent with exception handling — never raises."""
    try:
        return await run_agent(
            role,
            idea,
            round_num,
            runner,
            config,
            project_path=project_path,
            prior_output=prior_output,
            directive=directive,
            is_terminal=is_terminal,
        )
    except Exception as exc:
        log.error(
            "agent_run_failed",
            role=role.value,
            round_num=round_num,
            error=str(exc),
        )
        return AgentResult(
            role=role,
            text="",
            return_code=1,
            error=f"Exception: {exc}",
        )
