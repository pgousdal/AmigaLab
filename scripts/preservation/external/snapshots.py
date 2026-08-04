from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from .models import ExternalItem, ExternalSnapshot
from .storage import ExternalStorage, stable_id, canonical


def snapshot_fingerprint(metadata: dict[str, object], items: tuple[ExternalItem, ...]) -> str:
    return stable_id({"metadata": metadata, "items": [asdict(item) for item in items]})


def create_snapshot(source_id: str, provider_type: str, check_id: str, metadata: dict[str, object], items: tuple[ExternalItem, ...], warnings: tuple[str, ...] = ()) -> ExternalSnapshot:
    fingerprint = snapshot_fingerprint(metadata, items)
    return ExternalSnapshot(stable_id({"source": source_id, "fingerprint": fingerprint}), source_id, provider_type, check_id, datetime.now(timezone.utc).isoformat(), metadata, tuple(sorted(items, key=lambda item: item.identifier)), warnings, True, fingerprint)


class SnapshotStore:
    def __init__(self, root): self.storage = ExternalStorage(root)
    def save(self, snapshot): return self.storage.put(f"external-snapshots/{snapshot.source_id}", snapshot.id, snapshot)
    def get(self, snapshot_id, source_id): return self.storage.get(f"external-snapshots/{source_id}", snapshot_id)
    def list(self, source_id): return self.storage.list(f"external-snapshots/{source_id}")
