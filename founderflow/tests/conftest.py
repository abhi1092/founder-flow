from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from founderflow.agents.protocol import Runner
from founderflow.models import (
    ActionItem,
    AgentRole,
    AgentUsage,
    CompetitorAnalysis,
    ConvergenceReason,
    CostSummary,
    CustomerDiscovery,
    DirectiveVerdict,
    FollowUpDirective,
    IdeaValidation,
    Priority,
    ResearchDirective,
    RoundResult,
    StartupBrief,
    ValidationThesis,
    Verdict,
)
from founderflow.store import RunStore


def _default_usage() -> AgentUsage:
    return AgentUsage(
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        total_cost_usd=0.001,
        duration_ms=500,
        num_turns=1,
        model="test-model",
    )


@pytest.fixture
def tmp_run_dir(tmp_path: Path) -> Path:
    ff_dir = tmp_path / ".founderflow"
    ff_dir.mkdir()
    runs_dir = ff_dir / "runs"
    runs_dir.mkdir()
    return ff_dir


@pytest.fixture
def sample_idea_validation() -> IdeaValidation:
    return IdeaValidation(
        problem_severity="High — users waste 3+ hours daily on manual data entry",
        target_customer_clarity="SMB accountants processing 50-200 invoices/month",
        value_proposition_strength="10x faster invoice processing via AI extraction",
        risk_factors=["OCR accuracy on handwritten invoices", "Integration complexity with legacy accounting software"],
        core_assumptions=["SMBs are willing to pay $50/mo for automation", "AI extraction reaches 95% accuracy"],
        confidence_score=72,
        summary="Strong problem-solution fit for SMB invoice automation.",
    )


@pytest.fixture
def sample_competitor_analysis() -> CompetitorAnalysis:
    return CompetitorAnalysis(
        direct_competitors=[
            {"name": "Dext", "description": "Receipt scanning and bookkeeping automation"},
            {"name": "Hubdoc", "description": "Document collection and data extraction"},
        ],
        indirect_competitors=[
            {"name": "QuickBooks", "description": "Full accounting suite with basic scanning"},
        ],
        substitutes=["Manual data entry", "Offshore bookkeeping services"],
        workarounds=["Excel spreadsheets with manual entry"],
        pricing_patterns=["$20-50/mo for SMB tier", "Usage-based pricing for enterprise"],
        positioning_gaps=["No competitor focuses on handwritten invoice support"],
        confidence_score=65,
        summary="Moderately competitive market with positioning opportunity.",
    )


@pytest.fixture
def sample_customer_discovery() -> CustomerDiscovery:
    return CustomerDiscovery(
        interview_targets=["SMB accountants", "Bookkeeping firm owners", "CFOs at 10-50 person companies"],
        discovery_questions=[
            "How many hours per week do you spend on invoice data entry?",
            "What tools have you tried and abandoned for this problem?",
            "What would you pay for a solution that eliminated manual entry?",
        ],
        demand_signals=["Reddit threads complaining about manual invoice entry", "Growing freelance bookkeeper market"],
        weak_signal_warnings=["Some SMBs may not trust AI with financial data"],
        validation_experiment="Landing page with waitlist to measure sign-up conversion",
        confidence_score=58,
        summary="Clear demand signals in SMB accounting segment.",
    )


@pytest.fixture
def sample_directive_needs_deeper() -> ResearchDirective:
    return ResearchDirective(
        verdict=DirectiveVerdict.needs_deeper,
        directives=[
            FollowUpDirective(
                agent_role=AgentRole.idea_validator,
                follow_up_question="Investigate accuracy requirements for handwritten vs printed invoices",
                priority=Priority.high,
            ),
            FollowUpDirective(
                agent_role=AgentRole.customer_discovery,
                follow_up_question="Explore willingness to pay among solo practitioners vs firms",
                priority=Priority.medium,
            ),
        ],
        resolved_contradictions=["Pricing expectations aligned across segments"],
        remaining_gaps=["Accuracy threshold for adoption", "Solo vs firm buying behavior"],
        round_confidence=45,
    )


@pytest.fixture
def sample_directive_sufficient() -> ResearchDirective:
    return ResearchDirective(
        verdict=DirectiveVerdict.evidence_sufficient,
        directives=[],
        resolved_contradictions=["Market size confirmed", "Pricing model validated"],
        remaining_gaps=[],
        round_confidence=80,
    )


@pytest.fixture
def sample_thesis() -> ValidationThesis:
    return ValidationThesis(
        thesis_statement="AI-powered invoice automation for SMB accountants is a viable opportunity with strong demand signals.",
        confidence_score=72,
        verdict=Verdict.go,
        contradictions=["Some concern about AI trust in financial workflows"],
        unresolved_assumptions=["95% accuracy is achievable with current models"],
        risk_assessment="Primary risk is OCR accuracy on diverse invoice formats.",
        research_journey_summary="2 rounds of research confirmed problem severity and market demand.",
        total_rounds=2,
        convergence_reason=ConvergenceReason.evidence_sufficient,
    )


