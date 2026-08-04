"""Opt-in scheduled operations, locks, run history, and safe retention plans."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import os
import socket

from .external.storage import ExternalStorage, stable_id


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class OperationsRun:
    id: str
    operation: str
    trigger: str
    target: str
    started_at: str
    updated_at: str
    completed_at: str = ""
    state: str = "planned"
    result: str = ""
    configuration_fingerprint: str = ""
    created_record_ids: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    notification_results: tuple[str, ...] = field(default_factory=tuple)
    tool_version: str = "amigalab"


class OperationsStore:
    def __init__(self, root: Path):
        self.storage = ExternalStorage(root)

    def save_run(self, run: OperationsRun):
        return self.storage.put("operations-runs", run.id, run)

    def get_run(self, run_id: str):
        try:
            return self.storage.get("operations-runs", run_id)
        except FileNotFoundError:
            return None

    def list_runs(self):
        return self.storage.list("operations-runs")

    def event(self, run_id: str, operation: str, **details):
        value = {"id": stable_id({"run": run_id, "operation": operation, "details": details}),
                 "run_id": run_id, "operation": operation, "timestamp": now(), **details}
        return self.storage.put("operations-events", value["id"], value)


class OperationsLock:
    """Atomic, conservative lock; stale locks are reported, never stolen."""
    def __init__(self, root: Path, name: str):
        self.path = root / "run" / "locks" / f"amigalab-{name}.lock"
        self.acquired = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"pid={os.getpid()} host={socket.gethostname()} started={now()}\n"
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
        except FileExistsError as error:
            raise RuntimeError(f"AmigaLab operation lock is held: {self.path}") from error
        self.acquired = True
        return self

    def __exit__(self, *_):
        if self.acquired:
            self.path.unlink(missing_ok=True)


def validate_operations_config(config: dict) -> tuple[str, ...]:
    errors = []
    if config.get("enabled") and not isinstance(config.get("operations", {}), dict):
        errors.append("operations must be a mapping")
    operations = config.get("operations", {})
    if operations.get("source_checks", {}).get("enabled") and not operations.get("source_checks", {}).get("schedule"):
        errors.append("source-check schedule is required when enabled")
    if operations.get("verification", {}).get("enabled") and not operations.get("verification", {}).get("collection"):
        errors.append("verification collection is required when enabled")
    return tuple(errors)


def operations_preview(config: dict, metadata_root: Path) -> dict:
    operations = config.get("operations", {})
    return {"enabled": bool(config.get("enabled", False)),
            "source_checks": operations.get("source_checks", {}),
            "verification": operations.get("verification", {}),
            "reconciliation": operations.get("reconciliation", {}),
            "retention": operations.get("retention", config.get("retention", {})),
            "notifications": operations.get("notifications", {}),
            "locks_root": str(metadata_root.parent / "run" / "locks"),
            "mutates_preserved_content": False,
            "approves_or_executes_plans": False}


def retention_plan(metadata_root: Path, policy: dict | None = None) -> dict:
    policy = policy or {}
    candidates = []
    # Only disposable operational material is ever proposed by default.
    cache_days = int(policy.get("provider_cache_days", 0) or 0)
    if cache_days > 0:
        candidates.extend({"path": str(path), "category": "provider-cache", "reason": "age-policy"}
                          for path in (metadata_root.parent / "cache" / "external-providers").rglob("*")
                          if path.is_file() and not path.is_symlink())
    payload = {"type": "retention-plan", "policy": policy, "candidates": sorted(candidates, key=lambda x: x["path"]),
               "blocking_findings": [], "content_modification": False, "status": "draft"}
    payload["id"] = stable_id(payload)
    return payload

