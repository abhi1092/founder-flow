from __future__ import annotations

import json
from pathlib import Path

import pytest

from founderflow.gates.validation import GateResult, run_gates
from founderflow.models import AgentRole


@pytest.fixture
def valid_outputs() -> dict:
    return {
        "idea_validation": {
            "problem_severity": "High",
            "target_customer_clarity": "SMB accountants",
            "value_proposition_strength": "Strong",
            "risk_factors": ["Market risk"],
            "core_assumptions": ["Willing to pay"],
            "confidence_score": 70,
            "summary": "Good fit.",
        },
        "competitor_analysis": {
            "direct_competitors": [{"name": "A"}],
            "indirect_competitors": [{"name": "B"}],
            "substitutes": ["Manual"],
            "workarounds": [],
            "pricing_patterns": [],
            "positioning_gaps": [],
            "confidence_score": 65,
            "summary": "Moderate.",
        },
        "customer_discovery": {
            "interview_targets": ["Accountants"],
            "discovery_questions": ["Q1?", "Q2?"],
            "demand_signals": ["Signal"],
            "weak_signal_warnings": [],
            "validation_experiment": "Test",
            "confidence_score": 60,
            "summary": "Clear demand.",
        },
    }


class TestValidOutputsPass:
    def test_all_gates_pass(self, valid_outputs):
        result = run_gates(1, valid_outputs)
        assert result.passed is True
        assert len(result.failures) == 0


class TestEmptyCompetitorsFail:
    def test_too_few_competitors(self, valid_outputs):
        valid_outputs["competitor_analysis"]["direct_competitors"] = []
        valid_outputs["competitor_analysis"]["indirect_competitors"] = []
        valid_outputs["competitor_analysis"]["substitutes"] = []
        result = run_gates(1, valid_outputs)
        assert result.passed is False
        content_fails = [f for f in result.failures if f.check_name == "min_content"]
        assert len(content_fails) >= 1

    def test_one_competitor_still_fails(self, valid_outputs):
        valid_outputs["competitor_analysis"]["direct_competitors"] = [{"name": "A"}]
        valid_outputs["competitor_analysis"]["indirect_competitors"] = []
        valid_outputs["competitor_analysis"]["substitutes"] = []
        result = run_gates(1, valid_outputs)
        assert result.passed is False


class TestMissingFieldsFail:
    def test_empty_risk_factors(self, valid_outputs):
        valid_outputs["idea_validation"]["risk_factors"] = []
        result = run_gates(1, valid_outputs)
        content_fails = [
            f for f in result.failures
            if f.check_name in ("schema_completeness", "min_content")
            and f.agent_role == AgentRole.idea_validator
        ]
        assert len(content_fails) >= 1

    def test_missing_agent_output(self, valid_outputs):
        del valid_outputs["idea_validation"]
        result = run_gates(1, valid_outputs)
        assert result.passed is False
        missing = [f for f in result.failures if f.check_name == "missing_output"]
        assert len(missing) == 1


class TestConfidenceFloor:
    def test_low_confidence_fails(self, valid_outputs):
        valid_outputs["idea_validation"]["confidence_score"] = 5
        result = run_gates(1, valid_outputs)
        assert result.passed is False
        conf_fails = [f for f in result.failures if f.check_name == "confidence_floor"]
        assert len(conf_fails) >= 1

    def test_confidence_at_floor_passes(self, valid_outputs):
        valid_outputs["idea_validation"]["confidence_score"] = 10
        result = run_gates(1, valid_outputs)
        conf_fails = [f for f in result.failures if f.check_name == "confidence_floor"]
        assert len(conf_fails) == 0


class TestRoundAwareness:
    def test_round2_only_checks_active_agents(self, valid_outputs):
        del valid_outputs["competitor_analysis"]
        result = run_gates(
            2,
            valid_outputs,
            active_roles=[AgentRole.idea_validator, AgentRole.customer_discovery],
        )
        assert result.passed is True

    def test_round2_missing_active_agent_fails(self, valid_outputs):
        del valid_outputs["idea_validation"]
        result = run_gates(
            2,
            valid_outputs,
            active_roles=[AgentRole.idea_validator, AgentRole.customer_discovery],
        )
        assert result.passed is False


class TestAgentHealth:
    def test_failed_agent_in_events(self, valid_outputs, tmp_path):
        run_path = tmp_path / "run1"
        run_path.mkdir()
        events = [
            {"event": "agent.failed", "round_num": 1, "agent": "idea_validator", "timestamp": 1.0}
        ]
        (run_path / "events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n"
        )
        result = run_gates(1, valid_outputs, run_path=run_path)
        assert result.passed is False
        health_fails = [f for f in result.failures if f.check_name == "agent_health"]
        assert len(health_fails) >= 1