@pytest.fixture
def sample_brief(
    sample_thesis: ValidationThesis,
    sample_idea_validation: IdeaValidation,
    sample_competitor_analysis: CompetitorAnalysis,
    sample_customer_discovery: CustomerDiscovery,
    sample_directive_needs_deeper: ResearchDirective,
    sample_directive_sufficient: ResearchDirective,
) -> StartupBrief:
    usage = _default_usage()
    return StartupBrief(
        thesis=sample_thesis,
        idea_validation=sample_idea_validation,
        competitor_analysis=sample_competitor_analysis,
        customer_discovery=sample_customer_discovery,
        round_results=[
            RoundResult(
                round_num=1,
                active_agents=[AgentRole.idea_validator, AgentRole.competitor_analyst, AgentRole.customer_discovery],
                agent_outputs={"idea_validation": sample_idea_validation.model_dump()},
                directive=sample_directive_needs_deeper,
                usage=usage,
                duration_ms=500,
                started_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-01T00:01:00Z",
            ),
            RoundResult(
                round_num=2,
                active_agents=[AgentRole.idea_validator, AgentRole.customer_discovery],
                agent_outputs={"idea_validation": sample_idea_validation.model_dump()},
                directive=sample_directive_sufficient,
                usage=usage,
                duration_ms=400,
                started_at="2026-01-01T00:01:00Z",
                completed_at="2026-01-01T00:02:00Z",
            ),
        ],
        action_plan=[
            ActionItem(day=1, action="Draft business plan", details="Incorporate thesis findings"),
            ActionItem(day=2, action="Find early customers", details="Use interview targets"),
        ],
        cost_summary=CostSummary(
            total_cost_usd=0.002,
            total_input_tokens=200,
            total_output_tokens=100,
            per_round=[usage, usage],
            per_agent={},
        ),
        generated_at="2026-01-01T00:02:00Z",
        idea="AI-powered invoice automation for SMB accountants",
    )


class MockRunner:
    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self._responses = responses or {}
        self._default_responses = {
            AgentRole.idea_validator.value: json.dumps({
                "problem_severity": "High",
                "target_customer_clarity": "SMB accountants",
                "value_proposition_strength": "Strong",
                "risk_factors": ["Market risk", "Tech risk"],
                "core_assumptions": ["Willing to pay", "AI is accurate enough"],
                "confidence_score": 70,
                "summary": "Promising idea.",
            }),
            AgentRole.competitor_analyst.value: json.dumps({
                "direct_competitors": [{"name": "CompA"}, {"name": "CompB"}],
                "indirect_competitors": [{"name": "IndirectA"}],
                "substitutes": ["Manual entry"],
                "workarounds": ["Spreadsheets"],
                "pricing_patterns": ["$20-50/mo"],
                "positioning_gaps": ["No AI focus"],
                "confidence_score": 65,
                "summary": "Moderate competition.",
            }),
            AgentRole.customer_discovery.value: json.dumps({
                "interview_targets": ["Accountants", "CFOs"],
                "discovery_questions": ["How much time on entry?", "What tools tried?"],
                "demand_signals": ["Reddit complaints"],
                "weak_signal_warnings": ["Trust concerns"],
                "validation_experiment": "Landing page test",
                "confidence_score": 60,
                "summary": "Clear demand.",
            }),
            AgentRole.evidence_integrator.value: json.dumps({
                "research_directive": {
                    "verdict": "evidence_sufficient",
                    "directives": [],
                    "resolved_contradictions": [],
                    "remaining_gaps": [],
                    "round_confidence": 75,
                },
                "validation_thesis": {
                    "thesis_statement": "Viable opportunity.",
                    "confidence_score": 72,
                    "verdict": "go",
                    "contradictions": [],
                    "unresolved_assumptions": [],
                    "risk_assessment": "Low risk.",
                    "research_journey_summary": "1 round.",
                    "total_rounds": 1,
                    "convergence_reason": "evidence_sufficient",
                },
            }),
        }
        self.calls: list[dict[str, Any]] = []

    async def headless(
        self,
        prompt: str,
        task: str,
        cwd: Path,
        *,
        timeout: float,
        model: str | None = None,
    ) -> tuple[str, int, AgentUsage | None]:
        self.calls.append({
            "prompt": prompt,
            "task": task,
            "cwd": str(cwd),
            "timeout": timeout,
            "model": model,
        })

        role = self._detect_role(prompt)
        if role:
            text = self._responses.get(role, self._default_responses.get(role, "{}"))
            return text, 0, _default_usage()

        return self._default_responses.get(
            AgentRole.idea_validator.value, "{}"
        ), 0, _default_usage()

    @staticmethod
    def _detect_role(prompt: str) -> str | None:
        markers = [
            ("evidence_integrator", "Evidence Integrator"),
            ("idea_validator", "Idea Validator"),
            ("competitor_analyst", "Competitor Analyst"),
            ("customer_discovery", "Customer Discovery"),
        ]
        for role, marker in markers:
            if marker in prompt:
                return role
        return None


@pytest.fixture
def mock_runner() -> MockRunner:
    return MockRunner()
