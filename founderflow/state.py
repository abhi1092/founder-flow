from __future__ import annotations

import json
from enum import Enum
from pathlib import Path


class RunState(str, Enum):
    SUBMITTED = "SUBMITTED"
    VALIDATING = "VALIDATING"
    DEEPENING = "DEEPENING"
    SYNTHESIZING = "SYNTHESIZING"
    RENDERING = "RENDERING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    ERRORED = "ERRORED"


def save_state(run_path: Path, state: RunState, round_num: int = 0) -> None:
    state_file = run_path / "state.json"
    state_file.write_text(
        json.dumps({"state": state.value, "round_num": round_num}, indent=2) + "\n"
    )


def load_state(run_path: Path) -> tuple[RunState, int]:
    state_file = run_path / "state.json"
    if not state_file.exists():
        return RunState.SUBMITTED, 0
    data = json.loads(state_file.read_text())
    return RunState(data["state"]), data.get("round_num", 0)


def detect_state(run_path: Path) -> tuple[RunState, int]:
    state_file = run_path / "state.json"
    if state_file.exists():
        return load_state(run_path)

    if (run_path / "brief.json").exists():
        return RunState.COMPLETE, _count_rounds(run_path)

    if (run_path / "synthesis.json").exists():
        return RunState.RENDERING, _count_rounds(run_path)

    rounds_dir = run_path / "rounds"
    if not rounds_dir.exists():
        if (run_path / "input.json").exists():
            return RunState.SUBMITTED, 0
        return RunState.SUBMITTED, 0

    round_num = _count_rounds(run_path)
    if round_num == 0:
        return RunState.SUBMITTED, 0

    latest_round = rounds_dir / str(round_num)
    if (latest_round / "directive.json").exists():
        if round_num > 1:
            return RunState.DEEPENING, round_num
        return RunState.VALIDATING, round_num

    return RunState.VALIDATING, round_num


def _count_rounds(run_path: Path) -> int:
    rounds_dir = run_path / "rounds"
    if not rounds_dir.exists():
        return 0
    round_dirs = [d for d in rounds_dir.iterdir() if d.is_dir() and d.name.isdigit()]
    return max((int(d.name) for d in round_dirs), default=0)
