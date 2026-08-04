"""Idempotent canonical verification, provenance, and relationship records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path


@dataclass(frozen=True)
class VerificationRecord:
    id: str
    operation_key: str
    transaction_id: str
    entry_id: str
    destination_path: str
    context: str
    expected_hashes: dict[str, str]
    observed_hashes: dict[str, str]
    success: bool
    failure_reason: str = ""
    attempt: int = 0
    tool_version: str = "amigalab"


@dataclass(frozen=True)
class RelationshipRecord:
    id: str
    operation_key: str
    relationship_type: str
    media_id: str
    object_id: str
    source_id: str
    transaction_id: str
    original_member_path: str
    imported_target_path: str
    original_member_identifier: str = ""
    tool_version: str = "amigalab"


class EventStore:
    def __init__(self, metadata_root: Path):
        self.root = metadata_root

    def _put_once(self, category: str, operation_key: str, value: object) -> Path:
        directory = self.root / category
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{sha256(operation_key.encode()).hexdigest()}.json"
        if not path.exists():
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(asdict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temporary.replace(path)
        return path

    def verification(self, record: VerificationRecord) -> Path:
        return self._put_once("verification-events", record.operation_key, record)

    def relationship(self, record: RelationshipRecord) -> Path:
        return self._put_once("media-relationships", record.operation_key, record)

    def exists(self, category: str, operation_key: str) -> bool:
        return (self.root / category / f"{sha256(operation_key.encode()).hexdigest()}.json").exists()
