"""Canonical JSON-backed resumable import transactions."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4
from hashlib import sha256

from .models import ImportTransaction, TransactionEntry, TransactionEvent

VALID_TRANSITIONS = {
    "pending": {"opening-source", "reused", "provenance-only", "skipped", "blocked", "failed"},
    "opening-source": {"streaming", "failed"},
    "streaming": {"staging", "failed"},
    "staging": {"staged", "failed"},
    "staged": {"hashing", "copying", "failed"},
    "hashing": {"ready-to-copy", "failed"},
    "ready-to-copy": {"copying", "failed"},
    "copying": {"verifying", "failed"},
    "verifying": {"metadata-writing", "completed", "reused", "failed"},
    "metadata-writing": {"completed", "failed"},
    "blocked": {"pending", "failed"},
    "failed": {"pending", "opening-source"},
}

PHASES = ("planned", "scanning", "staging", "hashing", "metadata-writing", "copying", "verifying", "completed", "failed", "cancelled")


def source_fingerprint(location: Path) -> str:
    digest = sha256()
    for path in sorted(location.rglob("*")):
        if path.is_file():
            stat = path.stat()
            digest.update(path.relative_to(location).as_posix().encode())
            digest.update(f":{stat.st_size}:{stat.st_mtime_ns}".encode())
    return digest.hexdigest()


def new_transaction(source_id: str, fingerprint: str, collection: str, operation: str, pending: tuple[str, ...]) -> ImportTransaction:
    now = datetime.now(timezone.utc).isoformat()
    return ImportTransaction(str(uuid4()), source_id, fingerprint, collection, operation, now, now, "planned", pending_entries=pending)


class TransactionStore:
    def __init__(self, metadata_root: Path):
        self.root = metadata_root / "imports"

    def save(self, transaction: ImportTransaction) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"transaction-{transaction.id}.json"
        path.write_text(json.dumps(asdict(transaction), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def load(self, transaction_id: str) -> ImportTransaction:
        path = self.root / f"transaction-{transaction_id}.json"
        return ImportTransaction(**json.loads(path.read_text(encoding="utf-8")))

    def update(self, transaction: ImportTransaction, **changes: object) -> ImportTransaction:
        updated = replace(transaction, updated_at=datetime.now(timezone.utc).isoformat(), **changes)
        self.save(updated)
        return updated

    def save_entry(self, entry: TransactionEntry) -> Path:
        directory = self.root / "entries"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{entry.id}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(entry), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)
        return path

    def append_event(self, event: TransactionEvent) -> Path:
        directory = self.root / "events"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{event.id}.json"
        path.write_text(json.dumps(asdict(event), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def transition(self, entry: TransactionEntry, new_state: str, phase: str, operation: str, result: str = "") -> TransactionEntry:
        if new_state not in VALID_TRANSITIONS.get(entry.state, set()):
            raise ValueError(f"invalid transaction entry transition: {entry.state} -> {new_state}")
        from dataclasses import replace
        from datetime import datetime, timezone
        updated = replace(entry, state=new_state)
        self.save_entry(updated)
        self.append_event(TransactionEvent(str(uuid4()), entry.transaction_id, entry.id, entry.state, new_state, phase, operation, datetime.now(timezone.utc).isoformat(), result))
        return updated
