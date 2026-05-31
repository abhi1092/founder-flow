from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Callable

import structlog

from founderflow.agents.protocol import Runner
from founderflow.agents.runner import AgentResult, run_agent_safe
from founderflow.config import FounderFlowConfig
from founderflow.events import (
    EVENT_AGENT_COMPLETED,
    EVENT_AGENT_FAILED,
    EVENT_AGENT_STARTED,
    EVENT_PIPELINE_COMPLETED,
    EVENT_PIPELINE_STARTED,
    EVENT_ROUND_COMPLETED,
    EVENT_ROUND_CONVERGENCE_CHECK,
    EVENT_ROUND_STARTED,
    EVENT_SYNTHESIS_COMPLETED,
    EVENT_SYNTHESIS_STARTED,
    emit_event,
    sum_round_costs,
)
from founderflow.models import (
    ActionItem,
    AgentRole,
    AgentUsage,
    ConvergenceReason,
    CostSummary,
    DirectiveVerdict,
    FollowUpDirective,
    ResearchDirective,
    StartupBrief,
    ValidationThesis,
    Verdict,
)
from founderflow.state import RunState, detect_state, save_state
from founderflow.store import RunStore

log = structlog.get_logger()

SPECIALIST_ROLES = [
    AgentRole.idea_validator,
    AgentRole.competitor_analyst,
    AgentRole.customer_discovery,
]

ROLE_OUTPUT_KEY = {
    AgentRole.idea_validator: "idea_validation",
    AgentRole.competitor_analyst: "competitor_analysis",
    AgentRole.customer_discovery: "customer_discovery",
}


ProgressCallback = Callable[[dict[str, Any]], None]


def _usage_dict(usage: AgentUsage | None) -> dict[str, Any]:
    if usage is None:
        return {}
    return usage.model_dump()


def _merge_usage(usages: list[AgentUsage]) -> AgentUsage:
    if not usages:
        return AgentUsage(
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            total_cost_usd=0.0,
            duration_ms=0,
            num_turns=0,
            model="unknown",
        )
    return AgentUsage(
        input_tokens=sum(u.input_tokens for u in usages),
        output_tokens=sum(u.output_tokens for u in usages),
        cache_read_tokens=sum(u.cache_read_tokens for u in usages),
        cache_creation_tokens=sum(u.cache_creation_tokens for u in usages),
        total_cost_usd=sum(u.total_cost_usd for u in usages),
        duration_ms=max(u.duration_ms for u in usages),
        num_turns=sum(u.num_turns for u in usages),
        model=usages[0].model,
    )


def _emit_progress(on_progress: ProgressCallback | None, event: dict[str, Any]) -> None:
    if on_progress is not None:
        try:
            on_progress(event)
        except Exception:
            pass


