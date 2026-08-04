"""Canonical, resumable metadata-inspection checkpoints."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from .storage import ExternalStorage
from .storage import stable_id


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
    provider_query_identity: str = ""
    source_fingerprint: str = ""
    current_cursor: str = ""
    next_cursor: str = ""
    page_size: int = 50
    retry_count: int = 0
    file_count_normalized: int = 0
    reported_byte_total: int = 0
    last_successful_checkpoint: str = ""
    partial_snapshot_id: str = ""
    final_snapshot_id: str = ""
    resumable: bool = True
    final_result: str = ""
    tool_version: str = "amigalab"
    completed_at: str = ""


def new_check(source_id: str, provider: str, check_id: str) -> InspectionCheck:
    now = datetime.now(timezone.utc).isoformat()
    return InspectionCheck(check_id, source_id, provider, now, now, "planned")


class InspectionStore:
    def __init__(self, root): self.storage = ExternalStorage(root)
    def save(self, check): return self.storage.put("external-checks", check.id, check)
    def load(self, check_id): return InspectionCheck(**self.storage.get("external-checks", check_id))
    def list(self, source_id): return tuple(InspectionCheck(**item) for item in self.storage.list("external-checks") if item.get("source_id") == source_id)

    def update(self, check: InspectionCheck, **changes) -> InspectionCheck:
        updated = replace(check, **changes, updated_at=datetime.now(timezone.utc).isoformat())
        self.save(updated)
        return updated


@dataclass(frozen=True)
class InspectionEvent:
    id: str
    check_id: str
    source_id: str
    timestamp: str
    previous_state: str
    new_state: str
    operation: str
    page: int = 0
    request_result: str = ""
    retry_count: int = 0
    item_count_delta: int = 0
    file_count_delta: int = 0
    detail: str = ""


class InspectionEventStore:
    def __init__(self, root): self.storage = ExternalStorage(root)
    def append(self, event: InspectionEvent): return self.storage.put("external-check-events", event.id, event)
    def list(self, check_id): return tuple(InspectionEvent(**item) for item in self.storage.list("external-check-events") if item.get("check_id") == check_id)


@dataclass(frozen=True)
class PageCheckpoint:
    id: str
    check_id: str
    source_id: str
    provider: str
    page: int
    items: tuple[dict[str, object], ...]
    item_count: int
    file_count: int
    reported_bytes: int
    fingerprint: str
    completed: bool = True


class CheckpointStore:
    def __init__(self, root): self.storage = ExternalStorage(root)
    def save(self, checkpoint: PageCheckpoint): return self.storage.put(f"external-checkpoints/{checkpoint.check_id}", f"page-{checkpoint.page:06d}", checkpoint)
    def list(self, check_id): return self.storage.list(f"external-checkpoints/{check_id}")


def checkpoint_from_items(check_id: str, source_id: str, provider: str, page: int, items: tuple[object, ...]) -> PageCheckpoint:
    payload = tuple(asdict(item) for item in items)
    files = sum(len(item.files) for item in items)
    total = sum(file.size or 0 for item in items for file in item.files)
    fingerprint = stable_id({"page": page, "items": payload})
    return PageCheckpoint(stable_id({"check": check_id, "page": page, "fingerprint": fingerprint}), check_id, source_id, provider, page, payload, len(items), files, total, fingerprint)


def inspect_resumable(source, provider, store: InspectionStore, check_id: str, *, page_size: int = 50, max_pages: int = 10000) -> InspectionCheck:
    """Inspect pages while checkpointing each normalized page atomically."""
    check = store.load(check_id)
    events = InspectionEventStore(store.storage.root)
    checkpoints = CheckpointStore(store.storage.root)
    if check.status in {"completed", "completed-with-warnings", "cancelled"}:
        raise ValueError(f"inspection is not resumable: {check.status}")
    check = store.update(check, status="requesting", page_size=page_size)
    page = max((int(item.get("page", 0)) for item in checkpoints.list(check_id)), default=0) + 1
    seen_pages = {int(item.get("page", 0)) for item in checkpoints.list(check_id)}
    while page <= max_pages:
        if page in seen_pages:
            raise ValueError("repeated pagination page detected")
        try:
            metadata, items, complete = provider.inspect(source, page_size=page_size, page=page)
            check = store.update(check, status="normalizing", current_cursor=str(page), request_count=check.request_count + 1)
            checkpoint = checkpoint_from_items(check_id, source.id, source.provider_type, page, items)
            checkpoints.save(checkpoint)
            events.append(InspectionEvent(stable_id({"check": check_id, "page": page, "fingerprint": checkpoint.fingerprint}), check_id, source.id, datetime.now(timezone.utc).isoformat(), "normalizing", "checkpointing", "page-checkpoint", page, "success", check.retry_count, len(items), checkpoint.file_count))
            check = store.update(check, status="checkpointing", current_cursor=str(page), last_successful_checkpoint=checkpoint.id, item_count_seen=check.item_count_seen + len(items), item_count_stored=check.item_count_stored + len(items), file_count_normalized=check.file_count_normalized + checkpoint.file_count, reported_byte_total=check.reported_byte_total + checkpoint.reported_bytes)
            if complete:
                check = store.update(check, status="finalizing", final_result="complete")
                check = store.update(check, status="completed", completed_at=datetime.now(timezone.utc).isoformat(), resumable=False)
                return check
            page += 1
            seen_pages.add(page - 1)
        except (TimeoutError, OSError) as error:
            check = store.update(check, status="interrupted", retry_count=check.retry_count + 1, errors=tuple((*check.errors, str(error))))
            return check
    return store.update(check, status="failed", resumable=False, errors=tuple((*check.errors, "maximum page safety limit reached")))
