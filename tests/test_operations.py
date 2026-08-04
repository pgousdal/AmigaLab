from pathlib import Path
import pytest

from scripts.preservation.operations import OperationsLock, OperationsStore, operations_preview, retention_plan, validate_operations_config


def test_operations_disabled_preview_is_safe(tmp_path):
    preview = operations_preview({"enabled": False, "operations": {}}, tmp_path / "metadata")
    assert preview["enabled"] is False
    assert preview["approves_or_executes_plans"] is False


def test_operations_config_rejects_enabled_verification_without_collection():
    errors = validate_operations_config({"enabled": True, "operations": {"verification": {"enabled": True}}})
    assert errors


def test_lock_is_atomic_and_second_owner_is_rejected(tmp_path):
    first = OperationsLock(tmp_path, "verify-aminet")
    with first:
        with pytest.raises(RuntimeError):
            with OperationsLock(tmp_path, "verify-aminet"):
                pass
    assert not first.path.exists()


def test_retention_plan_has_no_content_candidates_by_default(tmp_path):
    plan = retention_plan(tmp_path / "metadata")
    assert plan["candidates"] == []
    assert plan["content_modification"] is False


def test_operations_run_round_trip(tmp_path):
    from scripts.preservation.operations import OperationsRun
    run = OperationsRun("run-1", "verification", "manual", "aminet", "t", "t")
    store = OperationsStore(tmp_path / "metadata")
    store.save_run(run)
    assert store.get_run("run-1")["operation"] == "verification"
