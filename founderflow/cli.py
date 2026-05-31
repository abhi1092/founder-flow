from __future__ import annotations

import asyncio
import json
import sys
import webbrowser
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from founderflow.config import FounderFlowConfig, load_config
from founderflow.models import AgentRole
from founderflow.rendering import BriefRenderer
from founderflow.runners.claude import ClaudeRunner
from founderflow.store import RunStore

app = typer.Typer(name="founderflow", help="Multi-agent startup idea validation")
console = Console()

AGENT_STATUS_ICONS = {
    "pending": "[dim]...[/dim]",
    "running": "[yellow]~[/yellow]",
    "complete": "[green]ok[/green]",
    "idle": "[dim]--[/dim]",
    "error": "[red]!![/red]",
}


def _build_dashboard(
    round_num: int,
    max_rounds: int,
    agent_states: dict[str, dict],
    round_type: str,
) -> Table:
    table = Table(
        title=f"Round {round_num}/{max_rounds} ({round_type})",
        show_header=True,
        header_style="bold",
        expand=True,
    )
    table.add_column("Agent", style="bold", width=22)
    table.add_column("Status", width=10, justify="center")
    table.add_column("Info", ratio=1)

    for name, state in agent_states.items():
        status = state.get("status", "pending")
        icon = AGENT_STATUS_ICONS.get(status, "?")
        info = state.get("message", "")
        if state.get("cost_usd"):
            info += f" ${state['cost_usd']:.4f}"
        table.add_row(name, icon, info)

    return table


def _make_progress_handler(live: Live, max_rounds: int):
    agent_states: dict[str, dict] = {}
    current_round = [1]
    round_type = ["broad"]
    total_cost = [0.0]

    def on_progress(event: dict) -> None:
        etype = event.get("type", "")

        if etype == "round_started":
            current_round[0] = event.get("round_num", 1)
            active = event.get("active_agents", [])
            if len(active) < 3 and current_round[0] > 1:
                round_type[0] = f"directed: {', '.join(active)}"
            else:
                round_type[0] = "broad"

            agent_states.clear()
            all_specialists = ["idea_validator", "competitor_analyst", "customer_discovery"]
            for a in all_specialists:
                if a in active:
                    agent_states[a] = {"status": "pending", "message": ""}
                else:
                    agent_states[a] = {"status": "idle", "message": "sufficient"}

        elif etype == "agent_started":
            agent = event.get("agent", "")
            agent_states[agent] = {"status": "running", "message": "working..."}

        elif etype == "agent_completed":
            agent = event.get("agent", "")
            error = event.get("error")
            usage = event.get("usage", {})
            cost = usage.get("total_cost_usd", 0)
            total_cost[0] += cost
            if error:
                agent_states[agent] = {"status": "error", "message": error[:40]}
            else:
                agent_states[agent] = {
                    "status": "complete",
                    "message": "done",
                    "cost_usd": cost,
                }

        elif etype == "integrator_completed":
            agent_states["evidence_integrator"] = {
                "status": "complete",
                "message": f"verdict: {event.get('verdict', '?')} (conf: {event.get('round_confidence', '?')}%)",
            }

        elif etype == "pipeline_completed":
            return

        dashboard = _build_dashboard(
            current_round[0], max_rounds, agent_states, round_type[0]
        )
        live.update(dashboard)

    return on_progress


async def _validate_async(
    idea: str,
    max_rounds: int,
    no_open: bool,
    model: str | None,
    verbose: bool,
) -> None:
    project_path = Path.cwd()
    config = load_config(project_path)

    if max_rounds != 3:
        config = FounderFlowConfig(
            max_rounds=max_rounds,
            model=model or config.model,
            integrator_model=config.integrator_model,
            per_agent_timeout=config.per_agent_timeout,
            per_agent_budget=config.per_agent_budget,
        )
    elif model:
        config = FounderFlowConfig(
            max_rounds=config.max_rounds,
            model=model,
            integrator_model=config.integrator_model,
            per_agent_timeout=config.per_agent_timeout,
            per_agent_budget=config.per_agent_budget,
        )

    store_path = project_path / ".founderflow"
    store_path.mkdir(parents=True, exist_ok=True)
    store = RunStore(store_path)
    runner = ClaudeRunner()
    renderer = BriefRenderer()

    with Live(console=console, refresh_per_second=4) as live:
        on_progress = _make_progress_handler(live, config.max_rounds)

        from founderflow.pipeline import run_pipeline

        brief = await run_pipeline(
            idea,
            config,
            store,
            runner,
            on_progress=on_progress,
            project_path=project_path,
        )

    run_id = store.list_runs()[0].run_id if store.list_runs() else "unknown"
    run_path = store.get_run(run_id)

    paths = renderer.render_all(brief, run_path, console)

    if not no_open and paths.get("html"):
        html_path = paths["html"]
        console.print(f"\n[dim]HTML brief:[/dim] {html_path}")
        webbrowser.open(html_path.as_uri())


