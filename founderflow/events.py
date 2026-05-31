from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from founderflow.models import AgentUsage

EVENT_PIPELINE_STARTED = "pipeline.started"
EVENT_PIPELINE_COMPLETED = "pipeline.completed"
EVENT_ROUND_STARTED = "round.started"
EVENT_ROUND_COMPLETED = "round.completed"
EVENT_ROUND_CONVERGENCE_CHECK = "round.convergence_check"
EVENT_AGENT_STARTED = "agent.started"
EVENT_AGENT_COMPLETED = "agent.completed"
EVENT_AGENT_FAILED = "agent.failed"
EVENT_AGENT_TIMEOUT = "agent.timeout"
EVENT_GATE_PASSED = "gate.passed"
EVENT_GATE_FAILED = "gate.failed"
EVENT_SYNTHESIS_STARTED = "synthesis.started"
EVENT_SYNTHESIS_COMPLETED = "synthesis.completed"


def emit_event(
    run_path: Path,
    event_type: str,
    *,
    agent: str | None = None,
    round_num: int | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    event = {
        "event": event_type,
        "timestamp": time.time(),
    }
    if agent is not None:
        event["agent"] = agent
    if round_num is not None:
        event["round_num"] = round_num
    if data is not None:
        event["data"] = data

    events_file = run_path / "events.jsonl"
    with events_file.open("a") as f:
        f.write(json.dumps(event) + "\n")


def _read_events(run_path: Path) -> list[dict[str, Any]]:
    events_file = run_path / "events.jsonl"
    if not events_file.exists():
        return []
    events = []
    for line in events_file.read_text().splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def sum_agent_costs(run_path: Path) -> AgentUsage:
    events = _read_events(run_path)
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_creation = 0
    total_cost = 0.0
    total_duration = 0
    total_turns = 0
    model = ""

    for event in events:
        if event.get("event") != EVENT_AGENT_COMPLETED:
            continue
        usage_data = event.get("data", {}).get("usage")
        if not usage_data:
            continue
        total_input += usage_data.get("input_tokens", 0)
        total_output += usage_data.get("output_tokens", 0)
        total_cache_read += usage_data.get("cache_read_tokens", 0)
        total_cache_creation += usage_data.get("cache_creation_tokens", 0)
        total_cost += usage_data.get("total_cost_usd", 0.0)
        total_duration += usage_data.get("duration_ms", 0)
        total_turns += usage_data.get("num_turns", 0)
        if not model:
            model = usage_data.get("model", "")

    return AgentUsage(
        input_tokens=total_input,
        output_tokens=total_output,
        cache_read_tokens=total_cache_read,
        cache_creation_tokens=total_cache_creation,
        total_cost_usd=total_cost,
        duration_ms=total_duration,
        num_turns=total_turns,
        model=model or "unknown",
    )


def sum_round_costs(run_path: Path, round_num: int) -> AgentUsage:
    events = _read_events(run_path)
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_creation = 0
    total_cost = 0.0
    total_duration = 0
    total_turns = 0
    model = ""

    for event in events:
        if event.get("event") != EVENT_AGENT_COMPLETED:
            continue
        if event.get("round_num") != round_num:
            continue
        usage_data = event.get("data", {}).get("usage")
        if not usage_data:
            continue
        total_input += usage_data.get("input_tokens", 0)
        total_output += usage_data.get("output_tokens", 0)
        total_cache_read += usage_data.get("cache_read_tokens", 0)
        total_cache_creation += usage_data.get("cache_creation_tokens", 0)
        total_cost += usage_data.get("total_cost_usd", 0.0)
        total_duration += usage_data.get("duration_ms", 0)
        total_turns += usage_data.get("num_turns", 0)
        if not model:
            model = usage_data.get("model", "")

    return AgentUsage(
        input_tokens=total_input,
        output_tokens=total_output,
        cache_read_tokens=total_cache_read,
        cache_creation_tokens=total_cache_creation,
        total_cost_usd=total_cost,
        duration_ms=total_duration,
        num_turns=total_turns,
        model=model or "unknown",
    )
