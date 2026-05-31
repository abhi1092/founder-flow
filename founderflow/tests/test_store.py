from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from founderflow.models import DirectiveVerdict, ResearchDirective
from founderflow.store import RunStore


@pytest.fixture
def store(tmp_run_dir: Path) -> RunStore:
    return RunStore(tmp_run_dir)


class TestCreateRun:
    def test_creates_directory_structure(self, store: RunStore):
        run_id = store.create_run("Test idea")
        run_path = store.get_run(run_id)
        assert run_path.exists()
        assert (run_path / "input.json").exists()
        assert (run_path / "state.json").exists()
        assert (run_path / "events.jsonl").exists()
        assert (run_path / "rounds").is_dir()

    def test_input_json_contents(self, store: RunStore):
        run_id = store.create_run("My startup idea", {"max_rounds": 3})
        run_path = store.get_run(run_id)
        data = json.loads((run_path / "input.json").read_text())
        assert data["idea"] == "My startup idea"
        assert data["config"] == {"max_rounds": 3}
        assert "created_at" in data

    def test_initial_state_is_submitted(self, store: RunStore):
        run_id = store.create_run("Idea")
        run_path = store.get_run(run_id)
        state_data = json.loads((run_path / "state.json").read_text())
        assert state_data["state"] == "SUBMITTED"


class TestGetRun:
    def test_existing_run(self, store: RunStore):
        run_id = store.create_run("Idea")
        path = store.get_run(run_id)
        assert path.name == run_id

    def test_missing_run_raises(self, store: RunStore):
        with pytest.raises(FileNotFoundError):
            store.get_run("nonexistent-run-id")


class TestSaveRoundOutput:
    def test_writes_to_correct_round(self, store: RunStore):
        run_id = store.create_run("Idea")
        data = {"summary": "test output", "confidence_score": 50}
        path = store.save_round_output(run_id, 1, "idea_validator", data)
        assert path.exists()
        assert path.parent.name == "1"
        loaded = json.loads(path.read_text())
        assert loaded["summary"] == "test output"

    def test_multiple_rounds(self, store: RunStore):
        run_id = store.create_run("Idea")
        store.save_round_output(run_id, 1, "idea_validator", {"round": 1})
        store.save_round_output(run_id, 2, "idea_validator", {"round": 2})
        run_path = store.get_run(run_id)
        assert (run_path / "rounds" / "1" / "idea_validator.json").exists()
        assert (run_path / "rounds" / "2" / "idea_validator.json").exists()


class TestSaveDirective:
    def test_writes_directive_json(self, store: RunStore):
        run_id = store.create_run("Idea")
        directive = ResearchDirective(
            verdict=DirectiveVerdict.evidence_sufficient,
            directives=[], resolved_contradictions=[], remaining_gaps=[],
            round_confidence=80,
        )
        path = store.save_directive(run_id, 1, directive)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["verdict"] == "evidence_sufficient"


class TestListRuns:
    def test_returns_runs_sorted(self, store: RunStore):
        store.create_run("First idea")
        store.create_run("Second idea")
        runs = store.list_runs()
        assert len(runs) >= 2
        assert runs[0].idea in ("First idea", "Second idea")

    def test_empty_store(self, tmp_path: Path):
        empty_store = RunStore(tmp_path / ".founderflow")
        runs = empty_store.list_runs()
        assert runs == []


class TestAppendTsv:
    def test_creates_header_on_first_write(self, store: RunStore):
        run_id = store.create_run("Idea")
        store.append_tsv(run_id, {"run_id": run_id, "verdict": "go", "cost": "0.01"})
        tsv = store.base_path / "runs.tsv"
        assert tsv.exists()
        lines = tsv.read_text().splitlines()
        assert lines[0] == "run_id\tverdict\tcost"
        assert run_id in lines[1]

    def test_appends_without_duplicate_header(self, store: RunStore):
        r1 = store.create_run("First")
        store.append_tsv(r1, {"id": r1, "v": "go"})
        r2 = store.create_run("Second")
        store.append_tsv(r2, {"id": r2, "v": "kill"})
        tsv = store.base_path / "runs.tsv"
        lines = tsv.read_text().splitlines()
        assert len(lines) == 3


class TestFileLock:
    def test_concurrent_creates(self, tmp_run_dir: Path):
        store = RunStore(tmp_run_dir)
        results: list[str] = []

        def _create(idx: int):
            rid = store.create_run(f"Idea {idx}")
            results.append(rid)

        threads = [threading.Thread(target=_create, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 5
        assert len(set(results)) == 5
