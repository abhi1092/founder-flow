from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from founderflow.models import StartupBrief
from founderflow.rendering import BriefRenderer


@pytest.fixture
def renderer() -> BriefRenderer:
    return BriefRenderer()


class TestHtmlRendering:
    def test_contains_verdict_badge(self, renderer, sample_brief, tmp_path):
        html_path = tmp_path / "brief.html"
        renderer.render_html(sample_brief, html_path)
        html = html_path.read_text()
        assert "badge-go" in html

    def test_contains_idea(self, renderer, sample_brief, tmp_path):
        html_path = tmp_path / "brief.html"
        renderer.render_html(sample_brief, html_path)
        html = html_path.read_text()
        assert "AI-powered invoice automation" in html

    def test_contains_sections(self, renderer, sample_brief, tmp_path):
        html_path = tmp_path / "brief.html"
        renderer.render_html(sample_brief, html_path)
        html = html_path.read_text()
        assert "Idea Validation" in html
        assert "Competitor Analysis" in html
        assert "Customer Discovery" in html

    def test_contains_action_plan(self, renderer, sample_brief, tmp_path):
        html_path = tmp_path / "brief.html"
        renderer.render_html(sample_brief, html_path)
        html = html_path.read_text()
        assert "Action Plan" in html
        assert "Day 1" in html

    def test_contains_cost_summary(self, renderer, sample_brief, tmp_path):
        html_path = tmp_path / "brief.html"
        renderer.render_html(sample_brief, html_path)
        html = html_path.read_text()
        assert "Total Cost" in html

    def test_contains_research_timeline(self, renderer, sample_brief, tmp_path):
        html_path = tmp_path / "brief.html"
        renderer.render_html(sample_brief, html_path)
        html = html_path.read_text()
        assert "Research Loop Timeline" in html
        assert "Round 1" in html

    def test_self_contained(self, renderer, sample_brief, tmp_path):
        html_path = tmp_path / "brief.html"
        renderer.render_html(sample_brief, html_path)
        html = html_path.read_text()
        assert "http://" not in html.split("<style>")[0]
        assert "https://" not in html or "https://" not in html.split("</style>")[1].split("<body>")[0]

    def test_responsive_meta(self, renderer, sample_brief, tmp_path):
        html_path = tmp_path / "brief.html"
        renderer.render_html(sample_brief, html_path)
        html = html_path.read_text()
        assert "viewport" in html


class TestJsonRendering:
    def test_roundtrip(self, renderer, sample_brief, tmp_path):
        json_path = tmp_path / "brief.json"
        renderer.render_json(sample_brief, json_path)
        restored = StartupBrief.model_validate_json(json_path.read_text())
        assert restored.idea == sample_brief.idea
        assert restored.thesis.verdict == sample_brief.thesis.verdict
        assert len(restored.round_results) == len(sample_brief.round_results)

    def test_cost_in_json(self, renderer, sample_brief, tmp_path):
        json_path = tmp_path / "brief.json"
        renderer.render_json(sample_brief, json_path)
        import json
        data = json.loads(json_path.read_text())
        assert "cost_summary" in data
        assert data["cost_summary"]["total_cost_usd"] == 0.002


class TestTerminalRendering:
    def test_no_crash(self, renderer, sample_brief):
        console = Console(file=open("/dev/null", "w"), force_terminal=True)
        renderer.render_terminal(sample_brief, console)

    def test_captures_output(self, renderer, sample_brief):
        console = Console(record=True, force_terminal=True)
        renderer.render_terminal(sample_brief, console)
        output = console.export_text()
        assert "AI-powered invoice automation" in output
        assert "Cost Summary" in output


class TestRenderAll:
    def test_creates_all_files(self, renderer, sample_brief, tmp_path):
        console = Console(file=open("/dev/null", "w"), force_terminal=True)
        paths = renderer.render_all(sample_brief, tmp_path, console)
        assert paths["html"].exists()
        assert paths["json"].exists()
