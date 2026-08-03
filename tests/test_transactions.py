from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.preservation.transactions import TransactionStore, new_transaction, source_fingerprint


def test_transaction_survives_interruption_and_resume_state(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "item.lha").write_bytes(b"item")
    store = TransactionStore(tmp_path / "metadata")
    transaction = new_transaction("source", source_fingerprint(source), "aminet", "import", ("item.lha",))
    store.save(transaction)
    updated = store.update(transaction, phase="staging", completed_entries=("item.lha",), pending_entries=())

    assert store.load(transaction.id).phase == "staging"
    (source / "item.lha").write_bytes(b"changed")
    assert source_fingerprint(source) != updated.source_fingerprint
