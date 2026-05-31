from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentRole(str, Enum):
    idea_validator = "idea_validator"
    competitor_analyst = "competitor_analyst"
    customer_discovery = "customer_discovery"
    evidence_integrator = "evidence_integrator"


class Verdict(str, Enum):
    go = "go"
    deeper = "deeper"
    pivot = "pivot"
    kill = "kill"


class DirectiveVerdict(str, Enum):
    needs_deeper = "needs_deeper"
    evidence_sufficient = "evidence_sufficient"


class ConvergenceReason(str, Enum):
    evidence_sufficient = "evidence_sufficient"
    max_rounds = "max_rounds"
    budget_exhausted = "budget_exhausted"


class Priority(str, Enum):
    high = "high"
    medium = "medium"


class AgentUsage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    total_cost_usd: float
    duration_ms: int
    num_turns: int
    model: str


class IdeaValidation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    problem_severity: str
    target_customer_clarity: str
    value_proposition_strength: str
    risk_factors: list[str]
    core_assumptions: list[str]
    confidence_score: int = Field(ge=0, le=100)
    summary: str


class CompetitorAnalysis(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    direct_competitors: list[dict[str, Any]]
    indirect_competitors: list[dict[str, Any]]
    substitutes: list[str]
    workarounds: list[str]
    pricing_patterns: list[str]
    positioning_gaps: list[str]
    confidence_score: int = Field(ge=0, le=100)
    summary: str


class CustomerDiscovery(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    interview_targets: list[str]
    discovery_questions: list[str]
    demand_signals: list[str]
    weak_signal_warnings: list[str]
    validation_experiment: str
    confidence_score: int = Field(ge=0, le=100)
    summary: str


class FollowUpDirective(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    agent_role: AgentRole
    follow_up_question: str
    priority: Priority


class ResearchDirective(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    verdict: DirectiveVerdict
    directives: list[FollowUpDirective]
    resolved_contradictions: list[str]
    remaining_gaps: list[str]
    round_confidence: int = Field(ge=0, le=100)


class ValidationThesis(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    thesis_statement: str
    confidence_score: int = Field(ge=0, le=100)
    verdict: Verdict
    contradictions: list[str]
    unresolved_assumptions: list[str]
    risk_assessment: str
    research_journey_summary: str
    total_rounds: int
    convergence_reason: ConvergenceReason


class RoundResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    round_num: int
    active_agents: list[AgentRole]
    agent_outputs: dict[str, Any]
    directive: ResearchDirective
    usage: AgentUsage
    duration_ms: int
    started_at: str
    completed_at: str


class CostSummary(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    per_round: list[AgentUsage]
    per_agent: dict[str, AgentUsage]


class ActionItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    day: int
    action: str
    details: str


class StartupBrief(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    thesis: ValidationThesis
    idea_validation: IdeaValidation
    competitor_analysis: CompetitorAnalysis
    customer_discovery: CustomerDiscovery
    round_results: list[RoundResult]
    action_plan: list[ActionItem]
    cost_summary: CostSummary
    generated_at: str
    idea: str
