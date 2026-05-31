from __future__ import annotations

from founderflow.models import AgentUsage


def _parse_usage(data: dict) -> AgentUsage:
    usage = data.get("usage", data)

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0) or usage.get(
        "cache_read_tokens", 0
    )
    cache_creation = usage.get("cache_creation_input_tokens", 0) or usage.get(
        "cache_creation_tokens", 0
    )
    cost = usage.get("total_cost_usd", 0.0) or usage.get("cost_usd", 0.0)
    duration = usage.get("duration_ms", 0)
    num_turns = usage.get("num_turns", 0)
    model = usage.get("model", "unknown")

    return AgentUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
        total_cost_usd=cost,
        duration_ms=duration,
        num_turns=num_turns,
        model=model,
    )
