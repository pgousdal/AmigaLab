"""Canonical, resumable metadata-inspection checkpoints."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from .storage import ExternalStorage


@dataclass(frozen=True)
class InspectionCheck:
    id: str
    source_id: str
    provider: str
    started_at: str
    updated_at: str
    status: str = "planned"
    page: int = 1
    request_count: int = 0
    item_count_seen: int = 0
    item_count_stored: int = 0
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    snapshot_id: str = ""
    schema_version: int = 1


def new_check(source_id: str, provider: str, check_id: str) -> InspectionCheck:
    now = datetime.now(timezone.utc).isoformat()
    return InspectionCheck(check_id, source_id, provider, now, now, "planned")


class InspectionStore:
    def __init__(self, root): self.storage = ExternalStorage(root)
    def save(self, check): return self.storage.put("external-checks", check.id, check)
    def load(self, check_id): return InspectionCheck(**self.storage.get("external-checks", check_id))
    def list(self, source_id): return tuple(InspectionCheck(**item) for item in self.storage.list("external-checks") if item.get("source_id") == source_id)
