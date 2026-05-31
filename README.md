# FounderFlow

**Treat your startup idea as a research hypothesis. Validate it before you build it.**

FounderFlow is a multi-agent CLI tool that validates startup ideas through an iterative research loop. Three specialist agents fan out in parallel — idea validation, competitor analysis, customer discovery — then an Evidence Integrator identifies gaps and sends agents back for deeper investigation until evidence converges. The output is a polished, self-contained HTML Startup Validation Research Brief with contradictions exposed, assumptions surfaced, and a concrete 7-day action plan.

**[Watch the demo video](https://drive.google.com/file/d/1E2lUUseWs7XgcXygnMyRUUozf14bNDGp/view?usp=sharing)** | **[View a sample brief](examples/sample-brief.html)**

## How It Works

FounderFlow models startup validation as a research process: your idea is the hypothesis, each agent is a research assistant covering a different dimension, and the Evidence Integrator is your research advisor who decides when the evidence is strong enough — or where to dig deeper.

```
                            ┌─────────────────┐
                            │   Startup Idea   │
                            └────────┬────────┘
                                     │
                    Round 1 (broad)   │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
     ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
     │ Idea Validator  │    │  Competitor    │    │   Customer     │
     │                │    │   Analyst      │    │  Discovery     │
     └───────┬────────┘    └───────┬────────┘    └───────┬────────┘
              │                     │                     │
              └──────────────────────┼──────────────────────┘
                                     ▼
                          ┌──────────────────┐
                          │    Evidence      │
                          │   Integrator     │
                          │  (gap analysis)  │
                          └────────┬─────────┘
                                   │
                        ┌──────────┴──────────┐
                        ▼                     ▼
               ┌─────────────┐       ┌─────────────┐
               │  Converged  │       │ Needs deeper │
               │  → Render   │       │ → Round 2+   │──── only agents
               │    brief    │       │  (directed)  │     with gaps
               └─────────────┘       └──────────────┘     re-run
```

### Research Phases → Startup Validation Mapping

| Research Phase | Startup Equivalent | What Happens |
|---|---|---|
| Literature review | Round 1 (broad) | All 3 agents investigate in parallel |
| Peer review | Integrator pass | Cross-agent critique, contradiction detection |
| Reviewer comments | ResearchDirective | Specific follow-up questions routed to specific agents |
| Revision | Round 2+ (directed) | Only gap-bearing agents re-run with targeted prompts |
| Acceptance | Convergence | Evidence sufficient, or max rounds reached |

## The 4 Agents

**Idea Validator** evaluates the idea across five dimensions: problem severity, target customer clarity, value proposition strength, risk factors, and core assumptions. Uses web search to ground analysis in real market data.

**Competitor Analyst** maps the full competitive landscape: direct competitors, indirect competitors, substitutes, current workarounds, pricing patterns, and positioning gaps. Researches real companies with funding, scale, and pricing details.

**Customer Discovery** designs a validation plan following *The Mom Test* principles. Identifies interview targets, crafts discovery questions, finds demand signals in forums and communities, spots weak-signal warnings, and proposes a cheap validation experiment.

**Evidence Integrator** acts as a research advisor. After each round, it reviews all agent outputs, detects contradictions between findings, identifies unresolved gaps, and either routes specific follow-up questions to specific agents (another round) or declares evidence sufficient and produces the final ValidationThesis with a go/deeper/pivot/kill verdict.

## Quick Start

### Prerequisites

- Python 3.11+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated

### Install

```bash
git clone https://github.com/anthropics/founderflow.git
cd founderflow
pip install -e .
```

### Run

```bash
founderflow validate "An AI receptionist for dental clinics that handles scheduling, insurance verification, and patient follow-ups via phone and text"
```

FounderFlow will:
1. Fan out 3 specialist agents in parallel (Round 1)
2. Run the Evidence Integrator to identify gaps
3. Re-run targeted agents on specific gaps (Round 2+)
4. Produce a verdict and render the brief
5. Auto-open the HTML brief in your browser

## CLI Reference

### `validate` — Run a validation

```bash
founderflow validate "your startup idea here"
```

| Flag | Default | Description |
|---|---|---|
| `--max-rounds`, `-r` | `3` | Maximum research rounds before forced convergence |
| `--no-open` | `false` | Don't auto-open the HTML brief in the browser |
| `--model`, `-m` | `sonnet` | Override the Claude model for all agents |
| `--verbose`, `-v` | `false` | Enable debug logging (structlog JSON output) |

### `runs` — List past validations

```bash
founderflow runs
```

Displays a table of past runs with verdict badges, round counts, and dates.

### `show` — Re-open a past brief

```bash
founderflow show <run-id>              # Open HTML in browser
founderflow show <run-id> --terminal   # Rich terminal output
founderflow show <run-id> --json       # Raw JSON
```

### `costs` — Aggregate cost report

```bash
founderflow costs
```

Shows per-run cost breakdowns and total spend across all runs.

## Output

The Startup Validation Research Brief contains 11 sections:

1. **Verdict** — go / dig deeper / pivot / kill with confidence score (0-100)
2. **Thesis Statement** — one-paragraph synthesis of the validation findings
3. **Problem Severity** — how painful is the problem for the target customer
4. **Target Customer Clarity** — who exactly pays and why
5. **Value Proposition Strength** — why this solution beats alternatives
6. **Risk Factors** — what can kill the startup
7. **Core Assumptions** — what must be true for the idea to work
8. **Competitive Landscape** — direct/indirect competitors, substitutes, positioning gaps
9. **Customer Discovery Plan** — interview targets, questions, demand signals, experiments
10. **Research Loop Timeline** — round-by-round progression showing agents, gaps, and convergence
11. **7-Day Action Plan** — concrete daily actions tailored to the verdict

The brief is delivered in 3 tiers:

- **Terminal** — Rich-formatted panels with color-coded verdict, displayed immediately
- **HTML** — self-contained `.html` file with all CSS inline, no external dependencies. Email it, double-click to open, share with advisors
- **JSON** — structured `brief.json` for programmatic access

## Example

```bash
$ founderflow validate "An AI receptionist for dental clinics that handles scheduling, insurance verification, and patient follow-ups via phone and text"

  Round 1/3 (broad)
  ┌────────────────────────┬────────┬──────────────────────┐
  │ Agent                  │ Status │ Info                 │
  ├────────────────────────┼────────┼──────────────────────┤
  │ idea_validator         │   ok   │ done         $0.0312 │
  │ competitor_analyst     │   ok   │ done         $0.0287 │
  │ customer_discovery     │   ok   │ done         $0.0245 │
  │ evidence_integrator    │   ok   │ verdict: needs_deeper│
  └────────────────────────┴────────┴──────────────────────┘

  Round 2/3 (directed: idea_validator, customer_discovery)
  ┌────────────────────────┬────────┬──────────────────────┐
  │ Agent                  │ Status │ Info                 │
  ├────────────────────────┼────────┼──────────────────────┤
  │ idea_validator         │   ok   │ done         $0.0198 │
  │ competitor_analyst     │   --   │ sufficient           │
  │ customer_discovery     │   ok   │ done         $0.0176 │
  │ evidence_integrator    │   ok   │ verdict: evidence_   │
  │                        │        │ sufficient (conf:78%)│
  └────────────────────────┴────────┴──────────────────────┘

  ╔══════════════════════════════════════════════════╗
  ║  VERDICT: GO                    Confidence: 78  ║
  ║                                                  ║
  ║  The dental AI receptionist addresses a genuine  ║
  ║  pain point — dental offices lose 20-30% of     ║
  ║  calls to voicemail. Existing solutions focus    ║
  ║  on scheduling only; the insurance verification  ║
  ║  + follow-up bundle is a defensible wedge.       ║
  ║                                                  ║
  ║  Key risk: integration with practice management  ║
  ║  software (Dentrix, Eaglesoft) requires          ║
  ║  partnerships that take 6-12 months.             ║
  ╚══════════════════════════════════════════════════╝

  7-Day Action Plan:
  Day 1: Draft one-page business plan
  Day 2: Identify 5 potential early customers
  Day 3: Design MVP feature set
  ...

  HTML brief: .founderflow/runs/a1b2c3/brief.html
```

The HTML brief auto-opens in your browser — a polished, single-page report you can forward to a co-founder or advisor.

## Architecture

```
founderflow/
├── cli.py                    # Thin Typer CLI — delegates to library modules
├── models.py                 # All Pydantic v2 models (strict, extra=forbid)
├── pipeline.py               # Research loop orchestration (async while + gather)
├── rendering.py              # BriefRenderer — terminal, HTML, and JSON output
├── state.py                  # RunState enum + filesystem-based state detection
├── store.py                  # Run persistence + FileLock
├── events.py                 # JSONL event emitter + cost aggregation
├── config.py                 # Configuration resolution (TOML)
├── agents/
│   ├── runner.py             # Agent invocation + two-tier prompt resolution
│   ├── protocol.py           # Runner protocol (LLM backend abstraction)
│   └── prompts/
│       ├── idea_validator.md
│       ├── competitor_analyst.md
│       ├── customer_discovery.md
│       ├── evidence_integrator.md
│       └── sections/         # Composable prompt fragments
├── gates/
│   └── validation.py         # Pre-synthesis quality gates
├── runners/
│   ├── claude.py             # ClaudeRunner — claude -p subprocess backend
│   └── usage.py              # Cost tracking
├── templates/
│   └── brief.html.j2         # Jinja2 HTML brief template
└── tests/
    ├── conftest.py           # MockRunner + sample fixtures
    ├── test_models.py
    ├── test_store.py
    ├── test_pipeline.py
    ├── test_rendering.py
    └── test_gates.py
```

### Key Design Decisions

- **No agent framework.** The orchestration is a Python `while` loop with conditional `asyncio.gather()`. The fixed three-agent topology with directive-driven re-invocation doesn't justify LangGraph or CrewAI.
- **Claude Code subprocesses.** Agents run as `claude -p` subprocesses with file-based communication. No message bus, no shared memory — clean isolation with inspectable JSON artifacts.
- **Strict Pydantic v2 models.** All inter-agent data uses `ConfigDict(strict=True, extra="forbid")` — schema drift is caught immediately.
- **Filesystem as database.** Runs are stored as directory trees under `.founderflow/runs/`. Crash recovery works by detecting state from filesystem markers rather than asserting it from memory.
- **Append-only event log.** Every agent spawn, completion, failure, and cost is recorded in JSONL. Enables cost tracking, audit trails, and crash recovery.

For the full design specification, see [`.factory/strategy/idea.md`](.factory/strategy/idea.md).

## Configuration

### Agent Prompt Overrides

FounderFlow uses two-tier prompt resolution. To customize an agent's behavior, drop a modified prompt at:

```
.founderflow/agents/<role>.md
```

This overrides the built-in default at `founderflow/agents/prompts/<role>.md`. For example, to focus the Idea Validator on B2B SaaS:

```bash
mkdir -p .founderflow/agents
cp founderflow/agents/prompts/idea_validator.md .founderflow/agents/idea_validator.md
# Edit .founderflow/agents/idea_validator.md to add B2B SaaS focus
```

### config.toml

Create `.founderflow/config.toml` to set defaults:

```toml
max_rounds = 3
model = "sonnet"
integrator_model = "sonnet"
per_agent_timeout = 600
```

| Option | Default | Description |
|---|---|---|
| `max_rounds` | `3` | Maximum research rounds |
| `model` | `"sonnet"` | Claude model for specialist agents |
| `integrator_model` | same as `model` | Claude model for the Evidence Integrator |
| `per_agent_timeout` | `600` | Per-agent timeout in seconds |
| `per_agent_budget` | none | Optional per-agent cost limit (USD) |

## Development

### Setup

```bash
git clone https://github.com/anthropics/founderflow.git
cd founderflow
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest
```

Tests use the `MockRunner` pattern — a fake `Runner` implementation that returns predefined JSON responses per agent role without calling any LLM. This makes the test suite fast, deterministic, and free.

```python
# Example: the MockRunner auto-detects agent role from prompts
runner = MockRunner()
result = await runner.headless(prompt="...", task="...", cwd=".")
# Returns sample IdeaValidation/CompetitorAnalysis/etc. based on role
```

### Lint

```bash
ruff check .
ruff format .
```

### Project Structure Conventions

- **CLI is thin.** `cli.py` only parses arguments and formats output — all logic lives in library modules.
- **Models are strict.** Every Pydantic model uses `strict=True, extra="forbid"`. If you add a field, update the model.
- **Events are append-only.** Never modify `events.jsonl` — only append.
- **State is detected, not asserted.** `detect_state()` reads filesystem markers to determine run state. If `state.json` is corrupted, the system self-heals.