async def _run_round(
    run_id: str,
    run_path: Path,
    idea: str,
    round_num: int,
    roles: list[AgentRole],
    runner: Runner,
    config: FounderFlowConfig,
    store: RunStore,
    on_progress: ProgressCallback | None,
    *,
    project_path: Path | None = None,
    prior_outputs: dict[AgentRole, str] | None = None,
    directives: dict[AgentRole, FollowUpDirective] | None = None,
    is_terminal: bool = False,
) -> tuple[list[AgentResult], dict[str, Any]]:
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    emit_event(
        run_path,
        EVENT_ROUND_STARTED,
        round_num=round_num,
        data={"active_agents": [r.value for r in roles]},
    )
    _emit_progress(
        on_progress,
        {
            "type": "round_started",
            "round_num": round_num,
            "active_agents": [r.value for r in roles],
        },
    )

    async def _invoke(role: AgentRole) -> AgentResult:
        emit_event(run_path, EVENT_AGENT_STARTED, agent=role.value, round_num=round_num)
        _emit_progress(
            on_progress,
            {
                "type": "agent_started",
                "round_num": round_num,
                "agent": role.value,
            },
        )

        prior = prior_outputs.get(role) if prior_outputs else None
        directive = directives.get(role) if directives else None

        result = await run_agent_safe(
            role,
            idea,
            round_num,
            runner,
            config,
            project_path=project_path,
            prior_output=prior,
            directive=directive,
            is_terminal=is_terminal,
        )

        if result.error:
            emit_event(
                run_path,
                EVENT_AGENT_FAILED,
                agent=role.value,
                round_num=round_num,
                data={"error": result.error},
            )
        else:
            emit_event(
                run_path,
                EVENT_AGENT_COMPLETED,
                agent=role.value,
                round_num=round_num,
                data={"usage": _usage_dict(result.usage)},
            )

        _emit_progress(
            on_progress,
            {
                "type": "agent_completed",
                "round_num": round_num,
                "agent": role.value,
                "error": result.error,
                "usage": _usage_dict(result.usage),
            },
        )

        return result

    results = await asyncio.gather(*[_invoke(role) for role in roles])

    agent_outputs: dict[str, Any] = {}
    for result in results:
        output_data = (
            result.parsed_output.model_dump()
            if hasattr(result.parsed_output, "model_dump")
            else result.parsed_output
        )
        if output_data is not None:
            key = ROLE_OUTPUT_KEY.get(result.role, result.role.value)
            agent_outputs[key] = output_data
            store.save_round_output(run_id, round_num, result.role.value, output_data)

    completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    round_usage = sum_round_costs(run_path, round_num)

    emit_event(
        run_path,
        EVENT_ROUND_COMPLETED,
        round_num=round_num,
        data={"cost_usd": round_usage.total_cost_usd},
    )
    _emit_progress(
        on_progress,
        {
            "type": "round_completed",
            "round_num": round_num,
            "cost_usd": round_usage.total_cost_usd,
        },
    )

    round_meta = {
        "started_at": started_at,
        "completed_at": completed_at,
        "agent_outputs": agent_outputs,
    }

    return list(results), round_meta


async def _run_integrator(
    run_id: str,
    run_path: Path,
    idea: str,
    round_num: int,
    agent_outputs: dict[str, Any],
    runner: Runner,
    config: FounderFlowConfig,
    store: RunStore,
    on_progress: ProgressCallback | None,
    *,
    project_path: Path | None = None,
    is_terminal: bool = False,
    prior_directive: ResearchDirective | None = None,
) -> tuple[ResearchDirective, ValidationThesis | None]:
    emit_event(run_path, EVENT_SYNTHESIS_STARTED, round_num=round_num)

    integrator_task_parts = [f"Startup idea: {idea}"]
    integrator_task_parts.append(
        f"\n\nCurrent round ({round_num}) agent outputs:\n" + json.dumps(agent_outputs, indent=2)
    )
    if prior_directive:
        integrator_task_parts.append(
            "\n\nPrior round directive summary:\n" + prior_directive.model_dump_json(indent=2)
        )

    if is_terminal:
        integrator_task_parts.append(
            f"\n\nThis is round {round_num} of {config.max_rounds}. "
            "This is the FINAL round — produce both research_directive and validation_thesis."
        )

    integrator_task = "\n".join(integrator_task_parts)

    result = await run_agent_safe(
        AgentRole.evidence_integrator,
        integrator_task,
        round_num,
        runner,
        config,
        project_path=project_path,
        is_terminal=is_terminal,
    )

    directive: ResearchDirective | None = None
    thesis: ValidationThesis | None = None

    if result.parsed_output is not None:
        if isinstance(result.parsed_output, ResearchDirective):
            directive = result.parsed_output
        elif isinstance(result.parsed_output, dict):
            if "research_directive" in result.parsed_output:
                directive = ResearchDirective.model_validate(
                    result.parsed_output["research_directive"], strict=False
                )
            if "validation_thesis" in result.parsed_output:
                thesis = ValidationThesis.model_validate(
                    result.parsed_output["validation_thesis"], strict=False
                )

    if result.text and (directive is None or thesis is None):
        try:
            raw = json.loads(result.text) if isinstance(result.text, str) else result.text
            if isinstance(raw, dict):
                if directive is None:
                    rd = raw.get("research_directive", raw)
                    directive = ResearchDirective.model_validate(rd, strict=False)
                if thesis is None and "validation_thesis" in raw:
                    thesis = ValidationThesis.model_validate(raw["validation_thesis"], strict=False)
        except Exception:
            log.warning("integrator_parse_fallback_failed", round_num=round_num)

    if directive is None:
        directive = ResearchDirective(
            verdict=DirectiveVerdict.evidence_sufficient,
            directives=[],
            resolved_contradictions=[],
            remaining_gaps=["Integrator failed to produce a valid directive"],
            round_confidence=0,
        )

    store.save_directive(run_id, round_num, directive)

    emit_event(
        run_path,
        EVENT_ROUND_CONVERGENCE_CHECK,
        round_num=round_num,
        data={
            "verdict": directive.verdict.value,
            "round_confidence": directive.round_confidence,
            "num_directives": len(directive.directives),
        },
    )
    emit_event(run_path, EVENT_SYNTHESIS_COMPLETED, round_num=round_num)

    _emit_progress(
        on_progress,
        {
            "type": "integrator_completed",
            "round_num": round_num,
            "verdict": directive.verdict.value,
            "round_confidence": directive.round_confidence,
        },
    )

    return directive, thesis


