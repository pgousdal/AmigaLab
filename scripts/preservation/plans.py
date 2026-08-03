"""Canonical selective import plans and append-only conflict decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4


STATUSES = ("draft", "ready", "blocked", "approved", "executing", "completed", "superseded", "cancelled")
MODES = ("media-only", "members-only", "media-and-members")


@dataclass(frozen=True)
class ConflictDecision:
    id: str
    conflict_id: str
    timestamp: str
    action: str
    reason: str
    tool_version: str = "amigalab-m2.4"


@dataclass(frozen=True)
class PlanEvent:
    id: str
    plan_id: str
    kind: str
    timestamp: str
    plan_fingerprint: str
    note: str = ""
    tool_version: str = "amigalab-m2.5"


@dataclass(frozen=True)
class ImportPlan:
    id: str
    source_id: str
    source_fingerprint: str
    adapter_type: str
    destination_collection: str
    created_at: str
    selected_entries: tuple[str, ...]
    excluded_entries: tuple[str, ...] = field(default_factory=tuple)
    status: str = "draft"
    import_mode: str = "media-only"
    conflicts: tuple[dict[str, str], ...] = field(default_factory=tuple)
    rules: tuple[str, ...] = field(default_factory=tuple)
    estimated_files: int = 0
    estimated_bytes: int = 0

    @property
    def fingerprint(self) -> str:
        return sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


def create_plan(source_id: str, source_fingerprint: str, adapter_type: str, collection: str, selected: tuple[str, ...], mode: str = "media-only", rules: tuple[str, ...] = ()) -> ImportPlan:
    if mode not in MODES:
        raise ValueError(f"invalid import mode: {mode}")
    if any(Path(path).is_absolute() or ".." in Path(path).parts for path in selected):
        raise ValueError("plan entries must be safe relative paths")
    return ImportPlan(str(uuid4()), source_id, source_fingerprint, adapter_type, collection, datetime.now(timezone.utc).isoformat(), tuple(sorted(selected)), import_mode=mode, rules=rules, estimated_files=len(selected))


class PlanStore:
    def __init__(self, metadata_root: Path):
        self.root = metadata_root / "import-plans"
        self.events = self.root / "events"

    def save(self, plan: ImportPlan) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{plan.id}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(plan), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)
        return path

    def load(self, plan_id: str) -> ImportPlan:
        return ImportPlan(**json.loads((self.root / f"{plan_id}.json").read_text(encoding="utf-8")))

    def update(self, plan: ImportPlan, **changes: object) -> ImportPlan:
        updated = replace(plan, **changes)
        self.save(updated)
        return updated

    def event(self, plan: ImportPlan, kind: str, note: str = "") -> PlanEvent:
        self.events.mkdir(parents=True, exist_ok=True)
        event = PlanEvent(str(uuid4()), plan.id, kind, datetime.now(timezone.utc).isoformat(), plan.fingerprint, note)
        path = self.events / f"{event.id}.json"
        path.write_text(json.dumps(asdict(event), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return event
