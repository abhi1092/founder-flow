from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from founderflow.models import AgentRole


@dataclass
class GateFailure:
    agent_role: AgentRole | None
    check_name: str
    message: str


@dataclass
class GateResult:
    passed: bool
    failures: list[GateFailure] = field(default_factory=list)
    degraded_agents: list[AgentRole] = field(default_factory=list)


EventEmitter = Callable[..., None] | None

SPECIALIST_ROLES = {
    AgentRole.idea_validator,
    AgentRole.competitor_analyst,
    AgentRole.customer_discovery,
}

ROLE_OUTPUT_KEY = {
    AgentRole.idea_validator: "idea_validation",
    AgentRole.competitor_analyst: "competitor_analysis",
    AgentRole.customer_discovery: "customer_discovery",
}


def _check_schema_completeness(
    role: AgentRole, output: dict[str, Any]
) -> list[GateFailure]:
    failures: list[GateFailure] = []
    if not output:
        failures.append(
            GateFailure(
                agent_role=role,
                check_name="schema_completeness",
                message=f"{role.value}: output is empty",
            )
        )
        return failures

    for key, value in output.items():
        if key == "confidence_score":
            continue
        if isinstance(value, str) and not value.strip():
            failures.append(
                GateFailure(
                    agent_role=role,
                    check_name="schema_completeness",
                    message=f"{role.value}: field '{key}' is empty",
                )
            )
        elif isinstance(value, list) and len(value) == 0:
            if key in (
                "risk_factors",
                "core_assumptions",
                "direct_competitors",
                "indirect_competitors",
                "substitutes",
                "discovery_questions",
                "interview_targets",
                "demand_signals",
            ):
                failures.append(
                    GateFailure(
                        agent_role=role,
                        check_name="schema_completeness",
                        message=f"{role.value}: field '{key}' is empty list",
                    )
                )
    return failures


def _check_content_thresholds(
    role: AgentRole, output: dict[str, Any]
) -> list[GateFailure]:
    failures: list[GateFailure] = []

    if role == AgentRole.competitor_analyst:
        total = (
            len(output.get("direct_competitors", []))
            + len(output.get("indirect_competitors", []))
            + len(output.get("substitutes", []))
        )
        if total < 2:
            failures.append(
                GateFailure(
                    agent_role=role,
                    check_name="min_content",
                    message=f"competitor_analyst: only {total} competitors/alternatives found (need >=2)",
                )
            )

    elif role == AgentRole.customer_discovery:
        questions = len(output.get("discovery_questions", []))
        if questions < 2:
            failures.append(
                GateFailure(
                    agent_role=role,
                    check_name="min_content",
                    message=f"customer_discovery: only {questions} discovery questions (need >=2)",
                )
            )

    elif role == AgentRole.idea_validator:
        risks = len(output.get("risk_factors", []))
        assumptions = len(output.get("core_assumptions", []))
        if risks < 1:
            failures.append(
                GateFailure(
                    agent_role=role,
                    check_name="min_content",
                    message="idea_validator: no risk factors identified (need >=1)",
                )
            )
        if assumptions < 1:
            failures.append(
                GateFailure(
                    agent_role=role,
                    check_name="min_content",
                    message="idea_validator: no core assumptions identified (need >=1)",
                )
            )

    return failures


def _check_confidence_floor(
    role: AgentRole, output: dict[str, Any]
) -> list[GateFailure]:
    score = output.get("confidence_score")
    if score is not None and score < 10:
        return [
            GateFailure(
                agent_role=role,
                check_name="confidence_floor",
                message=f"{role.value}: confidence {score} below floor of 10",
            )
        ]
    return []


def _check_agent_health(
    round_num: int, run_path: Path | None, active_roles: list[AgentRole]
) -> list[GateFailure]:
    if run_path is None:
        return []

    events_file = run_path / "events.jsonl"
    if not events_file.exists():
        return []

    import json

    failures: list[GateFailure] = []
    failed_agents: set[str] = set()

    for line in events_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        event = json.loads(line)
        if event.get("round_num") != round_num:
            continue
        if event.get("event") in ("agent.failed", "agent.timeout"):
            agent_name = event.get("agent", "")
            failed_agents.add(agent_name)

    for role in active_roles:
        if role.value in failed_agents:
            failures.append(
                GateFailure(
                    agent_role=role,
                    check_name="agent_health",
                    message=f"{role.value}: agent failed or timed out in round {round_num}",
                )
            )

    return failures


def run_gates(
    round_num: int,
    agent_results: dict[str, Any],
    event_emitter: EventEmitter = None,
    *,
    run_path: Path | None = None,
    active_roles: list[AgentRole] | None = None,
) -> GateResult:
    all_failures: list[GateFailure] = []
    degraded: list[AgentRole] = []

    roles_to_check = active_roles or list(SPECIALIST_ROLES)

    for role in roles_to_check:
        if role == AgentRole.evidence_integrator:
            continue

        output_key = ROLE_OUTPUT_KEY.get(role, role.value)
        output = agent_results.get(output_key)

        if output is None:
            all_failures.append(
                GateFailure(
                    agent_role=role,
                    check_name="missing_output",
                    message=f"{role.value}: no output found for this round",
                )
            )
            degraded.append(role)
            continue

        all_failures.extend(_check_schema_completeness(role, output))
        all_failures.extend(_check_content_thresholds(role, output))
        all_failures.extend(_check_confidence_floor(role, output))

    all_failures.extend(_check_agent_health(round_num, run_path, roles_to_check))

    for f in all_failures:
        if f.agent_role and f.agent_role not in degraded:
            if f.check_name in ("missing_output", "agent_health"):
                degraded.append(f.agent_role)

    passed = len(all_failures) == 0

    if event_emitter is not None:
        event_type = "gate.passed" if passed else "gate.failed"
        try:
            event_emitter(
                event_type,
                round_num=round_num,
                data={
                    "passed": passed,
                    "num_failures": len(all_failures),
                    "failures": [
                        {"check": f.check_name, "message": f.message}
                        for f in all_failures
                    ],
                },
            )
        except Exception:
            pass

    return GateResult(passed=passed, failures=all_failures, degraded_agents=degraded)
