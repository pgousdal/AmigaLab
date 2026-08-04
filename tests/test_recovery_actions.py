from pathlib import Path

import pytest

from scripts.preservation.models import TransactionEntry
from scripts.preservation.recovery import RecoveryContext, RecoveryExecutor
from scripts.preservation.services import hash_file, validate_staging, verify_destination
from scripts.preservation.transactions import TransactionStore


def _entry(tmp_path: Path, state: str = "staged") -> TransactionEntry:
    staged = tmp_path / "staging" / "item.bin"
    target = tmp_path / "collection" / "item.bin"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"hello")
    return TransactionEntry("e", "t", "item.bin", str(target), str(staged), state=state)


def test_hash_file_calculates_all_preservation_hashes(tmp_path: Path) -> None:
    path = tmp_path / "x"
    path.write_bytes(b"hello")
    hashes, size = hash_file(path)
    assert size == 5
    assert len(hashes.md5) == 32 and len(hashes.sha1) == 40
    assert len(hashes.sha256) == 64 and len(hashes.sha512) == 128


def test_staging_validation_and_destination_verification(tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    staging = validate_staging(entry, tmp_path / "staging")
    assert staging.status == "valid"
    assert verify_destination(tmp_path / "collection" / "missing", tmp_path / "collection").status == "missing"


def test_copy_from_staging_is_atomic_and_state_driven(tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    store = TransactionStore(tmp_path / "metadata")
    store.save_entry(entry)
    executor = RecoveryExecutor(store, context=RecoveryContext(tmp_path / "staging", tmp_path / "collection"))
    result = executor.execute(entry, "copy-from-staging")
    assert result.changed
    assert (tmp_path / "collection" / "item.bin").read_bytes() == b"hello"
    assert store.list_entries("t")[0].state == "verifying"


def test_invalid_transition_is_rejected(tmp_path: Path) -> None:
    store = TransactionStore(tmp_path / "metadata")
    entry = _entry(tmp_path, "completed")
    store.save_entry(entry)
    with pytest.raises(ValueError):
        store.transition(entry, "pending", "planned", "invalid")


def test_recovery_plan_is_read_only(tmp_path: Path) -> None:
    store = TransactionStore(tmp_path / "metadata")
    entry = _entry(tmp_path, "staged")
    store.save_entry(entry)
    before = store.list_entries("t")[0]
    assert store.recovery_plan("t")[0]["action"] == "copy-from-staging"
    assert store.list_entries("t")[0] == before