def _generate_action_plan(
    thesis: ValidationThesis,
    idea_validation: dict[str, Any] | None,
    competitor_analysis: dict[str, Any] | None,
    customer_discovery: dict[str, Any] | None,
) -> list[ActionItem]:
    verdict = thesis.verdict

    if verdict == Verdict.go:
        return [
            ActionItem(
                day=1,
                action="Draft one-page business plan",
                details="Incorporate thesis findings: target customer, value proposition, and competitive positioning",
            ),
            ActionItem(
                day=2,
                action="Identify 5 potential early customers",
                details="Use interview targets from customer discovery to build outreach list",
            ),
            ActionItem(
                day=3,
                action="Design MVP feature set",
                details="Focus on core value proposition; strip to minimum testable product",
            ),
            ActionItem(
                day=4,
                action="Set up landing page or waitlist",
                details="Validate demand signals with a real conversion funnel",
            ),
            ActionItem(
                day=5,
                action="Conduct 3 customer discovery interviews",
                details="Use discovery questions identified in research to validate assumptions",
            ),
            ActionItem(
                day=6,
                action="Analyze competitive pricing and positioning",
                details="Define pricing strategy based on competitor pricing patterns and positioning gaps",
            ),
            ActionItem(
                day=7,
                action="Create 30-day execution roadmap",
                details="Prioritize by risk: address highest-risk assumptions first",
            ),
        ]
    elif verdict == Verdict.deeper:
        questions = []
        if customer_discovery:
            questions = customer_discovery.get("discovery_questions", [])[:2]
        return [
            ActionItem(
                day=1,
                action="Map unresolved assumptions",
                details=f"Focus on: {', '.join(thesis.unresolved_assumptions[:3]) or 'key assumptions from thesis'}",
            ),
            ActionItem(
                day=2,
                action="Design lightweight validation experiment",
                details=customer_discovery.get(
                    "validation_experiment", "Design a cheap test for core assumption"
                )
                if customer_discovery
                else "Design a cheap test for core assumption",
            ),
            ActionItem(
                day=3,
                action="Conduct 2 expert interviews",
                details=f"Key questions: {'; '.join(questions) or 'validate core market assumptions'}",
            ),
            ActionItem(
                day=4,
                action="Research competitor weak points",
                details="Deep-dive into positioning gaps and underserved segments identified in analysis",
            ),
            ActionItem(
                day=5,
                action="Run validation experiment",
                details="Execute the cheapest possible test of your riskiest assumption",
            ),
            ActionItem(
                day=6,
                action="Synthesize findings",
                details="Compare experiment results against thesis contradictions and gaps",
            ),
            ActionItem(
                day=7,
                action="Make go/no-go decision",
                details="Based on week's evidence, decide: commit, pivot, or abandon",
            ),
        ]
    elif verdict == Verdict.pivot:
        risks = thesis.risk_assessment or "fundamental positioning issues"
        return [
            ActionItem(day=1, action="Document pivot rationale", details=f"Core issue: {risks}"),
            ActionItem(
                day=2,
                action="Brainstorm 3 alternative approaches",
                details="Vary target customer, distribution channel, or value proposition",
            ),
            ActionItem(
                day=3,
                action="Score alternatives against original risks",
                details="Which alternative avoids the fatal flaws identified in analysis?",
            ),
            ActionItem(
                day=4,
                action="Pick strongest alternative and redefine hypothesis",
                details="Write a clear, testable statement of the new approach",
            ),
            ActionItem(
                day=5,
                action="Identify 3 people to validate new direction",
                details="Different target segment may require different interview subjects",
            ),
            ActionItem(
                day=6,
                action="Conduct rapid customer conversations",
                details="30-minute conversations focused on the new value proposition",
            ),
            ActionItem(
                day=7,
                action="Assess pivot viability",
                details="Does the new direction have stronger demand signals than the original?",
            ),
        ]
    else:  # kill
        return [
            ActionItem(
                day=1,
                action="Document lessons learned",
                details="What specific evidence killed this idea? Capture for future reference",
            ),
            ActionItem(
                day=2,
                action="Extract reusable insights",
                details="Market knowledge, customer contacts, and technical learnings from this exploration",
            ),
            ActionItem(
                day=3,
                action="Identify adjacent opportunities",
                details="Did research reveal unmet needs in adjacent markets or customer segments?",
            ),
            ActionItem(
                day=4,
                action="Talk to 2 people in the space",
                details="Share findings and ask: what problems do YOU see that nobody is solving?",
            ),
            ActionItem(
                day=5,
                action="Brainstorm new ideas using gathered insights",
                details="Use demand signals, weak points, and market gaps as inspiration",
            ),
            ActionItem(
                day=6,
                action="Select most promising new direction",
                details="Apply lessons from this failure: stronger evidence threshold before committing",
            ),
            ActionItem(
                day=7,
                action="Write hypothesis for next idea",
                details="Clear problem statement, target customer, and first validation step",
            ),
        ]