@app.command()
def validate(
    idea: str = typer.Argument(..., help="The startup idea to validate"),
    max_rounds: int = typer.Option(3, "--max-rounds", "-r", help="Maximum research rounds"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't auto-open HTML in browser"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Validate a startup idea with multi-agent research."""
    if verbose:
        import structlog
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(0),
        )

    asyncio.run(_validate_async(idea, max_rounds, no_open, model, verbose))


@app.command()
def runs() -> None:
    """List past validation runs."""
    project_path = Path.cwd()
    store_path = project_path / ".founderflow"
    if not store_path.exists():
        console.print("[dim]No runs found. Run 'founderflow validate' first.[/dim]")
        raise typer.Exit()

    store = RunStore(store_path)
    all_runs = store.list_runs()

    if not all_runs:
        console.print("[dim]No runs found.[/dim]")
        raise typer.Exit()

    table = Table(title="Past Runs")
    table.add_column("ID", style="dim", max_width=20)
    table.add_column("Idea", max_width=40)
    table.add_column("Verdict", justify="center")
    table.add_column("Rounds", justify="center")
    table.add_column("Date")

    verdict_styles = {"go": "green", "deeper": "yellow", "pivot": "red", "kill": "red"}

    for r in all_runs:
        v = r.verdict or "?"
        style = verdict_styles.get(v, "dim")
        table.add_row(
            r.run_id,
            r.idea[:40],
            Text(v.upper(), style=style),
            str(r.rounds),
            r.created_at[:10] if r.created_at else "",
        )

    console.print(table)


@app.command()
def show(
    run_id: str = typer.Argument(..., help="Run ID to display"),
    terminal: bool = typer.Option(False, "--terminal", "-t", help="Show Rich terminal output"),
    json_out: bool = typer.Option(False, "--json", "-j", help="Print raw JSON"),
) -> None:
    """Re-open a past brief."""
    project_path = Path.cwd()
    store_path = project_path / ".founderflow"
    store = RunStore(store_path)

    try:
        run_path = store.get_run(run_id)
    except FileNotFoundError:
        console.print(f"[red]Run '{run_id}' not found.[/red]")
        raise typer.Exit(1)

    brief_file = run_path / "brief.json"
    if not brief_file.exists():
        console.print(f"[red]No brief found for run '{run_id}'.[/red]")
        raise typer.Exit(1)

    from founderflow.models import StartupBrief

    brief = StartupBrief.model_validate_json(brief_file.read_text())

    if json_out:
        console.print(brief.model_dump_json(indent=2))
    elif terminal:
        renderer = BriefRenderer()
        renderer.render_terminal(brief, console)
    else:
        html_path = run_path / "brief.html"
        if not html_path.exists():
            renderer = BriefRenderer()
            renderer.render_html(brief, html_path)
        console.print(f"[dim]Opening:[/dim] {html_path}")
        webbrowser.open(html_path.as_uri())


@app.command()
def costs() -> None:
    """Show aggregate cost report across all runs."""
    project_path = Path.cwd()
    store_path = project_path / ".founderflow"
    if not store_path.exists():
        console.print("[dim]No runs found.[/dim]")
        raise typer.Exit()

    store = RunStore(store_path)
    all_runs = store.list_runs()

    if not all_runs:
        console.print("[dim]No runs found.[/dim]")
        raise typer.Exit()

    table = Table(title="Cost Report")
    table.add_column("Run ID", style="dim", max_width=20)
    table.add_column("Idea", max_width=30)
    table.add_column("Verdict", justify="center")
    table.add_column("Rounds", justify="center")
    table.add_column("Cost", justify="right", style="bold")

    total_cost = 0.0

    for r in all_runs:
        run_path = store.get_run(r.run_id)
        brief_file = run_path / "brief.json"
        cost_str = "?"
        if brief_file.exists():
            try:
                data = json.loads(brief_file.read_text())
                cost = data.get("cost_summary", {}).get("total_cost_usd", 0)
                cost_str = f"${cost:.4f}"
                total_cost += cost
            except Exception:
                pass
        table.add_row(
            r.run_id,
            r.idea[:30],
            (r.verdict or "?").upper(),
            str(r.rounds),
            cost_str,
        )

    console.print(table)
    console.print(f"\n[bold]Total across all runs:[/bold] ${total_cost:.4f}")
