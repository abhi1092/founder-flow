from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from filelock import FileLock

from founderflow.models import ResearchDirective, StartupBrief, ValidationThesis
from founderflow.state import RunState, save_state


@dataclass
class RunSummary:
    run_id: str
    idea: str
    state: str
    created_at: str
    verdict: str | None = None
    rounds: int = 0
    cost_usd: float = 0.0


class RunStore:
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        self.runs_dir = base_path / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = base_path / ".lock"

    def _lock(self) -> FileLock:
        return FileLock(self._lock_path)

    def create_run(self, idea: str, config: dict | None = None) -> str:
        run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
        run_path = self.runs_dir / run_id
        with self._lock():
            run_path.mkdir(parents=True, exist_ok=True)
            (run_path / "rounds").mkdir(exist_ok=True)

            input_data = {
                "idea": idea,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "run_id": run_id,
            }
            if config:
                input_data["config"] = config
            (run_path / "input.json").write_text(json.dumps(input_data, indent=2) + "\n")

            save_state(run_path, RunState.SUBMITTED, 0)

            (run_path / "events.jsonl").touch()

        return run_id

    def get_run(self, run_id: str) -> Path:
        run_path = self.runs_dir / run_id
        if not run_path.exists():
            raise FileNotFoundError(f"Run {run_id} not found")
        return run_path

    def list_runs(self) -> list[RunSummary]:
        summaries = []
        if not self.runs_dir.exists():
            return summaries

        for run_dir in sorted(self.runs_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            input_file = run_dir / "input.json"
            if not input_file.exists():
                continue

            data = json.loads(input_file.read_text())
            state_file = run_dir / "state.json"
            state = "SUBMITTED"
            round_num = 0
            if state_file.exists():
                state_data = json.loads(state_file.read_text())
                state = state_data.get("state", "SUBMITTED")
                round_num = state_data.get("round_num", 0)

            verdict = None
            synthesis_file = run_dir / "synthesis.json"
            if synthesis_file.exists():
                synthesis = json.loads(synthesis_file.read_text())
                verdict = synthesis.get("verdict")

            summaries.append(
                RunSummary(
                    run_id=run_dir.name,
                    idea=data.get("idea", ""),
                    state=state,
                    created_at=data.get("created_at", ""),
                    verdict=verdict,
                    rounds=round_num,
                )
            )

        return summaries

    def save_round_output(
        self, run_id: str, round_num: int, role: str, data: dict
    ) -> Path:
        run_path = self.get_run(run_id)
        round_dir = run_path / "rounds" / str(round_num)
        round_dir.mkdir(parents=True, exist_ok=True)

        output_file = round_dir / f"{role}.json"
        with self._lock():
            output_file.write_text(json.dumps(data, indent=2) + "\n")
        return output_file

    def save_directive(
        self, run_id: str, round_num: int, directive: ResearchDirective
    ) -> Path:
        run_path = self.get_run(run_id)
        round_dir = run_path / "rounds" / str(round_num)
        round_dir.mkdir(parents=True, exist_ok=True)

        directive_file = round_dir / "directive.json"
        with self._lock():
            directive_file.write_text(directive.model_dump_json(indent=2) + "\n")
        return directive_file

    def save_synthesis(self, run_id: str, thesis: ValidationThesis) -> Path:
        run_path = self.get_run(run_id)
        synthesis_file = run_path / "synthesis.json"
        with self._lock():
            synthesis_file.write_text(thesis.model_dump_json(indent=2) + "\n")
        return synthesis_file

    def save_brief(self, run_id: str, brief: StartupBrief) -> Path:
        run_path = self.get_run(run_id)
        brief_file = run_path / "brief.json"
        with self._lock():
            brief_file.write_text(brief.model_dump_json(indent=2) + "\n")
        return brief_file

    def append_tsv(self, run_id: str, record: dict) -> None:
        tsv_file = self.base_path / "runs.tsv"
        with self._lock():
            write_header = not tsv_file.exists()
            with tsv_file.open("a") as f:
                if write_header:
                    f.write("\t".join(record.keys()) + "\n")
                f.write("\t".join(str(v) for v in record.values()) + "\n")