def _build_cost_summary(
    run_path: Path,
    round_results: list[dict[str, Any]],
    num_rounds: int,
) -> CostSummary:
    per_round: list[AgentUsage] = []
    per_agent: dict[str, AgentUsage] = {}

    for rr in round_results:
        usage = rr.get("usage")
        if usage:
            per_round.append(usage)

    total = (
        _merge_usage(per_round)
        if per_round
        else AgentUsage(
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            total_cost_usd=0.0,
            duration_ms=0,
            num_turns=0,
            model="unknown",
        )
    )

    return CostSummary(
        total_cost_usd=total.total_cost_usd,
        total_input_tokens=total.input_tokens,
        total_output_tokens=total.output_tokens,
        per_round=per_round,
        per_agent=per_agent,
    )


def _find_completed_agents(run_path: Path, round_num: int) -> set[str]:
    round_dir = run_path / "rounds" / str(round_num)
    if not round_dir.exists():
        return set()
    return {f.stem for f in round_dir.iterdir() if f.suffix == ".json" and f.stem != "directive"}


async def run_pipeline(
    idea: str,
    config: FounderFlowConfig,
    store: RunStore,
    runner: Runner,
    on_progress: ProgressCallback | None = None,
    *,
    project_path: Path | None = None,
) -> StartupBrief:
    run_id = store.create_run(idea, config.model_dump())
    run_path = store.get_run(run_id)

    current_state, current_round = detect_state(run_path)
    if current_state not in (RunState.SUBMITTED, RunState.COMPLETE, RunState.FAILED):
        completed = _find_completed_agents(run_path, current_round)
        log.info(
            "pipeline.resume",
            state=current_state.value,
            round=current_round,
            completed_agents=list(completed),
        )

    emit_event(
        run_path, EVENT_PIPELINE_STARTED, data={"idea": idea, "max_rounds": config.max_rounds}
    )
    _emit_progress(on_progress, {"type": "pipeline_started", "run_id": run_id, "idea": idea})

    save_state(run_path, RunState.VALIDATING, 1)

    all_round_results: list[dict[str, Any]] = []
    latest_outputs: dict[str, Any] = {}
    prior_agent_texts: dict[AgentRole, str] = {}

    round_num = 1
    is_terminal = config.max_rounds == 1

    results, round_meta = await _run_round(
        run_id,
        run_path,
        idea,
        round_num,
        SPECIALIST_ROLES,
        runner,
        config,
        store,
        on_progress,
        project_path=project_path,
        is_terminal=False,
    )

    for r in results:
        if r.parsed_output is not None:
            key = ROLE_OUTPUT_KEY.get(r.role, r.role.value)
            latest_outputs[key] = (
                r.parsed_output.model_dump()
                if hasattr(r.parsed_output, "model_dump")
                else r.parsed_output
            )
        prior_agent_texts[r.role] = r.text

    directive, thesis = await _run_integrator(
        run_id,
        run_path,
        idea,
        round_num,
        latest_outputs,
        runner,
        config,
        store,
        on_progress,
        project_path=project_path,
        is_terminal=is_terminal,
    )

    round_usage = sum_round_costs(run_path, round_num)
    all_round_results.append(
        {
            "round_num": round_num,
            "active_agents": SPECIALIST_ROLES,
            "agent_outputs": round_meta["agent_outputs"],
            "directive": directive,
            "usage": round_usage,
            "started_at": round_meta["started_at"],
            "completed_at": round_meta["completed_at"],
        }
    )

    round_num = 2
    entered_deepening = False

    while directive.verdict == DirectiveVerdict.needs_deeper and round_num <= config.max_rounds:
        is_terminal = round_num == config.max_rounds

        if not entered_deepening:
            save_state(run_path, RunState.DEEPENING, round_num)
            entered_deepening = True
        else:
            save_state(run_path, RunState.DEEPENING, round_num)

        agents_to_run: list[AgentRole] = []
        directive_map: dict[AgentRole, FollowUpDirective] = {}
        for d in directive.directives:
            if d.agent_role in SPECIALIST_ROLES:
                agents_to_run.append(d.agent_role)
                directive_map[d.agent_role] = d

        if not agents_to_run:
            log.info("pipeline.no_agents_to_run", round_num=round_num)
            break

        results, round_meta = await _run_round(
            run_id,
            run_path,
            idea,
            round_num,
            agents_to_run,
            runner,
            config,
            store,
            on_progress,
            project_path=project_path,
            prior_outputs=prior_agent_texts,
            directives=directive_map,
            is_terminal=False,
        )

        for r in results:
            if r.parsed_output is not None:
                key = ROLE_OUTPUT_KEY.get(r.role, r.role.value)
                latest_outputs[key] = (
                    r.parsed_output.model_dump()
                    if hasattr(r.parsed_output, "model_dump")
                    else r.parsed_output
                )
            prior_agent_texts[r.role] = r.text

        directive, thesis = await _run_integrator(
            run_id,
            run_path,
            idea,
            round_num,
            latest_outputs,
            runner,
            config,
            store,
            on_progress,
            project_path=project_path,
            is_terminal=is_terminal,
            prior_directive=directive,
        )

        round_usage = sum_round_costs(run_path, round_num)
        all_round_results.append(
            {
                "round_num": round_num,
                "active_agents": agents_to_run,
                "agent_outputs": round_meta["agent_outputs"],
                "directive": directive,
                "usage": round_usage,
                "started_at": round_meta["started_at"],
                "completed_at": round_meta["completed_at"],
            }
        )

        round_num += 1

    save_state(run_path, RunState.SYNTHESIZING, round_num - 1)

    if thesis is None:
        _, thesis = await _run_integrator(
            run_id,
            run_path,
            idea,
            round_num - 1,
            latest_outputs,
            runner,
            config,
            store,
            on_progress,
            project_path=project_path,
            is_terminal=True,
            prior_directive=directive,
        )

    if thesis is None:
        convergence = ConvergenceReason.max_rounds
        if directive.verdict == DirectiveVerdict.evidence_sufficient:
            convergence = ConvergenceReason.evidence_sufficient

        thesis = ValidationThesis(
            thesis_statement="Unable to produce a definitive thesis — integrator did not return structured output",
            confidence_score=0,
            verdict=Verdict.deeper,
            contradictions=[],
            unresolved_assumptions=["Integrator output could not be parsed"],
            risk_assessment="Assessment could not be completed",
            research_journey_summary=f"Completed {round_num - 1} round(s) of research",
            total_rounds=round_num - 1,
            convergence_reason=convergence,
        )

    store.save_synthesis(run_id, thesis)

    action_plan = _generate_action_plan(
        thesis,
        latest_outputs.get("idea_validation"),
        latest_outputs.get("competitor_analysis"),
        latest_outputs.get("customer_discovery"),
    )

    round_result_models = []
    for rr in all_round_results:
        from founderflow.models import RoundResult

        round_result_models.append(
            RoundResult(
                round_num=rr["round_num"],
                active_agents=rr["active_agents"],
                agent_outputs=rr["agent_outputs"],
                directive=rr["directive"],
                usage=rr["usage"],
                duration_ms=rr["usage"].duration_ms,
                started_at=rr["started_at"],
                completed_at=rr["completed_at"],
            )
        )

    cost_summary = _build_cost_summary(run_path, all_round_results, round_num - 1)

    from founderflow.models import (
        CompetitorAnalysis,
        CustomerDiscovery,
        IdeaValidation,
    )

    iv_data = latest_outputs.get("idea_validation", {})
    ca_data = latest_outputs.get("competitor_analysis", {})
    cd_data = latest_outputs.get("customer_discovery", {})

    brief = StartupBrief(
        thesis=thesis,
        idea_validation=IdeaValidation.model_validate(iv_data, strict=False),
        competitor_analysis=CompetitorAnalysis.model_validate(ca_data, strict=False),
        customer_discovery=CustomerDiscovery.model_validate(cd_data, strict=False),
        round_results=round_result_models,
        action_plan=action_plan,
        cost_summary=cost_summary,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        idea=idea,
    )

    store.save_brief(run_id, brief)

    save_state(run_path, RunState.RENDERING, round_num - 1)

    store.append_tsv(
        run_id,
        {
            "run_id": run_id,
            "idea": idea[:80],
            "verdict": thesis.verdict.value,
            "confidence": str(thesis.confidence_score),
            "rounds": str(thesis.total_rounds),
            "cost_usd": f"{cost_summary.total_cost_usd:.4f}",
            "generated_at": brief.generated_at,
        },
    )

    save_state(run_path, RunState.COMPLETE, round_num - 1)

    emit_event(
        run_path,
        EVENT_PIPELINE_COMPLETED,
        data={
            "verdict": thesis.verdict.value,
            "confidence": thesis.confidence_score,
            "total_rounds": len(all_round_results),
            "cost_usd": cost_summary.total_cost_usd,
        },
    )
    _emit_progress(
        on_progress,
        {
            "type": "pipeline_completed",
            "run_id": run_id,
            "verdict": thesis.verdict.value,
            "confidence": thesis.confidence_score,
        },
    )

    return brief
