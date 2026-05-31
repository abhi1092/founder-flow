from __future__ import annotations

import pytest
from pydantic import ValidationError

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


class TestEnums:
    def test_agent_role_values(self):
        assert AgentRole.idea_validator.value == "idea_validator"
        assert AgentRole.evidence_integrator.value == "evidence_integrator"

    def test_verdict_values(self):
        assert set(v.value for v in Verdict) == {"go", "deeper", "pivot", "kill"}

    def test_directive_verdict_values(self):
        assert set(v.value for v in DirectiveVerdict) == {"needs_deeper", "evidence_sufficient"}

    def test_convergence_reason_values(self):
        assert "max_rounds" in [r.value for r in ConvergenceReason]

    def test_priority_values(self):
        assert set(v.value for v in Priority) == {"high", "medium"}

    def test_invalid_enum_raises(self):
        with pytest.raises(ValueError):
            Verdict("invalid")


class TestAgentUsage:
    def test_valid(self):
        u = AgentUsage(
            input_tokens=10, output_tokens=5, cache_read_tokens=0,
            cache_creation_tokens=0, total_cost_usd=0.01, duration_ms=100,
            num_turns=1, model="test",
        )
        assert u.input_tokens == 10

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            AgentUsage(
                input_tokens=10, output_tokens=5, cache_read_tokens=0,
                cache_creation_tokens=0, total_cost_usd=0.01, duration_ms=100,
                num_turns=1, model="test", extra_field="bad",
            )


class TestIdeaValidation:
    def test_valid(self, sample_idea_validation):
        assert sample_idea_validation.confidence_score == 72

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            IdeaValidation(
                problem_severity="x", target_customer_clarity="x",
                value_proposition_strength="x", risk_factors=[], core_assumptions=[],
                confidence_score=50, summary="x", unknown="bad",
            )

    def test_confidence_bounds_low(self):
        with pytest.raises(ValidationError):
            IdeaValidation(
                problem_severity="x", target_customer_clarity="x",
                value_proposition_strength="x", risk_factors=[], core_assumptions=[],
                confidence_score=-1, summary="x",
            )

    def test_confidence_bounds_high(self):
        with pytest.raises(ValidationError):
            IdeaValidation(
                problem_severity="x", target_customer_clarity="x",
                value_proposition_strength="x", risk_factors=[], core_assumptions=[],
                confidence_score=101, summary="x",
            )

    def test_strict_rejects_wrong_type(self):
        with pytest.raises(ValidationError):
            IdeaValidation(
                problem_severity=123,
                target_customer_clarity="x",
                value_proposition_strength="x",
                risk_factors=[], core_assumptions=[],
                confidence_score=50, summary="x",
            )


class TestCompetitorAnalysis:
    def test_valid(self, sample_competitor_analysis):
        assert len(sample_competitor_analysis.direct_competitors) == 2

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            CompetitorAnalysis(
                direct_competitors=[], indirect_competitors=[], substitutes=[],
                workarounds=[], pricing_patterns=[], positioning_gaps=[],
                confidence_score=50, summary="x", extra="bad",
            )


class TestCustomerDiscovery:
    def test_valid(self, sample_customer_discovery):
        assert len(sample_customer_discovery.discovery_questions) == 3

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            CustomerDiscovery(
                interview_targets=[], discovery_questions=[], demand_signals=[],
                weak_signal_warnings=[], validation_experiment="x",
                confidence_score=50, summary="x", extra="bad",
            )


class TestResearchDirective:
    def test_evidence_sufficient_empty_directives(self, sample_directive_sufficient):
        assert sample_directive_sufficient.verdict == DirectiveVerdict.evidence_sufficient
        assert sample_directive_sufficient.directives == []

    def test_needs_deeper_has_directives(self, sample_directive_needs_deeper):
        assert sample_directive_needs_deeper.verdict == DirectiveVerdict.needs_deeper
        assert len(sample_directive_needs_deeper.directives) == 2

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            ResearchDirective(
                verdict=DirectiveVerdict.evidence_sufficient,
                directives=[], resolved_contradictions=[], remaining_gaps=[],
                round_confidence=101,
            )


class TestValidationThesis:
    def test_valid(self, sample_thesis):
        assert sample_thesis.verdict == Verdict.go
        assert sample_thesis.total_rounds == 2

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            ValidationThesis(
                thesis_statement="x", confidence_score=50, verdict=Verdict.go,
                contradictions=[], unresolved_assumptions=[], risk_assessment="x",
                research_journey_summary="x", total_rounds=1,
                convergence_reason=ConvergenceReason.evidence_sufficient, extra="bad",
            )


class TestRoundResult:
    def test_serialization_roundtrip(self, sample_brief):
        rr = sample_brief.round_results[0]
        data = rr.model_dump()
        restored = RoundResult.model_validate(data, strict=False)
        assert restored.round_num == rr.round_num
        assert restored.started_at == rr.started_at


class TestStartupBrief:
    def test_valid(self, sample_brief):
        assert sample_brief.idea == "AI-powered invoice automation for SMB accountants"
        assert len(sample_brief.round_results) == 2
        assert len(sample_brief.action_plan) == 2

    def test_json_roundtrip(self, sample_brief):
        json_str = sample_brief.model_dump_json()
        restored = StartupBrief.model_validate_json(json_str)
        assert restored.thesis.verdict == sample_brief.thesis.verdict
        assert restored.idea == sample_brief.idea
