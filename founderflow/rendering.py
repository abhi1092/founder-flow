from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from founderflow.models import StartupBrief, Verdict


VERDICT_COLORS = {
    Verdict.go: "green",
    Verdict.deeper: "yellow",
    Verdict.pivot: "red",
    Verdict.kill: "red",
}

VERDICT_STYLE = {
    Verdict.go: "bold green",
    Verdict.deeper: "bold yellow",
    Verdict.pivot: "bold red",
    Verdict.kill: "bold red",
}


class BriefRenderer:
    def __init__(self) -> None:
        self._env = Environment(
            loader=PackageLoader("founderflow", "templates"),
            autoescape=select_autoescape(["html"]),
        )

    def render_terminal(self, brief: StartupBrief, console: Console) -> None:
        verdict = brief.thesis.verdict
        color = VERDICT_COLORS.get(verdict, "white")
        style = VERDICT_STYLE.get(verdict, "bold")

        verdict_text = Text()
        verdict_text.append(f" {verdict.value.upper()} ", style=f"bold white on {color}")
        verdict_text.append(f"  Confidence: {brief.thesis.confidence_score}%\n\n")
        verdict_text.append(brief.thesis.thesis_statement)

        console.print(Panel(verdict_text, title=f"[bold]{brief.idea}[/bold]", border_style=color))

        sections = [
            ("Idea Validation", brief.idea_validation.summary),
            ("Competitor Analysis", brief.competitor_analysis.summary),
            ("Customer Discovery", brief.customer_discovery.summary),
        ]
        for title, summary in sections:
            console.print(Panel(summary, title=title, border_style="dim"))

        if brief.thesis.risk_assessment:
            console.print(
                Panel(brief.thesis.risk_assessment, title="Risk Assessment", border_style="red")
            )

        if brief.thesis.research_journey_summary:
            console.print(
                Panel(
                    brief.thesis.research_journey_summary,
                    title="Research Journey",
                    border_style="blue",
                )
            )

        if brief.action_plan:
            plan_table = Table(title="7-Day Action Plan")
            plan_table.add_column("Day", style="bold", width=5)
            plan_table.add_column("Action", style="cyan")
            plan_table.add_column("Details")
            for item in brief.action_plan:
                plan_table.add_row(str(item.day), item.action, item.details)
            console.print(plan_table)

        cost_table = Table(title="Cost Summary")
        cost_table.add_column("Metric", style="bold")
        cost_table.add_column("Value", justify="right")
        cost_table.add_row("Total Cost", f"${brief.cost_summary.total_cost_usd:.4f}")
        cost_table.add_row("Input Tokens", f"{brief.cost_summary.total_input_tokens:,}")
        cost_table.add_row("Output Tokens", f"{brief.cost_summary.total_output_tokens:,}")
        cost_table.add_row("Rounds", str(len(brief.round_results)))
        console.print(cost_table)

    def render_html(self, brief: StartupBrief, output_path: Path) -> None:
        template = self._env.get_template("brief.html.j2")
        html = template.render(**brief.model_dump())
        output_path.write_text(html)

    def render_json(self, brief: StartupBrief, output_path: Path) -> None:
        output_path.write_text(brief.model_dump_json(indent=2))

    def render_all(
        self, brief: StartupBrief, run_path: Path, console: Console
    ) -> dict[str, Path]:
        self.render_terminal(brief, console)

        html_path = run_path / "brief.html"
        self.render_html(brief, html_path)

        json_path = run_path / "brief.json"
        self.render_json(brief, json_path)

        return {"html": html_path, "json": json_path}
