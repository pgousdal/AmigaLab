from pathlib import Path
import json

import pytest

from scripts.preservation.models import TransactionEntry
from scripts.preservation.recovery_workflow import (
    ExecutionState, ExecutionStateStore, PlanLock, RecoveryPlanStore,
    dry_run, generate_plan,
)


def make_entry(tmp_path: Path, state: str = "staged") -> TransactionEntry:
    staging = tmp_path / "staging" / "a.bin"
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_bytes(b"data")
    return TransactionEntry("entry-a", "tx", "a.bin", str(tmp_path / "collection" / "a.bin"), str(staging), state=state)


def test_recovery_plan_id_ignores_creation_time(tmp_path: Path) -> None:
    entry = make_entry(tmp_path)
    first = generate_plan((entry,), "fingerprint", "tx", tmp_path, tmp_path / "staging", tmp_path / "collection", created_at="2020")
    second = generate_plan((entry,), "fingerprint", "tx", tmp_path, tmp_path / "staging", tmp_path / "collection", created_at="2030")
    assert first.id == second.id
    assert first.canonical_content() == second.canonical_content()


def test_plan_order_is_canonical_and_round_trips(tmp_path: Path) -> None:
    one = make_entry(tmp_path)
    two = TransactionEntry("entry-b", "tx", "b.bin", str(tmp_path / "collection" / "b.bin"), str(tmp_path / "staging" / "b.bin"))
    plan = generate_plan((two, one), "fp", "tx", tmp_path, tmp_path / "staging", tmp_path / "collection")
    assert [action.entry_id for action in plan.actions] == ["entry-a", "entry-b"]
    store = RecoveryPlanStore(tmp_path / "metadata")
    store.save(plan)
    assert store.load(plan.id).id == plan.id


def test_dry_run_does_not_copy_or_write_metadata(tmp_path: Path) -> None:
    entry = make_entry(tmp_path)
    plan = generate_plan((entry,), "fp", "tx", tmp_path, tmp_path / "staging", tmp_path / "staging", created_at="now")
    report = dry_run(plan, (entry,), tmp_path / "staging", tmp_path / "collection")
    assert report.result == "ready"
    assert report.action_counts["would_copy"] == 1
    assert not (tmp_path / "collection" / "a.bin").exists()


def test_dry_run_reuses_matching_destination(tmp_path: Path) -> None:
    entry = make_entry(tmp_path)
    destination = tmp_path / "collection" / "a.bin"
    destination.parent.mkdir()
    destination.write_bytes(b"data")
    plan = generate_plan((entry,), "fp", "tx", tmp_path, tmp_path / "staging", tmp_path / "collection")
    report = dry_run(plan, (entry,), tmp_path / "staging", tmp_path / "collection")
    assert report.action_counts["already_satisfied"] == 1
    assert report.files_reused == (str(destination),)


def test_dry_run_detects_conflict_without_mutation(tmp_path: Path) -> None:
    entry = make_entry(tmp_path)
    destination = tmp_path / "collection" / "a.bin"
    destination.parent.mkdir()
    destination.write_bytes(b"different")
    plan = generate_plan((entry,), "fp", "tx", tmp_path, tmp_path / "staging", tmp_path / "collection")
    report = dry_run(plan, (entry,), tmp_path / "staging", tmp_path / "collection")
    assert report.result == "blocked"
    assert report.action_counts["conflict"] == 1
    assert destination.read_bytes() == b"different"


def test_execution_state_is_atomic_and_round_trips(tmp_path: Path) -> None:
    state = ExecutionState("plan", "exec", "start", "update", "running", {"a": "completed"}, ("a",))
    store = ExecutionStateStore(tmp_path / "metadata")
    path = store.save(state)
    assert json.loads(path.read_text())["status"] == "running"
    assert store.load("exec").completed_actions == ("a",)


def test_lock_rejects_concurrent_and_releases(tmp_path: Path) -> None:
    first = PlanLock(tmp_path, "plan")
    with first:
        with pytest.raises(RuntimeError):
            with PlanLock(tmp_path, "plan"):
                pass
    with PlanLock(tmp_path, "plan"):
        pass


def test_lock_file_is_namespaced(tmp_path: Path) -> None:
    lock = PlanLock(tmp_path, "p")
    with lock:
        assert lock.path == tmp_path / "recovery-locks" / "p.lock"
