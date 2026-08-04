from pathlib import Path

import pytest

from scripts.preservation.models import TransactionEntry
from scripts.preservation.recovery_workflow import RecoveryOrchestrator, RecoveryPlanStore, generate_plan
from scripts.preservation.transactions import TransactionStore


def setup_case(tmp_path: Path):
    staging = tmp_path / "staging"
    destination = tmp_path / "collection"
    staged = staging / "file.bin"
    staged.parent.mkdir()
    staged.write_bytes(b"payload")
    entry = TransactionEntry("entry", "tx", "file.bin", str(destination / "file.bin"), str(staged), state="staged")
    plan = generate_plan((entry,), "fp", "tx", tmp_path, staging, destination, created_at="fixed")
    return plan, entry


def test_orchestrator_executes_and_checkpoints(tmp_path: Path) -> None:
    plan, entry = setup_case(tmp_path)
    result = RecoveryOrchestrator(tmp_path / "metadata").execute(plan, (entry,))
    assert result.status == "completed"
    assert (tmp_path / "collection" / "file.bin").read_bytes() == b"payload"
    state = RecoveryOrchestrator(tmp_path / "metadata").states.load(result.execution_id)
    assert state.status == "completed" and state.revision >= 3
    assert state.actions


def test_orchestrator_resume_completed_is_idempotent(tmp_path: Path) -> None:
    plan, entry = setup_case(tmp_path)
    orchestrator = RecoveryOrchestrator(tmp_path / "metadata")
    first = orchestrator.execute(plan, (entry,))
    second = orchestrator.resume(plan, first.execution_id, (entry,))
    assert second.status == "completed"
    assert (tmp_path / "collection" / "file.bin").read_bytes() == b"payload"


def test_dependency_blocks_action(tmp_path: Path) -> None:
    plan, entry = setup_case(tmp_path)
    action = plan.actions[0]
    modified = type(plan)(plan.id, plan.schema_version, plan.created_at, plan.identity, plan.source_path,
                          plan.staging_path, plan.destination_path, plan.source_fingerprint,
                          (type(action)(action.id, action.entry_id, action.operation, action.status,
                                        action.source_path, action.staging_path, action.destination_path,
                                        action.preconditions, ("missing",), action.obligations, action.expected_hashes),),
                          plan.preconditions)
    result = RecoveryOrchestrator(tmp_path / "metadata").execute(modified, (entry,))
    assert result.status == "blocked"


def test_state_plan_mismatch_rejected(tmp_path: Path) -> None:
    plan, entry = setup_case(tmp_path)
    orchestrator = RecoveryOrchestrator(tmp_path / "metadata")
    state = orchestrator.states
    from scripts.preservation.recovery_workflow import ExecutionState
    state.save(ExecutionState("other", "exec", "a", "b", "running"))
    with pytest.raises(ValueError):
        orchestrator.execute(plan, (entry,), execution_id="exec", resume=True)
