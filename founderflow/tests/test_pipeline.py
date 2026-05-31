from __future__ import annotations

import json
from pathlib import Path

import pytest

from founderflow.config import FounderFlowConfig
from founderflow.models import AgentRole, DirectiveVerdict
from founderflow.store import RunStore
from founderflow.tests.conftest import MockRunner, _default_usage


@pytest.fixture
def store(tmp_run_dir: Path) -> RunStore:
    return RunStore(tmp_run_dir)


@pytest.fixture
def config() -> FounderFlowConfig:
    return FounderFlowConfig(max_rounds=3, model="test-model")


_ROLE_MARKERS = [
    ("evidence_integrator", "Evidence Integrator"),
    ("idea_validator", "Idea Validator"),
    ("competitor_analyst", "Competitor Analyst"),
    ("customer_discovery", "Customer Discovery"),
]


def _detect_role(prompt: str) -> str | None:
    for role, marker in _ROLE_MARKERS:
        if marker in prompt:
            return role
    return None


def _make_integrator_response(
    verdict: str = "evidence_sufficient",
    directives: list | None = None,
    confidence: int = 75,
    include_thesis: bool = True,
) -> str:
    result: dict = {
        "research_directive": {
            "verdict": verdict,
            "directives": directives or [],
            "resolved_contradictions": [],
            "remaining_gaps": [],
            "round_confidence": confidence,
        }
    }
    if include_thesis:
        result["validation_thesis"] = {
            "thesis_statement": "Test thesis.",
            "confidence_score": confidence,
            "verdict": "go",
            "contradictions": [],
            "unresolved_assumptions": [],
            "risk_assessment": "Low risk.",
            "research_journey_summary": "Test journey.",
            "total_rounds": 1,
            "convergence_reason": "evidence_sufficient",
        }
    return json.dumps(result)


class TestSingleRoundConvergence:
    @pytest.mark.asyncio
    async def test_converges_in_one_round(self, store: RunStore, config: FounderFlowConfig, tmp_run_dir: Path):
        config = FounderFlowConfig(max_rounds=1, model="test-model")
        runner = MockRunner()

        from founderflow.pipeline import run_pipeline

        brief = await run_pipeline(
            "Test idea",
            config,
            store,
            runner,
            project_path=tmp_run_dir.parent,
        )

        assert brief.thesis is not None
        assert brief.idea == "Test idea"
        assert len(brief.round_results) >= 1


class TestMultiRoundDeepening:
    @pytest.mark.asyncio
    async def test_deepens_when_needs_deeper(self, store: RunStore, tmp_run_dir: Path):
        round1_integrator = json.dumps({
            "research_directive": {
                "verdict": "needs_deeper",
                "directives": [
                    {
                        "agent_role": "idea_validator",
                        "follow_up_question": "Go deeper on accuracy",
                        "priority": "high",
                    }
                ],
                "resolved_contradictions": [],
                "remaining_gaps": ["Accuracy unclear"],
                "round_confidence": 40,
            }
        })

        round2_integrator = _make_integrator_response(
            verdict="evidence_sufficient", confidence=80
        )

        call_count = [0]
        original_default = MockRunner()._default_responses

        class DeepRunner:
            def __init__(self):
                self.calls = []

            async def headless(self, prompt, task, cwd, *, timeout, model=None):
                self.calls.append({"prompt": prompt, "task": task})
                role = _detect_role(prompt)
                if role == "evidence_integrator":
                    call_count[0] += 1
                    if call_count[0] <= 1:
                        return round1_integrator, 0, _default_usage()
                    return round2_integrator, 0, _default_usage()
                if role and role in original_default:
                    return original_default[role], 0, _default_usage()
                return original_default["idea_validator"], 0, _default_usage()

        runner = DeepRunner()
        config = FounderFlowConfig(max_rounds=3, model="test-model")

        from founderflow.pipeline import run_pipeline

        brief = await run_pipeline(
            "Test deepening idea",
            config,
            store,
            runner,
            project_path=tmp_run_dir.parent,
        )

        assert len(brief.round_results) >= 2


class TestMaxRoundsCap:
    @pytest.mark.asyncio
    async def test_stops_at_max_rounds(self, store: RunStore, tmp_run_dir: Path):
        always_deeper = json.dumps({
            "research_directive": {
                "verdict": "needs_deeper",
                "directives": [
                    {
                        "agent_role": "idea_validator",
                        "follow_up_question": "Keep digging",
                        "priority": "high",
                    }
                ],
                "resolved_contradictions": [],
                "remaining_gaps": ["Still unclear"],
                "round_confidence": 30,
            }
        })

        original_default = MockRunner()._default_responses

        class AlwaysDeeperRunner:
            async def headless(self, prompt, task, cwd, *, timeout, model=None):
                role = _detect_role(prompt)
                if role == "evidence_integrator":
                    return always_deeper, 0, _default_usage()
                if role and role in original_default:
                    return original_default[role], 0, _default_usage()
                return original_default["idea_validator"], 0, _default_usage()

        config = FounderFlowConfig(max_rounds=2, model="test-model")
        runner = AlwaysDeeperRunner()

        from founderflow.pipeline import run_pipeline

        brief = await run_pipeline(
            "Capped idea",
            config,
            store,
            runner,
            project_path=tmp_run_dir.parent,
        )

        assert len(brief.round_results) <= 2
        assert brief.thesis is not None


class TestPartialFailure:
    @pytest.mark.asyncio
    async def test_handles_agent_parse_error(self, store: RunStore, tmp_run_dir: Path):
        """When an agent returns unparseable output, the pipeline still completes
        because the agent text is stored but parsed_output is None, and the
        pipeline uses whatever outputs succeeded."""
        original_default = MockRunner()._default_responses

        class PartialFailRunner:
            async def headless(self, prompt, task, cwd, *, timeout, model=None):
                role = _detect_role(prompt)
                if role == "competitor_analyst":
                    return "not valid json at all", 0, _default_usage()
                if role == "evidence_integrator":
                    return _make_integrator_response(), 0, _default_usage()
                if role and role in original_default:
                    return original_default[role], 0, _default_usage()
                return original_default["idea_validator"], 0, _default_usage()

        config = FounderFlowConfig(max_rounds=1, model="test-model")
        runner = PartialFailRunner()

        from founderflow.pipeline import run_pipeline
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            await run_pipeline(
                "Partial fail idea",
                config,
                store,
                runner,
                project_path=tmp_run_dir.parent,
            )


class TestCostAccumulation:
    @pytest.mark.asyncio
    async def test_cost_summary_populated(self, store: RunStore, config: FounderFlowConfig, tmp_run_dir: Path):
        config = FounderFlowConfig(max_rounds=1, model="test-model")
        runner = MockRunner()

        from founderflow.pipeline import run_pipeline

        brief = await run_pipeline(
            "Cost test idea",
            config,
            store,
            runner,
            project_path=tmp_run_dir.parent,
        )

        assert brief.cost_summary is not None
        assert brief.cost_summary.total_input_tokens >= 0
        assert brief.cost_summary.total_output_tokens >= 0
