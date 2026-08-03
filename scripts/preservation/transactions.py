"""Canonical JSON-backed resumable import transactions."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4
from hashlib import sha256

from .models import ImportTransaction

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
